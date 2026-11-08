"""Składy, strzelcy, kartki i sędziowie Ekstraklasy z 90minut.pl (docs/03, sekcja 3.3.3).

Pobieramy za zgodą redakcji 90minut.pl: jedna strona co kilka sekund, każda relacja tylko raz
(cache surowego HTML w data/raw/90minut/).

Użycie:
    python -m typerai.collectors.ninetymin --seasons 2024/25 2025/26   # wybrane sezony
    python -m typerai.collectors.ninetymin --current                   # nowe mecze bieżącego sezonu
"""

import argparse
import re
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup, Tag

from typerai import config, db, teams
from typerai.matches import find_match

BASE_URL = "http://www.90minut.pl"
RAW_DIR = config.RAW_DIR / "90minut"
USER_AGENT = "TyperAI-student-project"
DELAY_SECONDS = 4.0
RETRY_PAUSES = [10, 30, 60, 120, 300, 600]

# Numery sezonów w archiwum 90minut.pl rosną o 2 co sezon (2026/27 = 109, 2025/26 = 107, ...)
ARCHIVE_ID_2026 = 109
CURRENT_SEASON = "2026/27"
FIRST_SEASON = "2015/16"

MONTHS = {
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5, "czerwca": 6,
    "lipca": 7, "sierpnia": 8, "września": 9, "października": 10, "listopada": 11, "grudnia": 12,
}

PLAYER_LINK = re.compile(r"wystepy\.php\?id=(\d+)")
# Rozegrane mecze są linkowane z wynikiem jako treścią linku, np. <a href="/mecz.php?id_mecz=2113301" ...>3-0</a>
PLAYED_MATCH_LINK = re.compile(r'href="/?mecz\.php\?id_mecz=(\d+)"[^>]*>\s*\d+\s*-\s*\d+\s*</a>')


@dataclass
class Appearance:
    player_id: int
    name: str
    side: str            # home | away
    is_starter: bool
    row_index: int       # wiersz składu 1–11 (rezerwowy dziedziczy wiersz zmienianego)
    minute_in: int
    minute_out: int = 90
    yellow: int = 0
    red: int = 0
    goals: int = 0

    @property
    def minutes(self) -> int:
        played = self.minute_out - self.minute_in
        return max(played, 1) if not self.is_starter else max(played, 0)


@dataclass
class Goal:
    scorer: str
    minute: int
    side: str
    own_goal: bool


@dataclass
class MatchReport:
    ninetymin_id: int
    season: str
    round: int | None
    kickoff_utc: str
    home: str
    away: str
    hg: int
    ag: int
    referee: str | None
    goals: list[Goal] = field(default_factory=list)
    players: list[Appearance] = field(default_factory=list)


# ---------------------------------------------------------------- pobieranie


class NinetyMin:
    """Klient z cache: strona pobrana raz nie jest pobierana ponownie (chyba że refresh=True)."""

    def __init__(self, delay: float = DELAY_SECONDS):
        self._client = httpx.Client(base_url=BASE_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
        self._delay = delay
        self._last_request = 0.0
        self.requests = 0

    def get(self, path: str, cache_name: str, refresh: bool = False) -> str:
        cached = RAW_DIR / cache_name
        if cached.exists() and not refresh:
            return cached.read_text(encoding="utf-8")
        wait = self._delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        resp = self._get_with_retry(path)
        html = resp.content.decode("iso-8859-2", errors="replace")
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        cached.write_text(html, encoding="utf-8")
        return html

    def _get_with_retry(self, path: str) -> httpx.Response:
        """Ponawia zapytanie przy błędzie sieci lub serwera z rosnącym odstępem (zanik sieci, uśpienie komputera)."""
        for attempt, pause in enumerate(RETRY_PAUSES + [None]):
            try:
                resp = self._client.get(path)
                self._last_request = time.monotonic()
                self.requests += 1
                if resp.status_code < 500:
                    resp.raise_for_status()
                    return resp
                error = f"HTTP {resp.status_code}"
            except httpx.TransportError as e:
                error = repr(e)
            if pause is None:
                raise RuntimeError(f"90minut.pl niedostępny po {attempt + 1} próbach: {error}")
            print(f"  błąd ({error}), ponowienie za {pause} s", flush=True)
            time.sleep(pause)

    def season_page(self, season: str, refresh: bool = False) -> str:
        start = int(season[:4])
        archive_id = ARCHIVE_ID_2026 - 2 * (2026 - start)
        archive = self.get(f"/archsezon.php?id_sezon={archive_id}", f"archsezon_{archive_id}.html", refresh)
        league_path = find_ekstraklasa_link(archive, season)
        league_id = re.search(r"liga(\d+)\.html", league_path).group(1)
        return self.get(league_path, f"liga_{league_id}.html", refresh)

    def match_page(self, ninetymin_id: int) -> str:
        return self.get(f"/mecz.php?id_mecz={ninetymin_id}", f"mecz_{ninetymin_id}.html")


# ---------------------------------------------------------------- parsowanie


def find_ekstraklasa_link(archive_html: str, season: str) -> str:
    """Link do strony Ekstraklasy z archiwum sezonu (pomija ligi kobiet i młodzieżowe)."""
    full = f"{season[:4]}/{int(season[:4]) + 1}"
    soup = BeautifulSoup(archive_html, "html.parser")
    for a in soup.find_all("a", href=re.compile(r"/liga/\d+/liga\d+\.html")):
        text = a.get_text(" ", strip=True)
        if "Ekstraklasa" in text and full in text and "kobiet" not in text.lower():
            return a["href"]
    raise ValueError(f"Brak linku do Ekstraklasy {full} w archiwum sezonu")


def parse_season(html: str) -> list[int]:
    """ID relacji rozegranych meczów ze strony sezonu (bez powtórzeń, w kolejności występowania)."""
    seen: dict[int, None] = {}
    for m in PLAYED_MATCH_LINK.finditer(html):
        seen.setdefault(int(m.group(1)), None)
    return list(seen)


def season_team_names(html: str) -> set[str]:
    """Nazwy drużyn z tytułów linków do meczów: title="Lech Poznań 3-0 Piast Gliwice"."""
    names = set()
    for home, away in re.findall(r'title="([^"]+?) \d+-\d+ ([^"]+?)"', html):
        names.update((home, away))
    return names


def unknown_teams(html: str) -> set[str]:
    unknown = set()
    for name in season_team_names(html):
        try:
            teams.resolve(name)
        except KeyError:
            unknown.add(name)
    return unknown


def _kickoff_utc(text: str) -> str:
    """'9 sierpnia 2026, 17:30' (czas polski) -> ISO w UTC."""
    m = re.search(r"(\d{1,2}) (\w+) (\d{4})(?:, (\d{1,2}):(\d{2}))?", text)
    if not m or m.group(2) not in MONTHS:
        raise ValueError(f"Nie rozpoznano daty: {text!r}")
    day, month, year = int(m.group(1)), MONTHS[m.group(2)], int(m.group(3))
    hour, minute = (int(m.group(4)), int(m.group(5))) if m.group(4) else (0, 0)
    local = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Europe/Warsaw"))
    return local.astimezone(timezone.utc).isoformat(timespec="minutes")


def _cards(player_link: Tag) -> tuple[int, int]:
    """Kartki to obrazki tuż za nazwiskiem (do następnego zawodnika w komórce)."""
    yellow = red = 0
    for sib in player_link.next_siblings:
        if isinstance(sib, Tag):
            if sib.name == "a" or (sib.name == "img" and "sub" in sib.get("src", "")):
                break
            if sib.name == "img":
                alt, src = sib.get("alt", ""), sib.get("src", "")
                if "CK" in alt or "red" in src:
                    red += 1
                elif "ŻK" in alt or "yel" in src:
                    yellow += 1
    return yellow, red


def _parse_cell(cell: Tag, side: str, row_index: int) -> list[Appearance]:
    """Komórka składu: zawodnik wyjściowy, a po nim ewentualne zmiany ('56 (99) Nazwisko')."""
    chain: list[Appearance] = []
    for a in cell.find_all("a", href=PLAYER_LINK):
        prev_tag = a.find_previous_sibling()
        is_sub = bool(chain) and prev_tag is not None and prev_tag.name == "img" and "sub" in prev_tag.get("src", "")
        name = re.sub(r"^\(\d+\)\s*", "", a.get_text(" ", strip=True))
        yellow, red = _cards(a)
        if is_sub:
            minute_text = a.previous_sibling if isinstance(a.previous_sibling, str) else ""
            m = re.search(r"(\d+)\s*$", minute_text.strip())
            minute_in = int(m.group(1)) if m else 90
            chain[-1].minute_out = minute_in
        else:
            minute_in = 0
        chain.append(Appearance(
            player_id=int(PLAYER_LINK.search(a["href"]).group(1)), name=name, side=side,
            is_starter=not is_sub, row_index=row_index, minute_in=minute_in, yellow=yellow, red=red,
        ))
    return chain


def parse_match(html: str, ninetymin_id: int) -> MatchReport:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    header = re.search(r"Ekstraklasa (\d{4})/(\d{4})(?: - Kolejka (\d+))?", text)
    if not header:
        raise ValueError(f"Mecz {ninetymin_id} nie jest meczem Ekstraklasy")
    season = f"{header.group(1)}/{header.group(2)[-2:]}"

    date_img = soup.find("img", src=re.compile(r"data\.gif"))
    header_td = date_img.find_parent("td")
    referee_link = header_td.find("a", href=re.compile(r"sedzia"))

    score_tag = soup.find("nobr", string=re.compile(r"^\s*\d+\s*-\s*\d+\s*$"))
    if score_tag is None:
        raise ValueError(f"Mecz {ninetymin_id} nie ma wyniku (nierozegrany lub walkower)")
    hg, ag = (int(x) for x in re.findall(r"\d+", score_tag.get_text()))
    score_td = score_tag.find_parent("td")
    home = score_td.find_previous_sibling("td").get_text(" ", strip=True)
    away = score_td.find_next_sibling("td").get_text(" ", strip=True)

    report = MatchReport(
        ninetymin_id=ninetymin_id, season=season,
        round=int(header.group(3)) if header.group(3) else None,
        kickoff_utc=_kickoff_utc(header_td.get_text(" ", strip=True)),
        home=home, away=away, hg=hg, ag=ag,
        # "Patryk Gryckiewicz (Toruń)" -> bez miasta
        referee=re.sub(r"\s*\(.*\)$", "", referee_link.get_text(" ", strip=True)) if referee_link else None,
    )

    # Gol: ikona goal.gif; gol samobójczy: own.gif i dopisek "(s)" – zaliczany drużynie z tej strony wiersza
    for img in soup.find_all("img", src=re.compile(r"(goal|own)\.gif")):
        td = img.find_parent("td")
        cells = td.find_parent("tr").find_all("td", recursive=False)
        side = "home" if cells.index(td) == 0 else "away"
        m = re.match(r"(.+?)\s+(\d+)(?:\+\d+)?\s*(\(.*\))?$", td.get_text(" ", strip=True))
        if m:
            own = "own" in img["src"] or (m.group(3) or "") in ("(s)", "(sam.)")
            report.goals.append(Goal(m.group(1), int(m.group(2)), side, own))

    row_index = 0
    for row in soup.find_all("tr", attrs={"height": "20"}):
        cells = row.find_all("td", attrs={"width": "45%"})
        if len(cells) != 2 or not row.find("a", href=PLAYER_LINK):
            continue
        row_index += 1
        for side, cell in zip(("home", "away"), cells):
            report.players.extend(_parse_cell(cell, side, row_index))

    _assign_goals(report)
    return report


def _assign_goals(report: MatchReport) -> None:
    """Strzelców podaje się z nazwiska – przypisujemy gole do zawodników ze składu strony strzelającej."""
    for goal in report.goals:
        if goal.own_goal:
            continue
        candidates = [p for p in report.players if p.side == goal.side]
        key = teams.normalize(goal.scorer)
        match = next((p for p in candidates if teams.normalize(p.name) == key), None)
        if match is None:  # np. inna pisownia imienia – porównujemy nazwiska
            last = key.split()[-1]
            same_last = [p for p in candidates if teams.normalize(p.name).split()[-1] == last]
            match = same_last[0] if len(same_last) == 1 else None
        if match:
            match.goals += 1


# ---------------------------------------------------------------- zapis


def save_report(conn: sqlite3.Connection, r: MatchReport) -> int:
    home_id, away_id = teams.resolve(r.home), teams.resolve(r.away)
    row = conn.execute("SELECT id FROM match WHERE ninetymin_id = ?", (r.ninetymin_id,)).fetchone()
    match_id = row["id"] if row else find_match(conn, home_id, away_id, r.kickoff_utc)
    if match_id is None:
        match_id = conn.execute(
            """INSERT INTO match (season, competition, kickoff_utc, home_id, away_id, hg, ag, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'finished')""",
            (r.season, config.LEAGUE, r.kickoff_utc, home_id, away_id, r.hg, r.ag),
        ).lastrowid
    else:
        existing = conn.execute("SELECT hg, ag FROM match WHERE id = ?", (match_id,)).fetchone()
        if existing["hg"] is not None and (existing["hg"], existing["ag"]) != (r.hg, r.ag):
            print(f"  UWAGA: wynik {r.home}–{r.away} różni się od football-data: "
                  f"{existing['hg']}:{existing['ag']} vs {r.hg}:{r.ag}")
    conn.execute(
        """UPDATE match SET ninetymin_id = ?, round = ?, referee = ?,
               hg = COALESCE(hg, ?), ag = COALESCE(ag, ?), status = 'finished' WHERE id = ?""",
        (r.ninetymin_id, r.round, r.referee, r.hg, r.ag, match_id),
    )

    team_of = {"home": home_id, "away": away_id}
    for p in r.players:
        conn.execute(
            """INSERT INTO player (id, team_id, name) VALUES (?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET team_id = excluded.team_id, name = excluded.name""",
            (p.player_id, team_of[p.side], p.name),
        )
        conn.execute(
            """INSERT OR REPLACE INTO lineup
               (match_id, player_id, team_id, source, is_starter, row_index, minutes, goals, yellow, red, created_at)
               VALUES (?, ?, ?, 'official', ?, ?, ?, ?, ?, ?, ?)""",
            (match_id, p.player_id, team_of[p.side], int(p.is_starter), p.row_index, p.minutes,
             p.goals, p.yellow, p.red, r.kickoff_utc),
        )
    cards = {side: (sum(p.yellow for p in r.players if p.side == side), sum(p.red for p in r.players if p.side == side))
             for side in ("home", "away")}
    conn.execute(
        "INSERT OR REPLACE INTO match_stats (match_id, yellow_h, red_h, yellow_a, red_a) VALUES (?, ?, ?, ?, ?)",
        (match_id, *cards["home"], *cards["away"]),
    )
    return match_id


def update_positions(conn: sqlite3.Connection) -> None:
    """Pozycja zawodnika z kolejności w składach: wiersz 1 = bramkarz, 2–5 obrona, 6–9 pomoc, 10–11 atak."""
    def position(row_index: int) -> str:
        return "G" if row_index == 1 else "D" if row_index <= 5 else "M" if row_index <= 9 else "F"

    rows = conn.execute(
        "SELECT player_id, row_index FROM lineup WHERE source = 'official' AND is_starter = 1 AND row_index <= 11"
    ).fetchall()
    votes: dict[int, Counter] = {}
    for r in rows:
        votes.setdefault(r["player_id"], Counter())[position(r["row_index"])] += 1
    conn.executemany("UPDATE player SET position = ? WHERE id = ?",
                     [(c.most_common(1)[0][0], pid) for pid, c in votes.items()])


def all_seasons() -> list[str]:
    first, last = int(FIRST_SEASON[:4]), int(CURRENT_SEASON[:4])
    return [f"{y}/{(y + 1) % 100:02d}" for y in range(first, last + 1)]


def collect(seasons: list[str], refresh_season_pages: bool = False, limit: int | None = None) -> None:
    client = NinetyMin()
    with db.connect() as conn:
        db.init_db(conn)
        pages = {season: client.season_page(season, refresh=refresh_season_pages) for season in seasons}
        unknown = set().union(*(unknown_teams(html) for html in pages.values()))
        if unknown:
            raise SystemExit(f"Nierozpoznane drużyny – dopisz aliasy w typerai/teams.py: {sorted(unknown)}")
        for season in seasons:
            ids = parse_season(pages[season])
            done = {r["ninetymin_id"] for r in conn.execute("SELECT ninetymin_id FROM match WHERE ninetymin_id IS NOT NULL")}
            todo = [i for i in ids if i not in done][:limit]
            print(f"{season}: relacji {len(ids)}, do pobrania {len(todo)}", flush=True)
            for n, mid in enumerate(todo, 1):
                try:
                    report = parse_match(client.match_page(mid), mid)
                except ValueError as e:  # mecz spoza Ekstraklasy, przełożony bez relacji itp.
                    print(f"  pominięto {mid}: {e}")
                    continue
                if not report.players:   # mecz jeszcze nierozegrany
                    continue
                save_report(conn, report)
                conn.commit()  # krótkie transakcje – inne procesy mogą w tym czasie pisać do bazy
                if n % 25 == 0:
                    print(f"  {n}/{len(todo)} (zapytań: {client.requests})", flush=True)
            conn.commit()
        update_positions(conn)
        conn.commit()
    print(f"Gotowe. Zapytań do 90minut.pl: {client.requests}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seasons", nargs="+", help="np. 2024/25 2025/26; domyślnie wszystkie od 2015/16")
    parser.add_argument("--current", action="store_true", help="tylko nowe mecze bieżącego sezonu")
    parser.add_argument("--limit", type=int, help="maks. liczba meczów na sezon (do testów)")
    args = parser.parse_args()
    if args.current:
        collect([CURRENT_SEASON], refresh_season_pages=True, limit=args.limit)
    else:
        collect(args.seasons or all_seasons(), limit=args.limit)


if __name__ == "__main__":
    main()
