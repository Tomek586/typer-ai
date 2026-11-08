from typerai.chat import cli, numbers

TOOL = [{"oczekiwane_gole_modelu": {"gospodarz": 2.0, "gosc": 0.82},
         "rynki": [{"zdarzenie": "wygrana gospodarza", "p": 0.649, "kurs_minimalny": 1.59, "najlepszy_kurs": 1.5,
                    "ev": -0.027}],
         "termin": "08.11 20:15", "reguly_typu": "p ≥ 0.52, EV ≥ 3%"}]


def test_answer_with_tool_numbers_passes():
    answer = "Lech 2,00 – 0,82. Wygrana: 64,9% (kurs 1,50, minimalny 1.59, EV -2,7%). Mecz 08.11 o 20:15, próg 52% i 3%."
    assert numbers.unverified(answer, TOOL) == []


def test_invented_numbers_are_caught():
    assert numbers.unverified("Oczekiwane gole 1,85 – 0,85, wygrana 60,1%, BTTS po 1,95.", TOOL) == [1.85, 0.85, 60.1, 1.95]


def test_integers_without_percent_are_ignored():
    assert numbers.unverified("H2H: 3 z 4 meczów, 5 ostatnich spotkań.", TOOL) == []


class _Session:
    """Atrapa rozmowy: przy każdym pytaniu „wywołuje narzędzie” (dopisuje wynik do TOOL_LOG) i zwraca odpowiedź."""

    def __init__(self, answers):
        self.answers, self.sent = list(answers), []

    def send(self, q):
        self.sent.append(q)
        cli.TOOL_LOG.extend(TOOL)
        return self.answers.pop(0)


def test_answer_question_retries_once_then_warns():
    s = _Session(["Wygrana 60,1%, kurs 1,95.", "Wygrana 64,9%, kurs 1,50."])
    assert cli.answer_question(s, "pytanie") == "Wygrana 64,9%, kurs 1,50."
    assert len(s.sent) == 2 and "60.1" in s.sent[1]

    bad = _Session(["Wygrana 60,1%, kurs 1,95.", "Nadal 60,1% i 1,95."])
    assert "nie udało się potwierdzić" in cli.answer_question(bad, "pytanie")

    good = _Session(["Wygrana 64,9%, kurs 1,50."])
    assert cli.answer_question(good, "pytanie") == "Wygrana 64,9%, kurs 1,50." and len(good.sent) == 1
