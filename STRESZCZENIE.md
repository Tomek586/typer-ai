# Typer AI: streszczenie projektu

*Skrót pełnej dokumentacji z folderu `docs/`, ok. 10 minut czytania.*

## Co robimy

Budujemy **chatbota po polsku, który analizuje mecze Ekstraklasy i proponuje typy bukmacherskie**. Rozmawia się z nim w przeglądarce (Streamlit) albo na Telegramie. Odpowiada na pytania o mecze, kursy i regulamin, sam proponuje typy i kupony, a do każdego dodaje uzasadnienie i informację o ryzyku.

**Cel liczbowy:** typy mają mieć **trafność powyżej 50%** i jednocześnie **dodatni zysk (ROI > 0)** przy stałej, wirtualnej stawce. Same 50% nie wystarczy, bo przy kursach 1,20–1,30 łatwo trafiać i mimo to tracić.

## Jak to działa: trzy warstwy

| Warstwa | Co robi | Czym |
|---|---|---|
| **Model statystyczny** | liczy prawdopodobieństwo każdego zdarzenia (1X2, podwójna szansa, gole, BTTS, handicap) | Dixon-Coles (model goli) + korekta o siłę drużyn (Elo, pi-ratings), skład, zmęczenie, motywację z tabeli + kalibracja |
| **Jev** (model decyzyjny TypeSafe AI) | podejmuje szybkie decyzje typu „tak/nie” lub „wybierz opcję”: ocenia newsy, przepuszcza lub blokuje typy, rozpoznaje intencję w czacie, pilnuje bezpieczeństwa | API Jev; zapasowo zwykły LLM z tymi samymi pytaniami |
| **Chatbot LLM** | rozmawia, wywołuje narzędzia (statystyki, kursy, predykcja, typy), wyszukuje w newsach i regulaminie (RAG), tłumaczy decyzje | Gemini (główny), Llama przez Groq, Bielik (porównanie) |

**Najważniejsza zasada:** liczby liczy tylko model statystyczny. LLM ich nie wymyśla, bo słabo radzi sobie z prawdopodobieństwem, a Jev ich nie zmienia, bo nie zna piłki. Jev może typ tylko **zablokować**, nigdy dodać.

## Jak powstaje typ

1. **Model** liczy prawdopodobieństwo `p` dla każdego zdarzenia.
2. Porównujemy je z **najlepszym kursem** spośród ok. 20 bukmacherów (The Odds API): `EV = p · kurs − 1` (oczekiwany zysk).
3. **Reguły:** typ jest kandydatem tylko, gdy `p ≥ 52%`, `EV ≥ 3%` i kurs mieści się w 1,50–2,30. Najwyżej jeden typ na mecz. Pierwsza reguła celuje w trafność > 50%, druga w zysk.
4. **Etap 1, typ wstępny** (dzień wcześniej lub rano): model korzysta ze składu **przewidywanego z newsów**, a Jev decyduje: wydaj / wstrzymaj / odrzuć.
5. **Etap 2, potwierdzenie** (ok. 60 min przed meczem): model liczy ponownie na **najświeższych newsach** (np. składach podanych przez kluby), opcjonalnie po **ręcznym potwierdzeniu** nieobecności, i na aktualnych kursach, a Jev decyduje: potwierdź / anuluj.
6. **Typy potwierdzone** to oficjalny wynik, z którego liczymy skuteczność.

Jeśli żaden mecz nie spełnia reguł, typer nie podaje typu. Nie szukamy typów na siłę.

## Rola newsów (mała, ale jest)

Newsy pobieramy co 2 godziny z RSS. Jev klasyfikuje każdy artykuł: której drużyny dotyczy, jakiego wydarzenia (kontuzja, zawieszenie, zmiana trenera, kryzys w klubie, zmęczenie, motywacja, pogoda), jaki ma wpływ i których zawodników dotyczy. Zawodników wybiera z listy kadry, więc nie wymyśli nazwiska. Newsy działają tylko na trzy sposoby:
- zmieniają **przewidywany skład** w etapie 1, np. „Ishak kontuzjowany” usuwa go ze składu,
- dają **kontekst bramce Jev**, która może typ wstrzymać lub odrzucić,
- są źródłem odpowiedzi w **czacie (RAG)**.

## Dane

- **football-data.co.uk:** wyniki Ekstraklasy od 2012/13 i kursy 1X2 (bez statystyk i innych rynków).
- **The Odds API (darmowy plan):** bieżące kursy ok. 20 bukmacherów (m.in. Pinnacle); bierzemy najlepszy kurs.
- **90minut.pl:** historyczne składy z minutami, strzelcy, kartki (za zgodą redakcji); z nich liczymy ważność zawodników.
- **Newsy (RSS)** i **regulaminy bukmacherów** do RAG.

Uwaga: SofaScore, STS, Flashscore i strona ligi blokują automaty, a API-Football jest płatne dla bieżącego sezonu, dlatego z nich zrezygnowaliśmy. Projekt kosztuje 0 zł. Brak oficjalnych składów przed meczem nadrabiamy NLP, czyli nieobecnościami wyciąganymi z newsów.

## Jak sprawdzimy, czy działa

- **Backtest:** model uczony na starszych sezonach i testowany raz na sezonie 2025/26, którego nie widział. Zysk liczymy tylko dla 1X2, bo dla innych rynków nie ma historycznych kursów.
- **Test na żywo:** od uruchomienia typy zapisują się codziennie przed meczem, bez możliwości zmiany. Zysk liczymy na wszystkich rynkach.
- **Porównanie z prostymi strategiami**, np. „zawsze gospodarz”, „zawsze faworyt”.
- **Ocena części NLP** (to jest oceniane na przedmiocie):
  - ok. 70 pytań testowych do chatbota: czy wybiera dobre narzędzia i czy odpowiedzi są wierne źródłom (RAGAS),
  - jakość klasyfikacji newsów na 150 ręcznie oznaczonych artykułach,
  - skuteczność routera i guardrails,
  - porównanie Gemini, Llamy i Bielika oraz Jev i zwykłego LLM.

## Podział pracy (propozycja)

| Osoba A: dane, model, typy | Osoba B: NLP, Jev, interfejsy |
|---|---|
| kolektory: football-data, The Odds API, 90minut.pl | pipeline newsów i klasyfikacja Jev |
| model statystyczny i kalibracja | silnik decyzyjny: bramka, router, guardrails |
| reguły typów, dwa etapy, kupony, rozliczanie | chatbot: agent, narzędzia, RAG, prompty |
| backtest i test na żywo | ocena NLP: newsy, router, chatbot, porównanie LLM |
| strony „Typy”, „Mecz”, „Wyniki” | czat w Streamlit, bot Telegram |

**Wspólnie w 1. tygodniu:** ustalamy formaty JSON (predykcja, typ, fakt z newsa, narzędzia czatu). Dzięki temu pracujemy równolegle, a osoba B do czasu gotowości modelu używa atrap.

## Kolejność prac (tygodnie od startu)

1. **Tydzień 1:** repozytorium, baza, **konto Jev**, test źródeł danych (zrobione), mail do 90minut.pl z prośbą o zgodę.
2. **Tydzień 2–3:** prosty model + reguły + codzienne zapisywanie typów. **Musi ruszyć szybko**, bo od połowy grudnia Ekstraklasa ma przerwę zimową, a potrzebujemy jak najwięcej meczów do testu na żywo.
3. **Tydzień 3–5:** newsy + Jev, pełny model, bramka Jev.
4. **Tydzień 4–7:** chatbot, interfejsy, ocena NLP.
5. **Tydzień 7–8:** raport i prezentacja z demo na żywo.

## Do sprawdzenia od razu

- czy da się założyć konto Jev (console.typesafe.ai) i jak radzi sobie z polskimi newsami,
- czy redakcja 90minut.pl zgadza się na pobieranie składów,
- czy Bielik jest dostępny przez API.

## Uczciwie o ryzyku

Pobicie bukmachera jest trudne. Trafność powyżej 50% jest realna, ale **trwały zysk już nie musi wyjść**. Jeśli nie wyjdzie, to też jest wynik: raport pokaże dlaczego, a chatbot i tak działa jako narzędzie analityczne. Zaliczenie zależy przede wszystkim od części NLP, a nie od tego, czy zarobimy.

---

**Więcej szczegółów:** `README.md` i folder `docs/`. Na start warto przeczytać rozdziały 1, 7 i 11, a potem rozdziały ze swojej części.
