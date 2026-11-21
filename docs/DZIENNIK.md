# Dziennik decyzji

Wspólna pamięć projektu dla wszystkich osób i sesji Claude. Najnowsze wpisy na górze. Każdy wpis: data, decyzja lub ustalenie, krótkie uzasadnienie. Szczegóły są w dokumentacji (`docs/`) i w historii commitów.

## Otwarte sprawy

- [ ] Klucz Jev (TypeSafe AI): konto nie jest jeszcze założone; bez niego część decyzyjna działa na planie B (LLM).
- [ ] Model kartek: sędzia, drużyny, derby jako cecha do sprawdzenia; wynik z kursem minimalnym.
- [ ] Model v2: krok 1 i diagnoza składu zrobione 21.11 (wpisy niżej). Ratingi Elo/pi i motywacja sprawdzone 21.11 (bez zysku); stabilny zysk daje tylko forma. Do decyzji: czy wdrożyć v1 + forma w trakcie testu na żywo. Niesprawdzone: derby (brak listy par w repozytorium), puchary (brak terminarza pucharów); każda cecha oceniana „każdy sezon po kolei” (9 sezonów) i zostaje tylko, jeśli poprawia wynik.
- [ ] Regulaminy serwisów newsowych (Sportowe Fakty/WP, Interia, TVP Sport, Sport.pl/Agora, Weszło): sprawdzić zastrzeżenia eksploracji tekstu i danych (TDM); serwis z zakazem usuwamy z `config.NEWS_SOURCES`.
- [ ] Newsy: pobieranie, fakty i ręczne potwierdzenia działają od 21.11; zostaje przewidywany skład z faktów, kontekst dla bramki, RAG, zbiór 150 artykułów do oceny.
- [ ] RAG, ocena NLP; aplikacja: strony „Mecz”, „Decyzje Jev”, „System” (Czat, Typy, Wyniki, Newsy gotowe 21.11).
- [ ] Jakość odpowiedzi modeli „lite” vs `3.5-flash` (od 21.11 domyślnie „lite”): porównać na zbiorze pytań testowych przy ewaluacji NLP.

---

## 2026-11-21

- **Twitter/X jako źródło – sprawdzone, decyzja: ręczne potwierdzenia.**
  - **Bluesky:** API darmowe i bez logowania (czytanie wpisów wybranych kont), ale polskie konta piłkarskie są martwe – żadne z 13 sprawdzonych (Ekstraklasa, kluby, Meczyki, Przegląd Sportowy, dziennikarze) nie pisało w ostatnich 14 dniach; konta klubów puste. Strony 18 klubów nie mają kanałów RSS.
  - **API X:** od 6.02.2026 tylko płatność za użycie, 0,005 USD za odczytany wpis, bez darmowego planu (20 USD kredytu na start); 10 kont ≈ 10–25 USD/mies. Scrapowanie X bez API łamie regulamin – odpada.
  - **Decyzja (Tomasz):** ręczne potwierdzenia w aplikacji zamiast płatnego API: formularz na stronie „Newsy” (drużyna, kategoria, zawodnik z kadry, status, pewność, wpływ, opis ze źródłem, link), fakty `source = manual` w tej samej tabeli i z tymi samymi zasadami scalania; możliwość wycofania pomyłki. Widoczne w czacie (`newsy`, z typem źródła) i na stronie „Newsy”. Nowe kolumny `news_fact.note`, `source_url`, `created_at` (migracja); odczyt działa też na starszej kopii bazy bez tych kolumn.
- **Zespół:** Tomasz Dziedzic, Adam Nowak (README, slajd tytułowy prezentacji PoC, notebook). **Komputer domowy:** usypianie przy zasilaniu z sieci wyłączone (sprawdzone `powercfg`: 0 = nigdy).
- **Newsy w czacie i aplikacji:** narzędzie czatu `newsy` (aktywne fakty z pewnością i źródłem + tytuły ostatnich artykułów), fakty obu drużyn w wyniku `analiza_meczu` (pole `newsy`), reguła 14 w prompcie (podawaj pewność i źródło; newsy nie zmieniają prawdopodobieństw ani typów), strona aplikacji „Newsy” i sekcja 3.5 w notebooku. Sprawdzone: pytanie o Śląsk → narzędzie `newsy`, odpowiedź w 2,1 s ze źródłem. Krótkie nazwy drużyn („Lech”, „Pogoń”, „Górnik”, „Korona”, „Motor”, „Piast”, „Płock”, „GieKSa” i in.) dodane jako aliasy w `teams.py` (21.11); „Lech” i „Lechia” rozróżniane, „Górnik” = Zabrze, „Wisła” = Kraków.
- **Pipeline newsów (docs/05), pierwsza wersja.**
  - **Źródła:** kanały RSS Sportowych Faktów (Ekstraklasa), Interii (Ekstraklasa), TVP Sport, Sport.pl i Weszło (`config.NEWS_SOURCES`). Sprawdzone 21.11: robots.txt żadnego z nich nie blokuje zwykłych botów; Meczyki, Onet (Ekstraklasa) i strony klubów nie mają działającego RSS.
  - **Decyzja: pobieramy pełne artykuły** (trafilatura), ale tylko te, w których tytuł lub zajawka wspomina drużynę Ekstraklasy (wzorce odmiany nazw, np. „Legii”, „Lechem”, z wykluczeniem Lechii). Przed każdym pobraniem sprawdzany jest robots.txt, między zapytaniami do serwisu 2 s przerwy. Regulaminy serwisów (zastrzeżenia TDM) sprawdza zespół – otwarta sprawa wyżej.
  - **Klasyfikacja:** `typerai/decision/engine.py` (`DecisionEngine`, `LLMEngine` na Gemini jako plan B dla Jev, każde zapytanie w `DECISION_LOG`) i `typerai/news/extract.py`: pytania i progi z docs/05 i docs/06 w jednym zapytaniu na artykuł, najwyżej 3 drużyny i ich kadry (zawodnicy tylko z listy). Fakty z ważnością według kategorii, nowszy fakt zastępuje starszy, chyba że starszy jest pewniejszy i sprzeczny; duplikat podnosi pewność.
  - **Próba 21.11:** z 115 pozycji RSS zapisano 17 artykułów (ok. 40 s); 3 sklasyfikowane poprawnie (zmiana trenera Śląska i Cracovii, zapowiedź transmisji bez faktu), ok. 15 s na zapytanie. Gemini zwraca prawdopodobieństwa prawie zawsze 0 lub 1, więc progi pewności działają jak zwykłe decyzje – do porównania z Jev.
  - **Harmonogram:** zadanie `news` o 8, 10, …, 22, najwyżej 10 artykułów do LLM na przebieg (limit chroni darmowe zapytania, z których korzysta też czat).
- **Motywacja z tabeli (model v2) bez stabilnego zysku.** Tabela przed meczem z formatem sezonów (ESA-37 z połowieniem punktów po 30. kolejce, 30 kolejek w 2020/21, 34 od 2021/22; spadki 2/3/1/3; 3 miejsca pucharowe; podział na grupy przybliżony jedną tabelą). Cechy w ostatnich 12 kolejkach: presja spadkowa, presja pucharowa, „nic do grania” (ostatnie 5 kolejek). Ocena „każdy sezon po kolei”: cała grupa +0,34 (t = 0,5, lepiej w 6/9), pojedynczo od −0,22 do +0,61 (najlepsza: rywal nie ma o co grać, t = 1,1). Drużyny w strefie spadkowej strzelają ok. 10% ponad λ DC, ale to tylko 309 wierszy i efekt nie przenosi się między sezonami. Cechy nie wchodzą do v2.
- **Podsumowanie modelu v2 po 21.11:** z cech z darmowych danych stabilnie pomaga tylko forma (log-loss 1X2 po zmieszaniu z rynkiem: 1,0592 → 1,0587 i 1,0220 → 1,0214). Skład oficjalny pomaga trochę, ale przed meczem go nie znamy. Ratingi, odpoczynek, skład z poprzedniego meczu i motywacja – bez zysku. Rynek (Pinnacle) pozostaje lepszy od modelu, więc przewaga z samego modelu jest mało prawdopodobna; to uczciwy wynik badawczy do raportu (tabela ablacji w `evaluation/reports/validate_v2.json`).
- **Ratingi Elo i pi-ratings (model v2) nic nie dodają do Dixona-Colesa.** Zaimplementowane według docs/04, 4.2 (`typerai/model/ratings/`), siatka ze specyfikacji: Elo K ∈ {15, 20, 25, 30} × HFA ∈ {40, 60, 80}, pi λ ∈ {0,025; 0,035; 0,045} × γ ∈ {0,5; 0,7; 0,9}. W ocenie „każdy sezon po kolei” wszystkie ustawienia dają ≈ 0 (od −0,12 do +0,03 na 1000 wierszy, lepiej w 4–5 z 9 sezonów). Same ratingi działają poprawnie – przewidują różnicę goli tak jak DC (korelacja 0,23–0,25) – ale są z nim silnie skorelowane (0,81 Elo, 0,87 pi), więc nie wnoszą nowej informacji. Na samym 2023/24 wyglądały na zysk (1,0627 → 1,0600), co znowu pokazuje, że jeden sezon walidacyjny myli. Parametry zostają domyślne (K = 20, HFA = 60, λ = 0,035, γ = 0,7); cechy nie wchodzą do v2.
- **Diagnoza cech składu (model v2):** ocena na dwóch sezonach walidacyjnych była za słaba – efekt składu w 2024/25 miał odwrotny znak niż w 7 z 9 sezonów. Dodano ocenę „każdy sezon po kolei” (leave-one-season-out, 9 sezonów 2016/17–2024/25, zmiana log-wiarygodności liczby goli względem Dixona-Colesa).
  - **Skład oficjalny ma prawdziwy, ale mały efekt:** udział podstawowych zawodników i ich wkład w atak dają +1,1 na 1000 wierszy (lepiej w 7/9 sezonach); forma +2,0 (7/9); forma + skład oficjalny +3,2 (t = 2,5). To nie błąd w kodzie: wynik prawie się nie zmienia przy oknie 5/10/20 meczów i przy ważeniu świeżych meczów (półokres 3 i 6).
  - **Odrzucone (bez sygnału):** skład z poprzedniego meczu, różnica dni odpoczynku, bramkarz rezerwowy rywala (flaga w 24% meczów, bo po zmianie bramkarza okno długo uznaje starego), udział podstawowych u rywala. Wcześniejszy „realny v2” 1,0575 w 2023/24 był szczęściem: skład z poprzedniego meczu nie ma sygnału.
  - **Wnioski:** realny v2 na dziś = v1 + forma (1X2: 2023/24 1,0627 → 1,0591, 2024/25 1,0414 → 1,0400). Informacja o składzie dałaby niewiele nawet przy pełnej wiedzy, więc newsy o kontuzjach mają małą wartość dla liczb modelu – ich rola to raczej bramka typów i czat. Przewagi szukamy w ratingach i motywacji.
- **Model v2, krok 1 (`evaluation/validate_v2.py`):** λ-GLM z offsetem log λ Dixona-Colesa, uczony na sezonach 2016/17 – S−1 (λ DC spoza próby, walk-forward co tydzień). Cechy liczone tylko z wcześniejszych meczów (`typerai/model/features.py`): forma goli (półokres 8 meczów), różnica dni odpoczynku (tylko liga – pucharów nie mamy w bazie), siła składu w dwóch wariantach: skład z poprzedniego meczu (dostępny w etapie 1) i skład oficjalny (górna granica, znany tuż przed meczem).
  - Log-loss 1X2, v1 → forma + odpoczynek + skład poprzedni: 2023/24 1,0627 → 1,0575 (rynek 1,0613), 2024/25 1,0414 → 1,0404 (rynek 1,0204); po diagnozie (wpis wyżej) zysk przypisany formie. Forma ma ujemny współczynnik (powrót do średniej po serii goli).
  - Skład oficjalny w tej ocenie nie pomógł (1,0649 i 1,0421), choć drużyny z najwyższym `reg_off` strzelały 18% ponad λ DC, a z najniższym 2% – wyjaśnione w diagnozie wyżej.
  - Alpha wybierana na sezonie walidacyjnym (zgodnie z docs/04, 4.10) – wyniki są więc lekko optymistyczne. Sezon testowy 2025/26 nieużyty. v2 **nie** jest jeszcze w produkcji.
- **Nowa kolejność modeli Gemini i limit 30 s.** Pomiar 21.11 (jedno krótkie zapytanie na model): `3.5-flash` 503 po 36 s (wcześniej 504 po 60 s), `3.7/3.6/3.8-flash` 503 po 2–8 s, działały tylko `3.5-flash-lite` (0,5 s) i `3.1-flash-lite` (2,9 s). Kolejność: `3.5-flash-lite` → `3.1-flash-lite` → `3.5-flash` → większe modele; limit czasu 60 → 30 s (`GEMINI_TIMEOUT_S`). Analiza meczu w czacie: 3,3 s zamiast ok. 68 s. Modele „lite” poprawnie wywołują narzędzia, a zmyślone liczby wyłapuje kontrola G5; jakość porównamy w ewaluacji.
- **Aplikacja Streamlit, pierwsza wersja:** Czat (z panelem „Jak powstała odpowiedź”), Typy (z tabelą „dlaczego jest albo nie ma typu”), Wyniki. Baza otwierana tylko do odczytu (`typerai/report.py`), więc aplikacja działa też na kopii na laptopie. Zależności w osobnych grupach `[app]` i `[notebook]`, żeby harmonogram ich nie wymagał.
- **Notebook na zajęcia 22.11** (`notebooks/postep_po_PoC.ipynb`): walidacja walk-forward liczona na żywo (ok. 45 s) zamiast „epok”, bo model v1 nie ma treningu iteracyjnego; symulacja reguł odtwarza liczby z analizy progu EV (8 → 22,5 typu/sezon). Zapisany z wynikami, żeby dało się go pokazać bez bazy.
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
