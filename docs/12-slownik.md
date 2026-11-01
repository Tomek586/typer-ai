# 12. Słownik pojęć

| Pojęcie | Znaczenie |
|---|---|
| **AH (handicap azjatycki)** | zakład z wirtualną przewagą bramkową dla jednej drużyny. Linie całkowite dają zwrot przy remisie po handicapie, a ćwiartkowe dzielą stawkę na dwie linie |
| **AKO / kupon** | zakład łączący kilka zdarzeń. Wygrywa tylko wtedy, gdy trafione są wszystkie; kursy się mnożą |
| **Backtest** | symulacja działania strategii na danych historycznych |
| **Bramka decyzyjna** | mechanizm Jev, który przepuszcza, wstrzymuje lub odrzuca typ wybrany przez reguły value (rozdz. 6.4.2) |
| **BTTS** | „both teams to score”, czyli obie drużyny strzelą gola |
| **Brier score** | średni kwadrat różnicy między prawdopodobieństwem a wynikiem (0/1). Im niższy, tym lepiej |
| **Choice / Score / Noul** | typy pytań w Jev: wybór opcji / ocena na skali / tak-nie |
| **CLV (closing line value)** | o ile kurs, po którym wydano typ, był lepszy od kursu zamknięcia. Dodatnie CLV w dłuższym okresie to silny sygnał realnej przewagi |
| **Dixon-Coles** | model liczby goli oparty na rozkładzie Poissona, z poprawką dla niskich wyników (0:0, 1:0, 0:1, 1:1) |
| **Data leakage (wyciek danych)** | użycie informacji niedostępnej w chwili decyzji. Zawyża wyniki backtestu |
| **ECE** | expected calibration error, czyli średnia rozbieżność między przewidywanym prawdopodobieństwem a faktyczną częstością |
| **Elo** | ranking siły drużyn aktualizowany po każdym meczu |
| **EV (wartość oczekiwana)** | `p · kurs − 1`, czyli średni zysk na jednostkę stawki. Dodatnie EV oznacza zakład opłacalny w długim okresie |
| **Function calling** | mechanizm, w którym LLM zwraca nazwę narzędzia i argumenty zamiast tekstu, a program je wykonuje |
| **GLM** | uogólniony model liniowy (tu: regresja Poissona) |
| **Jev** | model decyzyjny „System One” firmy TypeSafe AI. Zwraca typowane decyzje z prawdopodobieństwami zamiast tekstu |
| **Kalibracja** | zgodność prawdopodobieństw z rzeczywistością: zdarzenia z p = 60% powinny zachodzić w ok. 60% przypadków |
| **Kelly (kryterium)** | wzór na optymalną wielkość stawki przy znanej przewadze. W projekcie ¼ Kelly'ego, wyłącznie informacyjnie |
| **Kurs zamknięcia** | ostatni kurs przed rozpoczęciem meczu, zwykle najbardziej „trafny” |
| **λ (lambda)** | oczekiwana liczba goli drużyny w meczu |
| **Log-loss** | `−log` prawdopodobieństwa, które model przypisał zdarzeniu, które faktycznie zaszło. Mocno karze pewne pomyłki; główne kryterium wyboru modelu |
| **Marża** | przewaga bukmachera: `Σ(1/kurs) − 1` na danym rynku |
| **Metoda Shina** | sposób usuwania marży uwzględniający, że bukmacher bardziej zaniża kursy na outsiderów |
| **Mieszanie z rynkiem** | łączenie prawdopodobieństw modelu z prawdopodobieństwami z kursów (rozdz. 4.9) |
| **Pi-ratings** | system ratingów z osobnymi wartościami dla gry u siebie i na wyjeździe (Constantinou i Fenton, 2013) |
| **Platt (kalibracja)** | korekta prawdopodobieństw funkcją `σ(a·logit(p) + b)` |
| **RAG** | retrieval-augmented generation: LLM odpowiada na podstawie wyszukanych fragmentów dokumentów |
| **RAGAS** | biblioteka do oceny systemów RAG (faithfulness, answer relevancy, context precision) |
| **Reranking** | ponowne uszeregowanie znalezionych fragmentów dokładniejszym modelem (cross-encoderem) |
| **ROI** | zwrot z inwestycji: `zysk / suma stawek` |
| **RPS** | ranked probability score, metryka dla wyników uporządkowanych (1, X, 2) |
| **Skład referencyjny** | 11 zawodników z największą liczbą minut w ostatnich 10 meczach |
| **Trafność** | odsetek wygranych typów (z połowami przy handicapie, bez zwrotów) |
| **Typ wstępny / potwierdzony** | typ z etapu 1 (przed składami) / z etapu 2 (po składach), rozdz. 7.4 |
| **Value** | sytuacja, w której prawdopodobieństwo modelu jest wyższe niż wynikające z kursu, czyli EV > 0 |
| **Walk-forward** | backtest, w którym model jest ponownie dopasowywany w miarę upływu czasu, tylko na danych z przeszłości |
| **xG (expected goals)** | oczekiwane gole: suma prawdopodobieństw zdobycia gola z oddanych strzałów. W projekcie niedostępne w darmowych źródłach dla Ekstraklasy |
