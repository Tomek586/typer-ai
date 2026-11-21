"""Silnik decyzyjny (docs/06, sekcje 6.3 i 6.6): typowane pytania → odpowiedzi z prawdopodobieństwami.

`LLMEngine` to plan B bez dostępu do Jev: te same pytania (Noul, Choice, Score) w jednym zapytaniu do
Gemini z wymuszonym JSON-em. Każde wywołanie trafia do DECISION_LOG. Gdy będzie klucz Jev, `JevEngine`
dostanie ten sam interfejs `ask()`, a reszta kodu się nie zmieni.
"""

import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

from typerai.chat import cli


@dataclass
class Question:
    type: Literal["noul", "choice", "score"]
    instructions: str
    criteria: dict[str, str] | list[str] | None = None

    def options(self) -> list[str]:
        if self.type == "noul":
            return ["yes", "no"]
        if self.type == "choice":
            return list(self.criteria)
        return [str(i) for i in range(len(self.criteria))]


@dataclass
class Answer:
    type: str
    value: float | str               # noul: P(tak); choice: opcja; score: średnia ważona poziomów
    probabilities: dict[str, float]
    confidence: float


class DecisionEngine(Protocol):
    name: str

    def ask(self, purpose: str, state: dict, questions: dict[str, Question],
            ref: tuple[str, int] | None = None) -> dict[str, Answer]: ...


def confidence(probs: dict[str, float]) -> float:
    """Wzór z dokumentacji Jev: (p_max − 1/n) / (1 − 1/n)."""
    n = len(probs)
    return (max(probs.values()) - 1 / n) / (1 - 1 / n) if n > 1 else 1.0


def to_answer(question: Question, raw: dict) -> Answer:
    """Rozkład z odpowiedzi LLM → Answer; brakujące opcje = 0, normalizacja do sumy 1."""
    options = question.options()
    probs = {o: max(0.0, float((raw or {}).get(o, 0.0))) for o in options}
    total = sum(probs.values())
    probs = {o: p / total for o, p in probs.items()} if total > 0 else {o: 1 / len(options) for o in options}
    if question.type == "noul":
        value: float | str = probs["yes"]
    elif question.type == "choice":
        value = max(probs, key=probs.get)
    else:
        value = sum(int(o) * p for o, p in probs.items())
    return Answer(question.type, value, probs, confidence(probs))


PROMPT = """You are a careful classifier. Read the STATE and answer every QUESTION independently.
For each question return a probability distribution over its options (numbers 0–1 that sum to 1).
Base the answers only on the STATE; if the information is missing, spread the probability accordingly.

STATE:
{state}

QUESTIONS (key → type, instructions, options):
{questions}

Respond with JSON only: {{"<question key>": {{"<option>": probability, ...}}, ...}} – one entry per question key,
using exactly the option names listed."""


def _describe(questions: dict[str, Question]) -> str:
    lines = []
    for key, q in questions.items():
        if q.type == "noul":
            opts = "yes | no"
        elif q.type == "choice":
            opts = "; ".join(f"{k} = {v}" for k, v in q.criteria.items())
        else:
            opts = "; ".join(f"{i} = {v}" for i, v in enumerate(q.criteria))
        lines.append(f"- {key} ({q.type}): {q.instructions} Options: {opts}")
    return "\n".join(lines)


class LLMEngine:
    """Plan B: pytania Jev obsługiwane przez Gemini (łańcuch modeli jak w czacie)."""

    name = "llm-gemini"

    def __init__(self, client=None, models: list[str] | None = None, log: sqlite3.Connection | None = None):
        if client is None:
            from google import genai
            client = genai.Client(http_options=cli.HTTP_OPTIONS)
        self.client, self.models, self.log = client, models or cli.MODELS, log

    def _generate(self, prompt: str) -> tuple[str, str]:
        from google.genai import errors, types

        last = None
        for model in self.models:
            try:
                r = self.client.models.generate_content(
                    model=model, contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0))
                return r.text or "{}", model
            except Exception as e:   # błąd limitu, przeciążenia lub czasu → kolejny model
                code = e.code if isinstance(e, errors.APIError) else ("timeout" if "timeout" in type(e).__name__.lower() else None)
                if code is None or not (code == "timeout" or code in cli.SWITCH_CODES or (isinstance(code, int) and code >= 500)):
                    raise
                last = e
        raise last

    def ask(self, purpose: str, state: dict, questions: dict[str, Question],
            ref: tuple[str, int] | None = None) -> dict[str, Answer]:
        prompt = PROMPT.format(state=json.dumps(state, ensure_ascii=False, indent=1), questions=_describe(questions))
        start = time.perf_counter()
        text, model = self._generate(prompt)
        latency = int(1000 * (time.perf_counter() - start))
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            raw = {}
        answers = {k: to_answer(q, raw.get(k) if isinstance(raw, dict) else None) for k, q in questions.items()}
        if self.log is not None:
            self.log.execute(
                """INSERT INTO decision_log (purpose, engine, model, ref_type, ref_id, state, questions, answers,
                   latency_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (purpose, self.name, model, ref[0] if ref else None, ref[1] if ref else None,
                 json.dumps(state, ensure_ascii=False), json.dumps({k: asdict(q) for k, q in questions.items()}, ensure_ascii=False),
                 json.dumps({k: asdict(a) for k, a in answers.items()}, ensure_ascii=False), latency,
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
            self.log.commit()
        return answers
