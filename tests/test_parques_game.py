import random

import pytest

from app.games.parques import HOME, LOOP, SAFE, TO_ENTRY, ParquesGame


def make(pieces=4):
    g = ParquesGame(["Ana", "Leo"], pieces=pieces, rng=random.Random(3))
    g.start()
    g.turn = "Ana"
    return g


def test_geometry():
    g = make()
    assert g.exit_square("Ana") == 13 and g.exit_square("Leo") == 47
    assert g.square("Ana", 0) == 13 and g.square("Ana", 60) == (13 + 60) % LOOP
    assert g.square("Ana", 64) is None and g.square("Ana", -1) is None
    assert 13 in SAFE and 47 in SAFE and len(SAFE) == 8
    # la entrada a la llegada de Ana es la casilla 8 de su brazo (justo antes de su salida)
    assert g.square("Ana", TO_ENTRY) == 8


def test_three_tries_to_leave_jail():
    g = make()
    g.roll((1, 2))
    g.roll((3, 4))
    assert g.turn == "Ana" and g.snapshot("Ana")["attemptsLeft"] == 1
    g.roll((5, 6))
    assert g.turn == "Leo"


def test_pairs_release_everyone_and_roll_again():
    g = make()
    g.roll((3, 3))
    assert g.pieces["Ana"] == [0, 0, 0, 0] and g.phase == "roll" and g.turn == "Ana"


def test_dice_move_separately_and_turn_passes():
    g = make()
    g.pieces["Ana"] = [0, 0, -1, -1]
    g.roll((2, 5))
    assert g.phase == "move" and {(m["piece"], m["die"]) for m in g.legal_moves()} >= {(0, 0), (0, 1), (1, 0)}
    g.move(0, 1)
    g.move(1, 0)
    assert g.pieces["Ana"][:2] == [5, 2] and g.turn == "Leo"
    with pytest.raises(ValueError):
        g.handle("Ana", {"type": "pa_roll"})


def test_capture_sends_rival_to_jail_but_not_on_safe_squares():
    g = make()
    g.pieces["Ana"] = [0, -1, -1, -1]
    # Leo en la casilla 16 (13 + 3), que no es seguro
    leo_prog = (16 - g.exit_square("Leo")) % LOOP
    g.pieces["Leo"] = [leo_prog, -1, -1, -1]
    g.roll((3, 1))
    g.move(0, 0)
    assert g.pieces["Leo"][0] == -1
    # en un seguro (casilla 21 = 17 + 4) conviven
    g.turn, g.phase = "Ana", "roll"
    g.pieces["Ana"] = [4, -1, -1, -1]  # casilla 17
    g.pieces["Leo"] = [(21 - g.exit_square("Leo")) % LOOP, -1, -1, -1]
    g.roll((4, 1))
    g.move(0, 0)
    assert g.square("Ana", g.pieces["Ana"][0]) == 21 and g.pieces["Leo"][0] != -1


def test_leaving_jail_eats_whoever_is_on_your_exit():
    g = make()
    g.pieces["Leo"] = [(13 - g.exit_square("Leo")) % LOOP, -1, -1, -1]
    g.roll((6, 6))
    assert g.pieces["Ana"] == [0, 0, 0, 0] and g.pieces["Leo"][0] == -1


def test_pairs_with_pieces_out_can_release_or_move():
    g = make()
    g.pieces["Ana"] = [10, -1, -1, -1]
    g.roll((4, 4))
    assert g.snapshot("Ana")["canRelease"]
    g.release()
    assert g.pieces["Ana"] == [10, 0, 0, 0] and g.phase == "roll" and g.turn == "Ana"


def test_exact_count_to_reach_heaven_and_lost_dice():
    g = make(pieces=2)
    g.pieces["Ana"] = [69, HOME]
    g.roll((5, 2))  # el 5 no sirve; el 2 entra justo
    assert g.unused == [1]
    g.move(0, 1)
    assert g.phase == "finished" and g.winner == "Ana"


def test_third_pair_sends_a_piece_to_heaven():
    g = make()
    g.pieces["Ana"] = [5, 5, -1, -1]
    g.pairs_in_row = 2
    g.roll((2, 2))
    assert g.phase == "bonus"
    g.bonus(2)
    assert g.pieces["Ana"][2] == HOME and g.turn == "Leo"


def test_random_games_finish():
    for seed in range(20):
        g = ParquesGame(["Ana", "Leo"], pieces=2, rng=random.Random(seed))
        g.start()
        rng = random.Random(seed)
        for _ in range(5000):
            if g.phase == "finished":
                break
            if g.phase == "roll":
                g.roll()
            elif g.phase == "bonus":
                g.bonus(next(i for i, p in enumerate(g.pieces[g.turn]) if p != HOME))
            elif g.can_release and rng.random() < 0.5:
                g.release()
            else:
                m = rng.choice(g.legal_moves())
                g.move(m["piece"], m["die"])
        assert g.phase == "finished"


def test_options():
    rng = random.Random()
    assert ParquesGame.from_options(["Ana", "Leo"], {"pieces": 2}, rng).n_pieces == 2
    with pytest.raises(ValueError):
        ParquesGame.from_options(["Ana", "Leo"], {"pieces": 3}, rng)
    with pytest.raises(ValueError):
        ParquesGame.from_options(["Ana"], {}, rng)
