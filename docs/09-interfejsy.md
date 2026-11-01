# 9. Interfejsy

Oba interfejsy korzystają z tego samego potoku czatu (`typerai/chat/`) i tych samych danych. Różnią się tylko sposobem prezentacji.

## 9.1 Aplikacja Streamlit

Uruchomienie: `streamlit run typerai/apps/streamlit_app.py`

| Strona | Zawartość | Dla kogo |
|---|---|---|
| **Czat** | rozmowa z Typer AI; wybór modelu LLM; rozwijany panel „Jak powstała odpowiedź”: intencja z routera (z prawdopodobieństwem), wywołania narzędzi, fragmenty RAG, decyzje guardrails | użytkownik, prezentacja |
| **Typy** | tabela typów: status (wstępny / wstrzymany / potwierdzony / anulowany), mecz, zdarzenie, kurs etap 1 → etap 2, p, EV, decyzja bramki; przycisk „Zbuduj kupon” | użytkownik |
| **Mecz** | karta meczu: ratingi, forma, H2H, skład przewidywany (z oznaczeniem źródła: newsy / ręczne) vs po meczu faktyczny, heatmapa macierzy wyników, wszystkie rynki (model vs kursy), top czynniki predykcji, aktywne fakty z newsów, pogoda | użytkownik |
| **Newsy** | lista artykułów z klasyfikacją Jev (kategoria, wpływ, kierunek, pewność, zawodnicy), filtr po drużynie; ręczna korekta etykiety, zapisywana do zbioru ewaluacyjnego | zespół |
| **Decyzje Jev** | log `DECISION_LOG`: cel, odpowiedzi z prawdopodobieństwami, decyzja, czas; statystyki per zastosowanie | zespół, prezentacja |
| **Wyniki** | skumulowany zysk w czasie, trafność i ROI z przedziałami ufności, CLV, podział na rynki, przedziały kursów i strategie (S2 / S1 / NOGATE), porównanie z baseline'ami | użytkownik, raport |
| **Kalibracja** | wykresy niezawodności, Brier, log-loss, ECE per rodzina rynków i per wersja modelu | zespół, raport |
| **System** | ostatnie uruchomienia zadań (`JOB_RUN`), błędy kolektorów, wiek ostatnich danych (kursy, newsy, składy) | zespół |
| **O projekcie** | opis metod, zastrzeżenia, 18+ | wszyscy |

Każda strona ma w stopce stałe zastrzeżenie o ryzyku i informację 18+.

## 9.2 Bot Telegram

Uruchomienie: `python -m typerai.apps.telegram_bot` (`TELEGRAM_BOT_TOKEN` w `.env`)

| Komenda | Działanie |
|---|---|
| `/start` | powitanie, zasady, 18+ |
| `/typy` | typy na dziś i jutro ze statusami |
| `/mecz Lech Legia` | skrócona analiza meczu |
| `/kupon 4` | kupon o kursie ok. 4,0 z potwierdzonych typów |
| `/newsy Legia` | aktywne fakty o drużynie |
| `/wyniki` | trafność, ROI i CLV z ostatnich 30 dni |
| `/model gemini\|llama\|bielik` | zmiana modelu LLM w rozmowie |
| zwykła wiadomość | swobodna rozmowa (ten sam potok co czat w Streamlit) |

**Powiadomienia automatyczne:**

| Kiedy | Treść |
|---|---|
| po etapie 1 | „Typ wstępny: …” (kurs, p, EV, „czekamy na składy”) |
| po etapie 2 | „✅ Potwierdzony” lub „❌ Anulowany: powód” (np. „brak kluczowego napastnika w składzie”, „kurs spadł poniżej progu EV”) |
| 23:30 | rozliczenie dnia: wyniki typów, zysk dnia, wynik narastająco |
| poniedziałek | raport tygodniowy: trafność, ROI, CLV, najlepsze i najgorsze rynki |
| błąd systemu | alert do administratorów (nieudany scraping, brak kursów przed etapem 2) |

**Bezpieczeństwo:** bot odpowiada wyłącznie na czatach z listy `TELEGRAM_ALLOWED_CHAT_IDS`, żeby nikt postronny nie zużywał limitów API. Wiadomości przechodzą przez te same guardrails co w Streamlit.

Format wiadomości: Markdown Telegrama, maks. ok. 1500 znaków. Dłuższe analizy kończą się linkiem „szczegóły w aplikacji”.
