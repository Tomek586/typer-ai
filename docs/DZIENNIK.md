# Dziennik decyzji

Wspólna pamięć projektu dla wszystkich osób i sesji Claude. Najnowsze wpisy na górze. Każdy wpis: data, decyzja lub ustalenie, krótkie uzasadnienie. Szczegóły są w dokumentacji (`docs/`) i w historii commitów.

## Otwarte sprawy

- [ ] Imiona i nazwiska zespołu w README, prezentacji i dokumentacji (teraz `[Imię Nazwisko]`).
- [ ] Klucz Jev (TypeSafe AI): konto nie jest jeszcze założone; bez niego część decyzyjna działa na planie B (LLM).
- [ ] Komputer domowy: ustawić „Uśpij po” = Nigdy przy zasilaniu z sieci (21.11 było 30 min), inaczej etapy przed meczami przepadną.
- [ ] Model kartek: sędzia, drużyny, derby jako cecha do sprawdzenia; wynik z kursem minimalnym.
- [ ] Model v2: siła składu, forma, H2H, derby, motywacja, zmęczenie; każda cecha zostaje tylko, jeśli poprawia backtest.
- [ ] Newsy: wykrywanie kontuzji i zawieszeń (Jev lub LLM), przewidywany skład.
- [ ] RAG, aplikacja webowa, ocena NLP.

---

## 2026-11-21

- **Harmonogram działa na komputerze domowym** (zadanie `TyperAI_Scheduler`, start 12:20). Testy: 104 przeszło. Po starcie nadrobił etap 1 (ok) i rozliczenie; pierwsze 2 typy strategii „cień”, oficjalnych 0. Od teraz `data/typer.db` na tym komputerze jest bazą główną.
- **Analiza braku typów (8–21.11):** trzy przyczyny.
  1. Laptop spał: etap 1 wykonał się **raz** zamiast ok. 26 razy; etap 2 316 razy, czyli laptop działał ok. 53 h w 13 dni.
  2. Przerwa na reprezentację: brak meczów Ekstraklasy 9–19.11.
  3. Reguły: z 70 ocenionych zdarzeń (12 meczów) próg **EV ≥ 3% blokował 69**. Najlepszy kurs spośród ok. 20 bukmacherów jest zwykle **gorszy** od uczciwej ceny Pinnacle (mediana −4,4%, maks. +2,5%), a przy wadze rynku 85% EV ≥ 3% jest prawie nieosiągalne. Założenie, że wybór najlepszego kursu da przewagę, się nie sprawdziło.
- **Symulacja na sezonach walidacyjnych 2023/24 + 2024/25** (1X2, najlepszy kurs zamknięcia; małe próbki, ostrożnie): obecne reguły 8 typów/sezon (43,8%, ROI −18%); EV ≥ 1% 22/sezon (55,6%, −0,3%); w = 0,3 18/sezon (57,1%, +6,1%); w = 0,5 24/sezon (55,1%, +4,3%); sam model 40/sezon (50%, −6%).
- **Decyzja: oficjalny próg EV z 3% na 1%**, waga modelu bez zmian (0,15 – wynika z log-loss; zmiana wagi po wyniku ROI byłaby przeuczeniem). Oczekiwanie: ok. 22 typy oficjalne na sezon.
- **Strategia „cień”** (EV ≥ 0%, p ≥ 45%, kurs 1,50–3,00) zapisywana obok oficjalnej, wyłącznie do pomiaru modelu; na 12 meczach z listopada dałaby 3 typy (oficjalna: 0).
- **Harmonogram nadrabia pominięte terminy:** etap 1 i rozliczenie wykonają się po wybudzeniu komputera, jeśli ostatni termin przepadł (każda próba, także nieudana, liczy się jako wykonanie, żeby błąd API nie zużywał limitów co minutę).
- **Harmonogram usunięty z laptopa**, kopia bazy zrobiona (4215 meczów, 43 122 kursy, integralność OK). Od startu 8.11 harmonogram nie wydał ani jednego typu – reguły (p ≥ 52%, EV ≥ 3%, kurs 1,50–2,30) przy mieszance 85% rynku rzadko są spełnione; do przeanalizowania przy modelu v2.
- **Praca na 3 komputerach (laptop, komputer domowy, komputer kolegi).** Claude Code nie ma natywnie wspólnego czatu dla dwóch kont; udostępnienie sesji w chmurze to podgląd stanu, bez aktualizacji na żywo. Nieoficjalnych wtyczek do wspólnych sesji nie używamy: polecenia drugiej osoby wykonywałyby się na cudzym komputerze. **Wspólny kontekst = repozytorium:** `CLAUDE.md`, ten dziennik, `docs/`. Zasady w [CONTRIBUTING.md](../CONTRIBUTING.md).
- **Harmonogram ma działać na komputerze domowym**, nie na laptopie: laptop jest noszony i usypiany, więc gubi etapy przed meczami.
- **Dodano `python -m typerai.db --backup PLIK`:** spójna kopia bazy także w trakcie pracy harmonogramu (zwykłe kopiowanie pliku w trybie WAL może dać uszkodzoną kopię).

## 2026-11-08 (zajęcia: Proof of Concept)

- **Chatbot PoC:** Gemini z function calling i 5 narzędziami (`terminarz`, `forma_druzyny`, `analiza_meczu`, `przelicz_kurs`, `typy`), uruchamiany przez `python -m typerai.chat.cli`.
- **Limity Gemini (darmowy plan):** ok. 20 zapytań dziennie **na model**; pytanie z narzędziami zużywa 2–4 zapytania. Alias `gemini-flash-latest` jest niedostępny dla naszego klucza, a `gemini-2.5-flash` i `2.5-flash-lite` dla nowych kont zwracają 404. **Łańcuch modeli:** `3.5-flash` → `3.5-flash-lite` → `3.7-flash` → `3.6-flash` → `3.8-flash` → `3.1-flash-lite`, z przełączaniem przy 404, 429, błędach 5xx i przekroczeniu 60 s, z zachowaniem historii. Kolejność według pomiarów czasu: `3.5-flash` 3–9 s, `3.5-flash-lite` poniżej 1 s, większe modele 20–70 s.
- **Słabszy model zmyślił liczby** (np. szansa 60,1% zamiast 64,9% z narzędzia), więc dodano **kontrolę liczb (guardrail G5):** liczby dziesiętne i procenty z odpowiedzi muszą występować w wynikach narzędzi z tej tury; jeśli nie, model dostaje polecenie poprawy, a potem użytkownik widzi ostrzeżenie.
- **Testy hipotez na danych 2015–2026:**
  - w 1X2 faworyt ma ≥ 52% szans tylko w **31%** meczów (≥ 60% w 14%),
  - „najczęstszy wynik z 4 ostatnich H2H” trafia **37,9%**, faworyt bukmachera **46,5%**,
  - derby (109 meczów) nie mają więcej kartek: **4,01** żółtej na mecz vs 4,21; czerwona w 14,7% vs 15,3% meczów; mniej goli (2,42 vs 2,67).
- **Decyzja:** H2H i forma są w chacie **kontekstem** z liczbą meczów („3 z 4”). Do prawdopodobieństwa wejdą tylko wtedy, gdy backtest w modelu v2 pokaże, że coś wnoszą.
- **Kurs minimalny** = (1 + 3%) / p, dla zdarzeń bez naszego kursu: „warto tylko, jeśli twój bukmacher daje co najmniej X” (np. do porównania z ofertą STS).
- **Model kartek wraca do planu** (wcześniej poza zakresem z powodu braku kursów): na danych z 90minut.pl, z kursem minimalnym zamiast naszych kursów.
- Harmonogram założony jako zadanie Windows (`scripts/setup_scheduler.bat`). Prezentacja PoC: `prezentacja/TyperAI_PoC.pptx`.
- Usunięto e-mail z nagłówka User-Agent kolektora 90minut.pl (neutralna nazwa projektu).

## 2026-11-02 – 2026-11-03

- **Historia składów z 90minut.pl pobrana:** 3359 meczów (2015/16–2026/27), 2395 zawodników. Kontrola jakości: wyniki w 100% zgodne z football-data, 990 minut na drużynę w każdym meczu, wszystkie gole poza 309 samobójczymi przypisane strzelcom.
- Kolektor 90minut.pl ponawia zapytania z rosnącym odstępem po błędach sieci (przerwa w nocy przez uśpienie komputera).

## 2026-11-01

- **Źródła danych (tylko darmowe, bez obchodzenia zabezpieczeń):**
  - **STS** odrzucony: oferta przez websocket, ochrona przed botami,
  - **SofaScore** odrzucony: po godzinie działania odpowiedź `403 challenge` (ochrona przed botami),
  - **Flashscore** i **ekstraklasa.org** odrzucone: zabezpieczony kanał danych lub zakaz w `robots.txt`,
  - **API-Football** odrzucone: darmowy plan bez bieżącego sezonu, brak xG dla Ekstraklasy,
  - przyjęte: **football-data.co.uk** (wyniki i kursy 1X2 od 2012/13), **The Odds API** (ok. 20 bukmacherów, darmowe 500 kredytów miesięcznie), **90minut.pl** (składy; **zgoda redakcji 1.11.2026**).
- **Kursy Pinnacle** w football-data kończą się w połowie 2025/26, więc punktem odniesienia w historii jest też Betfair Exchange.
- **Rynki:** 1X2, podwójna szansa, gole, BTTS, handicap. Rożne i kartki bez typów (brak kursów).
- **Jev (TypeSafe AI)** jako silnik decyzyjny wyłącznie z **prawem weta** (nie zmienia prawdopodobieństw, nie dodaje typów): ocena newsów, bramka typu, routing pytań, guardrails. Plan B: ten sam interfejs na LLM.
- **Model v1 i walidacja walk-forward** (log-loss 1X2): rynek 1,0408, model 1,052, mieszanka 1,0406 (dwa sezony łącznie). Model na samych wynikach **nie pokonuje rynku**. Zamrożone: ξ = 0,0005, waga modelu w = 0,15. Przewaga v1 = wybór najlepszego kursu spośród ok. 20 bukmacherów.
- **Reguły typu:** p ≥ 52%, EV ≥ 3%, kurs 1,50–2,30, EV ≤ 25%, jeden typ na mecz; kurs odstający o ponad 8% od mediany odrzucany. Dwa etapy: typ wstępny i potwierdzenie ok. 60 min przed meczem.
- Commity po angielsku w stylu Conventional Commits, bez stopek AI (`CLAUDE.md`).

## 2026-10-18

- Wybór tematu: **Typer AI**, polskojęzyczny chatbot LLM z RAG do analizy meczów Ekstraklasy. Cel: trafność typów > 50% i dodatni ROI.
