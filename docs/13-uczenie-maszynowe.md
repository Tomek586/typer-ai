# 13. Uczenie maszynowe

Projekt zalicza dwa przedmioty: *Przetwarzanie języka naturalnego i modele generatywne* oraz *Uczenie maszynowe* (zgoda prowadzącego ML, 22.11.2026; rodzaj algorytmów dowolny). Ten rozdział zbiera elementy uczenia maszynowego: te, które już są w kodzie, i te zaplanowane. Wybraliśmy algorytmy, które rozwiązują konkretne problemy aplikacji, a nie algorytmy dla samego ich użycia.

## 13.1 Zasady wspólne dla wszystkich modeli

- **Podział czasowy, bez wycieku informacji z przyszłości.** Cechy liczone są wyłącznie z meczów i informacji sprzed chwili predykcji (docs/03, 3.7).
- **Trzy zbiory:** trening (starsze sezony), walidacja (2023/24, 2024/25: dobór hiperparametrów), test (2025/26: uruchamiany raz, na końcu).
- **Walidacja „każdy sezon po kolei”** (leave-one-season-out, 9 sezonów 2016/17–2024/25) do oceny cech: jeden sezon walidacyjny okazał się mylący (dziennik, 21.11).
- **Punkt odniesienia:** prawdopodobieństwa z kursów Pinnacle bez marży. Model, który ich nie pobija, opisujemy uczciwie jako wynik negatywny.
- **Metryki:** log-loss i Brier (jakość prawdopodobieństw), dla klasyfikacji F1 i macierz pomyłek, dla regresji liczby zdarzeń log-wiarygodność. Modele wybieramy po log-loss, nie po zysku (zysk na małej próbce prowadzi do przeuczenia).

## 13.2 Elementy już zaimplementowane

| Element | Metoda | Uczenie | Kod | Status |
|---|---|---|---|---|
| Model goli Dixona-Colesa | model probabilistyczny (Poisson z poprawką dla niskich wyników) | największa wiarygodność z wagami czasowymi i regularyzacją L2 (L-BFGS-B) | `typerai/model/dixon_coles.py` | produkcja |
| Dobór hiperparametrów | przeszukiwanie siatki | ξ (ważenie czasem), w (waga mieszania z rynkiem), wybór po log-loss walk-forward | `evaluation/validate_v1.py` | zrobione |
| Łączenie z rynkiem | łączenie log-liniowe prognoz (prosty ensembling) | waga w = 0,15 z walidacji | `typerai/betting/value.py` | produkcja |
| λ-GLM (model v2) | regresja Poissona z offsetem λ Dixona-Colesa | L2, standaryzacja cech, alpha z walidacji | `typerai/model/glm.py` | badania |
| Inżynieria cech | forma goli, siła składu z minut i goli, odpoczynek, motywacja z tabeli | – | `typerai/model/features.py` | badania |
| Ratingi Elo i pi-ratings | algorytmy uczenia online (aktualizacja po każdym meczu) | parametry z siatki | `typerai/model/ratings/` | badania |
| Ablacja cech | leave-one-season-out, 9 sezonów | – | `evaluation/validate_v2.py` | zrobione: stabilnie pomaga tylko forma |
| Klasyfikacja newsów | klasyfikacja zero-shot przez LLM (bez uczenia) | – | `typerai/news/extract.py` | produkcja; punkt odniesienia dla 13.3.1 |

## 13.3 Elementy zaplanowane

Kolejność według korzyści dla aplikacji. Każdy element ma osobny zbiór danych, punkt odniesienia i kryterium sukcesu.

### 13.3.1 Własny klasyfikator newsów (ML + NLP)

- **Problem aplikacji:** każdy artykuł to dziś zapytanie do Gemini (ok. 15 s). Czat i newsy dzielą darmowy limit ok. 20 zapytań dziennie na model, a LLM zwraca prawdopodobieństwa prawie zawsze 0 albo 1, więc progi pewności niewiele dają.
- **Zadanie:** kategoria wydarzenia (kontuzja, zawieszenie, powrót, zmiana trenera, kryzys, terminarz, motywacja, warunki, transfer, inne) oraz „czy artykuł dotyczy drużyny X”.
- **Metody do porównania:**
  1. TF-IDF (słowa i n-gramy znakowe, odporne na polską odmianę) + regresja logistyczna,
  2. embeddingi polskiego modelu zdaniowego (np. `sdadas/mmlw-roberta-base`, na CPU) + regresja logistyczna,
  3. punkt odniesienia: obecna klasyfikacja zero-shot przez Gemini.
- **Dane:** artykuły zbierane przez pipeline newsów od 21.11. Etykiety wstępnie z Gemini (destylacja wiedzy), poprawiane ręcznie; ręcznie sprawdzony zbiór testowy ok. 150 artykułów, ten sam co w ocenie NLP (docs/10, B.1).
- **Ocena:** macro-F1 i macierz pomyłek na zbiorze testowym, kalibracja prawdopodobieństw, czas na artykuł.
- **Wdrożenie:** klasyfikator decyduje sam, gdy jest pewny, a trudne przypadki (niska pewność) idą do LLM. Zapytań do Gemini ubywa, a czat ma więcej limitu.

### 13.3.2 Model kartek

- **Problem aplikacji:** brak rynku kartek; użytkownik dostaje kurs minimalny, porównywany z ofertą własnego bukmachera.
- **Metoda:** regresja ujemna dwumianowa (liczba kartek ma większą wariancję niż w rozkładzie Poissona) dla każdej drużyny osobno; cechy: forma kartkowa drużyny i rywala, **sędzia** (średnia kartek z przyciąganiem do średniej ligi przy małej liczbie meczów), derby, różnica sił. Rozkład sumy kartek meczu jako splot rozkładów obu drużyn.
- **Dane:** 3359 meczów z kartkami i sędziami z 90minut.pl (2015/16–2026/27).
- **Punkt odniesienia:** średnia ligi oraz rozkład Poissona bez cech.
- **Ocena:** log-wiarygodność i kalibracja rynków „powyżej/poniżej X,5 kartki”, walidacja „każdy sezon po kolei”. Hipoteza o derbach jest już częściowo sprawdzona: 109 derbów nie ma więcej kartek (dziennik, 8.11), więc cecha zostanie tylko, jeśli poprawi wynik.

### 13.3.3 Gradient boosting jako korektor rynku (1X2)

- **Problem aplikacji:** model statystyczny nie pokonuje rynku, a przewaga z samego wyboru kursu okazała się ujemna (dziennik, 21.11). Jedyną drogą do uzasadnionych typów jest wykrycie **systematycznych błędów rynku** (np. niedoszacowanych remisów lub outsiderów w Ekstraklasie).
- **Metody do porównania:** wielomianowa regresja logistyczna, gradient boosting (HistGradientBoosting lub LightGBM), punkt odniesienia: rynek (Pinnacle bez marży) i obecna mieszanka.
- **Cechy:** prawdopodobieństwa rynku, prawdopodobieństwa Dixona-Colesa, forma, różnica ratingów, faza sezonu.
- **Dane:** ok. 3900 meczów z kursami zamknięcia Pinnacle (2012/13–2025/26).
- **Ocena:** log-loss „każdy sezon po kolei” i symulacja reguł typów; z góry zakładamy, że wynik może być negatywny. Wtedy w raporcie pokażemy, że rynek Ekstraklasy jest efektywny.

### 13.3.4 Kalibracja prawdopodobieństw

- **Problem aplikacji:** EV i reguły typów zależą od tego, czy „60%” rzeczywiście znaczy 60%.
- **Metody:** skalowanie Platta i regresja izotoniczna dla każdej rodziny rynków (docs/04, 4.8).
- **Ocena:** ECE i wykres niezawodności przed i po kalibracji.
- **Uwaga:** robimy ją razem z 13.3.3, na tych samych danych i podziale.

## 13.4 Co pokażemy na zaliczeniu ML

1. Pipeline danych i podział czasowy (dlaczego nie losowy).
2. Model Dixona-Colesa i dobór hiperparametrów (walk-forward).
3. Ablacja cech v2 („każdy sezon po kolei”), w tym wyniki negatywne (ratingi, motywacja).
4. Porównanie algorytmów: klasyfikator newsów (TF-IDF vs embeddingi vs LLM), korektor rynku (regresja logistyczna vs gradient boosting vs rynek), model kartek vs punkty odniesienia.
5. Kalibracja i jej wpływ na typy.

Wyniki każdego elementu trafiają do `evaluation/reports/` i do dziennika (`docs/DZIENNIK.md`).
