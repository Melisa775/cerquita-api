import random

import pytest

from app.games.crosswords import CENTER, PREMIUMS, TILES, CrosswordsGame, word_ok


def make(check=True):
    g = CrosswordsGame(["Ana", "Leo"], check=check, rng=random.Random(5))
    g.start()
    g.turn = "Ana"
    return g


def tiles(word, r, c, horizontal=True, blanks=()):
    out = []
    for i, ch in enumerate(word):
        rr, cc = (r, c + i) if horizontal else (r + i, c)
        out.append({"r": rr, "c": cc, "letter": ch, "blank": i in blanks})
    return out


def give(g, player, letters):
    g.racks[player] = list(letters)


def test_bag_board_and_racks():
    assert sum(n for n, _ in TILES.values()) == 100
    g = make()
    assert len(g.racks["Ana"]) == len(g.racks["Leo"]) == 7 and len(g.bag) == 86
    assert PREMIUMS[CENTER] == "DP"
    snap = g.snapshot("Ana")
    assert snap["rack"] == g.racks["Ana"] and snap["racks"] is None and snap["rackCounts"]["Leo"] == 7


def test_dictionary_with_short_words():
    assert word_ok("CASA") and word_ok("CAMION") and word_ok("EL") and word_ok("YA") and word_ok("ÑU")
    assert not word_ok("XQ") and not word_ok("CASAQZ")


def test_first_word_must_cross_center_and_scores_double_word():
    g = make()
    give(g, "Ana", "CASAXYZ")
    with pytest.raises(ValueError, match="centro"):
        g.play("Ana", tiles("CASA", 0, 0))
    g.play("Ana", tiles("CASA", 7, 4))  # C(7,4) A(7,5) S(7,6) A(7,7)=centro DP
    # C3 + A1 + S1 + A1 = 6, doble palabra = 12; (7,4) y (7,6) no tienen premio
    assert g.scores["Ana"] == 12 and g.turn == "Leo" and len(g.racks["Ana"]) == 7
    assert g.board[7][4]["letter"] == "C"


def test_invalid_words_are_rejected_without_losing_turn():
    g = make()
    give(g, "Ana", "QZXQZXA")
    with pytest.raises(ValueError, match="diccionario"):
        g.play("Ana", tiles("QZX", 7, 6))
    assert g.turn == "Ana" and g.board[7][6] is None


def test_placement_rules():
    g = make(check=False)
    give(g, "Ana", "CASAOSO")
    g.play("Ana", tiles("CASA", 7, 4))
    give(g, "Leo", "OSOXXXX")
    with pytest.raises(ValueError, match="tocar"):
        g.play("Leo", tiles("OSO", 0, 0))
    with pytest.raises(ValueError, match="fila o columna"):
        g.play("Leo", [{"r": 8, "c": 4, "letter": "O"}, {"r": 9, "c": 5, "letter": "S"}])
    with pytest.raises(ValueError, match="seguidas"):
        g.play("Leo", [{"r": 8, "c": 4, "letter": "O"}, {"r": 10, "c": 4, "letter": "S"}])
    with pytest.raises(ValueError, match="ocupada"):
        g.play("Leo", [{"r": 7, "c": 4, "letter": "O"}])
    with pytest.raises(ValueError, match="No tienes"):
        g.play("Leo", tiles("AAA", 8, 4, horizontal=False))


def test_cross_words_and_extending():
    g = make()
    give(g, "Ana", "CASAEEE")
    g.play("Ana", tiles("CASA", 7, 4))
    give(g, "Leo", "SOLXXXX")
    # "COLA"? Leo pone O y L debajo de la C: C-O-L vertical → "COL"
    result = g.evaluate([{"r": 8, "c": 4, "letter": "O"}, {"r": 9, "c": 4, "letter": "L"}])
    assert [w["word"] for w in result["words"]] == ["COL"]
    # una S al final de CASA forma CASAS
    result = g.evaluate([{"r": 7, "c": 8, "letter": "S"}])
    assert result["words"][0]["word"] == "CASAS"


def test_blank_scores_zero_and_bingo_bonus():
    g = make(check=False)
    give(g, "Ana", list("CAMION") + ["?"])
    play = tiles("CAMIONS", 7, 1, blanks=(6,))  # 7 letras, la S es comodín
    result = g.evaluate(play)
    assert result["bingo"]
    g.play("Ana", play)
    assert g.board[7][7]["blank"] and g.scores["Ana"] == result["score"] >= 50


def test_exchange_and_pass_end_the_game_after_four_scoreless_turns():
    g = make()
    before = g.racks["Ana"][:]
    g.exchange("Ana", before[:3])
    assert len(g.racks["Ana"]) == 7 and len(g.bag) == 86 and g.turn == "Leo"
    g.pass_turn("Leo")
    g.pass_turn("Ana")
    g.pass_turn("Leo")
    assert g.phase == "finished" and g.final["out"] is None
    assert g.snapshot()["racks"]["Ana"]


def test_going_out_collects_rival_rack():
    g = make(check=False)
    g.bag = []
    give(g, "Ana", "OS")
    give(g, "Leo", "QZ")
    g.play("Ana", tiles("OS", 7, 7))
    assert g.phase == "finished" and g.final["out"] == "Ana"
    assert g.scores["Leo"] == -15 and g.winner == "Ana"


def test_room_rejects_wrong_turn():
    g = make()
    with pytest.raises(ValueError, match="Le toca"):
        g.handle("Leo", {"type": "cw_pass"})
