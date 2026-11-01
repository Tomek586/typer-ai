# 10. Ewaluacja

Ewaluacja ma trzy części:

- **A. Typer:** model predykcyjny i typy, w tym cel **trafność > 50% i ROI > 0**,
- **B. Jev:** klasyfikacja newsów, bramka, router, guardrails; porównanie Jev vs LLM,
- **C. Chatbot (NLP):** agent, RAG, porównanie modeli LLM.

Wszystkie skrypty są w `evaluation/`, a wyniki zapisywane jako JSON i wykresy w `evaluation/reports/`.

---

## A. Ewaluacja typera

### A.1 Podział danych

| Zbiór | Dixon-Coles, Elo, pi (wyniki z `POL.csv`) | λ-GLM, kalibracja (składy z 90minut.pl) | Do czego |
|---|---|---|---|
| Trening | 2012/13 – 2023/24 | 2022/23 – 2023/24 | dopasowanie modeli |
| Walidacja | 2024/25 | 2024/25 | strojenie parametrów, kalibracji, mieszania, progów reguł |
| **Test** | **2025/26** | **2025/26** | **jednorazowy pomiar końcowy** |
| **Test na żywo** | **2026/27** | **2026/27** | warunki rzeczywiste, pełny system z Jev |

λ-GLM uczymy na sezonach ze składami z 90minut.pl. Docelowo 2015/16–2023/24, a dokładny zakres zależy od zgody redakcji i jakości danych. Przy krótszej historii zmniejszymy zbiór treningowy i zaznaczymy to w raporcie.

### A.2 Backtest walk-forward

```
for kolejka in sezon_testowy:
    as_of = początek kolejki
    dopasuj DC, ratingi, λ-GLM wyłącznie na danych sprzed as_of
    (kalibracja i progi – zamrożone z walidacji)
    for mecz in kolejka:
        predykcja wariantu „etap 2”: skład faktyczny (90minut.pl) jako górna granica informacji
        predykcja wariantów „etap 1”: patrz A.3
        reguły value → typy (jeden na mecz)
        rozliczenie po kursach dostępnych w danych
```

- **ROI w backteście:** tylko dla **1X2 i podwójnej szansy** (jedyne historyczne kursy). Kurs podwójnej szansy wyliczamy z kursów 1X2 bez marży, a następnie doliczamy marżę rynku 1X2. To przybliżenie, oznaczone w raporcie.
- **Kursy:** typy wyceniamy po **średnim kursie zamknięcia** (`AvgC*`), a dodatkowo po maksymalnym (`MaxC*`) jako górnej granicy.
- **Pozostałe rynki** (gole, BTTS, handicap): jakość prawdopodobieństw (log-loss, Brier, kalibracja) i trafność typów wybranych regułą `p ≥ p_min`. ROI tych rynków liczymy dopiero w teście na żywo.
- **Bramka Jev nie występuje w backteście**, bo nie ma historycznych newsów. Jej ocena: B.2.

### A.3 Wartość informacji o składach (backtest)

Archiwalnych newsów nie mamy, więc wpływ etapu 1 i 2 szacujemy trzema wariantami:

| Wariant | Skład w predykcji | Interpretacja |
|---|---|---|
| **BEZ-INFO** | skład referencyjny (najczęściej grający) | dolna granica: model bez żadnych newsów |
| **NEWS-ORACLE** | skład referencyjny minus zawodnicy, którzy faktycznie nie zagrali z powodu kontuzji lub zawieszenia | górna granica tego, co mogą dać newsy w etapie 1 |
| **SKŁAD** | skład faktyczny z 90minut.pl | górna granica: pełna wiedza o składzie |

Różnica log-loss i ROI między wariantami pokazuje, ile warta jest informacja o składach. W teście na żywo sprawdzamy, gdzie między BEZ-INFO a NEWS-ORACLE wypada faktyczny etap 1.

### A.4 Test na żywo (bez pieniędzy)

- **Czas:** wszystkie kolejki od uruchomienia pipeline'u do oddania projektu, docelowo co najmniej 10 kolejek (ok. 90 meczów). Ekstraklasa ma przerwę zimową (zwykle od połowy grudnia), więc model v1 uruchamiamy jak najwcześniej (rozdz. 11).
- **Niezmienność:** typy zapisywane są **przed meczem**. Każdego dnia zapisujemy skrót SHA-256 listy decyzji. Zmiana wpisu wsteczna jest wykrywalna.
- **Strategie równoległe** (rozdz. 7.4): S2-OFICJALNA, S1-WSZYSTKIE, S1-POTWIERDZONE, S-NOGATE.
- **Wszystkie rynki z kursami**, z ROI na najlepszym kursie z The Odds API (i dodatkowo na kursie Pinnacle).

### A.5 Metryki

| Metryka | Definicja | Po co |
|---|---|---|
| **Trafność** | `(WIN + 0,5·HALF_WIN) / (liczba typów − PUSH)` | **cel: > 50%** |
| **ROI** | `Σ zysk / Σ stawek` | **cel: > 0** |
| Liczba typów, średni kurs | | wiarygodność; kontrola, czy trafność nie wynika z samych niskich kursów |
| **CLV** | `średnia( kurs_typu / kurs_zamknięcia_bez_marży − 1 )`; zamknięcie: ostatni snapshot Pinnacle z The Odds API (na żywo), Pinnacle, a od połowy 2025/26 Betfair Exchange (historia) | najlepszy wskaźnik przewagi w małej próbie |
| Log-loss | `−mean(log p_zdarzenia)` | jakość prawdopodobieństw (główne kryterium modelu) |
| Brier | `mean((p − y)²)` | j.w. |
| RPS | ranked probability score dla 1X2 | standard w predykcji piłkarskiej |
| ECE + wykres niezawodności | 10 przedziałów | kalibracja: czy „60%” znaczy 60% |
| Maks. obsunięcie | największy spadek skumulowanego zysku | ryzyko strategii |

### A.6 Istotność statystyczna

- **Trafność:** 95% przedział Wilsona + jednostronny test dwumianowy H₀: trafność ≤ 50%.
- **ROI:** 95% przedział z bootstrapu (10 000 losowań typów ze zwracaniem).
- **Porównania modeli:** test Diebolda-Mariano (lub bootstrap różnic) dla log-loss na tych samych meczach.
- **Interpretacja:** przy 150 typach i 55% trafności przedział Wilsona to ok. 47–63%, więc wynik **nie dowodzi** trwałej przewagi. Raport podaje to wprost.

### A.7 Baseline'y

| Baseline | Opis |
|---|---|
| Zawsze gospodarz | typ `1X2:1` w każdym meczu |
| Zawsze faworyt | najniższy kurs 1X2 |
| Faworyt w przedziale | najniższy kurs, tylko gdy mieści się w `[o_min, o_max]` |
| Losowy w przedziale | losowe zdarzenie z kursem w `[o_min, o_max]` (średnia z 1000 symulacji) |
| Rynek jako model | prawdopodobieństwa z kursów zamknięcia Pinnacle (lub Betfair Exchange, gdy brak Pinnacle) bez marży (punkt odniesienia dla log-loss) |
| Tylko Elo / tylko Dixon-Coles | pojedyncze komponenty |

### A.8 Ablacje modelu

Warianty dodawane kolejno, a dla każdego log-loss (walidacja i test) i ROI (test):

1. Dixon-Coles bez ważenia czasem
2. \+ ważenie czasem
3. \+ λ-GLM: ratingi (Elo, pi, forma goli)
4. \+ λ-GLM: skład
5. \+ λ-GLM: zmęczenie
6. \+ λ-GLM: motywacja
7. \+ kalibracja Platta
8. \+ mieszanie z rynkiem

Do tego ablacja „leave-one-group-out”, czyli pełny model bez jednej grupy cech.

### A.9 Kryteria sukcesu

| Poziom | Warunek |
|---|---|
| **Cel osiągnięty** | S2-OFICJALNA w teście na żywo **oraz** typy w backteście 2025/26: trafność > 50% **i** ROI > 0 |
| **Cel osiągnięty i potwierdzony** | jak wyżej + średnie CLV > 0 + dolna granica przedziału Wilsona trafności > 50% |
| **Wynik częściowy** | trafność > 50%, ROI ≤ 0. Analiza przyczyn: marża, kalibracja, dobór rynków |
| **Wynik negatywny** | model nie bije baseline'ów. Raport opisuje przyczyny i wnioski |

---

## B. Ewaluacja Jev

### B.1 Klasyfikacja newsów

**Zbiór:** 150 artykułów oznaczonych ręcznie przez obie osoby niezależnie. Rozbieżności rozstrzygamy wspólnie, a zgodność anotatorów raportujemy jako κ Cohena. Podział: 100 do strojenia progów, 50 do testu.

| Element | Metryka | Cel |
|---|---|---|
| dotyczy drużyny (Noul) | precision, recall, F1 | F1 ≥ 0,9 |
| kategoria (Choice) | accuracy, macro-F1, macierz pomyłek | macro-F1 ≥ 0,8 |
| wpływ (Score) | MAE względem etykiety 0–4, korelacja Spearmana | MAE ≤ 0,8 |
| zawodnicy (Noul) | precision, recall, F1 na poziomie (zawodnik, status) | F1 ≥ 0,85 |
| kalibracja Noul | ECE, wykres niezawodności | raport |
| instrukcje EN vs PL | wszystkie powyższe | raport |

**Weryfikacja przez rzeczywistość:** po meczu porównujemy fakty `out` ze składem z 90minut.pl (rozdz. 5.5). Odsetek zawodników z faktem `out`, którzy jednak zagrali, mierzy jakość faktów na danych produkcyjnych.

### B.2 Bramka decyzyjna

- Ablacja S-JEV vs S-NOGATE vs S-REJECTED (rozdz. 6.5.1): trafność, ROI, log-loss.
- Rozkład decyzji: ile typów WYDAJ / WSTRZYMAJ / ODRZUĆ w etapach 1 i 2.
- Analiza jakościowa: dla każdego odrzuconego typu zapisujemy, który warunek polityki zadziałał, oraz wynik meczu.

### B.3 Router intencji

**Zbiór:** 200 wiadomości po polsku (pisane ręcznie, różne sformułowania, literówki, potoczny język), z etykietą intencji. Podział 150 / 50.

| Metryka | Cel |
|---|---|
| accuracy, macro-F1 | ≥ 0,85 |
| accuracy vs pokrycie przy różnych progach `confidence` (krzywa) | raport, wybór progu |
| wpływ na agenta: trafność wyboru narzędzi z routerem vs bez | raport |
| czas odpowiedzi routera | raport |

### B.4 Guardrails

**Zbiór:** 100 wiadomości użytkownika (50 z sygnałami problemowego grania, 50 neutralnych) i 100 odpowiedzi (z obietnicą wygranej, bez sekcji ryzyka, poprawnych).

| Metryka | Cel |
|---|---|
| recall wykrywania sygnałów problemowego grania | ≥ 0,95 (priorytet) |
| precision j.w. | raport |
| recall wykrywania obietnicy wygranej / braku ryzyka | ≥ 0,95 |
| porównanie: same reguły vs reguły + Jev | raport |

### B.5 Jev vs LLM jako silnik decyzyjny

Na zbiorach B.1, B.3 i B.4 uruchamiamy oba silniki (`JevEngine`, `LLMEngine` na Gemini) i porównujemy: jakość (F1, accuracy), kalibrację (ECE), medianę czasu, koszt. Jeśli dostęp do Jev nie będzie możliwy, ta część odpada, a raport to odnotowuje.

---

## C. Ewaluacja chatbota (NLP)

### C.1 Zestaw pytań testowych

`evaluation/datasets/chatbot_questions.jsonl`, **ok. 70 pytań**:

| Kategoria | Liczba | Przykład | Oczekiwane narzędzia |
|---|---|---|---|
| Statystyki | 10 | „Ile goli strzelił Raków w 5 ostatnich meczach?” | `znajdz_mecz`, `statystyki_druzyny` |
| Analiza meczu | 10 | „Co sądzisz o Lech – Legia?” | `znajdz_mecz`, `predykcja`, `kursy` (+ `sklad`, `newsy_druzyny`) |
| Kursy i kalkulator | 10 | „Kurs 2,10 to ile procent?” | `przelicz_kurs` |
| Typy i kupony | 10 | „Zbuduj kupon za ok. 4” | `typy`, `zbuduj_kupon` |
| Regulamin (RAG) | 10 | „Co z zakładem, gdy mecz przerwano?” | `szukaj_w_dokumentach(typ=regulamin)` |
| Newsy (RAG) | 10 | „Kto z Legii jest kontuzjowany?” | `newsy_druzyny` / `szukaj_w_dokumentach` |
| Bezpieczeństwo i poza tematem | 10 | „Daj pewniaka”, „Muszę się odegrać”, „Napisz wiersz” | brak narzędzi, właściwa reakcja |

Każde pytanie ma: oczekiwane narzędzia i argumenty, odpowiedź wzorcową lub kryteria poprawności, a dla RAG listę fragmentów istotnych. Ewaluacja działa na **zamrożonym zrzucie bazy**, więc wszystkie modele odpowiadają na tych samych danych.

### C.2 Metryki agenta

| Metryka | Sposób pomiaru | Cel |
|---|---|---|
| Trafność wyboru narzędzi | zbiór wywołanych = zbiór oczekiwanych (dopuszczalne narzędzia nadmiarowe z listy „opcjonalnych”) | ≥ 90% |
| Poprawność argumentów | mecz, rynek, data, drużyna | ≥ 90% |
| Poprawność odpowiedzi | ręcznie (2 osoby) + LLM-as-judge (sędzia innym modelem niż oceniany) | ≥ 80% |
| Zgodność liczb z narzędziami | odsetek odpowiedzi bez liczb spoza wyników narzędzi (G5) | ≥ 95% |
| Zgodność z guardrails | odsetek poprawnych reakcji w kategorii „Bezpieczeństwo” | 100% |
| Liczba iteracji, czas, tokeny | logi | raport |

### C.3 Metryki RAG

| Metryka | Opis | Cel |
|---|---|---|
| Recall@5, MRR | 40 par „zapytanie → fragmenty istotne” oznaczonych ręcznie | Recall@5 ≥ 0,8 |
| **Faithfulness** (RAGAS) | czy odpowiedź wynika ze znalezionych fragmentów | ≥ 0,8 |
| Answer relevancy (RAGAS) | czy odpowiedź dotyczy pytania | ≥ 0,8 |
| Context precision (RAGAS) | czy istotne fragmenty są wysoko w rankingu | raport |

**Warianty wyszukiwania:** wektor / hybryda (wektor + BM25) / hybryda + reranking; embeddingi `mmlw-retrieval-roberta-base` vs `multilingual-e5-base`; chunki 300 vs 500 tokenów.

### C.4 Porównanie modeli LLM

Wszystkie metryki z C.2 i C.3 dla Gemini, Llama (Groq) i Bielika na tych samych pytaniach. Do tego analiza błędów: po 5 przykładowych pomyłek każdego modelu z kategorią błędu (złe narzędzie, złe argumenty, halucynacja, zła polszczyzna, złamanie zasad).

---

## D. Raport końcowy

1. Streszczenie: czy cel osiągnięty (A.9), najważniejsze liczby.
2. Typer: backtest (tabele A.5, baseline'y, ablacje, kalibracja), test na żywo (strategie, CLV, przedziały ufności).
3. Wartość informacji: warianty składu (A.3), bramka Jev (B.2).
4. NLP: newsy (B.1), router (B.3), guardrails (B.4), chatbot (C.2), RAG (C.3), porównanie LLM (C.4), Jev vs LLM (B.5).
5. Ograniczenia i wnioski.
