import random

import pytest

from app.games.murdoku import BLOCKING, LEVELS, MurdokuGame, generate


@pytest.mark.parametrize("level", list(LEVELS))
def test_generated_cases_have_one_solution_and_one_murderer(level):
    for seed in range(8):
        case, sol, clues, murderer = generate(level, random.Random(seed))
        n = LEVELS[level]["size"]
        assert len(case.people) == n
        assert sorted(r for r, _ in sol.values()) == list(range(n))  # una persona por fila
        assert sorted(c for _, c in sol.values()) == list(range(n))  # y por columna
        assert all(case.objects.get(cell) not in BLOCKING for cell in sol.values())
        assert case.count_solutions(clues, limit=3) == 1
        victim_room = case.rooms[sol[n - 1][0]][sol[n - 1][1]]
        with_victim = [p for p in range(n - 1) if case.rooms[sol[p][0]][sol[p][1]] == victim_room]
        assert with_victim == [murderer]
        assert all(any(c[1] == p for c in clues) for p in range(n))  # todos tienen pista
        # Ninguna pista dice directamente quién estaba con la víctima
        assert not any(c[0] == "same_room" and n - 1 in c[1:] for c in clues)


def make(mode="team"):
    g = MurdokuGame(["Ana", "Leo"], mode=mode, level="facil", rng=random.Random(4))
    g.start()
    return g


def test_team_board_is_shared_and_solving_reveals_the_murderer():
    g = make("team")
    assert g.snapshot("Leo")["placed"] == {}
    pid, cell = next(iter(g.solution.items()))
    g.place("Ana", pid, list(cell))
    assert g.snapshot("Leo")["placed"][str(pid)] == {"cell": list(cell), "by": "Ana"}
    for p, c in g.solution.items():
        g.place("Leo", p, list(c))
    assert g.phase == "round_over"
    assert g.result["murderer"] == g.murderer
    assert g.snapshot("Ana")["placed"][str(g.murderer)]["cell"] == list(g.solution[g.murderer])


def test_cannot_stand_on_blocking_furniture_and_cells_hold_one_person():
    g = make()
    blocked = next(cell for cell, kind in g.case.objects.items() if kind in BLOCKING)
    with pytest.raises(ValueError, match="no se puede ocupar"):
        g.place("Ana", 0, list(blocked))
    free = next((r, c) for r in range(5) for c in range(5) if g.case.free((r, c)))
    g.place("Ana", 0, list(free))
    g.place("Ana", 1, list(free))  # el segundo reemplaza al primero
    assert list(g._board("Ana")["placed"]) == [1]
    g.place("Ana", 1, None)
    assert g._board("Ana")["placed"] == {}


def test_notes_and_violations():
    g = make()
    g.note("Ana", [0, 0])
    assert g.snapshot("Leo")["notes"] == [[0, 0]]
    g.note("Ana", [0, 0])
    assert g.snapshot("Leo")["notes"] == []
    # Plano lleno pero equivocado: se muestran las pistas que no cuadran
    wrong = dict(g.solution)
    a, b = 0, 1
    wrong[a], wrong[b] = (g.solution[a][0], g.solution[b][1]), (g.solution[b][0], g.solution[a][1])
    if all(g.case.free(c) for c in wrong.values()):
        for p, c in wrong.items():
            g.place("Ana", p, list(c))
        if g.phase == "playing":
            assert g.snapshot("Ana")["violations"]


def test_race_boards_are_private_and_first_solver_wins():
    g = make("race")
    p0, c0 = next(iter(g.solution.items()))
    g.place("Leo", p0, list(c0))
    assert g.snapshot("Ana")["placed"] == {}
    assert g.snapshot("Ana")["progress"] == {"Ana": 0, "Leo": 1}
    for p, c in g.solution.items():
        g.place("Ana", p, list(c))
    assert g.result["winner"] == "Ana" and g.scores == {"Ana": 1, "Leo": 0}


def test_options_are_validated():
    with pytest.raises(ValueError):
        MurdokuGame.from_options(["Ana"], {"level": "imposible"}, random.Random())
    with pytest.raises(ValueError):
        MurdokuGame.from_options(["Ana"], {"mode": "otro"}, random.Random())
