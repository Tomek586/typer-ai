import inspect

from typerai.chat import cli, tools


def test_tools_keep_signatures_for_function_calling():
    # Gemini buduje opis narzędzia z sygnatury i docstringu – opakowanie nie może ich zgubić
    for fn in tools.TOOLS:
        traced = cli._traced(fn)
        assert inspect.signature(traced) == inspect.signature(fn)
        assert traced.__doc__ == fn.__doc__ and traced.__name__ == fn.__name__


def test_guard_output_removes_guarantees_and_adds_risk():
    out = cli.guard_output("To pewniak na kurs 2,0, gwarancja wygranej!")
    answer = out[: -len(cli.RISK_NOTE)]
    assert "pewniak" not in answer.lower() and "gwarancja" not in answer.lower()
    assert out.endswith(cli.RISK_NOTE)


def test_harm_signals():
    assert cli.HARM.search("Przegrałem, muszę się odegrać")
    assert not cli.HARM.search("Co sądzisz o meczu Legii?")


def test_przelicz_kurs():
    r = tools.przelicz_kurs([2.0, 2.0])
    assert r["marza"] == 0 and r["bez_marzy_shin"] == [0.5, 0.5]


def test_risk_note_only_for_betting_answers():
    assert cli.guard_output("Dziś grają trzy mecze.") == "Dziś grają trzy mecze."
    assert cli.guard_output("Najlepszy kurs to 2,0.").endswith(cli.RISK_NOTE)


def test_guard_keeps_negated_guarantee():
    text = "Wysokie prawdopodobieństwo nie gwarantuje wygranej."
    assert cli.guard_output(text).startswith(text)
    assert "pewniak" not in cli.guard_output("Mam pewniaka na dziś").split(cli.RISK_NOTE)[0].lower()


class _FakeChat:
    def __init__(self, model, history, fail_code=None):
        self.model, self.history, self.fail_code = model, list(history or []), fail_code

    def send_message(self, q):
        if self.fail_code:
            raise cli.errors.ClientError(self.fail_code, {"error": {"code": self.fail_code, "message": "limit", "status": "X"}})
        self.history.append(q)
        return type("R", (), {"text": f"{self.model}: {q}"})()

    def get_history(self):
        return list(self.history)


def test_session_switches_model_on_quota_and_keeps_history():
    failing = {"m1": None, "m2": 429, "m3": None}
    chats = []

    def factory(client, model, history=None):
        chats.append(_FakeChat(model, history, failing[model]))
        return chats[-1]

    s = cli.ChatSession(client=None, models=["m1", "m2", "m3"], factory=factory)
    assert s.send("pierwsze") == "m1: pierwsze"
    s.chat.fail_code = 429                        # m1 wyczerpał limit
    assert s.send("drugie") == "m3: drugie"       # m2 też bez limitu -> m3
    assert s.model == "m3" and chats[-1].history == ["pierwsze", "drugie"]


class ReadTimeout(Exception):
    pass


def test_session_switches_model_on_timeout():
    def factory(client, model, history=None):
        chat = _FakeChat(model, history)
        if model == "wolny":
            chat.send_message = lambda q: (_ for _ in ()).throw(ReadTimeout("45 s"))
        return chat

    s = cli.ChatSession(client=None, models=["wolny", "szybki"], factory=factory)
    assert s.send("pytanie") == "szybki: pytanie"
