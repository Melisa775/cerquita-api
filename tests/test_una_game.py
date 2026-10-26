import random
from collections import Counter

import pytest

from app.games.una import UnaGame, build_deck, points

_next_id = [1000]


def card(color, value):
    _next_id[0] += 1
    return {"id": _next_id[0], "color": color, "value": value}


def make(stacking=False, goal=0):
    g = UnaGame(["Ana", "Leo"], goal=goal, stacking=stacking, rng=random.Random(2))
    g.start()
    return g


def rig(g, ana, leo, top, turn="Ana", pile=None):
    g.hands = {"Ana": list(ana), "Leo": list(leo)}
    g.discard = [top]
    g.color = top["color"]
    g.turn = turn
    g.drawn = None
    g.pending = 0
    g.catchable = None
    g.said_una = {"Ana": False, "Leo": False}
    if pile is not None:
        g.pile = list(pile)


def test_deck_has_108_cards():
    deck = build_deck()
    assert len(deck) == 108 and len({c["id"] for c in deck}) == 108
    kinds = Counter(c["value"] for c in deck)
    assert kinds["0"] == 4 and kinds["5"] == 8 and kinds["draw2"] == 8 and kinds["wild"] == 4 and kinds["wild4"] == 4
    assert points({"value": "7"}) == 7 and points({"value": "skip"}) == 20 and points({"value": "wild4"}) == 50


def test_deal_is_private():
    g = make()
    assert len(g.hands["Ana"]) == len(g.hands["Leo"]) == 7 and g.top["value"].isdigit()
    snap = g.snapshot("Ana")
    assert snap["hand"] == g.hands["Ana"] and snap["hands"] is None and snap["counts"]["Leo"] == 7


def test_match_by_color_or_value():
    g = make()
    r5, b5, g7, w = card("r", "5"), card("b", "5"), card("g", "7"), card(None, "wild")
    rig(g, [b5, g7, w, card("y", "1")], [card("y", "2")], r5)
    assert set(g.playable_ids("Ana")) == {b5["id"], w["id"]}
    with pytest.raises(ValueError):
        g.play("Ana", g7["id"])
    g.play("Ana", b5["id"])
    assert g.color == "b" and g.turn == "Leo"


def test_wild_needs_a_color():
    g = make()
    w = card(None, "wild")
    rig(g, [w, card("y", "1")], [card("y", "2")], card("r", "5"))
    with pytest.raises(ValueError, match="color"):
        g.play("Ana", w["id"])
    g.play("Ana", w["id"], "g")
    assert g.color == "g" and g.turn == "Leo"


def test_specials_for_two_players():
    g = make()
    skip, d2 = card("r", "skip"), card("r", "draw2")
    rig(g, [skip, d2, card("y", "1")], [card("y", "2")], card("r", "5"))
    g.play("Ana", skip["id"])
    assert g.turn == "Ana"
    g.play("Ana", d2["id"])
    assert g.turn == "Ana" and len(g.hands["Leo"]) == 3


def test_stacking_draw_twos():
    g = make(stacking=True)
    a2, l2 = card("r", "draw2"), card("b", "draw2")
    rig(g, [a2, card("y", "1")], [l2, card("g", "4")], card("r", "5"))
    g.play("Ana", a2["id"])
    assert g.turn == "Leo" and g.pending == 2
    assert g.playable_ids("Leo") == [l2["id"]]
    g.play("Leo", l2["id"])
    assert g.pending == 4 and g.turn == "Ana"
    g.draw("Ana")
    assert len(g.hands["Ana"]) == 5 and g.pending == 0 and g.turn == "Leo"


def test_draw_then_play_or_pass():
    g = make()
    good, bad = card("r", "9"), card("y", "3")
    rig(g, [card("g", "1")], [card("y", "2")], card("r", "5"), pile=[bad, good])
    g.draw("Ana")  # roba el 9 rojo, que sirve
    assert g.drawn["id"] == good["id"] and g.turn == "Ana"
    with pytest.raises(ValueError):
        g.play("Ana", g.hands["Ana"][0]["id"])  # solo la robada
    g.pass_turn("Ana")
    assert g.turn == "Leo"
    g.draw("Leo")  # roba el 3 amarillo: no sirve sobre rojo 5 → pasa solo
    assert g.turn == "Ana" and g.drawn is None


def test_una_and_catch():
    g = make()
    a, b = card("r", "1"), card("r", "2")
    rig(g, [a, b], [card("y", "2"), card("g", "3")], card("r", "5"))
    g.play("Ana", a["id"])  # queda con una sin decirlo
    assert g.catchable == "Ana"
    g.handle("Leo", {"type": "un_catch"})
    assert len(g.hands["Ana"]) == 3 and g.catchable is None
    # diciéndolo a tiempo no la pillan
    rig(g, [a, b], [card("y", "2")], card("r", "5"))
    g.say_una("Ana")
    g.play("Ana", a["id"])
    assert g.catchable is None
    with pytest.raises(ValueError):
        g.catch("Leo")


def test_catch_window_closes_when_rival_plays():
    g = make()
    a, b, y5 = card("r", "1"), card("r", "2"), card("y", "5")
    rig(g, [a, b], [card("r", "8"), y5, card("g", "6")], card("r", "5"))
    g.play("Ana", a["id"])
    g.play("Leo", g.hands["Leo"][0]["id"])  # Leo juega sin pillarla
    assert g.catchable is None


def test_winning_scores_rival_cards():
    g = make(goal=0)
    last = card("r", "7")
    rig(g, [last], [card("y", "9"), card(None, "wild"), card("b", "skip")], card("r", "5"))
    g.play("Ana", last["id"])
    assert g.phase == "finished" and g.winner == "Ana" and g.scores["Ana"] == 79


def test_rounds_until_goal():
    g = make(goal=200)
    last = card("r", "7")
    rig(g, [last], [card("y", "9")], card("r", "5"))
    g.play("Ana", last["id"])
    assert g.phase == "round_over" and g.scores["Ana"] == 9
    g.next_round()
    assert g.phase == "playing" and g.round == 2


def test_random_games_finish_and_keep_108_cards():
    for seed in range(25):
        g = UnaGame(["Ana", "Leo"], goal=0, stacking=seed % 2 == 0, rng=random.Random(seed))
        g.start()
        rng = random.Random(seed)
        for _ in range(3000):
            if g.phase == "finished":
                break
            p = g.turn
            ids = g.playable_ids(p)
            if ids and rng.random() < 0.9:
                pick = rng.choice(ids)
                c = next(c for c in g.hands[p] if c["id"] == pick)
                g.play(p, c["id"], rng.choice("rygb") if c["color"] is None else None)
            elif g.drawn:
                g.pass_turn(p)
            else:
                g.draw(p)
            total = len(g.pile) + len(g.discard) + sum(len(h) for h in g.hands.values())
            assert total == 108
        assert g.phase == "finished"
