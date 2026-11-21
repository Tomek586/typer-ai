from datetime import datetime, timezone

import httpx
import pytest

from typerai import db
from typerai.collectors import news

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
ARTICLE = ("Mikael Ishak nie zagra w najbliższym meczu Lecha Poznań. Napastnik doznał urazu mięśnia na treningu "
           "i według klubu będzie pauzował co najmniej dwa tygodnie. Trener musi szukać zastępstwa w ataku. ") * 3


def feed(items):
    body = "".join(f"<item><title>{t}</title><link>{u}</link><description>{d}</description>"
                   f"<pubDate>{p}</pubDate></item>" for t, u, d, p in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'


def make_fetcher(routes, robots="User-agent: *\nDisallow:"):
    def handler(request):
        url = str(request.url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text=robots)
        if url in routes:
            return httpx.Response(200, text=routes[url])
        return httpx.Response(404)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return news.Fetcher(client=client, delay=0, sleep=lambda s: None)


def setup(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    return conn


@pytest.mark.parametrize("text, teams", [
    ("Legia przegrała z Lechem", ["lech", "legia"]),
    ("Lechia Gdańsk awansowała", []),
    ("Ishak nie zagra przeciwko Rakowowi", ["rakow"]),
    ("Wisła Płock pokonała Cracovię", ["cracovia", "wisla-plock"]),
    ("GKS-u Katowice nie stać na transfer", ["gks-katowice"]),
])
def test_team_mentions_handle_polish_inflection(text, teams):
    assert news.team_mentions(text) == teams


def test_simhash_finds_near_duplicates():
    a = news.simhash(ARTICLE)
    b = news.simhash(ARTICLE.replace("dwa tygodnie", "dwa tygodnie."))
    c = news.simhash("Zupełnie inny tekst o transferze bramkarza do klubu z Hiszpanii, bez związku z kontuzją. " * 3)
    assert news.hamming(a, b) <= 3 < news.hamming(a, c)


def test_collect_saves_relevant_articles_and_marks_duplicates(tmp_path):
    conn = setup(tmp_path)
    date = "Sat, 21 Nov 2026 10:00:00 +0000"
    routes = {
        "https://a.pl/rss": feed([("Ishak kontuzjowany, Lech bez napastnika", "https://a.pl/1", "Lech traci Ishaka", date),
                                  ("Tenis: finał turnieju", "https://a.pl/2", "Wyniki tenisa", date)]),
        "https://b.pl/rss": feed([("Lech bez Ishaka", "https://b.pl/9", "Przedruk", date)]),
        "https://a.pl/1": f"<html><body><article><p>{ARTICLE}</p></article></body></html>",
        "https://b.pl/9": f"<html><body><article><p>{ARTICLE}</p></article></body></html>",
    }
    sources = [{"name": "a", "feed": "https://a.pl/rss", "reliability": "medialne"},
               {"name": "b", "feed": "https://b.pl/rss", "reliability": "medialne"}]
    stats = news.collect(conn, NOW, make_fetcher(routes), sources)
    assert (stats["zapisanych"], stats["bez_druzyny"], stats["duplikatow"]) == (2, 1, 1)
    first, second = conn.execute("SELECT id, text, duplicate_of FROM news_article ORDER BY id").fetchall()
    assert "Ishak nie zagra" in first[1] and first[2] is None
    assert second[2] == first[0]
    # drugie przejście niczego nie dubluje
    assert news.collect(conn, NOW, make_fetcher(routes), sources)["zapisanych"] == 0


def test_collect_respects_robots_and_skips_old_articles(tmp_path):
    conn = setup(tmp_path)
    routes = {
        "https://a.pl/rss": feed([("Legia: nowy trener", "https://a.pl/x", "Legia ogłosiła trenera", "Sat, 21 Nov 2026 10:00:00 +0000"),
                                  ("Legia: stary tekst", "https://a.pl/y", "Legia sprzed miesiąca", "Wed, 21 Oct 2026 10:00:00 +0000")]),
        "https://a.pl/x": f"<html><body><p>{ARTICLE}</p></body></html>",
    }
    stats = news.collect(conn, NOW, make_fetcher(routes, robots="User-agent: *\nDisallow: /x"),
                         [{"name": "a", "feed": "https://a.pl/rss", "reliability": "medialne"}])
    assert (stats["zapisanych"], stats["zablokowanych"], stats["starych"]) == (1, 1, 1)
    # strona zablokowana w robots.txt: zostaje tylko zajawka z RSS
    assert conn.execute("SELECT text FROM news_article").fetchone()[0] == "Legia ogłosiła trenera"
