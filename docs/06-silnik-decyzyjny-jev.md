# 6. Silnik decyzyjny Jev

## 6.1 Czym jest Jev

**Jev** to model firmy **TypeSafe AI**, opisywany jako model „System One”. W przeciwieństwie do LLM **nie generuje tekstu**. Dostaje dane (`state`) i zestaw typowanych pytań, a zwraca **ustrukturyzowane odpowiedzi z rozkładami prawdopodobieństwa**. Pytania są oceniane równolegle i niezależnie od siebie.

| Typ pytania | Do czego | Zwraca |
|---|---|---|
| **Noul** | tak/nie | `noul`: prawdopodobieństwo „tak” (0–1) |
| **Choice** | wybór jednej z 1–255 opcji | `choice`, `probabilities` (rozkład po opcjach), `confidence` |
| **Score** | ocena na skali 2–10 opisanych poziomów | `score` (średnia ważona poziomów), `probabilities`, `confidence`, `legend` |

Fakty z dokumentacji producenta (stan na 1.11.2026):

| Cecha | Wartość |
|---|---|
| Wersje | `jev-1.14.0` (od 14.10.2026), `jev-1.13.0`; alias `jev-latest` |
| Endpoint | `POST https://api.typesafe.ai/v1/systemone`, nagłówek `Authorization: Bearer <klucz>` |
| SDK | `pip install typesafe-sdk`, zmienna `TYPESAFE_API_KEY`, klucz z `console.typesafe.ai` |
| Kontekst | 64k tokenów na zapytanie, 32k na `state` + jedno pytanie |
| Liczba pytań | bez limitu, o ile mieszczą się w kontekście |
| Cena | $0,042 za 1 mln tokenów wejścia; tokeny wyjścia bezpłatne |
| Języki | najlepiej angielski; inne języki obsługiwane, ale słabiej (zalecane testy na własnych danych) |
| Dostosowanie | brak fine-tuningu; wynik kształtuje się przez `state`, `instructions` i `criteria` |
| `confidence` | miara „skupienia” rozkładu (dla Choice: `(p_max − 1/n)/(1 − 1/n)`). Producent **nie twierdzi**, że jest skalibrowana względem trafności |

Źródło: dokumentacja `docs.typesafe.ai` (strony: System One API, Models, Confidence, Score, Python SDK).

## 6.2 Dlaczego Jev i do czego (a do czego nie)

| Zadanie | Czy Jev? | Uzasadnienie |
|---|---|---|
| Prawdopodobieństwo wyniku meczu | ❌ | Jev nie zna piłki i nie da się go douczyć na danych meczowych. To zadanie modelu statystycznego |
| Klasyfikacja newsów (kategoria, wpływ, zawodnicy) | ✅ | decyzje typowane z gotowej listy, szybko i tanio, bez halucynacji nazw |
| Bramka typu (wydaj / wstrzymaj / odrzuć) | ✅ | ocena spójności liczb i kontekstu tekstowego, z prawdopodobieństwem decyzji do logowania i analizy |
| Routing intencji w czacie | ✅ | klasyczny wzorzec „intent routing” z dokumentacji Jev |
| Guardrails | ✅ | pytania tak/nie o treść wiadomości i odpowiedzi |
| Rozmowa, wyjaśnienia, odpowiedzi RAG | ❌ | Jev nie generuje tekstu. To zadanie LLM |

**Zasada nadrzędna:** decyzje Jev mogą tylko **ograniczać** działanie systemu (wstrzymać lub odrzucić typ, zawęzić narzędzia, zablokować odpowiedź). Jev nigdy nie tworzy typu i nie zmienia prawdopodobieństwa.

## 6.3 Architektura: `DecisionEngine`

```python
@dataclass
class Question:                      # odpowiednik pytań Jev
    type: Literal["noul", "choice", "score"]
    instructions: str
    criteria: dict[str, str] | list[str] | None = None

@dataclass
class Answer:
    type: str
    value: float | str               # noul / choice / score
    probabilities: dict[str, float] | None
    confidence: float | None

class DecisionEngine(Protocol):
    name: str                        # "jev" | "llm-gemini"
    def ask(self, purpose: str, state: dict | str,
            questions: dict[str, Question]) -> dict[str, Answer]: ...
```

| Implementacja | Opis |
|---|---|
| `JevEngine` | `typesafe_sdk.TypeSafeClient.system_one(...)`, model **przypięty do wersji** (`jev-1.14.0`), bo progi stroimy pod konkretną wersję |
| `LLMEngine` | te same pytania jako prompt + wymuszony JSON (structured output) z prawdopodobieństwami opcji; plan B i punkt odniesienia w porównaniu |
| `CachedEngine` | wrapper: cache po `hash(purpose, state, questions, model)`, żeby ewaluacja nie płaciła dwa razy za to samo zapytanie |

Każde wywołanie trafia do `DECISION_LOG`: cel, silnik, model, `state`, pytania, odpowiedzi, wynikowa decyzja, czas i liczba tokenów.

Definicje pytań trzymamy w plikach YAML (`typerai/decision/questions/*.yaml`), wersjonowanych w repozytorium. Zmiana pytania to zmiana wersji polityki (`policy_version`).

**Ważne:** odpowiedzi Jev zamieniane są na decyzje **w kodzie** (`policies.py`), według jawnych progów. Dzięki temu decyzja jest deterministyczna dla danych odpowiedzi, a progi da się testować i stroić.

## 6.4 Cztery zastosowania

### 6.4.1 Klasyfikacja newsów

Pełna specyfikacja w [rozdz. 5.2](05-newsy-i-wydarzenia.md#52-pipeline). Polityka w skrócie:

| Odpowiedź | Próg | Decyzja |
|---|---|---|
| `about_{team}` (Noul) | ≥ 0,6 | artykuł dotyczy drużyny |
| `category` (Choice) | `confidence ≥ 0,4` | kategoria przyjęta; poniżej progu → `other` (tylko RAG) |
| `impact` (Score) | – | zapisany jako liczba 0–4 |
| `p_{player}` (Noul) | ≥ 0,7 | zawodnik przypisany do faktu |
| `status_{player}` (Choice) | `confidence ≥ 0,3` | status przyjęty; poniżej progu → `doubtful` |

### 6.4.2 Bramka decyzyjna typu

Wywoływana w **etapie 1** dla każdego kandydata, który przeszedł reguły value, oraz w **etapie 2** dla każdego typu wstępnego i nowego kandydata.

**`state`** (przykład dla etapu 2):

```json
{
  "stage": 2,
  "match": {"home": "Lech Poznań", "away": "Legia Warszawa", "kickoff": "2026-11-08T17:30", "derby": false},
  "pick": {"market": "1X2:1", "description": "Lech Poznań to win",
           "odds_now": 2.15, "odds_stage1": 2.25, "p_model": 0.531, "p_market": 0.447, "ev": 0.142},
  "model_inputs": {"lineup_home": {"type": "expected+manual", "att_ratio": 0.91, "reg_ratio": 0.94, "gk_backup": false},
                   "lineup_away": {"type": "expected", "att_ratio": 1.0, "reg_ratio": 0.97, "gk_backup": false},
                   "rest_days": {"home": 3, "away": 7}, "cup_midweek": {"home": true, "away": false},
                   "table": {"home_position": 2, "away_position": 4, "rounds_left": 20}},
  "odds_movement": {"since_stage1_pct": -4.4, "direction": "shortened"},
  "news_context": {"home": ["..."], "away": ["..."]},
  "weather": {"rain_mm": 6.5, "wind_kmh": 18, "temp_c": 5},
  "stage1_decision": "issue"
}
```

**Pytania:**

```json
{
  "decision": {
    "type": "choice",
    "instructions": "A statistical model suggests this bet has positive expected value. Considering the news, lineups, context and odds movement, what should be done with this bet?",
    "criteria": {
      "issue": "The context supports or does not contradict the model; the bet can be issued",
      "hold": "Important information is missing or uncertain (e.g. lineup, key player status); wait for more information",
      "reject": "The context clearly contradicts the premise of the bet or reveals a risk the model cannot see"
    }
  },
  "contradiction": {
    "type": "noul",
    "instructions": "Does any news or lineup information directly contradict the premise of this bet (e.g. the backed team is missing key players not reflected in the model, or the team is likely to rotate heavily)?"
  },
  "uncertainty": {
    "type": "noul",
    "instructions": "Is information that could significantly change the outcome probability still unconfirmed (e.g. doubtful key player, unconfirmed lineup, possible postponement)?"
  },
  "context_risk": {
    "type": "score",
    "instructions": "How risky is this match context for a pre-match bet, beyond what the statistics show?",
    "criteria": [
      "Normal match, no unusual circumstances",
      "Minor unusual circumstances",
      "Notable circumstances (new coach, heavy rotation risk, extreme weather)",
      "Highly unpredictable (crisis at club, many absences, match conditions in doubt)"
    ]
  }
}
```

**Polityka** (`policies.gate_policy`), sprawdzana po kolei:

| # | Warunek | Etap 1 | Etap 2 |
|---|---|---|---|
| 1 | `contradiction ≥ 0,70` | ODRZUĆ | ANULUJ |
| 2 | `decision = reject` i `confidence ≥ 0,35` | ODRZUĆ | ANULUJ |
| 3 | `context_risk ≥ 2,5` | WSTRZYMAJ | ANULUJ |
| 4 | `uncertainty ≥ 0,60` lub `decision = hold` | WSTRZYMAJ (decyzja w etapie 2) | ANULUJ (brak informacji przed meczem) |
| 5 | w pozostałych przypadkach | WYDAJ (typ wstępny) | POTWIERDŹ |

- Progi to **wartości startowe**, ustalone przed testem na żywo i zamrożone na jego czas. Nie da się ich stroić w backteście, bo nie ma historycznych newsów. Przyjmujemy wartości konserwatywne i oceniamy je ablacją (6.5).
- Na wejściu bramki zawsze jest typ, który już spełnił reguły value. Bramka nie ma żadnej ścieżki, która dodaje typ.

### 6.4.3 Router intencji w czacie

Zgodny ze wzorcem „intent routing” i „confidence-gated routing” z dokumentacji Jev.

```json
"intent": {
  "type": "choice",
  "instructions": "What does the user want? The message is in Polish and concerns football betting in the Polish Ekstraklasa.",
  "criteria": {
    "team_stats": "Statistics, form or table position of a team",
    "head_to_head": "History of matches between two teams",
    "match_analysis": "Analysis or prediction of a specific match",
    "odds_info": "Current odds for a match or market",
    "odds_math": "Converting odds to probability, margin, expected value",
    "daily_picks": "Recommended bets for today or upcoming days",
    "coupon": "Building an accumulator / coupon",
    "rules": "Bookmaker rules, how bets are settled",
    "news": "Injuries, lineups, news about a team",
    "my_results": "Performance history of the tipster",
    "general_betting": "General question about betting concepts",
    "off_topic": "Not related to football or betting",
    "gambling_harm": "Signs of problem gambling, chasing losses, distress"
  }
}
```

**Polityka:**

| Warunek | Działanie |
|---|---|
| `choice = gambling_harm` i `p ≥ 0,3` | tryb wsparcia (rozdz. 8.6), bez narzędzi i typów |
| `choice = off_topic` i `confidence ≥ 0,6` | uprzejma odmowa (szablon), bez wywołania LLM |
| `confidence ≥ 0,5` | LLM dostaje **zawężony zestaw narzędzi** przypisany do intencji (tabela w rozdz. 8.3) |
| `confidence < 0,5` | LLM dostaje **pełny zestaw narzędzi** (fallback) |

Zawężony zestaw narzędzi skraca prompt i zmniejsza ryzyko wywołania złego narzędzia. Czy to faktycznie poprawia trafność, sprawdza ewaluacja (z routerem vs bez routera).

### 6.4.4 Guardrails

**Na wejściu** (wiadomość użytkownika):

```json
"harm_signal": {
  "type": "noul",
  "instructions": "Does the user show signs of problem gambling: chasing losses, betting money they cannot afford, borrowing to bet, loss of control or distress?"
}
```

`noul ≥ 0,5` → tryb wsparcia. Działa razem z listą fraz (np. „odegrać się”, „postawiłem wszystko”), więc wystarczy, że zadziała jeden z dwóch mechanizmów.

**Na wyjściu** (szkic odpowiedzi LLM):

```json
"guarantee": {
  "type": "noul",
  "instructions": "Does this answer promise, guarantee or strongly imply a certain win or risk-free profit?"
},
"missing_risk": {
  "type": "noul",
  "instructions": "Does this answer recommend a bet without mentioning that it can lose or without stating its probability?"
}
```

`guarantee ≥ 0,5` albo `missing_risk ≥ 0,5` oznacza ponowne wygenerowanie odpowiedzi z dodatkową instrukcją (maks. 1 raz). Jeśli to nie pomoże, do odpowiedzi automatycznie dopisywana jest sekcja ryzyka. Działają też niezależne reguły deterministyczne (rozdz. 8.6).

## 6.5 Ocena i strojenie Jev

| Zastosowanie | Zbiór | Metryki | Strojenie |
|---|---|---|---|
| Newsy | 150 artykułów oznaczonych ręcznie | F1 per kategoria, F1 zawodników, ECE dla Noul | progi Noul i `confidence` (siatka) na 100 artykułach, test na 50 |
| Bramka | wszystkie decyzje z testu na żywo | ablacja (6.5.1), trafność, ROI, log-loss typów przepuszczonych vs zablokowanych | brak (progi zamrożone) |
| Router | 200 wiadomości oznaczonych ręcznie | accuracy, macro-F1, krzywa accuracy vs próg `confidence` | próg na 150, test na 50 |
| Guardrails | 100 wiadomości i 100 odpowiedzi oznaczonych | recall (priorytet), precision | próg pod recall ≥ 0,95 |

**Kalibracja `confidence`:** producent nie gwarantuje, że `confidence` odpowiada trafności. Dla każdego zastosowania rysujemy więc wykres niezawodności (trafność w przedziałach `confidence`) i na tej podstawie ustalamy progi.

### 6.5.1 Ablacja bramki

W teście na żywo system zapisuje **trzy strategie** równolegle (tylko jedna jest „oficjalna”):

| Strategia | Opis |
|---|---|
| **S-JEV** (oficjalna) | typy potwierdzone przez bramkę w etapie 2 |
| S-NOGATE | wszystkie typy spełniające reguły value w etapie 2, bez bramki |
| S-REJECTED | tylko typy zablokowane przez bramkę |

Bramka ma sens, jeśli S-REJECTED wypada **gorzej** niż S-NOGATE (niższe ROI i log-loss). Wynik raportujemy z przedziałami ufności, bo zablokowanych typów będzie niewiele.

## 6.6 Plan B: `LLMEngine`

Dostęp do Jev nie jest jeszcze potwierdzony. `LLMEngine` przyjmuje te same `Question` i zwraca te same `Answer`:

- prompt: `state` + lista pytań + instrukcja „dla każdego pytania podaj rozkład prawdopodobieństwa opcji”,
- wymuszony schemat JSON (structured output w Gemini),
- `confidence` liczone tym samym wzorem co w Jev, z prawdopodobieństw zwróconych przez LLM.

Jeśli dostęp do Jev się uda, **porównujemy oba silniki** na tych samych zbiorach: jakość (F1, accuracy), kalibrację (ECE), czas odpowiedzi i koszt. To dodatkowy wynik badawczy projektu.

## 6.7 Koszt i wydajność (szacunek)

| Zastosowanie | Zapytań dziennie | Tokeny wejścia (szac.) | Koszt dzienny (szac.) |
|---|---|---|---|
| Newsy | ok. 40 artykułów × (≈5 pytań o drużyny + 4 o klasyfikację + ≈30 o zawodników dla części artykułów) | ok. 2–4 mln (zakładając, że `state` liczy się osobno dla każdego pytania) | ok. $0,10–0,20 |
| Bramka | ok. 10–30 typów × 2 etapy | ok. 0,1 mln | < $0,01 |
| Router i guardrails | ok. 100 wiadomości | ok. 0,1 mln | < $0,01 |

Szacunek jest zgrubny. Sposób liczenia tokenów przy wielu pytaniach do jednego `state` sprawdzimy w polu `usage` pierwszych odpowiedzi. Nawet przy dziesięciokrotnym przekroczeniu koszt całego projektu powinien zamknąć się w kilkunastu dolarach. Opóźnienia podawane przez producenta to 70–500 ms, a faktyczne mierzymy w `DECISION_LOG`.
