"""Aplikacja webowa Typer AI (docs/09, sekcja 9.1) – pierwsza wersja: Czat, Typy, Wyniki.

    .venv/Scripts/streamlit run typerai/apps/streamlit_app.py

Aplikacja tylko czyta bazę (typerai.report.connect_ro), więc działa także na kopii bazy.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # uruchomienie z dowolnego katalogu

import os  # noqa: E402

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from typerai import config, report  # noqa: E402
from typerai.betting.settle import OFFICIAL, SHADOW_CONFIRMED  # noqa: E402

DISCLAIMER = ("Typer AI to projekt studencki. Typy są wynikiem analizy statystycznej, nie gwarancją wygranej – "
              "każdy zakład może przegrać. Gra u nielegalnych bukmacherów jest zabroniona. Tylko dla osób 18+.")

EXAMPLES = [
    "Jakie mecze Ekstraklasy są w najbliższych dniach?",
    "Co sądzisz o meczu Raków – Widzew?",
    "Jak grała Legia w ostatnich 5 meczach?",
    "Jakie są najnowsze wiadomości o Śląsku Wrocław?",
    "Kursy 2,10 / 3,40 / 3,60 – jaka jest marża bukmachera?",
    "Muszę się odegrać, daj pewniaka",
]


@st.cache_resource
def _conn():
    return report.connect_ro()


def _pct(x, digits=1):
    return "–" if x is None else f"{x:.{digits}%}".replace(".", ",")


def _footer():
    st.divider()
    st.caption(f"⚠️ {DISCLAIMER}")


# ------------------------------------------------------------------ Czat

def _trace_panel(msg: dict) -> None:
    """Rozwijany panel „Jak powstała odpowiedź” (docs/09): model, narzędzia, kontrola liczb, guardrails."""
    with st.expander("Jak powstała odpowiedź"):
        if msg.get("guard_input"):
            st.markdown("**Guardrail wejścia:** wykryto sygnał problemowego grania – odpowiedź wsparcia "
                        "bez wywołania modelu i bez typów.")
            return
        st.markdown(f"**Model:** `{msg['model']}` · czas odpowiedzi {msg['seconds']:.1f} s")
        calls = [t for t in msg["trace"] if "narzedzie" in t]
        for t in msg["trace"]:
            if "przelaczenie" in t:
                st.markdown(f"🔁 {t['przelaczenie']}")
        if not calls:
            st.markdown("Model odpowiedział bez wywołania narzędzi.")
        for i, t in enumerate(calls, 1):
            args = ", ".join(f"{k}={v!r}" for k, v in t["argumenty"].items())
            st.markdown(f"**{i}. 🔧 `{t['narzedzie']}({args})`**")
            st.json(t["wynik"], expanded=False)
        check = msg["check"]
        if not check:
            return
        if check["poprawka"]:
            st.markdown(f"**Kontrola liczb (G5):** {len(check['spoza_narzedzi'])} liczb spoza narzędzi "
                        f"→ model poprawił odpowiedź; po poprawce niepotwierdzonych: {len(check['po_poprawce'])}.")
        else:
            extra = check["spoza_narzedzi"]
            st.markdown("**Kontrola liczb (G5):** liczby dziesiętne i procenty pochodzą z wyników narzędzi"
                        + (f" (jedna liczba spoza narzędzi: {extra[0]:g}, w granicy tolerancji)." if extra else "."))
        st.markdown("**Guardrails wyjścia:** " + ("dodano informację o ryzyku" if msg["risk_note"] else
                                                   "odpowiedź bez kursów i typów – bez noty o ryzyku")
                    + ("; usunięto obietnicę wygranej" if msg["removed"] else ""))


def page_chat() -> None:
    import time

    from google import genai

    from typerai.chat import cli

    cli.ECHO = False
    st.title("💬 Czat z Typer AI")
    st.caption("Gemini z narzędziami (function calling): model sam wybiera narzędzie, a liczby bierze z jego wyniku.")

    if not os.getenv("GEMINI_API_KEY"):
        st.error("Brak `GEMINI_API_KEY` w pliku `.env` (klucz z https://aistudio.google.com/).")
        _footer()
        return

    if "chat" not in st.session_state:
        st.session_state.chat = cli.ChatSession(genai.Client(http_options=cli.HTTP_OPTIONS))
        st.session_state.messages = []

    with st.sidebar:
        st.markdown(f"**Model:** `{st.session_state.chat.model}`")
        st.caption(f"Przy limicie (429), przeciążeniu (5xx), niedostępności (404) lub przekroczeniu {cli.TIMEOUT_S} s "
                   "czat przechodzi na kolejny model z zachowaniem historii.")
        if st.button("Nowa rozmowa"):
            for key in ("chat", "messages"):
                st.session_state.pop(key, None)
            st.rerun()
        st.markdown("**Przykładowe pytania**")
        for q in EXAMPLES:
            if st.button(q, width="stretch"):
                st.session_state.pending = q

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                _trace_panel(msg)

    question = st.chat_input("Zapytaj o mecz, formę drużyny, kursy albo typy…") or st.session_state.pop("pending", None)
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            if cli.HARM.search(question):           # guardrail wejścia (docs/08, 8.6)
                msg = {"role": "assistant", "content": cli.SUPPORT, "guard_input": True}
            else:
                start = time.perf_counter()
                with st.spinner("Typer AI analizuje…"):
                    try:
                        raw = cli.answer_question(st.session_state.chat, question)
                    except cli.errors.APIError as e:
                        st.error(f"Błąd API Gemini: {e.code} {e.message}. Spróbuj ponownie za chwilę.")
                        st.session_state.messages.pop()
                        return
                answer = cli.guard_output(raw)
                msg = {"role": "assistant", "content": answer, "model": st.session_state.chat.model,
                       "seconds": time.perf_counter() - start, "trace": list(cli.TRACE),
                       "check": dict(cli.LAST_CHECK), "risk_note": answer.endswith(cli.RISK_NOTE),
                       "removed": "[usunięte]" in answer and "[usunięte]" not in raw}
            st.markdown(msg["content"])
            _trace_panel(msg)
        st.session_state.messages.append(msg)
    _footer()


# ------------------------------------------------------------------ Typy

PICK_COLUMNS = {"termin": "Termin", "mecz": "Mecz", "zdarzenie": "Zdarzenie", "strategia": "Strategia",
                "status": "Status", "p_model": "p", "ev": "EV", "kurs_etap1": "Kurs etap 1",
                "kurs_etap2": "Kurs etap 2", "bukmacher": "Bukmacher", "wynik_meczu": "Wynik",
                "rozliczenie": "Rozliczenie", "zysk": "Zysk"}


def page_picks() -> None:
    conn = _conn()
    st.title("🎯 Typy")
    rows = report.picks(conn)
    upcoming = report.upcoming(conn)
    runs = report.job_runs(conn, 1)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Typy oficjalne", sum(r["strategia"] == "oficjalna" for r in rows))
    c2.metric("Typy „cień”", sum(r["strategia"] == "cień" for r in rows))
    c3.metric("Mecze w 7 dni", len({(u["termin"], u["mecz"]) for u in upcoming}))
    c4.metric("Harmonogram",
              report.local_time(runs[0]["started_at"])[-5:] if runs else "–",
              help=f"Ostatnie uruchomienie harmonogramu: {runs[0]['job'] if runs else '–'} (tabela job_run)")

    r, s = config.RULES, config.SHADOW_RULES
    st.caption(f"**Oficjalna:** p ≥ {_pct(r['p_min'], 0)}, EV ≥ {_pct(r['ev_min'], 0)}, kurs "
               f"{r['odds_min']:.2f}–{r['odds_max']:.2f}. **Cień** (tylko pomiar modelu): p ≥ {_pct(s['p_min'], 0)}, "
               f"EV ≥ {_pct(s['ev_min'], 0)}, kurs do {s['odds_max']:.2f}. Etap 1: typ wstępny; etap 2 (ok. 60 min "
               "przed meczem): potwierdzenie albo anulowanie na świeżych kursach.")

    choice = st.radio("Strategia", ["wszystkie", "oficjalna", "cień"], horizontal=True)
    shown = [x for x in rows if choice == "wszystkie" or x["strategia"] == choice]
    if shown:
        df = pd.DataFrame(shown)[list(PICK_COLUMNS)].rename(columns=PICK_COLUMNS)
        st.dataframe(df, hide_index=True, width="stretch",
                     column_config={"p": st.column_config.NumberColumn(format="percent"),
                                    "EV": st.column_config.NumberColumn(format="percent")})
    else:
        st.info("Brak typów w tej strategii. Reguły oficjalne są celowo ostre (docs/DZIENNIK.md, 21.11).")

    st.subheader("Najbliższe mecze: dlaczego jest albo nie ma typu")
    if upcoming:
        df = pd.DataFrame(upcoming)
        only = st.toggle("Tylko zdarzenia z dodatnim EV")
        if only:
            df = df[df["ev"] > 0]
        df = df.rename(columns={"termin": "Termin", "mecz": "Mecz", "zdarzenie": "Zdarzenie", "p_model": "p model",
                                "p_rynek": "p rynek", "p_mieszanka": "p mieszanka", "kurs": "Najlepszy kurs",
                                "bukmacher": "Bukmacher", "ev": "EV", "spelnia_reguly": "Reguły oficjalne"})
        pct = st.column_config.NumberColumn(format="percent")
        st.dataframe(df, hide_index=True, width="stretch",
                     column_config={"p model": pct, "p rynek": pct, "p mieszanka": pct, "EV": pct,
                                    "Reguły oficjalne": st.column_config.CheckboxColumn()})
        st.caption(f"Rynek 1X2. p rynek – kursy Pinnacle bez marży (metoda Shina); p mieszanka – "
                   f"p_model^w · p_rynek^(1−w) z w = {config.MODEL['blend_w']:g}; najlepszy kurs spośród ok. 20 "
                   "bukmacherów po odrzuceniu ofert odstających o ponad 8% od mediany; EV = p mieszanka · kurs − 1. "
                   "Pozostałe rynki (podwójna szansa, gole, BTTS, handicap) sprawdza etap 1.")
    else:
        st.info("Brak meczów w najbliższych 7 dniach.")
    _footer()


# ------------------------------------------------------------------ Wyniki

def _summary_block(title: str, s: dict) -> None:
    st.markdown(f"**{title}**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rozliczone typy", s["typy"])
    c2.metric("Trafność", _pct(s["trafnosc"]))
    c3.metric("ROI", _pct(s["roi"]))
    c4.metric("Średnie CLV", _pct(s["clv_srednie"]), help="Nasz kurs względem ostatniego kursu Pinnacle przed meczem")


def page_results() -> None:
    conn = _conn()
    st.title("📈 Wyniki")

    st.header("Test na żywo")
    st.caption("Od 8.11.2026; harmonogram na komputerze domowym od 21.11.2026. Stawka 1 j. na typ, kurs z etapu 2.")
    rows = report.picks(conn)
    live = report.live_summary(conn)
    _summary_block("Strategia oficjalna (cel projektu)", live["oficjalna"])
    _summary_block("Strategia „cień” (pomiar modelu)", live["cień"])
    for label, statuses in (("oficjalna", OFFICIAL), ("cień", SHADOW_CONFIRMED)):
        curve = report.cumulative_profit(rows, statuses)
        if curve:
            st.markdown(f"Skumulowany zysk – {label}")
            st.line_chart(pd.DataFrame(curve).set_index("typ")["zysk_narastajaco"])
    if not live["oficjalna"]["typy"] and not live["cień"]["typy"]:
        st.info("Nie ma jeszcze rozliczonych typów: wyniki pojawią się po pierwszych meczach z typami.")

    st.header("Walidacja modelu v1 (walk-forward)")
    reports = report.validation_reports()
    st.markdown("Log-loss 1X2 na kursach zamknięcia (mniej = lepiej). Model dopasowywany co tydzień tylko na "
                "meczach sprzed tygodnia.")
    st.dataframe(pd.DataFrame(report.validation_table(reports)), hide_index=True, width="stretch")
    curves = pd.DataFrame([{"sezon": season, "w": float(w), "log-loss": v}
                           for season, d in reports.items() for w, v in d["blend_log_loss"].items()])
    st.markdown("Log-loss mieszanki w zależności od wagi modelu (w = 0 – sam rynek, w = 1 – sam model)")
    chart = alt.Chart(curves).mark_line(point=True).encode(
        x=alt.X("w:Q", title="waga modelu w"),
        y=alt.Y("log-loss:Q", scale=alt.Scale(zero=False), title="log-loss 1X2"),
        color=alt.Color("sezon:N"), tooltip=["sezon", "w", alt.Tooltip("log-loss:Q", format=".4f")])
    rule = alt.Chart(pd.DataFrame({"w": [config.MODEL["blend_w"]]})).mark_rule(strokeDash=[4, 4]).encode(x="w:Q")
    st.altair_chart(chart + rule, width="stretch")
    st.caption("Wniosek: model na samych wynikach nie pokonuje rynku; mała waga (w = 0,15) daje mieszankę "
               "porównywalną z rynkiem. Przewagę ma dać model v2 (skład, forma, motywacja).")

    st.subheader("Symulacja reguł na sezonach walidacyjnych")
    sim = [{"sezon": season, "wariant": k, "typy": v["typy"], "trafność": v["trafnosc"], "ROI": v["roi"]}
           for season, d in reports.items() for k, v in d["rules"].items()]
    pct = st.column_config.NumberColumn(format="percent")
    st.dataframe(pd.DataFrame(sim), hide_index=True, width="stretch",
                 column_config={"trafność": pct, "ROI": pct})
    _footer()


# ------------------------------------------------------------------ Newsy

MANUAL_CATEGORIES = {"injury": "kontuzja", "suspension": "zawieszenie", "return": "powrót do składu",
                     "coach_change": "zmiana trenera", "club_crisis": "kryzys w klubie",
                     "fatigue_schedule": "zmęczenie, rotacja", "motivation_context": "stawka meczu",
                     "match_conditions": "warunki meczu"}
MANUAL_STATUS = {"out": "nie zagra", "doubtful": "niepewny", "available": "dostępny"}
MANUAL_CERTAINTY = {"official": "oficjalne (klub, trener, liga)", "reported": "doniesienia mediów / dziennikarza",
                    "speculation": "spekulacja"}


def _manual_form(ro_conn, facts) -> None:
    """Ręczne potwierdzenie (docs/05, 5.5): np. wpis dziennikarza na X albo komunikat klubu."""
    from datetime import datetime, timezone

    from typerai import db
    from typerai.collectors.news import current_teams
    from typerai.news import extract, manual

    with st.expander("➕ Dodaj ręczne potwierdzenie (np. wpis z X, komunikat klubu)"):
        st.caption("Zapis trafia do bazy na tym komputerze. Wpisuj na komputerze domowym – na kopii bazy (laptop) "
                   "wpis zniknie przy następnej kopii.")
        if st.session_state.pop("manual_saved", None):
            st.success("Zapisano. Fakt jest widoczny w czacie (narzędzie newsy) i w tabeli poniżej.")
        names = dict(ro_conn.execute("SELECT id, name FROM team").fetchall())
        teams = sorted(current_teams(ro_conn), key=lambda t: names.get(t, t))
        team = st.selectbox("Drużyna", teams, format_func=lambda t: names.get(t, t), key="m_team")
        now = datetime.now(timezone.utc)
        squad = extract.squad(ro_conn, team, now.isoformat(timespec="minutes"))
        with st.form("manual_fact", clear_on_submit=True):
            category = st.selectbox("Co się stało", list(MANUAL_CATEGORIES), format_func=MANUAL_CATEGORIES.get)
            player = st.selectbox("Zawodnik (opcjonalnie)", [None] + [p for p, _ in squad],
                                  format_func=lambda p: "— cała drużyna —" if p is None else dict(squad)[p])
            c1, c2, c3 = st.columns(3)
            status = c1.selectbox("Status zawodnika", list(MANUAL_STATUS), format_func=MANUAL_STATUS.get)
            certainty = c2.selectbox("Pewność", list(MANUAL_CERTAINTY), format_func=MANUAL_CERTAINTY.get)
            impact = c3.slider("Wpływ na najbliższy mecz (0–4)", 0.0, 4.0, 3.0, 0.5)
            note = st.text_input("Opis i źródło (wymagane)", placeholder="np. @dziennikarz: Ishak nie zagra z Legią (uraz uda)")
            url = st.text_input("Link (opcjonalnie)")
            if st.form_submit_button("Zapisz fakt"):
                try:
                    conn = db.connect()
                    db.init_db(conn)               # dodaje nowe kolumny w starszej bazie
                    manual.add(conn, team, category, note, player_id=player,
                               status=status if player is not None else None, certainty=certainty,
                               impact=impact, source_url=url)
                    conn.close()
                except ValueError as e:
                    st.error(str(e))
                else:
                    st.session_state.manual_saved = True
                    st.rerun()                     # odświeża liczniki i tabelę faktów
        own = [f for f in facts if f["typ"] == "ręczne"]
        if own:
            choice = st.selectbox("Wycofaj ręczny fakt (pomyłka)", [None] + [f["id"] for f in own],
                                  format_func=lambda i: "—" if i is None else next(
                                      f"{f['drużyna']}: {f['kategoria']} {f['zawodnik']} – {f['źródło']}" for f in own if f["id"] == i))
            if choice is not None and st.button("Wycofaj"):
                conn = db.connect()
                manual.withdraw(conn, choice)
                conn.close()
                st.rerun()


def page_news() -> None:
    conn = _conn()
    st.title("📰 Newsy")
    st.caption("Artykuły z kanałów RSS (co 2 godziny, 8–22) i fakty wyciągnięte przez silnik decyzyjny "
               "(Gemini jako plan B dla Jev): kontuzje, zawieszenia, zmiany trenerów. Fakty to kontekst – "
               "nie zmieniają prawdopodobieństw modelu ani typów.")
    articles = report.news_articles(conn)
    facts = report.news_facts(conn)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Artykuły (7 dni)", len(articles))
    c2.metric("Sklasyfikowane", sum(a["status"].startswith("sklasyfikowany") for a in articles))
    c3.metric("Czekają", sum(a["status"] == "czeka na klasyfikację" for a in articles),
              help="Najwyżej 10 artykułów na przebieg – limit chroni darmowe zapytania do Gemini")
    c4.metric("Aktywne fakty", len(facts))

    _manual_form(conn, facts)

    names = sorted({f["drużyna"] for f in facts})
    team = st.selectbox("Drużyna", ["wszystkie"] + names)
    st.subheader("Aktywne fakty")
    shown = [f for f in facts if team == "wszystkie" or f["drużyna"] == team]
    if shown:
        df = pd.DataFrame(shown).drop(columns=["team_id", "id"])
        st.dataframe(df, hide_index=True, width="stretch",
                     column_config={"url": st.column_config.LinkColumn("link", display_text="otwórz")})
    else:
        st.info("Brak aktywnych faktów.")

    st.subheader("Artykuły")
    if articles:
        st.dataframe(pd.DataFrame(articles), hide_index=True, width="stretch",
                     column_config={"url": st.column_config.LinkColumn("link", display_text="otwórz")})
    else:
        st.info("Brak artykułów z ostatnich 7 dni.")
    _footer()


# ------------------------------------------------------------------ nawigacja

def main() -> None:
    st.set_page_config(page_title="Typer AI", page_icon="⚽", layout="wide")
    try:
        _conn()
    except FileNotFoundError as e:
        st.error(str(e))
        st.stop()
    nav = st.navigation([
        st.Page(page_chat, title="Czat", icon="💬", url_path="czat", default=True),
        st.Page(page_picks, title="Typy", icon="🎯", url_path="typy"),
        st.Page(page_results, title="Wyniki", icon="📈", url_path="wyniki"),
        st.Page(page_news, title="Newsy", icon="📰", url_path="newsy"),
    ])
    with st.sidebar:
        st.caption(f"Baza: `{Path(config.DB_PATH).name}` (tylko odczyt)")
    nav.run()


main()
