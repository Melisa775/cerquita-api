import random

import pytest

from app.games.wordsearch import LEVELS, WordSearchGame, build, line_cells, themes, to_letters


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def make(mode="race", level="normal", rounds=1, players=("Ana", "Leo")):
    clock = Clock()
    g = WordSearchGame(list(players), mode=mode, level=level, rounds=rounds, rng=random.Random(3), clock=clock)
    g.start()
    return g, clock


def ends(item, reverse=False):
    cells = item["cells"]
    a, b = cells[0], cells[-1]
    return (list(b), list(a)) if reverse else (list(a), list(b))


def test_to_letters_strips_accents_but_keeps_enie():
    assert to_letters("Alegría") == "ALEGRIA"
    assert to_letters("piña") == "PIÑA"


def test_line_cells_only_allows_straight_lines():
    assert line_cells((0, 0), (0, 3)) == [(0, 0), (0, 1), (0, 2), (0, 3)]
    assert line_cells((3, 3), (1, 1)) == [(3, 3), (2, 2), (1, 1)]
    assert line_cells((0, 0), (1, 2)) is None
    assert line_cells((2, 2), (2, 2)) is None


@pytest.mark.parametrize("level", list(LEVELS))
def test_generated_grid_contains_every_word_in_allowed_directions(level):
    cfg = LEVELS[level]
    for seed in range(5):
        words = themes(cfg["size"])["Animales"][: cfg["words"]]
        grid, placed = build(cfg["size"], words, cfg["dirs"], random.Random(seed))
        assert len(grid) == cfg["size"] and all(len(row) == cfg["size"] for row in grid)
        assert len(placed) >= len(words) - 1  # casi siempre caben todas
        for item in placed:
            text = "".join(grid[r][c] for r, c in item["cells"])
            assert text == item["letters"]
            (r1, c1), (r2, c2) = item["cells"][:2]
            assert (r2 - r1, c2 - c1) in cfg["dirs"]


def test_marking_a_word_forward_or_backward_in_race_mode():
    g, _ = make()
    first, second = g.placed[0], g.placed[1]
    g.mark("Ana", *ends(first))
    g.mark("Leo", *ends(second, reverse=True))  # de atrás para adelante también vale
    assert g.found[first["word"]]["player"] == "Ana"
    assert g.found[second["word"]]["player"] == "Leo"
    assert g.scores == {"Ana": 1, "Leo": 1}
    with pytest.raises(ValueError, match="ya la encontraron"):
        g.mark("Leo", *ends(first))


def test_wrong_selections_are_rejected():
    g, _ = make()
    with pytest.raises(ValueError, match="línea recta"):
        g.mark("Ana", [0, 0], [1, 2])
    item = g.placed[0]
    a, b = ends(item)
    b_short = item["cells"][-2]
    with pytest.raises(ValueError, match="no es una de las palabras"):
        g.mark("Ana", a, list(b_short))  # le falta una letra


def test_hidden_words_are_not_leaked_until_the_round_ends():
    g, clock = make(mode="team")
    snap = g.snapshot("Ana")
    assert snap["missing"] == [] and snap["found"] == {}
    assert set(snap["words"]) == {i["word"] for i in g.placed}
    clock.t += 42
    for item in g.placed:
        g.mark("Ana", *ends(item))
    assert g.phase == "round_over"
    assert g.history[0]["seconds"] == 42
    assert g.scores == {"Ana": 0, "Leo": 0}  # juntos no hay puntos individuales


def test_live_selection_is_shown_to_the_other_player_only():
    g, _ = make()
    g.select("Ana", [0, 0], [0, 3])
    assert g.snapshot("Leo")["selecting"] == {"Ana": {"start": (0, 0), "end": (0, 3)}}
    assert g.snapshot("Ana")["selecting"] == {}
    g.select("Ana", None, None)
    assert g.snapshot("Leo")["selecting"] == {}


def test_give_up_reveals_missing_words():
    g, _ = make(rounds=2)
    g.mark("Ana", *ends(g.placed[0]))
    g.give_up()
    snap = g.snapshot("Leo")
    assert snap["phase"] == "round_over" and snap["gaveUp"]
    assert len(snap["missing"]) == len(g.placed) - 1
    theme = g.theme
    g.next_round()
    assert g.theme != theme and g.found == {}


def test_options_are_validated():
    with pytest.raises(ValueError):
        WordSearchGame.from_options(["Ana"], {"level": "imposible"}, random.Random())
    with pytest.raises(ValueError):
        WordSearchGame.from_options(["Ana"], {"mode": "otro"}, random.Random())


@pytest.mark.parametrize("level", list(LEVELS))
def test_directions_are_spread_out(level):
    from collections import Counter

    counts = Counter()
    for seed in range(60):
        g = WordSearchGame(["Ana"], level=level, rng=random.Random(seed))
        g.start()
        for item in g.placed:
            (r1, c1), (r2, c2) = item["cells"][:2]
            counts[(r2 - r1, c2 - c1)] += 1
    total = sum(counts.values())
    dirs = LEVELS[level]["dirs"]
    assert set(counts) == set(dirs)  # salen todas las direcciones del nivel
    assert min(counts[d] for d in dirs) / total > 0.5 / len(dirs)  # y ninguna queda casi olvidada
