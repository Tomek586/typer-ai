import inspect

from typerai.chat import cli, tools


def test_tools_keep_signatures_for_function_calling():
    # Gemini buduje opis narzędzia z sygnatury i docstringu – opakowanie nie może ich zgubić
    for fn in tools.TOOLS:
        traced = cli._traced(fn)
        assert inspect.signature(traced) == inspect.signature(fn)
        assert traced.__doc__ == fn.__doc__ and traced.__name__ == fn.__name__


def test_guard_output_removes_guarantees_and_adds_risk():
    out = cli.guard_output("To pewniak, gwarancja wygranej!")
    answer, note = out.split(cli.RISK_NOTE.strip()[:2], 1)
    assert "pewniak" not in answer.lower() and "gwarancja" not in answer.lower()
    assert out.endswith(cli.RISK_NOTE)


def test_harm_signals():
    assert cli.HARM.search("Przegrałem, muszę się odegrać")
    assert not cli.HARM.search("Co sądzisz o meczu Legii?")


def test_przelicz_kurs():
    r = tools.przelicz_kurs([2.0, 2.0])
    assert r["marza"] == 0 and r["bez_marzy_shin"] == [0.5, 0.5]
