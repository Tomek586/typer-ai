# Przeniesienie harmonogramu na komputer domowy

Harmonogram (etap 1 o 9:00 i 18:00, etap 2 ok. 60 min przed każdym meczem, rozliczenia o 10:30 i 23:45) musi działać na komputerze, który jest włączony w dni meczowe. Laptop noszony na uczelnię i usypiany gubi etapy, więc harmonogram przenosimy na komputer stacjonarny. Całość zajmuje ok. 20 minut.

**Ważne:** przez cały czas harmonogram może działać tylko na **jednym** komputerze.

## Część 1: laptop (wyłączenie i kopia bazy)

W folderze projektu na laptopie:

**1. Usuń zadanie harmonogramu:**

```bash
scripts/setup_scheduler.bat -Remove
```

Okno powinno pokazać „Usunieto zadanie TyperAI_Scheduler.”

**2. Zrób spójną kopię bazy:**

```bash
.venv/Scripts/python -m typerai.db --backup data/typer_kopia.db
```

**3. Przenieś na komputer domowy** plik `data/typer_kopia.db` (ok. 19 MB) oraz zawartość pliku `.env`, np. pendrivem albo przez własny dysk w chmurze. Pliku `.env` nie wysyłaj przez czat ani mailem: są w nim klucze API.

## Część 2: komputer domowy (instalacja i uruchomienie)

**1. Programy:** Python 3.11+ i git (jeśli ich nie ma).

**2. Kod i środowisko:**

```bash
git clone https://github.com/Tomek586/typer-ai.git
```

```bash
cd typer-ai && python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
```

**3. Klucze:** utwórz plik `.env` w folderze projektu i wklej zawartość z laptopa. Na tym komputerze potrzebne są `ODDS_API_KEY` (kursy) i `GEMINI_API_KEY` (chatbot).

**4. Baza:** skopiuj `typer_kopia.db` do folderu `data/` i zmień nazwę na `typer.db`.

**5. Sprawdzenie:**

```bash
.venv/Scripts/python -m pytest
```

```bash
.venv/Scripts/python -m typerai.pipeline picks
```

Testy muszą przechodzić, a `picks` ma pokazać typy z laptopa (lub pustą listę, jeśli jeszcze ich nie było).

**6. Uruchom harmonogram:** dwuklik na `scripts\setup_scheduler.bat`. Jeśli pojawi się „Odmowa dostępu”: prawy przycisk → Uruchom jako administrator.

**7. Zasilanie:** Ustawienia → System → Zasilanie → „Uśpij po” = **Nigdy** (przynajmniej przy zasilaniu z sieci). Uśpiony komputer nie wykona etapów przed meczami.

**8. Kontrola:** w pliku `data/scheduler.log` powinna pojawić się linia „Harmonogram Typer AI uruchomiony”. Po najbliższej godzinie 9:00 lub 18:00 powinien być wpis o etapie 1.

## Część 3: laptop po przeniesieniu

- Laptop służy do pracy nad kodem i do chatbota. **Nie uruchamiaj na nim** `python -m typerai.pipeline stage1/stage2/settle`, bo to zapis do kopii bazy, która przy następnej kopii zostanie nadpisana.
- **Świeże dane na laptopie:** na komputerze domowym `python -m typerai.db --backup data/typer_kopia.db`, potem skopiuj plik na laptopa jako `data/typer.db`. Wystarczy raz na jakiś czas albo przed prezentacją.
- **Rozmowa z Claude działającym w domu:** na komputerze domowym w sesji Claude Code wpisz `/remote-control`, a na laptopie otwórz claude.ai/code. Komputer domowy musi być wtedy włączony. Wymaga płatnego planu Claude.

## Gdyby coś poszło nie tak

| Objaw | Co zrobić |
|---|---|
| brak `data/scheduler.log` po uruchomieniu | otwórz Harmonogram zadań Windows, znajdź `TyperAI_Scheduler`, sprawdź kolumnę „Wynik ostatniego uruchomienia” |
| w logu `Brak ODDS_API_KEY` | uzupełnij `.env` i zrestartuj zadanie (albo wyloguj się i zaloguj ponownie) |
| typy dublują się | harmonogram działa na dwóch komputerach; usuń go z laptopa (część 1, krok 1) |
| `database is locked` w logu | inny program trzyma bazę otwartą (np. przeglądarka SQLite); zamknij go |
