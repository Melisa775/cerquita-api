import math
import random

import pytest

from app.games.golf import GolfGame, MAX_STROKES
from app.games.golf_courses import COURSES
from app.games.golf_physics import BALL_R, simulate


def make(holes=9):
    g = GolfGame(["Ana", "Leo"], holes=holes, rng=random.Random(1))
    g.first = "Ana"
    g.start()
    return g


def toward(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def test_straight_putt_goes_in():
    c = COURSES[0]
    r = simulate(c, c["tee"], toward(c["tee"], c["hole"]), 0.6)
    assert r["result"] == "holed" and r["end"] == [50.0, 32.0]
    assert len(r["path"]) > 5


def test_soft_shot_stops_short_and_too_hard_bounces_off_the_wall():
    c = COURSES[0]
    soft = simulate(c, c["tee"], -math.pi / 2, 0.15)
    assert soft["result"] == "stopped" and soft["end"][1] > 60
    # tirando de lado contra la pared rebota y queda dentro del green
    side = simulate(c, c["tee"], 0, 1.0)
    assert 22 + BALL_R - 0.01 <= side["end"][0] <= 78 - BALL_R + 0.01
    assert any(e["kind"] == "wall" for e in side["events"])


@pytest.mark.parametrize("index", range(len(COURSES)))
def test_ball_never_leaves_the_green(index):
    c = COURSES[index]
    xs = [p[0] for p in c["walls"][0]]
    ys = [p[1] for p in c["walls"][0]]
    rng = random.Random(index)
    for _ in range(25):
        r = simulate(c, c["tee"], rng.uniform(0, 2 * math.pi), rng.uniform(0.1, 1.0))
        for x, y in r["path"]:
            assert min(xs) - 0.5 <= x <= max(xs) + 0.5 and min(ys) - 0.5 <= y <= max(ys) + 0.5


def test_water_returns_ball_with_penalty():
    g = make()
    g.hole = 3  # El río
    g._start_hole()
    tee = g.course["tee"]
    g.shoot("Ana", -math.pi / 2, 0.7)  # derecho hacia el agua
    assert g.last_shot["result"] == "water" and g.last_shot["penalty"]
    assert g.strokes["Ana"] == 2 and g.balls["Ana"] == [float(tee[0]), float(tee[1])]


def test_turns_scorecard_and_finish():
    g = make(holes=3)
    with pytest.raises(ValueError, match="Le toca"):
        g.handle("Leo", {"type": "gf_shoot", "angle": 0, "power": 0.5})
    for h in range(3):
        while g.phase == "playing":
            p = g.turn
            ball = g.balls[p]
            d = math.dist(ball, g.course["hole"])
            g.shoot(p, toward(ball, g.course["hole"]), min(1.0, 0.12 + d / 160))
        if g.phase == "hole_over":
            g.next_hole()
    assert g.phase == "finished" and len(g.card) == 3
    assert all(1 <= h["strokes"][p] <= MAX_STROKES + 1 for h in g.card for p in g.players)
    assert g.totals() == {p: sum(h["strokes"][p] for h in g.card) for p in g.players}


def test_who_holed_out_stops_shooting():
    g = make()
    g.shoot("Ana", toward(g.balls["Ana"], g.course["hole"]), 0.6)
    assert g.done["Ana"] and g.turn == "Leo"
    g.shoot("Leo", -math.pi / 2, 0.1)
    assert g.turn == "Leo"


def test_pick_up_after_max_strokes():
    g = make()
    g.strokes["Ana"] = MAX_STROKES - 1
    g.shoot("Ana", 0, 0.05)
    assert g.done["Ana"] and g.strokes["Ana"] == MAX_STROKES and g.last_shot["pickedUp"]


def test_aim_is_relayed_not_stored():
    g = make()
    out = g.handle("Ana", {"type": "gf_aim", "angle": 1.2345, "power": 2})
    assert out == {"relay": {"kind": "aim", "player": "Ana", "angle": 1.234, "power": 1}}
    with pytest.raises(ValueError):
        g.handle("Ana", {"type": "gf_shoot", "angle": 0, "power": 0})


def test_options():
    rng = random.Random()
    assert len(GolfGame.from_options(["Ana", "Leo"], {"holes": 3}, rng).courses) == 3
    with pytest.raises(ValueError):
        GolfGame.from_options(["Ana", "Leo"], {"holes": 4}, rng)
