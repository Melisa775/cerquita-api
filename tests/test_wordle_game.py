import random

import pytest

from app.games.wordle import LENGTHS, MAX_TRIES, WordleGame, answers, is_valid, score_guess


def duel(answer="gatos", rounds=2):
    g = WordleGame(["Ana", "Leo"], mode="duel", length=5, rounds=rounds, rng=random.Random(1), word_list=[answer])
    g.start()
    return g


def team(answer="gatos", rounds=2):
    g = WordleGame(["Ana", "Leo"], mode="team", length=5, rounds=rounds, rng=random.Random(1), word_list=[answer])
    g.start()
    return g


@pytest.mark.parametrize(
    ("guess", "answer", "expected"),
    [
        ("gatos", "gatos", "CCCCC"),
        ("sagot", "gatos", "PCPCP"),
        ("perro", "gatos", "AAAAP"),
        ("llama", "plato", "ACCAA"),  # the second L and the second A no longer count
        ("aabbb", "ababa", "CPPCA"),  # only two B's left: the third is gray
        ("mamma", "madre", "CCAAA"),
    ],
)
def test_score_guess_handles_repeated_letters(guess, answer, expected):
    code = {"correct": "C", "present": "P", "absent": "A"}
    assert "".join(code[m] for m in score_guess(guess, answer)) == expected


def test_answer_lists_are_clean():
    for n in LENGTHS:
        words = answers()[n]
        assert len(words) >= 100
        assert all(len(w) == n and is_valid(w) for w in words)


def test_duel_hides_letters_from_the_other_player():
    g = duel()
    g.guess("Ana", "perro")
    leo = g.snapshot("Leo")
    assert leo["boards"]["Ana"][0]["word"] is None
    assert leo["boards"]["Ana"][0]["marks"] == ["absent"] * 4 + ["present"]
    assert g.snapshot("Ana")["boards"]["Ana"][0]["word"] == "perro"
    assert leo["answer"] is None and "gatos" not in str(leo)


def test_guess_validation():
    g = duel()
    with pytest.raises(ValueError, match="5 letras"):
        g.guess("Ana", "gato")
    with pytest.raises(ValueError, match="diccionario"):
        g.guess("Ana", "qxzpt")
    g.guess("Ana", "Pérro")  # accents don't count
    with pytest.raises(ValueError, match="Ya probaste"):
        g.guess("Ana", "perro")


def test_duel_winner_is_fewer_tries_then_first_to_solve():
    g = duel()
    g.guess("Leo", "perro")
    g.guess("Ana", "perro")
    g.guess("Ana", "gatos")  # Ana: 2 attempts
    assert g.phase == "playing"  # Leo keeps going
    g.guess("Leo", "gatos")  # Leo: 2 attempts, but later
    assert g.phase == "round_over"
    assert g.result["winner"] == "Ana" and g.scores == {"Ana": 1, "Leo": 0}
    assert g.snapshot("Leo")["boards"]["Ana"][1]["word"] == "gatos"  # everything is visible at the end
    assert g.snapshot("Leo")["answer"] == "gatos"


def test_duel_without_solving_nobody_scores():
    g = duel(rounds=1)
    for word in ["perro", "barco", "nubes", "mesas", "lunes", "cielo"]:
        g.guess("Ana", word)
        g.guess("Leo", word)
    assert g.phase == "round_over" and g.result["winner"] is None
    with pytest.raises(ValueError):
        g.guess("Ana", "gatos")
    g.next_round()
    assert g.phase == "finished"


def test_team_takes_turns_and_shares_a_board():
    g = team()
    assert g.current == "Ana"
    g.set_draft("Ana", "per")
    assert g.snapshot("Leo")["draft"] == "per"
    g.set_draft("Leo", "xx")  # not their turn: ignored
    assert g.draft == "per"
    with pytest.raises(ValueError, match="turno de Ana"):
        g.guess("Leo", "perro")
    g.guess("Ana", "perro")
    assert g.current == "Leo" and g.draft == ""
    with pytest.raises(ValueError, match="Ya probaron"):
        g.guess("Leo", "perro")
    g.guess("Leo", "gatos")
    assert g.result == {"solved": True, "tries": 2, "by": "Leo"} and g.saved == 1
    g.next_round()
    assert g.current == "Leo"  # the other player starts


def test_team_runs_out_of_tries():
    g = team(rounds=1)
    for i, word in enumerate(["perro", "barco", "nubes", "mesas", "lunes", "cielo"]):
        g.guess(g.current, word)
    assert len(g.team_rows) == MAX_TRIES and g.result["solved"] is False


def test_options_are_validated():
    with pytest.raises(ValueError):
        WordleGame.from_options(["Ana"], {"length": 7}, random.Random())
    with pytest.raises(ValueError):
        WordleGame.from_options(["Ana"], {"mode": "otro"}, random.Random())
    g = WordleGame.from_options(["Ana"], {"length": 4, "mode": "team"}, random.Random(2))
    g.start()
    assert len(g.answer) == 4
