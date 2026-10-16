import random

import pytest

from app.games.toolate import CATEGORIES, DEFAULT_LETTERS, TooLateGame


def make_game(letters=("A", "B", "C", "D", "E"), rounds=2):
    g = TooLateGame.from_options(
        ["Ana", "Leo"], {"letters": list(letters), "rounds": rounds, "turnSeconds": 10}, rng=random.Random(2)
    )
    g.start()
    return g


def test_options_are_validated():
    with pytest.raises(ValueError):
        TooLateGame.from_options(["Ana"], {"letters": ["A", "B"]}, random.Random())
    with pytest.raises(ValueError):
        TooLateGame.from_options(["Ana"], {"turnSeconds": 7}, random.Random())
    with pytest.raises(ValueError):
        TooLateGame.from_options(["Ana"], {"letters": "ABCDE"}, random.Random())
    g = TooLateGame.from_options(["Ana"], {"letters": ["e", "a", "Ñ", "a", "zz", "c", "b"]}, random.Random())
    assert g.letters == ["A", "B", "C", "E", "Ñ"]  # orden del alfabeto, sin repetidas ni basura
    assert TooLateGame.from_options(["Ana"], {}, random.Random()).letters == DEFAULT_LETTERS


def test_ready_phase_allows_new_category_then_turns_alternate():
    g = make_game()
    assert g.phase == "ready" and g.category in CATEGORIES
    first = g.category
    g.reroll()
    assert g.category != first
    assert g.snapshot()["turn"] == "Ana"

    g.begin()
    assert g.timer_key == ("turn", 1)
    with pytest.raises(ValueError):
        g.pick("Leo", "A")  # no es su turno
    g.pick("Ana", "a")
    assert g.current == "Leo" and g.timer_key == ("turn", 2)  # el reloj se reinicia
    with pytest.raises(ValueError):
        g.pick("Leo", "A")  # ya salió
    with pytest.raises(ValueError):
        g.pick("Leo", "Z")  # no está en el tablero
    with pytest.raises(ValueError):
        g.reroll()


def test_timeout_gives_point_to_the_other_player():
    g = make_game()
    g.begin()
    g.pick("Ana", "A")
    g.on_timeout()  # a Leo se le acabó el tiempo
    assert g.phase == "round_over"
    assert g.result == {"type": "timeout", "loser": "Leo"}
    assert g.scores == {"Ana": 1, "Leo": 0}
    assert g.timer_key is None

    g.next_round()
    assert g.phase == "ready" and g.round == 2
    assert g.snapshot()["turn"] == "Leo"  # empieza el otro
    assert g.used == []


def test_completing_the_board_gives_both_a_point():
    g = make_game(rounds=1)
    g.begin()
    for player, letter in zip(["Ana", "Leo", "Ana", "Leo", "Ana"], "ABCDE"):
        g.pick(player, letter)
    assert g.result == {"type": "completed"}
    assert g.scores == {"Ana": 1, "Leo": 1}
    g.next_round()
    assert g.phase == "finished"
    assert g.history[0]["letters"] == 5


def test_no_vale_returns_letter_and_turn():
    g = make_game()
    g.begin()
    g.pick("Ana", "C")
    g.undo()
    assert g.used == [] and g.current == "Ana"
    assert g.timer_key == ("turn", 3)
    with pytest.raises(ValueError):
        g.undo()


def test_categories_do_not_repeat_until_exhausted():
    g = TooLateGame(["Ana"], rounds=10, rng=random.Random(5))
    seen = set()
    for _ in range(len(CATEGORIES)):
        seen.add(g._new_category())
    assert seen == set(CATEGORIES)
