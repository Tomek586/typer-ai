# 8. Chatbot i warstwa LLM

Chatbot to główny interfejs projektu i główna część NLP. Każda wiadomość przechodzi przez:

```
guardrails wejścia → router intencji (Jev) → agent LLM + narzędzia + RAG → guardrails wyjścia → odpowiedź
```

## 8.1 Dostawcy LLM

Wspólny interfejs `typerai/chat/llm.py`:

```python
class LLMClient(Protocol):
    name: str
    def chat(self, messages: list[Message], tools: list[ToolSpec] | None = None,
             temperature: float = 0.2, json_schema: dict | None = None) -> LLMResponse: ...
```

| Model | Dostęp | Rola | Function calling |
|---|---|---|---|
| **Gemini** (Flash) | Gemini API, darmowy plan | model główny | natywne |
| **Llama** (70B) | Groq API, darmowy plan | porównanie: model otwarty | natywne |
| **Bielik** (instruct) | API lub lokalnie (kwantyzacja), do ustalenia | porównanie: polski model | tryb ReAct-JSON |

**Tryb ReAct-JSON** (dla modeli bez natywnego function calling): model odpowiada wyłącznie JSON-em postaci `{"thought": "...", "tool": "...", "args": {...}}` albo `{"final": "..."}`. Parser wykonuje narzędzie, a przy błędnym JSON-ie prosi model o poprawkę (maks. 2 razy).

Dokładne identyfikatory wersji modeli zapisujemy w konfiguracji i w każdym logu rozmowy.

## 8.2 Pętla agenta

```
wejście: wiadomość, historia (ostatnie 10 wymian), wynik routera
1. prompt systemowy + kontekst (data, sezon, kolejka) + historia + wiadomość
2. narzędzia = zawężone (router conf ≥ 0,5) albo pełne
3. LLM → odpowiedź końcowa ALBO wywołania narzędzi
4. wykonaj narzędzia (równolegle, jeśli niezależne), timeout 20 s każde
5. wyniki (JSON) dopisz do rozmowy, wróć do 3 (maks. 5 iteracji)
6. odpowiedź → guardrails wyjścia → użytkownik
```

**Obsługa błędów:**

| Sytuacja | Reakcja |
|---|---|
| narzędzie zwraca błąd | LLM dostaje `{"error": "..."}` i informuje użytkownika, czego nie udało się sprawdzić |
| limit zapytań API (429) | ponowienie z wykładniczym odstępem; po 3 próbach przełączenie na zapasowego dostawcę (Gemini ↔ Groq) |
| przekroczono 5 iteracji | odpowiedź z dotychczasowych wyników + informacja o niepełnej analizie |
| nieznana drużyna | `znajdz_mecz` zwraca listę podobnych nazw, a LLM dopytuje użytkownika |

Każda rozmowa jest logowana: wiadomości, intencja, wywołania narzędzi (nazwa, argumenty, czas, wynik), tokeny, model.

## 8.3 Narzędzia

| Narzędzie | Argumenty | Zwraca |
|---|---|---|
| `znajdz_mecz` | `druzyna_1`, `druzyna_2?`, `data?` | ID meczu, data, godzina, status; rozwiązuje aliasy (np. „Kolejorz”) |
| `statystyki_druzyny` | `druzyna`, `ostatnie_n=5` | forma, gole, xG, rożne, kartki, Elo, pi-rating, pozycja w tabeli |
| `h2h` | `druzyna_1`, `druzyna_2`, `n=5` | ostatnie bezpośrednie mecze |
| `sklad` | `mecz_id` | skład przewidywany lub oficjalny, wskaźniki siły składu, nieobecni |
| `predykcja` | `mecz_id`, `rynki?` | prawdopodobieństwa, top 3 czynniki (`top_contributions`), etap |
| `kursy` | `mecz_id`, `rynek?` | kursy (bet365 przez SofaScore), marża, prawdopodobieństwa bez marży, ruch kursu |
| `przelicz_kurs` | `kursy: list[float]`, `metoda=proporcjonalna\|shin` | prawdopodobieństwa, marża |
| `typy` | `data?`, `status?` | typy wstępne i potwierdzone (format z rozdz. 7.8) |
| `zbuduj_kupon` | `kurs_docelowy`, `max_zdarzen=3` | kupon, `p_kupon`, `EV_kupon` |
| `newsy_druzyny` | `druzyna`, `dni=7` | aktywne fakty (rozdz. 5.4) z tytułami i linkami |
| `szukaj_w_dokumentach` | `zapytanie`, `typ=news\|regulamin`, `druzyna?`, `od_daty?` | fragmenty z numerami, źródłem, datą, URL |
| `historia_typow` | `okres=30`, `rynek?` | trafność, ROI, CLV, liczba typów, przedziały ufności |

**Zawężone zestawy narzędzi** według intencji z routera:

| Intencja | Narzędzia |
|---|---|
| `team_stats` | `znajdz_mecz`, `statystyki_druzyny` |
| `head_to_head` | `h2h`, `znajdz_mecz` |
| `match_analysis` | `znajdz_mecz`, `predykcja`, `kursy`, `sklad`, `newsy_druzyny`, `h2h` |
| `odds_info` | `znajdz_mecz`, `kursy` |
| `odds_math` | `przelicz_kurs` |
| `daily_picks` | `typy` |
| `coupon` | `typy`, `zbuduj_kupon` |
| `rules` | `szukaj_w_dokumentach` |
| `news` | `newsy_druzyny`, `szukaj_w_dokumentach`, `sklad` |
| `my_results` | `historia_typow` |
| `general_betting` | `przelicz_kurs`, `szukaj_w_dokumentach` |

**Zasada:** LLM nigdy sam nie liczy prawdopodobieństw, EV ani marży. Każda liczba w odpowiedzi musi pochodzić z wyniku narzędzia (sprawdzane w 8.6).

## 8.4 RAG

### Korpus

| Typ | Źródło | Chunking | Metadane |
|---|---|---|---|
| newsy | pipeline z rozdz. 5 | akapity łączone do 300–500 tokenów, zakładka 50 | `team_ids`, `category`, `published_at`, `source`, `url` |
| regulaminy bukmacherów | PDF / strona | jeden paragraf lub punkt = jeden chunk | `section`, `title`, `url` |
| słownik pojęć | [12-slownik.md](12-slownik.md) | jedno hasło = jeden chunk | `term` |

### Indeksowanie
- Embeddingi: `sdadas/mmlw-retrieval-roberta-base`. Zapytania dostają prefiks wymagany przez model (zgodnie z kartą modelu na Hugging Face).
- ChromaDB, kolekcje osobno dla newsów, regulaminu i słownika.

### Wyszukiwanie
1. Filtry z argumentów narzędzia (drużyna, typ, `od_daty`). Dla newsów domyślnie 14 dni.
2. **Wyszukiwanie hybrydowe:** wektorowe (top 20) + BM25 (top 20), połączone metodą Reciprocal Rank Fusion. BM25 dobrze łapie nazwiska i nazwy własne, które embeddingi czasem gubią.
3. **Reranking** cross-encoderem (wielojęzyczny model rerankingowy na CPU) i wybór top 5.
4. Fragmenty trafiają do LLM ponumerowane `[1]…[5]` z tytułem, źródłem i datą.

Warianty (wektor / hybryda / hybryda + reranking) porównujemy w ewaluacji (rozdz. 10).

### Generowanie
- LLM odpowiada **tylko** na podstawie fragmentów i powołuje się na nie numerami.
- Jeśli fragmenty nie zawierają odpowiedzi, LLM mówi to wprost („nie znalazłem informacji”).
- Na końcu odpowiedzi jest lista źródeł z linkami.

## 8.5 Prompt systemowy

```
Jesteś Typer AI – asystentem do analizy meczów Ekstraklasy i zakładów sportowych.
Dzisiaj: {data}. Sezon {sezon}, kolejka {kolejka}.
Odpowiadasz po polsku, rzeczowo i zwięźle. Używasz tabel, gdy porównujesz liczby.

ZASADY LICZB
1. Nie licz prawdopodobieństw, EV ani marży samodzielnie – używaj narzędzi.
2. Każda liczba w odpowiedzi musi pochodzić z wyniku narzędzia w tej rozmowie.

ZASADY TYPÓW
3. Typ podawaj w formacie: zdarzenie, kurs (bukmacher), prawdopodobieństwo modelu,
   EV, status (wstępny/potwierdzony), 2–3 powody, ryzyko.
4. Podawaj tylko typy zwrócone przez narzędzie „typy”. Nie twórz własnych typów.
5. Jeśli brak typów spełniających reguły – powiedz to wprost.
6. Nigdy nie obiecuj wygranej. Nie używaj słów „pewniak”, „pewna wygrana”, „gwarancja”.

ZASADY ŹRÓDEŁ
7. Informacje z newsów i regulaminu podawaj z numerem źródła [n].
8. Jeśli nie wiesz – powiedz to. Nie zgaduj.

ZAKRES
9. Tematy: piłka nożna (Ekstraklasa), kursy, zakłady, wyniki typera.
   Inne tematy – uprzejmie odmów.
```

Prompty (systemowy, ekstrakcyjne, guardrails) trzymamy w `typerai/chat/prompts/*.md`, wersjonowane w repozytorium.

## 8.6 Guardrails

| # | Reguła | Mechanizm | Reakcja |
|---|---|---|---|
| G1 | sygnały problemowego grania na wejściu | lista fraz **lub** Jev `harm_signal ≥ 0,5` | **tryb wsparcia**: empatyczna odpowiedź, zachęta do przerwy, informacja o pomocy, brak typów w tej rozmowie przez 24 h |
| G2 | pytanie poza tematem | router: `off_topic` | szablon odmowy |
| G3 | obietnica wygranej | lista słów (regex) **lub** Jev `guarantee ≥ 0,5` | ponowna generacja (1×), potem usunięcie zdania i dopisanie ostrzeżenia |
| G4 | typ bez ryzyka lub prawdopodobieństwa | sprawdzenie pól formatu **lub** Jev `missing_risk ≥ 0,5` | automatyczne dopisanie sekcji „Ryzyko” |
| G5 | liczby spoza narzędzi | ekstrakcja liczb z odpowiedzi (regex) i porównanie z liczbami w wynikach narzędzi (tolerancja zaokrągleń) | ponowna generacja (1×), a przy powtórce ostrzeżenie w logu |
| G6 | brak źródeł przy faktach z RAG | obecność `[n]` przy odpowiedzi z `szukaj_w_dokumentach` | ponowna generacja (1×) |
| G7 | typ nieistniejący w bazie | porównanie wymienionych zdarzeń z wynikiem `typy` | usunięcie i ostrzeżenie |

Mechanizmy deterministyczne (regex, sprawdzanie pól) działają zawsze. Jev jest dodatkową warstwą, która łapie przypadki sformułowane nietypowo.

## 8.7 Pamięć rozmowy

- Ostatnie 10 wymian w kontekście. Starsze są streszczane przez LLM do 5 zdań.
- „Aktywny mecz” w rozmowie (`mecz_id`) jest zapamiętywany, więc „a co z rożnymi?” odnosi się do ostatnio omawianego meczu.
- Brak pamięci między sesjami, poza flagą trybu wsparcia (G1) z czasem ważności 24 h.

## 8.8 Przykładowa rozmowa (docelowa)

> **Użytkownik:** Co myślisz o Lech – Legia w niedzielę?
>
> *(guardrails OK → router: `match_analysis`, conf 0,81 → znajdz_mecz → predykcja → kursy → sklad → newsy_druzyny)*
>
> **Typer AI:** **Lech Poznań – Legia Warszawa**, niedziela 17:30, etap 1 (skład przewidywany)
>
> | Zdarzenie | Model | Kurs | Bez marży | EV |
> |---|---|---|---|---|
> | 1 | 49,7% | 2,20 | 43,6% | +9,3% |
> | X | 26,2% | 3,50 | 27,4% | −8,3% |
> | 2 | 24,1% | 3,30 | 29,0% | −20,5% |
>
> **Typ:** brak. Wygrana Lecha ma dodatnie EV, ale model daje jej 49,7%, czyli poniżej progu 52%. Pozostałe rynki nie spełniają reguł.
>
> **Co wpływa na predykcję:**
> - Lech grał w czwartek w pucharach, co obniża jego oczekiwane gole o ok. 4%,
> - pi-rating wyraźnie na korzyść Lecha u siebie,
> - Legia ma nowego trenera od 4 dni [1].
>
> Po ogłoszeniu składów (ok. 16:30) sprawdzę mecz ponownie.
>
> ⚠️ To analiza statystyczna, nie gwarancja. Każdy zakład może przegrać.
>
> [1] *tytuł artykułu – serwis, data, link*

Liczby w przykładzie są ilustracyjne.
