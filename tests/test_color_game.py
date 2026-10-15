import random

import pytest

from app.colors import HSB
from app.games.color import ColorGame


def make_game(rounds=2):
    return ColorGame(["Ana", "Leo"], rounds=rounds, rng=random.Random(42))


def test_full_round_flow():
    g = make_game()
    g.start_round()
    assert g.phase == "memorize" and g.round == 1
    assert g.snapshot()["target"] is not None

    g.begin_guess()
    snap = g.snapshot()
    assert snap["phase"] == "guess"
    assert snap["target"] is None  # el color se oculta mientras adivinan

    assert g.submit("Ana", g.target) is False
    assert g.snapshot()["submitted"] == ["Ana"]
    assert g.snapshot()["guesses"] == {}  # no se filtra el intento del otro
    assert g.submit("Leo", HSB(0, 0, 0)) is True

    g.reveal()
    assert g.phase == "reveal"
    assert g.round_scores["Ana"] == 10
    assert g.totals["Ana"] > g.totals["Leo"]


def test_game_finishes_after_last_round():
    g = make_game(rounds=1)
    g.start_round()
    g.begin_guess()
    g.submit("Ana", HSB(0, 50, 50))
    g.reveal()  # Leo no respondió a tiempo
    assert g.phase == "finished"
    assert g.round_scores["Leo"] == 0
    assert len(g.snapshot()["history"]) == 1
    with pytest.raises(ValueError):
        g.start_round()


def test_cannot_guess_twice_or_out_of_phase():
    g = make_game()
    with pytest.raises(ValueError):
        g.submit("Ana", HSB(0, 0, 0))
    g.start_round()
    with pytest.raises(ValueError):
        g.submit("Ana", HSB(0, 0, 0))  # aún memorizando
    g.begin_guess()
    g.submit("Ana", HSB(0, 0, 0))
    with pytest.raises(ValueError):
        g.submit("Ana", HSB(1, 1, 1))
    with pytest.raises(ValueError):
        g.submit("Intruso", HSB(1, 1, 1))


def test_totals_accumulate_across_rounds():
    g = make_game(rounds=2)
    for _ in range(2):
        g.start_round()
        g.begin_guess()
        g.submit("Ana", g.target)
        g.submit("Leo", g.target)
        g.reveal()
    assert g.totals == {"Ana": 20, "Leo": 20}
    assert g.phase == "finished"
