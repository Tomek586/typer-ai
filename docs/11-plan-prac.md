# 11. Plan prac

Termin oddania nie jest jeszcze znany, więc etapy opisane są w tygodniach od startu. Kluczowe ograniczenie czasowe to **przerwa zimowa Ekstraklasy** (zwykle od połowy grudnia). Test na żywo musi wystartować jak najszybciej, dlatego **etap 2 ma priorytet** nad resztą.

## 11.1 Etapy

| Etap | Tydz. | Zakres | Kryterium ukończenia |
|---|---|---|---|
| **0. Start** | 1 | repozytorium, struktura, `.env`, schemat SQLite, aliasy drużyn, **założenie konta Jev i test API na 10 polskich newsach**, decyzja o dostępie do Bielika | oba środowiska działają; wiadomo, czy Jev jest dostępny |
| **1. Dane** | 1–2 | import `POL.csv` (gotowe); The Odds API: terminarz i kursy (gotowe); 90minut.pl (zgoda redakcji): parser relacji i historia składów (gotowe); pogoda; lista źródeł newsów | baza z historią; codzienne snapshoty kursów |
| **2. Model v1 + start testu na żywo** | 2–3 | Elo, pi-ratings, Dixon-Coles, macierz → rynki golowe, reguły value, cykl życia typu (bez bramki: wszystko WYDAJ/POTWIERDŹ), rozliczanie, harmonogram, powiadomienia Telegram (minimalne) | **od tego dnia typy zapisywane są codziennie** |
| **3. Newsy + Jev** | 3–4 | pipeline newsów, deduplikacja, `DecisionEngine` (Jev + LLM), pytania klasyfikacyjne, fakty, przewidywany skład, oznaczenie 150 artykułów | fakty z newsów w bazie; F1 na zbiorze testowym |
| **4. Model v2** | 3–5 | ważność zawodników i cechy składu, zmęczenia i motywacji, λ-GLM, kalibracja, mieszanie z rynkiem, strojenie na walidacji, backtest | model zamrożony, wyniki backtestu |
| **5. Bramka Jev** | 5 | pytania i polityka bramki, strategie równoległe (S-NOGATE itd.), wdrożenie do testu na żywo razem z modelem v2 | bramka działa w etapach 1 i 2 |
| **6. Chatbot** | 4–6 | `LLMClient` (Gemini, Groq, Bielik), narzędzia, pętla agenta, router Jev, RAG (hybryda + reranking), guardrails, prompty | chatbot odpowiada na 70 pytań testowych |
| **7. Interfejsy** | 5–7 | Streamlit (wszystkie strony), pełny bot Telegram | demo gotowe |
| **8. Ewaluacja NLP** | 6–7 | zbiory: intencje (200), guardrails (200), RAG (40), pytania (70); uruchomienie B.1–B.5, C.1–C.4 | tabele wyników |
| **9. Raport i prezentacja** | 7–8 | podsumowanie testu na żywo, raport (rozdz. 10.D), slajdy, scenariusz demo | projekt oddany |

**Zmiana wersji modelu w trakcie testu na żywo** (v1 → v2 w tygodniu 5) jest oznaczona w `model_version`. W raporcie oba okresy opisujemy osobno.

## 11.2 Podział zadań (propozycja)

| Obszar | Osoba A: **dane, model, typy** | Osoba B: **NLP, Jev, interfejsy** |
|---|---|---|
| Dane | `POL.csv`, The Odds API, 90minut.pl, pogoda, schemat bazy | kolektor newsów, regulaminy bukmacherów |
| Model | ratingi, Dixon-Coles, λ-GLM, kalibracja, mieszanie | – |
| Newsy | cechy składu (`lineup_*`) z faktów | pipeline newsów, pytania Jev, fakty, przewidywany skład |
| Jev | dane wejściowe bramki (`state`) | `DecisionEngine`, polityki, router, guardrails |
| Typy | reguły value, cykl życia, kupony, rozliczanie | – |
| Chatbot | narzędzia zwracające JSON (implementacja logiki) | agent, prompty, RAG, obsługa narzędzi |
| UI | strony „Typy”, „Mecz”, „Wyniki”, „Kalibracja” | „Czat”, „Newsy”, „Decyzje Jev”, „System”, bot Telegram |
| Ewaluacja | A (backtest, baseline'y, ablacje, test na żywo) | B i C (Jev, router, guardrails, RAG, LLM) |
| **Wspólnie** | kontrakty JSON (narzędzia, predykcja, typ, fakt), oznaczanie zbiorów, raport, prezentacja | |

**Kontrakty JSON ustalamy w tygodniu 1:** format predykcji (rozdz. 4.11), typu (7.8), faktu (5.4), `state` bramki (6.4.2) i definicje narzędzi (8.3). Dzięki temu obie osoby pracują równolegle. Osoba B do czasu gotowości modelu używa atrap (mocków) zwracających przykładowe JSON-y.

**Rytm pracy:** krótka synchronizacja raz w tygodniu, praca na gałęziach i pull requestach z przeglądem drugiej osoby.

## 11.3 Ryzyka

| Ryzyko | Prawd. | Wpływ | Plan B |
|---|---|---|---|
| Model nie osiąga ROI > 0 | wysokie | średni | dopuszczalny wynik badawczy; raport z analizą (10.A.9); chatbot działa jako narzędzie analityczne |
| Mało typów w teście na żywo (przerwa zimowa) | wysokie | wysoki | start modelu v1 w tygodniu 2–3; łączny raport backtest + test na żywo; CLV jako wskaźnik w małej próbie |
| Brak dostępu do Jev | średnie | średni | `LLMEngine` z tymi samymi pytaniami; porównanie Jev vs LLM odpada |
| Jev słabo radzi sobie z polskim tekstem | średnie | średni | instrukcje po angielsku; ewentualnie tłumaczenie tytułu i leadu artykułu przez LLM przed klasyfikacją; porównanie z `LLMEngine` |
| Wyczerpanie kredytów The Odds API | średnie | wysoki | budżet kredytów (rozdz. 3.3.2), próg ostrzegawczy |
| Zmiana układu stron 90minut.pl | niskie | średni | model bez cech składu (ratingi + motywacja); newsy tylko w bramce Jev |
| Brak oficjalnych składów przed meczem | pewne | średni | newsy (NLP) + ręczne potwierdzenie; ocena wartości tej informacji w ewaluacji (rozdz. 10, A.3) |
| Limity darmowych API LLM | średnie | niski | cache w ewaluacji, przełączanie Gemini ↔ Groq |
| Bielik niedostępny lub za wolny | średnie | niski | porównanie tylko Gemini vs Llama, z opisem próby |
| Mało newsów o mniejszych klubach | średnie | niski | strony klubów jako źródło; newsy mają z założenia małą rolę |
| Rozjazd prac obu osób | niskie | średni | kontrakty JSON od tygodnia 1, cotygodniowa synchronizacja |

## 11.4 Rezultaty do oddania

- repozytorium z kodem, testami i dokumentacją,
- działająca aplikacja Streamlit i bot Telegram (demo na żywo),
- zbiory ewaluacyjne oznaczone ręcznie (newsy, intencje, guardrails, pytania, RAG),
- raport z ewaluacji (rozdz. 10.D),
- prezentacja na ostatnich zajęciach.

## 11.5 Scenariusz demo na prezentacji (5–7 min)

1. Strona „Typy”: dzisiejsze typy wstępne i potwierdzone, z decyzjami bramki Jev.
2. Czat: „Co sądzisz o meczu X?” z rozwiniętym panelem „Jak powstała odpowiedź” (router, narzędzia, RAG).
3. Czat: „Co się dzieje z zakładem, gdy mecz przerwano?” (RAG z cytatem z regulaminu).
4. Czat: „Muszę się odegrać, daj pewniaka” (guardrails, tryb wsparcia).
5. Strona „Newsy”: artykuł → klasyfikacja Jev → fakt → zmiana przewidywanego składu.
6. Strona „Wyniki”: trafność, ROI, CLV, porównanie z baseline'ami.
7. Telegram: powiadomienie o potwierdzeniu lub anulowaniu typu.
