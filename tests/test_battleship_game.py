import random

import pytest

from app.games.battleship import BattleshipGame, FLEETS, random_fleet, validate_fleet

# Flota fija de 10x10 en filas separadas (no se tocan)
FLEET = [
    {"id": "portaaviones", "row": 0, "col": 0, "dir": "h"},
    {"id": "acorazado", "row": 2, "col": 0, "dir": "h"},
    {"id": "crucero", "row": 4, "col": 0, "dir": "h"},
    {"id": "submarino", "row": 6, "col": 0, "dir": "h"},
    {"id": "destructor", "row": 8, "col": 0, "dir": "h"},
]


class FirstRng(random.Random):
    def choice(self, seq):
        return seq[0]


def make(bonus=True, no_touch=True):
    g = BattleshipGame(["Ana", "Leo"], bonus=bonus, no_touch=no_touch, rng=FirstRng(1))
    g.start()
    g.place("Ana", FLEET)
    g.place("Leo", FLEET)
    return g


def test_validation_rules():
    assert len(validate_fleet(FLEET, 10, True)) == 5
    with pytest.raises(ValueError, match="todos"):
        validate_fleet(FLEET[:4], 10, True)
    out = [dict(s) for s in FLEET]
    out[0]["col"] = 7
    with pytest.raises(ValueError, match="fuera"):
        validate_fleet(out, 10, True)
    over = [dict(s) for s in FLEET]
    over[1]["row"] = 0
    with pytest.raises(ValueError, match="encima"):
        validate_fleet(over, 10, True)
    touching = [dict(s) for s in FLEET]
    touching[1]["row"] = 1  # justo debajo del portaaviones
    with pytest.raises(ValueError, match="tocar"):
        validate_fleet(touching, 10, True)
    assert validate_fleet(touching, 10, False)
    dup = [dict(s) for s in FLEET]
    dup[4]["id"] = "submarino"
    with pytest.raises(ValueError):
        validate_fleet(dup, 10, True)


@pytest.mark.parametrize("size", [8, 10])
def test_random_fleets_are_always_valid(size):
    rng = random.Random(4)
    for _ in range(40):
        assert len(validate_fleet(random_fleet(size, True, rng), size, True)) == len(FLEETS[size])


def test_battle_starts_when_both_are_ready_and_ships_stay_private():
    g = BattleshipGame(["Ana", "Leo"], rng=FirstRng(1))
    g.start()
    g.place("Ana", FLEET)
    assert g.phase == "placing" and g.snapshot("Leo")["ready"]["Ana"]
    assert g.snapshot("Leo")["boards"]["Ana"]["ships"] == []
    assert len(g.snapshot("Ana")["boards"]["Ana"]["ships"]) == 5
    g.unready("Ana")
    assert not g.ready["Ana"]
    g.place("Ana", FLEET)
    g.place("Leo", FLEET)
    assert g.phase == "battle" and g.turn == "Ana"
    with pytest.raises(ValueError):
        g.place("Ana", FLEET)


def test_water_passes_turn_and_hit_shoots_again():
    g = make()
    with pytest.raises(ValueError, match="Ana"):
        g.fire("Leo", 0, 0)
    g.fire("Ana", 0, 0)
    assert g.last_shot["result"] == "hit" and g.turn == "Ana"
    g.fire("Ana", 9, 9)
    assert g.last_shot["result"] == "water" and g.turn == "Leo"
    with pytest.raises(ValueError, match="Ya disparaste"):
        g.phase, g.turn = "battle", "Ana"
        g.fire("Ana", 9, 9)


def test_without_bonus_turn_always_passes():
    g = make(bonus=False)
    g.fire("Ana", 0, 0)
    assert g.turn == "Leo"


def test_sinking_reveals_ship_and_marks_water_around():
    g = make()
    g.fire("Ana", 8, 0)
    g.fire("Ana", 8, 1)
    assert g.last_shot == {"by": "Ana", "row": 8, "col": 1, "result": "sunk", "ship": "destructor"}
    view = g.snapshot("Ana")["boards"]["Leo"]
    assert [s["id"] for s in view["ships"]] == ["destructor"] and view["afloat"] == 4
    assert [7, 0] in view["autoWater"] and [9, 2] in view["autoWater"]
    with pytest.raises(ValueError, match="Ya disparaste"):
        g.fire("Ana", 9, 0)


def test_sinking_everything_wins_and_reveals_fleets():
    g = make()
    for ship in FLEET:
        length = next(l for sid, _, l in FLEETS[10] if sid == ship["id"])
        for i in range(length):
            g.fire("Ana", ship["row"], ship["col"] + i)
    assert g.phase == "finished" and g.winner == "Ana"
    assert len(g.snapshot("Ana")["boards"]["Leo"]["ships"]) == 5
    assert g.stats["Ana"] == {"shots": 17, "hits": 17}


def test_options():
    rng = random.Random()
    g = BattleshipGame.from_options(["Ana", "Leo"], {"size": 8, "noTouch": False, "bonus": False}, rng)
    assert g.size == 8 and not g.no_touch and not g.bonus
    with pytest.raises(ValueError):
        BattleshipGame.from_options(["Ana", "Leo"], {"size": 12}, rng)
    with pytest.raises(ValueError):
        BattleshipGame.from_options(["Ana"], {}, rng)
