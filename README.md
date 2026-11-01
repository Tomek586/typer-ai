# Typer AI

**Polskojęzyczny chatbot oparty na LLM z mechanizmem RAG i modelem decyzyjnym Jev do analizy meczów Ekstraklasy i zakładów sportowych.**

Projekt zaliczeniowy z przedmiotu *Przetwarzanie języka naturalnego (NLP) i modele generatywne*.

**Zespół:** [Imię Nazwisko], [Imię Nazwisko]

---

## W skrócie

Typer AI łączy trzy warstwy, z których każda robi to, w czym jest najlepsza:

| Warstwa | Rola | Technologia |
|---|---|---|
| **Model predykcyjny** | liczy prawdopodobieństwa wszystkich zdarzeń meczu | Dixon-Coles + λ-GLM (Elo, pi-ratings, xG, siła składu, zmęczenie, motywacja) + NB dla rożnych i kartek + kalibracja |
| **Silnik decyzyjny Jev** | szybkie, typowane decyzje: ocena newsów, bramka typu (wydaj / wstrzymaj / odrzuć), routing intencji, guardrails | Jev (TypeSafe AI), z LLM jako planem B |
| **Chatbot LLM** | rozmowa po polsku, narzędzia, RAG, wyjaśnienia | Gemini / Llama (Groq) / Bielik, ChromaDB, `mmlw-retrieval-roberta-base` |

Typy powstają w dwóch etapach:
1. **typ wstępny** (dzień wcześniej lub rano), na składzie przewidywanym z newsów,
2. **potwierdzenie albo anulowanie** ok. 60 min przed meczem, na oficjalnych składach i aktualnych kursach (bet365 przez SofaScore).

Typy potwierdzone to oficjalny wynik typera.

## Cel ilościowy

Na typach potwierdzonych, na danych, których model nie widział, typer ma jednocześnie osiągnąć:

- **trafność > 50%**,
- **ROI > 0** przy stałej stawce.

Szczegóły: [rozdz. 1.6](docs/01-koncepcja.md#16-definicja-sukcesu-dlaczego-trafność-i-roi-razem), [rozdz. 10](docs/10-ewaluacja.md).

## Dokumentacja

| # | Rozdział | Zawartość |
|---|---|---|
| 1 | [Koncepcja](docs/01-koncepcja.md) | problem, rozwiązanie, cele, zakres, źródła przewagi, odpowiedzialna gra |
| 2 | [Architektura](docs/02-architektura.md) | komponenty, przepływy, harmonogram zadań, struktura repozytorium, technologie |
| 3 | [Dane](docs/03-dane.md) | źródła, adaptery kursów, kody rynków, schemat bazy, zasady anty-wyciekowe |
| 4 | [Model predykcyjny](docs/04-model-predykcyjny.md) | ratingi, Dixon-Coles, cechy, λ-GLM, rynki, NB, kalibracja, mieszanie z rynkiem, strojenie |
| 5 | [Newsy i wydarzenia](docs/05-newsy-i-wydarzenia.md) | pipeline, klasyfikacja Jev, fakty, przewidywany skład, kontekst |
| 6 | [Silnik decyzyjny Jev](docs/06-silnik-decyzyjny-jev.md) | czym jest Jev, `DecisionEngine`, cztery zastosowania, polityki, ocena, plan B, koszty |
| 7 | [Typy i decyzje](docs/07-typy-i-decyzje.md) | marża, EV, reguły, dwuetapowy cykl życia typu, stawki, kupony, rozliczanie |
| 8 | [Chatbot i LLM](docs/08-chatbot-llm.md) | dostawcy LLM, agent, narzędzia, RAG, prompt, guardrails |
| 9 | [Interfejsy](docs/09-interfejsy.md) | Streamlit, bot Telegram |
| 10 | [Ewaluacja](docs/10-ewaluacja.md) | backtest, test na żywo, metryki, istotność, ablacje, ocena Jev i NLP |
| 11 | [Plan prac](docs/11-plan-prac.md) | etapy, podział zadań, ryzyka, scenariusz demo |
| 12 | [Słownik](docs/12-slownik.md) | pojęcia bukmacherskie, statystyczne i NLP |

## Zastrzeżenie

Projekt ma charakter edukacyjny i badawczy. Typer AI nie gwarantuje wygranych i nie zachęca do hazardu. Testy prowadzone są wyłącznie na wirtualnych stawkach. Zakłady bukmacherskie są dozwolone od 18 lat i mogą uzależniać.
