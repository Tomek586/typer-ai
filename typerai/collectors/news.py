"""Kolektor newsów (docs/05, sekcja 5.2, kroki 1–2): RSS → pełny tekst → deduplikacja → NEWS_ARTICLE.

- kanały RSS z config.NEWS_SOURCES,
- artykuł pobieramy tylko wtedy, gdy tytuł lub zajawka wspomina drużynę obecnego sezonu (wstępny filtr
  z config.NEWS_TEAM_PATTERNS) – mniej obciążenia serwisów i mniej zapytań do LLM,
- przed każdym pobraniem sprawdzamy robots.txt; między pobraniami z jednego serwisu przerwa,
- tekst bez menu i reklam (trafilatura); krótszy niż NEWS["min_chars"] → zostaje zajawka z RSS,
- duplikaty: SimHash tekstu, odległość Hamminga ≤ 3 względem artykułów z ostatnich 48 h.

    .venv/Scripts/python -m typerai.collectors.news
"""

import calendar
import hashlib
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import feedparser
import httpx
import trafilatura

from typerai import config, db

USER_AGENT = "TyperAI-student-project"
TEAM_PATTERNS = {team: re.compile(p) for team, p in config.NEWS_TEAM_PATTERNS.items()}
WORD = re.compile(r"\w+", re.UNICODE)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="minutes")


def team_mentions(text: str, teams: set[str] | None = None) -> list[str]:
    """Drużyny, których nazwa (w dowolnej odmianie) pada w tekście."""
    return [t for t, p in TEAM_PATTERNS.items() if (teams is None or t in teams) and p.search(text)]


def simhash(text: str, bits: int = 64) -> int:
    """SimHash z trójek słów: podobne teksty mają hash różniący się na kilku bitach."""
    words = WORD.findall(text.lower())
    shingles = [" ".join(words[i:i + 3]) for i in range(max(1, len(words) - 2))]
    weights = [0] * bits
    for s in shingles:
        h = int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big")
        for b in range(bits):
            weights[b] += 1 if h >> b & 1 else -1
    return sum(1 << b for b in range(bits) if weights[b] > 0)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def current_teams(conn: sqlite3.Connection) -> set[str]:
    season = conn.execute("SELECT season FROM match ORDER BY kickoff_utc DESC LIMIT 1").fetchone()
    if not season:
        return set(TEAM_PATTERNS)
    return {t for row in conn.execute("SELECT home_id, away_id FROM match WHERE season = ?", season) for t in row}


class Fetcher:
    """Pobieranie z poszanowaniem robots.txt i przerwą między zapytaniami do jednego serwisu."""

    def __init__(self, client: httpx.Client | None = None, delay: float = config.NEWS["request_delay_s"], sleep=time.sleep):
        self.client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)
        self.delay, self.sleep = delay, sleep
        self.robots: dict[str, RobotFileParser] = {}
        self.last_request: dict[str, float] = {}

    def allowed(self, url: str) -> bool:
        host = "{0.scheme}://{0.netloc}".format(urlsplit(url))
        if host not in self.robots:
            parser = RobotFileParser()
            try:
                r = self.client.get(f"{host}/robots.txt")
                parser.parse(r.text.splitlines() if r.status_code == 200 else [])
            except httpx.HTTPError:
                parser.parse([])
            self.robots[host] = parser
        return self.robots[host].can_fetch(USER_AGENT, url)

    def get(self, url: str) -> httpx.Response:
        host = urlsplit(url).netloc
        wait = self.delay - (time.monotonic() - self.last_request.get(host, -1e9))
        if wait > 0:
            self.sleep(wait)
        self.last_request[host] = time.monotonic()
        return self.client.get(url)


def _published(entry, now: datetime) -> datetime:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(parsed), timezone.utc) if parsed else now


def _clean(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def find_duplicate(conn: sqlite3.Connection, fingerprint: int, published: datetime) -> int | None:
    since = _iso(published - timedelta(hours=config.NEWS["dedup_hours"]))
    for article_id, other in conn.execute(
            "SELECT id, simhash FROM news_article WHERE published_at >= ? AND duplicate_of IS NULL", (since,)):
        if other and hamming(fingerprint, int(other, 16)) <= config.NEWS["simhash_max_distance"]:
            return article_id
    return None


def collect(conn: sqlite3.Connection, now: datetime | None = None, fetcher: Fetcher | None = None,
            sources: list[dict] | None = None) -> dict:
    """Jedno przejście po wszystkich kanałach. Zwraca liczniki do logu harmonogramu."""
    now = now or datetime.now(timezone.utc)
    fetcher = fetcher or Fetcher()
    teams = current_teams(conn)
    stats = {"pozycji": 0, "zapisanych": 0, "duplikatow": 0, "bez_druzyny": 0, "starych": 0, "zablokowanych": 0,
             "bledow": 0}
    for source in sources or config.NEWS_SOURCES:
        try:
            feed = feedparser.parse(fetcher.get(source["feed"]).content)
        except httpx.HTTPError:
            stats["bledow"] += 1
            continue
        for entry in feed.entries:
            stats["pozycji"] += 1
            url = entry.get("link")
            if not url or conn.execute("SELECT 1 FROM news_article WHERE url = ?", (url,)).fetchone():
                continue
            published = _published(entry, now)
            if now - published > timedelta(days=config.NEWS["max_age_days"]):
                stats["starych"] += 1
                continue
            title = _clean(entry.get("title", ""))
            summary = _clean(entry.get("summary", ""))
            if not team_mentions(f"{title} {summary}", teams):
                stats["bez_druzyny"] += 1
                continue
            text = summary
            if fetcher.allowed(url):
                try:
                    r = fetcher.get(url)
                    if r.status_code == 200:
                        text = trafilatura.extract(r.text, include_comments=False, include_tables=False) or summary
                except httpx.HTTPError:
                    stats["bledow"] += 1
            else:
                stats["zablokowanych"] += 1
            if len(text) < config.NEWS["min_chars"] and len(summary) > len(text):
                text = summary
            fingerprint = simhash(f"{title} {text}")
            duplicate = find_duplicate(conn, fingerprint, published)
            conn.execute(
                """INSERT INTO news_article (url, source, reliability, published_at, fetched_at, title, text, simhash, duplicate_of)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (url, source["name"], source["reliability"], _iso(published), _iso(now), title, text,
                 f"{fingerprint:016x}", duplicate))
            conn.commit()
            stats["zapisanych"] += 1
            stats["duplikatow"] += duplicate is not None
    return stats


def main() -> None:
    conn = db.connect()
    db.init_db(conn)
    print(collect(conn))
    conn.close()


if __name__ == "__main__":
    main()
