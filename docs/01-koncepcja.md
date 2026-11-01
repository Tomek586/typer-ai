# 1. Koncepcja projektu

## 1.1 Problem

Osoba, która chce świadomie obstawić mecz Ekstraklasy, musi zebrać informacje z wielu miejsc:

- statystyki drużyn: forma, gole, bilans bezpośrednich spotkań,
- informacje o składach i wydarzeniach: kontuzje, zawieszenia, zmiana trenera, problemy w klubie, zmęczenie po meczu pucharowym, pogoda, zamknięty stadion,
- kursy, które trzeba przeliczyć na prawdopodobieństwo i oczyścić z marży bukmachera,
- regulaminy, np. co się dzieje z zakładem przy przerwanym meczu.

Zajmuje to dużo czasu, a decyzje często opierają się na intuicji. Większość graczy nie wie też, że **wysoka trafność nie oznacza zysku**. Liczy się to, czy prawdopodobieństwo zdarzenia jest wyższe niż to, które wynika z kursu.

## 1.2 Rozwiązanie

Typer AI to system złożony z trzech współpracujących warstw:

| Warstwa | Za co odpowiada | Technologia |
|---|---|---|
| **Model predykcyjny** | liczy prawdopodobieństwa wszystkich zdarzeń meczu | Dixon-Coles + regresja korygująca (Elo, pi-ratings, siła składu, zmęczenie, motywacja) + kalibracja |
| **Silnik decyzyjny Jev** | podejmuje szybkie, typowane decyzje: ocenia newsy, przepuszcza lub wstrzymuje typy, kieruje pytania w czacie, pilnuje bezpieczeństwa | Jev (TypeSafe AI), model „System One” |
| **Chatbot LLM** | rozmawia po polsku, wywołuje narzędzia, wyszukuje dokumenty (RAG), tłumaczy decyzje | Gemini / Llama (Groq) / Bielik + RAG |

Podział ról wynika z mocnych i słabych stron każdej technologii:

- **liczby liczy model statystyczny**, bo LLM-y słabo radzą sobie z rachunkiem prawdopodobieństwa, a Jev nie zna piłki i nie da się go douczyć na danych meczowych,
- **Jev podejmuje decyzje na podstawie tekstu i kontekstu**: zwraca prawdopodobieństwa wybranych opcji, jest szybki i tani, a jego decyzje da się logować i porównywać,
- **LLM prowadzi rozmowę**: rozumie swobodne pytania, wybiera narzędzia i pisze wyjaśnienia.

## 1.3 Jak powstaje typ (w skrócie)

1. **Etap 1, typ wstępny** (rano w dniu meczu lub dzień wcześniej):
   - model liczy prawdopodobieństwa, uwzględniając przewidywany skład wynikający z newsów,
   - reguły value wybierają kandydatów,
   - Jev przepuszcza, wstrzymuje albo odrzuca kandydatów.
2. **Etap 2, potwierdzenie** (ok. 60 min przed meczem):
   - model liczy prawdopodobieństwa ponownie, na składzie przewidywanym z najnowszych newsów i opcjonalnych ręcznych potwierdzeń,
   - pobierane są aktualne kursy ok. 20 bukmacherów i ponownie sprawdzane reguły,
   - Jev ponownie ocenia typ, który zostaje **potwierdzony** albo **anulowany**.
3. Typy potwierdzone to **oficjalny wynik typera**: są rozliczane i wchodzą do statystyk skuteczności.

Szczegóły opisuje [07-typy-i-decyzje.md](07-typy-i-decyzje.md).

## 1.4 Cele

| # | Cel | Miernik |
|---|---|---|
| C1 | Model predykcyjny lepszy od prostych strategii i bliski rynkowi | log-loss / Brier niższe niż u baseline'ów; różnica do rynku (Pinnacle / Betfair Exchange) raportowana |
| **C2** | **Trafność typów > 50% i ROI > 0** | typy potwierdzone: backtest sezonu 2025/26 + test na żywo w sezonie 2026/27 |
| C3 | Typy biją kurs zamknięcia | średnie CLV > 0 |
| C4 | Newsy poprawnie klasyfikowane | Jev: F1 ≥ 0,8 dla kategorii wydarzeń, ≥ 0,85 dla nieobecności zawodników |
| C5 | Bramka decyzyjna Jev poprawia wynik | ablacja: typy z bramką vs bez bramki (ROI, trafność, log-loss) |
| C6 | Chatbot poprawnie korzysta z narzędzi | ≥ 90% poprawnie wybranych narzędzi na zestawie testowym |
| C7 | Odpowiedzi RAG wierne źródłom | RAGAS faithfulness ≥ 0,8 |
| C8 | Porównanie modeli | LLM: Gemini vs Llama vs Bielik; silnik decyzyjny: Jev vs LLM |
| C9 | Bezpieczne zachowanie | 100% typów z informacją o ryzyku; brak „pewniaków”; wykrywanie sygnałów problemowego grania |

## 1.5 Zakres

**W zakresie:**
- liga: **Ekstraklasa**,
- rynki: **1X2, podwójna szansa, gole (powyżej/poniżej), BTTS, handicap azjatycki**,
- kursy, na których podejmowane są decyzje: **najlepszy kurs spośród ok. 20 bukmacherów z The Odds API**. Punkt odniesienia: Pinnacle (na żywo i w historii) i Betfair Exchange (historia),
- dane wyłącznie z **darmowych źródeł bez obchodzenia zabezpieczeń**: football-data.co.uk, The Odds API, 90minut.pl, newsy. SofaScore, STS, Flashscore, strona ligi i płatne API-Football odpadły (rozdz. 3.2),
- **rożne i kartki są poza zakresem**, bo brak dla nich darmowych kursów i bieżących statystyk,
- newsy i wydarzenia: kontuzje, zawieszenia, powroty, zmiana trenera, sytuacja w klubie, terminarz i zmęczenie, motywacja i kontekst, warunki meczu,
- interfejsy: **Streamlit** (czat + panele) i **bot Telegram**,
- język: **polski**.

**Poza zakresem:**
- stawianie zakładów za użytkownika i integracja z kontem u bukmachera,
- zakłady na żywo (in-play),
- inne ligi i sporty (architektura pozwala je dodać),
- prawdziwe pieniądze w testach (wyłącznie wirtualne stawki).

## 1.6 Definicja sukcesu: dlaczego trafność i ROI razem

Sama trafność łatwo wprowadza w błąd:

- zdarzenie z kursem 1,25 bukmacher wycenia na ok. 80%; typer obstawiający same takie zdarzenia może mieć 75% trafności i **tracić** pieniądze,
- typer, który trafia 40% typów po kursie 3,00, **zarabia** (0,40 × 3,00 = 1,20).

Dlatego cel jest podwójny:

> **Trafność > 50% oraz ROI > 0 przy stałej stawce**, zmierzone na typach potwierdzonych, na danych, których model nie widział podczas treningu ani strojenia.

Przy trafności `h` typ jest opłacalny, gdy średni kurs przekracza `1/h`. Dla 55% to 1,82. Typer wybiera więc zdarzenia o kursach ok. **1,50–2,30**, w których model widzi przewagę nad rynkiem.

## 1.7 Skąd ma się wziąć przewaga nad bukmacherem

Rynek bukmacherski jest efektywny, więc przewaga może pochodzić tylko z kilku źródeł. Projekt świadomie korzysta z każdego z nich:

| Źródło przewagi | Mechanizm w projekcie | Rozdział |
|---|---|---|
| Lepsza miara siły drużyn niż tabela | pi-ratings (osobno u siebie i na wyjeździe), Elo, ważenie czasem | [4](04-model-predykcyjny.md) |
| Informacja o składach szybciej niż rynek | przewidywany skład z newsów (etap 1), faktyczny skład (etap 2), indeks siły składu | [4](04-model-predykcyjny.md), [5](05-newsy-i-wydarzenia.md) |
| Kontekst, którego nie ma w statystykach | zmęczenie, motywacja z tabeli, wydarzenia z newsów oceniane przez Jev | [5](05-newsy-i-wydarzenia.md), [6](06-silnik-decyzyjny-jev.md) |
| Dyscyplina decyzji | sztywne reguły value, brak typów „na siłę”, bramka decyzyjna Jev z prawem weta | [7](07-typy-i-decyzje.md) |
| Moment zawarcia zakładu | dwa etapy: wczesny kurs vs pełna informacja; pomiar CLV | [7](07-typy-i-decyzje.md), [10](10-ewaluacja.md) |
| Dobra kalibracja | kalibracja per rodzina rynków, mieszanie z rynkiem, wybór modeli po log-loss | [4](04-model-predykcyjny.md) |

**Porównywanie kursów u wielu bukmacherów** (*line shopping*) to zwykle duże źródło przewagi. The Odds API daje kursy ok. 20 bukmacherów naraz, więc każdy typ wyceniamy po najlepszym dostępnym kursie (z odrzuceniem kursów odstających, rozdz. 3.3.4). Przykład z pierwszego pobrania: najlepszy kurs na zwycięstwo Zagłębia wynosił 2,63, a u Pinnacle 2,51.

## 1.8 Realistyczne oczekiwania

- **Trafność > 50%** jest osiągalna przez dobór rynków, kursów i progu prawdopodobieństwa.
- **Trwale dodatni ROI** jest trudny. W małej próbie (dziesiątki do kilkuset typów) wynik może być dziełem przypadku, dlatego raportujemy przedziały ufności i CLV (rozdz. 10).
- **Negatywny wynik też jest wynikiem**: jeśli model nie pokona rynku, raport pokaże dlaczego, a chatbot nadal działa jako narzędzie analityczne.

## 1.9 Odpowiedzialna gra

- System nigdy nie używa słów „pewniak”, „pewna wygrana”, „gwarancja”.
- Każdy typ zawiera prawdopodobieństwo, kurs i informację o ryzyku.
- Stawki są tylko wirtualne; w ewaluacji stała stawka, bez progresji.
- Jev i reguły wykrywają sygnały problemowego grania („muszę się odegrać”), a wtedy chatbot nie podaje typów, tylko informację o pomocy.
- W interfejsie jest stała informacja: 18+, hazard może uzależniać.
