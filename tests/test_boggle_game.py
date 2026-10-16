import random

import pytest

from app.dictionary import Dictionary, spanish
from app.games.boggle import BoggleGame, find_path, points_for, roll, solve

# C A S A
# O S O L
# M E R Qu
# A T Ñ O
BOARD = ["c", "a", "s", "a",
         "o", "s", "o", "l",
         "m", "e", "r", "qu",
         "a", "t", "ñ", "o"]
WORDS = Dictionary(["casa", "casas", "cosa", "osos", "sol", "solo", "mesa", "meta", "comer", "queso", "ola", "oso", "año"])


def make_game(rounds=2, players=("Ana", "Leo")):
    g = BoggleGame(list(players), rounds=rounds, rng=random.Random(1), dictionary=WORDS, board=list(BOARD))
    g.start()
    return g


def test_paths_use_neighbours_including_diagonals_and_no_repeats():
    assert find_path(BOARD, 4, "casa") == [0, 1, 2, 3]
    assert find_path(BOARD, 4, "cosa") == [0, 4, 5, 1]  # diagonal o→s, s→a
    assert find_path(BOARD, 4, "sol") is not None
    assert find_path(BOARD, 4, "casas") is None  # habría que repetir un dado
    assert find_path(BOARD, 4, "queso") is None  # Qu no toca la E
    assert find_path(BOARD, 4, "mata") is None


def test_qu_die_counts_as_two_letters():
    board = ["qu", "e", "s", "o"] + ["a"] * 12
    assert find_path(board, 4, "queso") == [0, 1, 2, 3]
    assert find_path(board, 4, "ueso") is None
    assert points_for("queso") == 2


def test_solver_finds_every_dictionary_word_on_the_board():
    expected = {w for w in WORDS.words if len(w) >= 3 and find_path(BOARD, 4, w) is not None}
    assert solve(BOARD, 4, WORDS, 3) == expected
    assert {"casa", "cosa", "sol", "comer"} <= expected


def test_scoring_by_length():
    assert [points_for("x" * n) for n in range(3, 10)] == [1, 1, 2, 3, 5, 11, 11]


def test_adding_words_validates_and_hides_them_from_the_other_player():
    g = make_game()
    g.add_word("Ana", "Cása ")
    with pytest.raises(ValueError, match="Ya tienes"):
        g.add_word("Ana", "casa")
    with pytest.raises(ValueError, match="mínimo"):
        g.add_word("Ana", "co")
    with pytest.raises(ValueError, match="tablero"):
        g.add_word("Ana", "perro")
    g.add_word("Ana", "asos")  # se puede armar aunque no esté en el diccionario
    leo = g.snapshot("Leo")
    assert leo["mine"] == [] and leo["counts"] == {"Ana": 2, "Leo": 0}
    assert g.snapshot("Ana")["mine"] == [{"word": "casa", "known": True}, {"word": "asos", "known": False}]
    assert "casa" not in str(leo)


def test_review_cancels_shared_words_and_allows_overrides():
    g = make_game()
    for w in ["casa", "cosa", "asos"]:
        g.add_word("Ana", w)
    for w in ["casa", "sol"]:
        g.add_word("Leo", w)
    g.on_timeout()
    r = {p: {i["word"]: i for i in items} for p, items in g.results().items()}
    assert r["Ana"]["casa"]["status"] == "shared" and r["Leo"]["casa"]["points"] == 0
    assert r["Ana"]["cosa"]["points"] == 1
    assert r["Ana"]["asos"]["status"] == "invalid"
    assert g.round_totals(g.results()) == {"Ana": 1, "Leo": 1}

    g.toggle("asos")  # la dan por buena
    assert g.round_totals(g.results())["Ana"] == 2
    g.toggle("sol")  # y anulan una del diccionario
    assert g.round_totals(g.results())["Leo"] == 0
    with pytest.raises(ValueError):
        g.toggle("casa")  # compartida
    with pytest.raises(ValueError):
        g.toggle("mesa")  # nadie la escribió

    snap = g.snapshot("Ana")
    assert "mesa" in snap["missed"] and "casa" not in snap["missed"]
    assert snap["possible"] == len(g.solutions)


def test_both_done_ends_round_early_and_totals_accumulate():
    g = make_game(rounds=1)
    g.add_word("Ana", "mesa")
    g.finish("Ana")
    assert g.phase == "playing"
    g.finish("Leo")
    assert g.phase == "review"
    g.next_round()
    assert g.phase == "finished"
    assert g.totals == {"Ana": 1, "Leo": 0}
    assert g.history[0]["best"] == {"Ana": "mesa", "Leo": None}


def test_options_are_validated():
    with pytest.raises(ValueError):
        BoggleGame.from_options(["Ana"], {"size": 6}, random.Random())
    with pytest.raises(ValueError):
        BoggleGame.from_options(["Ana"], {"minutes": 10}, random.Random())


def test_real_dictionary_and_generated_boards():
    d = spanish()
    assert len(d) > 600_000
    assert "casa" in d and "niño" in d and "comiendo" in d
    assert d.has_prefix("murcielag") and not d.has_prefix("zzq")
    g = BoggleGame(["Ana"], size=5, rng=random.Random(7))
    g.start()
    assert len(g.board) == 25 and g.min_len == 4
    assert len(g.solutions) > 50
    assert all(len(w) >= 4 for w in g.solutions)
    assert len(roll(4, random.Random(3))) == 16
