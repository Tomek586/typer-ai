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
from typerai.chat import numbers
from typerai.chat.tools import TOOLS

# Darmowy plan Gemini: ok. 20 zapytań dziennie NA MODEL, a pytanie z narzędziami zużywa 2–4 zapytania.
# Gdy model wyczerpie limit (429), jest przeciążony (503) albo niedostępny (404), przechodzimy na następny.
MODELS = os.getenv("GEMINI_MODELS", "gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash,"
                                    "gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite").split(",")
SWITCH_CODES = (404, 429)  # oraz każdy błąd serwera 5xx
# Bez ukrytych ponowień SDK (potrafią czekać minutami) – po 60 s lub błędzie od razu następny model
HTTP_OPTIONS = types.HttpOptions(timeout=60_000, retry_options=types.HttpRetryOptions(attempts=1))

SYSTEM_PROMPT = """Jesteś Typer AI – asystentem do analizy meczów piłkarskiej Ekstraklasy i zakładów sportowych.
Odpowiadasz po polsku, rzeczowo i zwięźle. Gdy porównujesz liczby, używasz krótkiej listy lub tabeli.

ZASADY LICZB
1. Nie licz samodzielnie prawdopodobieństw, EV ani marży – zawsze używaj narzędzi.
2. Każda liczba w odpowiedzi musi pochodzić z wyniku narzędzia w tej rozmowie.
3. „Oczekiwane gole modelu” to wynik modelu Dixona-Colesa, a NIE xG – nigdy nie nazywaj ich xG.

ZASADY TYPÓW
4. Typ podajesz tylko wtedy, gdy narzędzie analiza_meczu zwróci pole "typ". Nie twórz własnych typów.
5. Jeśli typu nie ma, powiedz to wprost i wyjaśnij dlaczego (np. za niskie EV lub prawdopodobieństwo).
6. Nigdy nie obiecuj wygranej. Nie używaj słów „pewniak”, „pewna wygrana”, „gwarancja wygranej”.
7. Przy każdej analizie dodaj jedno zdanie o ryzyku.

TRENDY I KURS MINIMALNY
8. Trendy (H2H z 4 ostatnich meczów, forma z 3 ostatnich) podawaj jako kontekst, zawsze z liczbą meczów („3 z 4”).
   Zaznacz, że to mała próbka i nie podstawa typu. Wynik meczu H2H dla gospodarza bierz z pola rezultat_dla_gospodarza.
9. Kurs minimalny to najniższy kurs, przy którym zakład ma wartość. Dla zdarzeń bez naszego kursu powiedz:
   „warto tylko, jeśli Twój bukmacher daje co najmniej X”. Kurs minimalny to NIE jest typ.
10. W analizie meczu pokaż 4–6 najciekawszych zdarzeń (najwyższe p, wartość, powtarzające się trendy), nie wszystkie.

ZAKRES
11. Tematy: Ekstraklasa, kursy, zakłady, wyniki typera. Inne tematy – uprzejmie odmów.
12. Jeśli nie wiesz – powiedz to. Nie zgaduj.

FORMAT
13. Odpowiedź czytana jest w terminalu: zwykły tekst, listy i tabele Markdown; bez wzorów LaTeX ($...$)."""

# Tylko obietnice wygranej – zdania typu „nie gwarantuje wygranej” są poprawne i zostają
FORBIDDEN = re.compile(r"pewniak\w*|pewn[aąe]\w* wygran\w*|(?<!nie )gwarant\w* wygran\w*|(?<!nie )gwarancj\w* wygran\w*"
                       r"|na 100\s?%", re.IGNORECASE)
HARM = re.compile(r"odegra[cć]|postawi[łl]em wszystko|po[zż]yczy[łl]em na zak[łl]ad|nie mog[eę] przesta[cć]", re.IGNORECASE)
BETTING_TOPIC = re.compile(r"kurs|typ|EV|zak[łl]ad|prawdopodobie", re.IGNORECASE)

RISK_NOTE = "\n⚠️ To analiza statystyczna, nie gwarancja. Każdy zakład może przegrać. Gra od 18 lat."
SUPPORT = ("Widzę, że sytuacja może być trudna. Nie podam teraz typów – w takiej chwili najlepiej zrobić przerwę "
           "od zakładów. Jeśli czujesz, że granie wymyka się spod kontroli, warto porozmawiać ze specjalistą "
           "(np. w poradni leczenia uzależnień).")


# Wyniki narzędzi z bieżącej tury – podstawa sprawdzania liczb w odpowiedzi (guardrail G5)
TOOL_LOG: list = []

CORRECTION = ("Twoja odpowiedź zawiera liczby, których nie ma w wynikach narzędzi: {nums}. "
              "Odpowiedz ponownie na to samo pytanie. Najpierw wywołaj potrzebne narzędzia i używaj WYŁĄCZNIE "
              "liczb z ich wyników.")
UNVERIFIED_NOTE = "\n⚠️ Uwaga: części liczb w tej odpowiedzi nie udało się potwierdzić w danych ({nums}) – traktuj je ostrożnie."


def _traced(fn):
    """Wypisuje wywołanie narzędzia i krótki podgląd wyniku – widać, co agent robi."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        shown = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
        print(f"  🔧 {fn.__name__}({shown})", flush=True)
        result = fn(*args, **kwargs)
        TOOL_LOG.append(result)
        preview = json.dumps(result, ensure_ascii=False)
        print(f"     ↳ {preview[:160]}{'…' if len(preview) > 160 else ''}", flush=True)
        return result
    return wrapper


def guard_output(text: str) -> str:
    """Guardrails wyjścia (docs/08, 8.6): bez obietnic wygranej; przy kursach i typach informacja o ryzyku."""
    if FORBIDDEN.search(text):
        text = FORBIDDEN.sub("[usunięte]", text)
    return text + RISK_NOTE if BETTING_TOPIC.search(text) else text


def make_chat(client: genai.Client, model: str, history=None):
    return client.chats.create(
        model=model,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[_traced(t) for t in TOOLS],
            temperature=0.2,
        ),
        history=history,
    )


class ChatSession:
    """Rozmowa z łańcuchem modeli: po błędzie limitu przechodzi na kolejny model z zachowaniem historii."""

    def __init__(self, client: genai.Client, models: list[str] = MODELS, factory=make_chat):
        self.client, self.models, self.factory = client, models, factory
        self.index = 0
        self.chat = factory(client, models[0])

    @property
    def model(self) -> str:
        return self.models[self.index]

    def send(self, question: str) -> str:
        while True:
            try:
                return self.chat.send_message(question).text or ""
            except Exception as e:
                # błąd API (kod HTTP) albo przekroczenie czasu – SDK używa własnej kopii httpx, więc po nazwie klasy
                if isinstance(e, errors.APIError):
                    code = e.code
                elif "timeout" in type(e).__name__.lower():
                    code = "timeout"
                else:
                    raise
                switchable = code == "timeout" or code in SWITCH_CODES or (isinstance(code, int) and code >= 500)
                if not switchable or self.index + 1 >= len(self.models):
                    raise
                history = self.chat.get_history()
                self.index += 1
                print(f"  [model niedostępny ({code}) – przełączam na {self.model}]", flush=True)
                self.chat = self.factory(self.client, self.model, history)


def answer_question(session: "ChatSession", question: str) -> str:
    """Pytanie -> odpowiedź z kontrolą liczb: przy liczbach spoza narzędzi jedna próba poprawy, potem ostrzeżenie."""
    TOOL_LOG.clear()
    answer = session.send(question)
    bad = numbers.unverified(answer, TOOL_LOG)
    if len(bad) >= 2:
        print(f"  [kontrola liczb: {len(bad)} liczb spoza narzędzi – poprawka]", flush=True)
        answer = session.send(CORRECTION.format(nums=", ".join(f"{x:g}" for x in bad[:6])))
        bad = numbers.unverified(answer, TOOL_LOG)
        if len(bad) >= 2:
            answer += UNVERIFIED_NOTE.format(nums=", ".join(f"{x:g}" for x in bad[:6]))
    return answer


def main() -> None:
    if not os.getenv("GEMINI_API_KEY"):
        sys.exit("Brak GEMINI_API_KEY w pliku .env (klucz z https://aistudio.google.com/)")
    session = ChatSession(genai.Client(http_options=HTTP_OPTIONS))
    print(f"Typer AI (model: {session.model}). Pisz pytania o Ekstraklasę; 'koniec' kończy rozmowę.\n")
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
            answer = answer_question(session, question)
        except errors.APIError as e:
            print(f"\n[Błąd API Gemini: {e.code} {e.message}. Spróbuj ponownie za chwilę.]\n")
            continue
        print(f"\nTyper AI: {guard_output(answer)}\n")


if __name__ == "__main__":
    main()
