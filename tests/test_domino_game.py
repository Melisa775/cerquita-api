import random

import pytest

from app.games.domino import TILES, DominoGame, pips


def make(goal=100, boneyard=True, seed=1):
    g = DominoGame(["Ana", "Leo"], goal=goal, boneyard=boneyard, rng=random.Random(seed))
    g.start()
    return g


def rig(g, ana, leo, pool, turn="Ana", line=None):
    """Prepara una mano a mano para probar una situación concreta."""
    g.hands = {"Ana": sorted(ana), "Leo": sorted(leo)}
    g.pool = list(pool)
    g.line = line or []
    g.turn = turn
    g.forced = None
    g.passes = 0
    g.phase = "playing"


def test_deal_and_opening_with_highest_double():
    g = make()
    assert len(TILES) == 28
    assert len(g.hands["Ana"]) == len(g.hands["Leo"]) == 7 and len(g.pool) == 14
    all_tiles = g.hands["Ana"] + g.hands["Leo"] + g.pool
    assert sorted(all_tiles) == sorted(TILES)
    doubles = [t for p in g.players for t in g.hands[p] if t[0] == t[1]]
    if doubles:
        assert g.forced == max(doubles) and g.forced in g.hands[g.turn]
    assert [m["tile"] for m in g.moves_for(g.turn)] == [list(g.forced)]


def test_hands_are_private():
    g = make()
    snap = g.snapshot("Ana")
    assert snap["hands"]["Ana"] and snap["hands"]["Leo"] is None and snap["counts"]["Leo"] == 7


def test_playing_on_both_ends_orients_tiles():
    g = make()
    rig(g, [(3, 5), (1, 6), (0, 0)], [(2, 4)], [(6, 6)], line=[(5, 5)])
    g.play("Ana", [3, 5], "left")
    assert g.line == [(3, 5), (5, 5)]
    rig(g, [(1, 6), (0, 0)], [(2, 4)], [(6, 6)], line=[(3, 5), (5, 6)])
    with pytest.raises(ValueError, match="pega"):
        g.play("Ana", [0, 0], "right")
    g.play("Ana", [1, 6], "right")
    assert g.line[-1] == (6, 1) and g.ends == (3, 1)


def test_tile_fitting_both_sides_needs_a_side():
    g = make()
    rig(g, [(2, 4), (6, 6)], [(1, 1)], [], line=[(2, 3), (3, 4)])
    with pytest.raises(ValueError, match="lado"):
        g.play("Ana", [2, 4], None)
    g.play("Ana", [2, 4], "right")
    assert g.line[-1] == (4, 2)


def test_must_draw_until_playable():
    g = make()
    rig(g, [(0, 1)], [(5, 6)], [(2, 2), (6, 6)], line=[(6, 3)])
    with pytest.raises(ValueError, match="turno|Le toca"):
        g.draw("Leo")
    assert g.snapshot("Ana")["mustDraw"]
    g.draw("Ana")  # roba el 6|6, que pega
    assert (6, 6) in g.hands["Ana"] and g.turn == "Ana"
    with pytest.raises(ValueError, match="Tienes con qué"):
        g.draw("Ana")


def test_auto_pass_when_pool_is_empty():
    g = make()
    rig(g, [(1, 3), (2, 2)], [(0, 0), (0, 1)], [], line=[(3, 4)])
    g.play("Ana", [1, 3], "left")  # extremos 1 y 4; Leo tiene 0|1 → juega
    assert g.turn == "Leo"
    g.play("Leo", [0, 1], "left")  # extremos 0 y 4; Ana (2|2) no puede → pasa sola
    assert g.turn == "Leo" and g.log[-1] == {"player": "Ana", "action": "pass"}


def test_domino_scores_opponents_pips():
    g = make()
    rig(g, [(4, 6)], [(5, 6), (1, 2)], [], line=[(6, 6)])
    g.play("Ana", [4, 6], "right")
    assert g.phase == "hand_over"
    assert g.result == {"winner": "Ana", "reason": "domino", "points": 14, "pips": {"Ana": 0, "Leo": 14}}
    assert g.scores["Ana"] == 14
    snap = g.snapshot("Ana")
    assert snap["hands"]["Leo"] == [[1, 2], [5, 6]]
    g.next_hand()
    assert g.turn == "Ana" and g.forced is None and g.phase == "playing"


def test_blocked_game_lowest_hand_wins():
    g = make(boneyard=False)
    rig(g, [(1, 4), (0, 0)], [(2, 2), (3, 3)], [], line=[(4, 6)])
    g.play("Ana", [1, 4], "left")  # extremos 1 y 6: nadie puede → tranque
    assert g.result["reason"] == "tranque" and g.result["winner"] == "Ana"
    assert g.scores["Ana"] == 10


def test_reaching_the_goal_finishes():
    g = make(goal=50)
    g.scores["Ana"] = 45
    rig(g, [(4, 6)], [(5, 6)], [], line=[(6, 6)])
    g.play("Ana", [4, 6], "right")
    assert g.phase == "finished" and g.winner == "Ana"


def test_full_random_games_always_end():
    for seed in range(30):
        g = make(goal=50, seed=seed)
        rng = random.Random(seed)
        for _ in range(2000):
            if g.phase == "finished":
                break
            if g.phase == "hand_over":
                g.next_hand()
                continue
            p = g.turn
            moves = g.moves_for(p)
            if moves:
                m = rng.choice(moves)
                g.play(p, m["tile"], rng.choice(m["sides"]))
            else:
                g.draw(p)
            total = len(g.line) + len(g.pool) + sum(len(h) for h in g.hands.values())
            assert total == 28
        assert g.phase == "finished"


def test_options():
    rng = random.Random()
    assert DominoGame.from_options(["Ana", "Leo"], {"goal": 150, "boneyard": False}, rng).goal == 150
    with pytest.raises(ValueError):
        DominoGame.from_options(["Ana", "Leo"], {"goal": 7}, rng)
    with pytest.raises(ValueError):
        DominoGame.from_options(["Ana"], {}, rng)
    assert pips([(6, 6), (0, 1)]) == 13
