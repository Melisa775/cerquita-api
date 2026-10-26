import random
from collections import Counter

import pytest

from app.games.trivia import CATEGORIES, CROWN, TriviaGame, questions


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FixedRng(random.Random):
    """Ruleta controlada: choice devuelve lo que se le pida."""

    def __init__(self, picks):
        super().__init__(3)
        self.picks = list(picks)

    def choice(self, seq):
        if self.picks and self.picks[0] in seq:
            return self.picks.pop(0)
        return super().choice(seq)


def make(mode="coronas", goal=6, picks=(), total=10):
    clock = Clock()
    g = TriviaGame(["Ana", "Leo"], mode=mode, goal=goal, total_questions=total, seconds=20, rng=FixedRng(picks), clock=clock)
    g.start()
    return g, clock


def spin_to_question(g, player):
    g.spin(player)
    assert g.phase == "spinning" and g.timer_key[0] == "spinning"
    g.on_timeout()


def right(g):
    return g.question["answer"]


def wrong(g):
    return (g.question["answer"] + 1) % 4


def test_bank_has_enough_questions_per_category_and_level():
    bank = questions()
    for c in CATEGORIES:
        for level in ("facil", "medio", "dificil"):
            assert sum(1 for q in bank if q["category"] == c and q["level"] == level) >= 18, (c, level)
    assert len({q["id"] for q in bank}) == len(bank)
    assert len({q["question"] for q in bank}) == len(bank)
    for q in bank:
        assert len(q["options"]) == 4 and len(set(q["options"])) == 4 and q["answer"] == 0


def test_options_are_shuffled_but_answer_tracks_them():
    g, _ = make(picks=["ciencia"])
    spin_to_question(g, "Ana")
    q = g.question
    raw = next(r for r in questions() if r["id"] == q["id"])
    assert q["options"][q["answer"]] == raw["options"][0]
    assert sorted(q["options"]) == sorted(raw["options"])


def test_snapshot_hides_answer_until_reveal():
    g, _ = make(picks=["arte"])
    spin_to_question(g, "Ana")
    snap = g.snapshot("Leo")
    assert snap["phase"] == "question" and "answer" not in snap["question"]
    g.answer("Ana", right(g))
    assert g.phase == "reveal"
    assert g.snapshot("Leo")["question"]["answer"] == g.question["answer"]


def test_only_current_player_spins_and_answers():
    g, _ = make(picks=["historia"])
    with pytest.raises(ValueError, match="girar a Ana"):
        g.spin("Leo")
    spin_to_question(g, "Ana")
    with pytest.raises(ValueError, match="Responde Ana"):
        g.answer("Leo", 0)
    with pytest.raises(ValueError):
        g.answer("Ana", 7)


def test_wrong_answer_passes_the_turn_and_resets_streak():
    g, _ = make(picks=["deportes", "deportes"])
    spin_to_question(g, "Ana")
    g.answer("Ana", right(g))
    g.next_round()
    assert g.current == "Ana" and g.streak["Ana"] == 1
    spin_to_question(g, "Ana")
    g.answer("Ana", wrong(g))
    g.next_round()
    assert g.current == "Leo" and g.streak["Ana"] == 0 and g.phase == "spin"


def test_three_in_a_row_unlocks_a_crown():
    g, _ = make(picks=["geografia"] * 3)
    for _ in range(3):
        spin_to_question(g, "Ana")
        g.answer("Ana", right(g))
        g.next_round()
    assert g.phase == "crown_pick"
    with pytest.raises(ValueError):
        g.spin("Ana")
    g.choose_crown("Ana", "arte")
    assert g.for_crown and g.question["category"] == "arte"
    g.answer("Ana", right(g))
    assert g.crowns["Ana"] == ["arte"] and g.last["crownWon"] == "arte" and g.streak["Ana"] == 0
    g.next_round()
    assert g.phase == "spin" and g.current == "Ana"
    # una corona ganada ya no se puede volver a elegir
    g.phase = "crown_pick"
    with pytest.raises(ValueError, match="no está disponible"):
        g.choose_crown("Ana", "arte")


def test_landing_on_crown_slot_lets_you_pick():
    g, _ = make(picks=[CROWN])
    g.spin("Ana")
    assert g.slot == CROWN
    g.on_timeout()
    assert g.phase == "crown_pick"


def test_failed_crown_question_passes_turn():
    g, _ = make(picks=[CROWN])
    spin_to_question(g, "Ana")
    g.choose_crown("Ana", "ciencia")
    g.answer("Ana", wrong(g))
    g.next_round()
    assert g.crowns["Ana"] == [] and g.current == "Leo"


def test_timeout_counts_as_wrong():
    g, _ = make(picks=["arte"])
    spin_to_question(g, "Ana")
    g.on_timeout()
    assert g.phase == "reveal" and g.last["results"]["Ana"]["choice"] is None
    g.next_round()
    assert g.current == "Leo"


def test_reaching_the_goal_wins():
    g, _ = make(goal=3, picks=[CROWN] * 3)
    for cat in ("arte", "historia", "ciencia"):
        spin_to_question(g, "Ana")
        g.choose_crown("Ana", cat)
        g.answer("Ana", right(g))
        g.next_round()
    assert g.phase == "finished" and g.winner == "Ana" and g.scores["Ana"] == 3
    assert len(g.snapshot()["history"]) == 3


def test_duel_both_answer_and_speed_matters():
    g, clock = make(mode="duelo", total=10, picks=["ciencia"])
    assert g.current is None
    g.spin("Leo")  # en duelo cualquiera gira
    g.on_timeout()
    clock.t += 1
    g.answer("Ana", right(g))
    assert g.phase == "question" and g.snapshot("Leo")["answered"] == ["Ana"]
    assert g.snapshot("Leo")["myChoice"] is None and g.snapshot("Ana")["myChoice"] == right(g)
    with pytest.raises(ValueError, match="Ya respondiste"):
        g.answer("Ana", 0)
    clock.t += 9
    g.answer("Leo", right(g))
    assert g.phase == "reveal"
    res = g.last["results"]
    assert res["Ana"]["points"] == 98 and res["Leo"]["points"] == 75
    assert g.scores == {"Ana": 98, "Leo": 75}


def test_duel_finishes_after_n_questions():
    g, _ = make(mode="duelo", total=10)
    for _ in range(10):
        g.spin("Ana")
        g.on_timeout()
        g.answer("Ana", right(g))
        g.answer("Leo", wrong(g))
        g.next_round()
    assert g.phase == "finished" and g.winner == "Ana" and g.correct == {"Ana": 10, "Leo": 0}


def test_questions_do_not_repeat_within_a_category():
    g, _ = make(mode="duelo", total=20)
    n = sum(1 for q in questions() if q["category"] == "arte")
    seen = [g._draw("arte")["id"] for _ in range(n)]
    assert len(set(seen)) == n


def test_options_validation():
    rng = random.Random()
    with pytest.raises(ValueError):
        TriviaGame.from_options(["Ana"], {}, rng)
    with pytest.raises(ValueError):
        TriviaGame.from_options(["Ana", "Leo"], {"mode": "x"}, rng)
    with pytest.raises(ValueError):
        TriviaGame.from_options(["Ana", "Leo"], {"goal": 4}, rng)
    g = TriviaGame.from_options(["Ana", "Leo"], {"mode": "duelo", "questions": 15, "seconds": 30}, rng)
    assert g.total_questions == 15 and g.seconds == 30


def test_level_filters_questions():
    g = TriviaGame(["Ana", "Leo"], level="dificil", rng=random.Random(2))
    assert g.bank and all(q["level"] == "dificil" for q in g.bank)
    g.start()
    g.spin("Ana")
    g.on_timeout()
    if g.phase == "question":
        assert g.snapshot("Leo")["question"]["level"] == "dificil"
    with pytest.raises(ValueError):
        TriviaGame.from_options(["Ana", "Leo"], {"level": "imposible"}, random.Random())


def test_double_taps_are_ignored_quietly():
    g, _ = make(mode="duelo", picks=["arte"])
    g.handle("Ana", {"type": "tv_spin", "at": 0})
    g.handle("Leo", {"type": "tv_spin", "at": 0})  # llegó tarde: no pasa nada
    assert g.spin_id == 1 and g.phase == "spinning"
    g.on_timeout()
    g.answer("Ana", right(g))
    g.answer("Leo", right(g))
    g.handle("Ana", {"type": "next_round", "at": 1})
    g.handle("Leo", {"type": "next_round", "at": 1})  # también tarde
    assert g.phase == "spin" and g.asked == 1
