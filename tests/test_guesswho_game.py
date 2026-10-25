import random

import pytest

from app.games.guesswho import CHARACTERS, QUESTIONS, GuessWhoGame


def make(rounds=2, size=24):
    g = GuessWhoGame.from_options(["Ana", "Leo"], {"rounds": rounds, "boardSize": size}, random.Random(5))
    g.start()
    return g


def test_every_question_splits_the_characters():
    for key, (text, check) in QUESTIONS.items():
        yes = sum(1 for c in CHARACTERS.values() if check(c))
        assert 2 <= yes <= 22, (key, yes)
    assert len(CHARACTERS) == 24
    assert len({c["name"] for c in CHARACTERS.values()}) == 24


def test_each_player_only_sees_their_own_secret():
    g = make()
    ana, leo = g.snapshot("Ana"), g.snapshot("Leo")
    assert ana["mySecret"] == g.secrets["Ana"] and leo["mySecret"] == g.secrets["Leo"]
    assert ana["secrets"] == {} and g.secrets["Leo"] != g.secrets["Ana"]
    assert all(s in g.board for s in g.secrets.values())
    assert len(ana["characters"]) == 24


def test_list_questions_are_answered_by_the_app_and_turns_alternate():
    g = make()
    assert g.current == "Ana"
    g.ask("Ana", "gafas")
    entry = g.log[-1]
    assert entry["asker"] == "Ana" and entry["auto"]
    assert entry["answer"] == CHARACTERS[g.secrets["Leo"]]["gafas"]
    assert g.current == "Leo"
    with pytest.raises(ValueError, match="turno de Leo"):
        g.ask("Ana", "pecas")


def test_free_questions_wait_for_the_partner():
    g = make()
    g.ask_free("Ana", "se parece a mí")
    assert g.pending == {"asker": "Ana", "text": "¿se parece a mí?"}
    with pytest.raises(ValueError, match="responder"):
        g.ask("Leo", "gafas")
    with pytest.raises(ValueError, match="pareja"):
        g.answer("Ana", True)
    g.answer("Leo", False)
    assert g.log[-1] == {"asker": "Ana", "text": "¿se parece a mí?", "answer": False, "auto": False}
    assert g.pending is None and g.current == "Leo"


def test_flipping_is_private_and_free():
    g = make()
    cid = g.board[0]
    g.flip("Leo", cid)  # no hace falta que sea su turno
    assert g.snapshot("Leo")["flipped"] == [cid]
    assert g.snapshot("Ana")["flipped"] == []
    assert g.snapshot("Ana")["remaining"] == {"Ana": 24, "Leo": 23}
    g.flip("Leo", cid)
    assert g.snapshot("Leo")["flipped"] == []


def test_right_guess_wins_wrong_guess_loses():
    g = make()
    g.guess("Ana", g.secrets["Leo"])
    assert g.result["correct"] and g.result["winner"] == "Ana"
    assert g.snapshot("Leo")["secrets"] == g.secrets  # al final se revelan
    g.next_round()
    assert g.current == "Leo"
    wrong = next(c for c in g.board if c != g.secrets["Ana"])
    g.guess("Leo", wrong)
    assert not g.result["correct"] and g.result["winner"] == "Ana"
    assert g.scores == {"Ana": 2, "Leo": 0}
    g.next_round()
    assert g.phase == "finished" and len(g.snapshot()["history"]) == 2


def test_options_need_two_players():
    with pytest.raises(ValueError, match="entre los dos"):
        GuessWhoGame.from_options(["Ana"], {}, random.Random())
    with pytest.raises(ValueError):
        GuessWhoGame.from_options(["Ana", "Leo"], {"boardSize": 10}, random.Random())
    g = make(size=16)
    assert len(g.board) == 16
