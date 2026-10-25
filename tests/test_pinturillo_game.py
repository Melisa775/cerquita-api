import random

import pytest

from app.games.pinturillo import HINT_AT, PinturilloGame, word_list


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make(rounds=1, words=("casa", "gato", "perro caliente")):
    clock = Clock()
    g = PinturilloGame(["Ana", "Leo"], draw_seconds=60, rounds=rounds, rng=random.Random(2), clock=clock, words=list(words))
    g.start()
    return g, clock


def choose(g, word):
    g.choose(g.drawer, g.choices.index(word))


def test_word_list_is_loaded():
    words = word_list()
    assert len(words) > 150 and "arepa" in words and all(w == w.strip() for w in words)


def test_only_the_drawer_sees_the_choices_and_the_word():
    g, _ = make()
    assert g.drawer == "Ana" and g.phase == "choosing"
    assert len(g.snapshot("Ana")["choices"]) == 3 and g.snapshot("Leo")["choices"] == []
    with pytest.raises(ValueError):
        g.choose("Leo", 0)
    choose(g, "perro caliente")
    assert g.snapshot("Ana")["mask"] == list("perro caliente")
    leo = g.snapshot("Leo")["mask"]
    assert leo.count(" ") == 1 and all(c is None for c in leo if c != " ")


def test_choosing_times_out_and_picks_a_word():
    g, _ = make()
    g.on_timeout()
    assert g.phase == "drawing" and g.word in ("casa", "gato", "perro caliente")


def test_strokes_are_relayed_and_validated():
    g, _ = make()
    choose(g, "gato")
    out = g.add_stroke("Ana", {"id": "s1", "color": "#22252E", "size": 8, "points": [[10, 10], [2000, -5]]})
    assert out["relay"]["kind"] == "stroke"
    assert g.strokes[0]["points"] == [[10, 10], [1000, 0]]  # se recortan al lienzo
    g.add_points("Ana", {"id": "s1", "points": [[20, 20]]})
    assert len(g.strokes[0]["points"]) == 3
    with pytest.raises(ValueError):
        g.add_stroke("Leo", {"id": "x", "color": "#000000", "points": []})
    with pytest.raises(ValueError):
        g.add_stroke("Ana", {"id": "x", "color": "rojo", "points": []})
    assert g.undo("Ana") == {"relay": {"kind": "undo"}} and g.strokes == []


def test_guessing_scores_by_speed_and_ends_the_turn():
    g, clock = make()
    choose(g, "perro caliente")
    assert g.guess("Leo", "perro") is None
    assert g.guess("Leo", "perro calientr") == {"notice": "¡Casi! «perro calientr» está muy cerca"}
    with pytest.raises(ValueError):
        g.guess("Ana", "perro caliente")  # quien dibuja no adivina
    clock.t = 30  # a la mitad del tiempo
    g.guess("Leo", "Perro  Caliente")
    assert g.phase == "turn_over"
    assert g.result["points"] == {"Leo": 75, "Ana": 50}
    snap = g.snapshot("Leo")
    assert [x["text"] for x in snap["guesses"]] == ["perro", "perro calientr", None]


def test_hints_reveal_letters_and_time_runs_out():
    g, clock = make()
    choose(g, "perro caliente")
    assert g.timer_seconds == pytest.approx(60 * HINT_AT[0])
    g.on_timeout()
    g.on_timeout()
    shown = [c for c in g.snapshot("Leo")["mask"] if c not in (None, " ")]
    assert len(shown) == 2
    g.on_timeout()
    assert g.phase == "turn_over" and g.result["guesser"] is None and g.result["points"] == {}


def test_turns_alternate_and_the_game_finishes():
    g, _ = make(rounds=1)
    choose(g, "casa")
    g.guess("Leo", "casa")
    g.next_round()
    assert g.drawer == "Leo" and g.phase == "choosing"
    g.on_timeout()
    g.guess("Ana", g.word)
    g.next_round()
    assert g.phase == "finished"
    snap = g.snapshot()
    assert len(snap["history"]) == 2 and len(snap["drawings"]) == 2


def test_needs_two_players():
    with pytest.raises(ValueError, match="entre los dos"):
        PinturilloGame.from_options(["Ana"], {}, random.Random())
    with pytest.raises(ValueError):
        PinturilloGame.from_options(["Ana", "Leo"], {"drawSeconds": 5}, random.Random())
