# Jak pracujemy nad Typer AI

Projekt rozwijają dwie osoby na trzech komputerach. Ten plik opisuje, jak przygotować komputer, gdzie co działa i jak współpracować, żeby się nie blokować.

## Komputery i ich role

| Komputer | Rola | Harmonogram typów | Baza danych |
|---|---|---|---|
| **Komputer domowy (stacjonarny)** | „baza”: stoi włączony, zbiera dane i wydaje typy | ✅ **tylko tutaj** | **główna**, jedyna uzupełniana |
| **Laptop** | praca na uczelni i w podróży | ❌ | kopia do odczytu |
| **Komputer kolegi** | praca nad częścią NLP | ❌ | kopia do odczytu |

**Harmonogram działa tylko na jednym komputerze.** Uruchomiony w dwóch miejscach liczy typy podwójnie i zużywa podwójnie darmowe limity API. Przeniesienie z laptopa na komputer domowy opisuje [docs/harmonogram-komputer-domowy.md](docs/harmonogram-komputer-domowy.md).

## Wspólny kontekst zamiast wspólnego czatu

Claude Code nie ma natywnie wspólnego czatu dla dwóch osób (stan na 21.11.2026). Każdy pracuje we własnym Claude Code na własnym koncie, a wspólną „pamięcią” jest repozytorium:

- [CLAUDE.md](CLAUDE.md): zasady pracy, czytane automatycznie przez każdą sesję Claude,
- [docs/DZIENNIK.md](docs/DZIENNIK.md): **dziennik decyzji**, czyli co ustaliliśmy, co sprawdziliśmy i dlaczego,
- [docs/](docs/): pełna dokumentacja projektu.

**Zasada:** po każdej ważnej decyzji lub ustaleniu dopisz krótki wpis do dziennika w tym samym pull requeście. Dzięki temu Claude kolegi następnego dnia „wie” to samo co twój.

**Ty na dwóch komputerach:** możesz kontynuować rozmowę z sesją działającą na komputerze domowym, będąc na laptopie, przez **Remote Control** (polecenie `/remote-control` w sesji Claude Code, a potem claude.ai/code w przeglądarce lub aplikacji). Komputer domowy musi wtedy być włączony. Wymaga płatnego planu Claude (Pro, Max, Team lub Enterprise) i logowania kontem claude.ai. Szczegóły: [dokumentacja Remote Control](https://code.claude.com/docs/en/remote-control).

## Przygotowanie nowego komputera

**1. Dostęp do repozytorium.** Repozytorium jest prywatne. Właściciel dodaje nową osobę w GitHub → Settings → Collaborators.

**2. Programy:** Python 3.11+, git, Claude Code (aplikacja desktopowa lub terminal).

**3. Kod i środowisko** (w folderze, w którym ma leżeć projekt):

```bash
git clone https://github.com/Tomek586/typer-ai.git
```

```bash
cd typer-ai && python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
```

**4. Klucze.** Skopiuj `.env.example` jako `.env` i uzupełnij. Każda osoba zakłada **własne** klucze, bo darmowe limity są małe:

| Klucz | Skąd | Limit darmowy | Potrzebny do |
|---|---|---|---|
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com/) | ok. 20 zapytań dziennie na model | chatbota |
| `ODDS_API_KEY` | [the-odds-api.com](https://the-odds-api.com/) | 500 kredytów miesięcznie | tylko na komputerze z harmonogramem |

Kluczy nie wysyłamy przez czat i nie wrzucamy do repozytorium (`.env` jest w `.gitignore`).

**5. Baza danych.** Plik `data/typer.db` (ok. 19 MB) nie jest w repozytorium. Na komputerze domowym zrób spójną kopię i przekaż ją (Google Drive, pendrive):

```bash
.venv/Scripts/python -m typerai.db --backup data/typer_kopia.db
```

Na nowym komputerze zapisz ją jako `data/typer.db`. **Nie pobieraj historii z 90minut.pl od nowa:** to ok. 4 godziny obciążania serwisu, który dał nam zgodę.

**6. Sprawdzenie:**

```bash
.venv/Scripts/python -m pytest
```

```bash
.venv/Scripts/python -m typerai.chat.cli
```

## Codzienna praca

1. **Zacznij od aktualizacji:** `git pull` na gałęzi `main`.
2. **Załóż gałąź** dla zadania: `feat/model-kartek`, `fix/limit-gemini`, `docs/rozdzial-newsy`.
3. **Pracuj z Claude Code.** Sesja sama wczyta `CLAUDE.md`; poproś ją też o przeczytanie `docs/DZIENNIK.md`, jeśli zadanie dotyczy wcześniejszych ustaleń.
4. **Przed wypchnięciem:** testy muszą przechodzić (`.venv/Scripts/python -m pytest`).
5. **Commity** według [CLAUDE.md](CLAUDE.md): po angielsku, Conventional Commits, bez stopek AI.
6. **Pull request** na GitHubie, a druga osoba go przegląda i scala.
7. **Ważna decyzja?** Wpis w [docs/DZIENNIK.md](docs/DZIENNIK.md) w tym samym pull requeście.

## Podział pracy

Według [docs/11-plan-prac.md](docs/11-plan-prac.md), z aktualnymi priorytetami:

| Osoba A: dane, model, typy | Osoba B: NLP, Jev, interfejsy |
|---|---|
| model kartek (sędzia, drużyny, kurs minimalny) | pipeline newsów i klasyfikacja nieobecności (Jev lub LLM) |
| model v2: skład, forma, H2H, derby, motywacja – z testem w backteście | RAG: newsy i regulaminy z podaniem źródeł |
| test na żywo i raport skuteczności | aplikacja webowa (Streamlit), ocena NLP |

Obie części łączą się przez **narzędzia chatbota** (`typerai/chat/tools.py`), które zwracają słowniki JSON. Zmianę formatu takiego słownika uzgadniamy przed scaleniem.

## Czego nie robimy

- Nie uruchamiamy harmonogramu poza komputerem domowym.
- Nie uruchamiamy `python -m typerai.pipeline stage1/stage2/settle` na kopiach bazy (laptop, komputer kolegi), bo to zapis do bazy, który przy następnej kopii zostanie nadpisany.
- Nie obchodzimy zabezpieczeń stron ani limitów API (rozdz. 3.2 dokumentacji).
- Nie commitujemy `.env`, `data/` ani logów.
