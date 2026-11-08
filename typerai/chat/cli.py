"""Chatbot Typer AI w terminalu – wersja PoC (docs/08).

Gemini z automatycznym wywoływaniem narzędzi (function calling): model sam decyduje, które narzędzie
wywołać, a wszystkie liczby bierze z ich wyników. Każde wywołanie narzędzia jest wypisywane na ekranie.

    .venv/Scripts/python -m typerai.chat.cli
"""

import functools
import json
import os
import re
import sys

from google import genai
from google.genai import errors, types

from typerai import config  # noqa: F401  (ładuje .env)
from typerai.chat.tools import TOOLS

MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

SYSTEM_PROMPT = """Jesteś Typer AI – asystentem do analizy meczów piłkarskiej Ekstraklasy i zakładów sportowych.
Odpowiadasz po polsku, rzeczowo i zwięźle. Gdy porównujesz liczby, używasz krótkiej listy lub tabeli.

ZASADY LICZB
1. Nie licz samodzielnie prawdopodobieństw, EV ani marży – zawsze używaj narzędzi.
2. Każda liczba w odpowiedzi musi pochodzić z wyniku narzędzia w tej rozmowie.

ZASADY TYPÓW
3. Typ podajesz tylko wtedy, gdy narzędzie analiza_meczu zwróci pole "typ". Nie twórz własnych typów.
4. Jeśli typu nie ma, powiedz to wprost i wyjaśnij dlaczego (np. za niskie EV lub prawdopodobieństwo).
5. Nigdy nie obiecuj wygranej. Nie używaj słów „pewniak”, „pewna wygrana”, „gwarancja”.
6. Przy każdej analizie dodaj jedno zdanie o ryzyku.

ZAKRES
7. Tematy: Ekstraklasa, kursy, zakłady, wyniki typera. Inne tematy – uprzejmie odmów.
8. Jeśli nie wiesz – powiedz to. Nie zgaduj."""

FORBIDDEN = re.compile(r"pewniak|pewn[aą] wygran|gwarantuj|gwarancj|na 100\s?%", re.IGNORECASE)
HARM = re.compile(r"odegra[cć]|postawi[łl]em wszystko|po[zż]yczy[łl]em na zak[łl]ad|nie mog[eę] przesta[cć]", re.IGNORECASE)

RISK_NOTE = "\n⚠️ To analiza statystyczna, nie gwarancja. Każdy zakład może przegrać. Gra od 18 lat."
SUPPORT = ("Widzę, że sytuacja może być trudna. Nie podam teraz typów – w takiej chwili najlepiej zrobić przerwę "
           "od zakładów. Jeśli czujesz, że granie wymyka się spod kontroli, warto porozmawiać ze specjalistą "
           "(np. w poradni leczenia uzależnień).")


def _traced(fn):
    """Wypisuje wywołanie narzędzia i krótki podgląd wyniku – widać, co agent robi."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        shown = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
        print(f"  🔧 {fn.__name__}({shown})", flush=True)
        result = fn(*args, **kwargs)
        preview = json.dumps(result, ensure_ascii=False)
        print(f"     ↳ {preview[:160]}{'…' if len(preview) > 160 else ''}", flush=True)
        return result
    return wrapper


def guard_output(text: str) -> str:
    """Guardrails wyjścia (docs/08, 8.6): bez obietnic wygranej, zawsze informacja o ryzyku."""
    if FORBIDDEN.search(text):
        text = FORBIDDEN.sub("[usunięte: brak gwarancji]", text)
    return text + RISK_NOTE


def make_chat(client: genai.Client):
    return client.chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[_traced(t) for t in TOOLS],
            temperature=0.2,
        ),
    )


def main() -> None:
    if not os.getenv("GEMINI_API_KEY"):
        sys.exit("Brak GEMINI_API_KEY w pliku .env (klucz z https://aistudio.google.com/)")
    client = genai.Client()
    chat = make_chat(client)
    print(f"Typer AI (model: {MODEL}). Pisz pytania o Ekstraklasę; 'koniec' kończy rozmowę.\n")
    while True:
        try:
            question = input("Ty: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in ("koniec", "exit", "quit"):
            break
        if not question:
            continue
        if HARM.search(question):           # guardrails wejścia: sygnały problemowego grania
            print(f"\nTyper AI: {SUPPORT}\n")
            continue
        try:
            response = chat.send_message(question)
            print(f"\nTyper AI: {guard_output(response.text or '')}\n")
        except errors.APIError as e:
            print(f"\n[Błąd API Gemini: {e.code} {e.message}. Spróbuj ponownie za chwilę.]\n")


if __name__ == "__main__":
    main()
