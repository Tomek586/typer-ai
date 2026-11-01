# 2. Architektura

## 2.1 Komponenty

```mermaid
flowchart TB
    subgraph UI[Interfejsy]
        ST[Streamlit]
        TG[Bot Telegram]
    end

    subgraph CHAT[Chatbot]
        ROUTER[Router intencji<br/>Jev Choice]
        AGENT[Agent LLM<br/>function calling]
        GUARD[Guardrails<br/>reguły + Jev Noul]
        RAG[RAG<br/>ChromaDB + mmlw]
    end

    subgraph DEC[Silnik decyzyjny]
        DE[DecisionEngine<br/>Jev / LLM fallback]
        GATE[Bramka typu]
        NEWSC[Klasyfikator newsów]
    end

    subgraph CORE[Rdzeń analityczny]
        RAT[Ratingi<br/>Elo, pi, xG]
        DC[Dixon-Coles + λ-GLM]
        STATM[Modele NB<br/>rożne, kartki]
        CAL[Kalibracja<br/>+ mieszanie z rynkiem]
        PICKS[Reguły value<br/>cykl życia typu]
        COUP[Kupony]
        TRACK[Rejestr i rozliczanie]
    end

    subgraph DATA[Dane]
        DB[(SQLite)]
        VDB[(ChromaDB)]
        FD[football-data.co.uk]
        SS[SofaScore]
        STS[STS]
        NEWS[Newsy RSS / strony<br/>regulaminy PDF]
    end

    ST & TG --> GUARD --> ROUTER --> AGENT
    AGENT --> RAG --> VDB
    AGENT -->|narzędzia| CORE
    GUARD & ROUTER & GATE & NEWSC --> DE
    FD & SS & STS --> DB
    NEWS --> NEWSC --> DB
    NEWS --> VDB
    DB --> RAT --> DC --> CAL
    DB --> STATM --> CAL
    CAL --> PICKS --> GATE --> TRACK
    PICKS --> COUP
    TRACK --> DB
```

| Komponent | Moduł | Opis | Rozdział |
|---|---|---|---|
| Kolektory danych | `typerai/collectors/` | import i scraping: football-data, SofaScore, STS, newsy | [3](03-dane.md) |
| Model predykcyjny | `typerai/model/` | ratingi, Dixon-Coles, λ-GLM, NB, kalibracja, rynki | [4](04-model-predykcyjny.md) |
| Pipeline newsów | `typerai/news/` | zbieranie, deduplikacja, klasyfikacja Jev, fakty, przewidywany skład | [5](05-newsy-i-wydarzenia.md) |
| Silnik decyzyjny | `typerai/decision/` | wspólny interfejs dla Jev i LLM, definicje pytań, polityki decyzji, log | [6](06-silnik-decyzyjny-jev.md) |
| Typy i decyzje | `typerai/betting/` | marża, EV, reguły, dwuetapowy cykl życia typu, stawki, kupony, rozliczanie | [7](07-typy-i-decyzje.md) |
| Chatbot | `typerai/chat/` | router, agent, narzędzia, RAG, guardrails, prompty | [8](08-chatbot-llm.md) |
| Interfejsy | `typerai/apps/` | Streamlit, Telegram | [9](09-interfejsy.md) |
| Ewaluacja | `evaluation/` | backtest, test na żywo, ocena NLP i Jev | [10](10-ewaluacja.md) |

## 2.2 Przepływ: dzień meczowy

```mermaid
sequenceDiagram
    participant SCH as Harmonogram
    participant COL as Kolektory
    participant NEWS as Pipeline newsów
    participant M as Model
    participant R as Reguły value
    participant J as Jev (bramka)
    participant DB as Rejestr typów
    participant TG as Telegram

    Note over SCH: D-1 18:00 / D 09:00 – ETAP 1
    SCH->>COL: kursy STS + terminarz
    SCH->>NEWS: nowe newsy → fakty → przewidywane składy
    SCH->>M: predykcja (przewidywane składy)
    M->>R: prawdopodobieństwa wszystkich rynków
    R->>J: kandydaci (EV, p, kurs, kontekst, newsy)
    J-->>DB: WSTĘPNY / WSTRZYMANY / ODRZUCONY
    DB-->>TG: typy wstępne

    Note over SCH: T-60 min (po składach) – ETAP 2
    SCH->>COL: oficjalne składy + kursy STS
    SCH->>M: predykcja (faktyczne składy)
    M->>R: reguły na nowych kursach
    R->>J: typ + zmiany od etapu 1
    J-->>DB: POTWIERDZONY / ANULOWANY
    DB-->>TG: potwierdzenia

    Note over SCH: po meczu
    SCH->>COL: wynik + statystyki
    COL->>DB: rozliczenie typów, aktualizacja ratingów
```

## 2.3 Przepływ: pytanie w czacie

```mermaid
sequenceDiagram
    actor U as Użytkownik
    participant G as Guardrails (wejście)
    participant RT as Router Jev
    participant A as Agent LLM
    participant T as Narzędzia
    participant GO as Guardrails (wyjście)

    U->>G: „Co sądzisz o Lech – Legia?”
    G->>G: Jev Noul: sygnały problemowego grania?
    G->>RT: OK
    RT->>RT: Jev Choice: intencja = analiza_meczu (conf 0,82)
    RT->>A: wiadomość + zawężony zestaw narzędzi
    A->>T: znajdz_mecz → predykcja → kursy → newsy_druzyny
    T-->>A: wyniki (JSON)
    A->>GO: szkic odpowiedzi
    GO->>GO: reguły + Jev Noul: obietnica wygranej? brak ryzyka?
    GO-->>U: odpowiedź z liczbami, źródłami, ryzykiem
```

## 2.4 Harmonogram zadań

| Kiedy | Zadanie | Co robi |
|---|---|---|
| co 2 h (08:00–22:00) | `collect_news` | RSS → nowe artykuły → deduplikacja → klasyfikacja Jev → fakty → indeks RAG |
| codziennie 06:00 | `collect_fixtures` | terminarz na 10 dni (SofaScore), sędziowie, prognoza pogody dla meczów w ciągu 48 h |
| co 6 h | `collect_odds` | snapshot kursów STS i SofaScore dla meczów w ciągu 7 dni |
| D-1 18:00 i D 09:00 | `stage1_picks` | etap 1 dla meczów w ciągu 36 h, które nie mają jeszcze decyzji etapu 1 |
| co 10 min w dni meczowe | `stage2_watch` | dla meczów, które zaczynają się za 75–45 min: składy → etap 2 |
| T-5 min | `closing_odds` | ostatni snapshot kursów (do metryki CLV) |
| codziennie 23:30 | `settle` | wyniki i statystyki, rozliczenie typów, aktualizacja ratingów |
| poniedziałek 04:00 | `retrain` | ponowne dopasowanie modeli i kalibracji na pełnej historii |

Harmonogram obsługuje APScheduler w osobnym procesie (`python -m typerai.scheduler`). Każde uruchomienie zadania zapisuje wpis w tabeli `JOB_RUN` (start, koniec, status, błąd).

## 2.5 Struktura repozytorium

```
typer-ai/
├── README.md
├── docs/                          # ta dokumentacja
├── pyproject.toml
├── .env.example                   # nazwy zmiennych, bez wartości
├── data/
│   ├── raw/                       # surowe odpowiedzi źródeł (do ponownego przetworzenia)
│   ├── typer.db                   # SQLite
│   └── chroma/                    # baza wektorowa
├── typerai/
│   ├── config.py                  # ustawienia + progi (jeden plik, wersjonowany)
│   ├── db.py                      # schemat, migracje, dostęp
│   ├── markets.py                 # kody rynków i ich rozliczanie
│   ├── collectors/
│   │   ├── football_data.py
│   │   ├── sofascore.py           # mecze, statystyki, xG, składy, zawodnicy, sędziowie
│   │   ├── odds/
│   │   │   ├── base.py            # interfejs OddsAdapter
│   │   │   ├── sts.py
│   │   │   └── sofascore_odds.py
│   │   ├── weather.py             # prognoza pogody (Open-Meteo)
│   │   └── news_feeds.py
│   ├── model/
│   │   ├── ratings/{elo,pi,xg}.py
│   │   ├── dixon_coles.py
│   │   ├── lambda_glm.py          # korekta λ kowariantami
│   │   ├── features.py            # skład, zmęczenie, motywacja
│   │   ├── stats_markets.py       # NB: rożne, kartki
│   │   ├── score_matrix.py        # macierz wyników → rynki
│   │   ├── calibration.py
│   │   └── predict.py             # jeden punkt wejścia: predict(match_id, stage)
│   ├── news/
│   │   ├── pipeline.py
│   │   ├── dedup.py
│   │   ├── classify.py            # pytania do Jev
│   │   ├── facts.py
│   │   └── expected_lineup.py
│   ├── decision/
│   │   ├── engine.py              # DecisionEngine, JevEngine, LLMEngine
│   │   ├── questions/             # definicje pytań (YAML)
│   │   ├── policies.py            # kod zamieniający odpowiedzi na decyzje
│   │   └── log.py
│   ├── betting/
│   │   ├── odds_math.py           # marża, Shin
│   │   ├── value.py
│   │   ├── lifecycle.py           # etap 1 / etap 2
│   │   ├── staking.py
│   │   ├── coupon.py
│   │   └── settle.py
│   ├── chat/
│   │   ├── llm.py                 # LLMClient: Gemini, Groq, Bielik
│   │   ├── router.py
│   │   ├── agent.py
│   │   ├── tools.py
│   │   ├── rag.py
│   │   ├── guardrails.py
│   │   └── prompts/
│   ├── apps/{streamlit_app,telegram_bot}.py
│   └── scheduler.py
├── evaluation/
│   ├── backtest.py
│   ├── baselines.py
│   ├── live_report.py
│   ├── datasets/                  # zestawy oznaczone ręcznie (newsy, intencje, guardrails, pytania)
│   └── nlp_eval.py
└── tests/
```

## 2.6 Technologie

| Obszar | Technologia | Uzasadnienie |
|---|---|---|
| Język | Python 3.11+ | standard w NLP i ML |
| Dane | pandas, numpy, SQLite | proste, bez serwera bazy danych |
| Scraping | Playwright, httpx | SofaScore i STS wymagają przeglądarki lub zapytań do API strony |
| Pogoda | Open-Meteo API | darmowe, bez klucza |
| Newsy | feedparser, trafilatura | RSS + czysty tekst artykułu |
| Model | scipy (MLE), statsmodels (GLM Poissona, NB), scikit-learn (kalibracja) | dojrzałe, działają na CPU |
| Silnik decyzyjny | **Jev** przez `typesafe-sdk` | typowane decyzje z prawdopodobieństwami, szybko i tanio |
| Embeddingi | `sdadas/mmlw-retrieval-roberta-base` | model wyszukiwawczy dla polskiego, CPU |
| Baza wektorowa | ChromaDB | lokalna, z filtrowaniem po metadanych |
| LLM | Gemini (główny), Llama przez Groq, Bielik | porównanie modelu komercyjnego, otwartego i polskiego |
| Ewaluacja | RAGAS, scikit-learn metrics, własne skrypty | metryki NLP + bukmacherskie |
| UI | Streamlit, python-telegram-bot | szybki prototyp, czat na telefonie |
| Harmonogram | APScheduler | zadania cykliczne |
| Testy | pytest | testy jednostkowe matematyki kursów, rynków, parserów |

## 2.7 Konfiguracja i sekrety

- `.env` (poza repozytorium): `GEMINI_API_KEY`, `GROQ_API_KEY`, `TYPESAFE_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_IDS`, opcjonalnie `BIELIK_API_URL`.
- `typerai/config.py`: wszystkie progi (EV, prawdopodobieństwo, przedział kursów, progi Jev), wersje modeli, `DECISION_ENGINE=jev|llm`. Zmiana progu to commit w repozytorium, więc wiadomo, od kiedy obowiązuje.
- Każda predykcja i decyzja zapisuje `config_hash`, czyli skrót aktualnej konfiguracji.
