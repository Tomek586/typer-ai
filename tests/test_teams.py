import pytest

from typerai import teams


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Lech Poznan", "lech"),
        ("Lech Poznań", "lech"),
        ("Kolejorz", "lech"),
        ("Gornik Z.", "gornik-zabrze"),
        ("Gornik Zabrze", "gornik-zabrze"),
        ("LKS Lodz", "lks-lodz"),
        ("ŁKS Łódź", "lks-lodz"),
        ("Wisla", "wisla-krakow"),
        ("Wisla Plock", "wisla-plock"),
        ("Zaglebie", "zaglebie-lubin"),
        ("Zaglebie Sosnowiec", "zaglebie-sosnowiec"),
        ("Termalica B-B.", "termalica"),
        ("Ruch Chorzow", "ruch"),
    ],
)
def test_resolve_known_variants(name, expected):
    assert teams.resolve(name) == expected


def test_unknown_team_raises_with_suggestions():
    with pytest.raises(KeyError, match="Lech Poznań"):
        teams.resolve("Lech Poznn")


def test_normalize_strips_polish_characters():
    assert teams.normalize("Śląsk Wrocław") == "slask wroclaw"
