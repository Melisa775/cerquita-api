import random

import pytest

from app.games.hangman import WORDS, HangmanGame, base_letter


def turns_game(rounds=2, lives=6):
    g = HangmanGame.from_options(["Ana", "Leo"], {"mode": "turns", "rounds": rounds, "lives": lives}, random.Random(1))
    g.start()
    return g


def letters(snap):
    return "".join(s["char"] or "_" for s in snap["slots"])


def test_base_letter_ignores_accents_but_not_enie():
    assert [base_letter(c) for c in "ÁéÍóÚüÑñ -"] == ["a", "e", "i", "o", "u", "u", "ñ", "ñ", " ", "-"]


def test_setter_writes_word_and_only_they_can_see_it():
    g = turns_game()
    assert g.phase == "choosing" and g.setter == "Ana" and g.guessers == ["Leo"]
    with pytest.raises(ValueError, match="pareja"):
        g.set_word("Leo", "hola", "")
    with pytest.raises(ValueError):
        g.set_word("Ana", "ab", "")
    with pytest.raises(ValueError):
        g.set_word("Ana", "hola123", "")
    g.set_word("Ana", "  Corazón   de melón ", "Algo dulce")
    assert g.word == "Corazón de melón" and g.phase == "guessing"

    leo = g.snapshot("Leo")
    assert letters(leo) == "_______ __ _____"
    assert leo["hint"] == "Algo dulce"
    assert "Corazón" not in str(leo)
    assert letters(g.snapshot("Ana")) == "Corazón de melón"  # quien eligió la ve


def test_guessing_reveals_accented_letters_and_counts_misses():
    g = turns_game()
    g.set_word("Ana", "Corazón de melón", "")
    with pytest.raises(ValueError, match="mirar"):
        g.guess("Ana", "o")
    g.guess("Leo", "O")
    assert letters(g.snapshot("Leo")) == "_o___ó_ __ ___ó_"
    g.guess("Leo", "x")
    g.guess("Leo", "z")
    assert g.snapshot("Leo")["wrong"] == ["x"] and g.misses == 1
    with pytest.raises(ValueError, match="ya salió"):
        g.guess("Leo", "ó")


def test_guesser_wins_point_when_solving_and_roles_swap():
    g = turns_game()
    g.set_word("Ana", "luna", "")
    for c in "lun":
        g.guess("Leo", c)
    g.guess("Leo", "a")
    assert g.phase == "round_over"
    assert g.result["won"] and g.result["winner"] == "Leo" and g.result["livesLeft"] == 6
    assert g.scores == {"Ana": 0, "Leo": 1}
    g.next_round()
    assert g.setter == "Leo" and g.guessers == ["Ana"]


def test_setter_wins_when_lives_run_out_and_wrong_solve_costs_a_life():
    g = turns_game(rounds=1, lives=6)
    g.set_word("Ana", "sol", "")
    g.solve("Leo", "mar")  # no era
    assert g.misses == 1 and g.wrong_solves == ["mar"]
    for c in "xyzwq":
        g.guess("Leo", c)
    assert g.phase == "round_over" and not g.result["won"]
    assert g.scores == {"Ana": 1, "Leo": 0}
    assert g.snapshot("Leo")["slots"][0]["char"] == "s"  # al final se revela
    g.next_round()
    assert g.phase == "finished" and g.snapshot()["history"][0]["word"] == "sol"


def test_solving_the_whole_word_ignores_accents_and_case():
    g = turns_game()
    g.set_word("Ana", "Corazón de melón", "")
    g.solve("Leo", "corazon DE melon")
    assert g.result["won"] and g.scores["Leo"] == 1


def test_random_mode_is_cooperative_and_words_do_not_repeat():
    g = HangmanGame.from_options(["Ana", "Leo"], {"mode": "random", "rounds": 3, "lives": 8}, random.Random(4))
    g.start()
    assert g.phase == "guessing" and g.setter is None and g.guessers == ["Ana", "Leo"]
    assert g.category in WORDS and g.word in WORDS[g.category]
    first = g.word
    g.solve("Ana", first)
    assert g.saved == 1 and g.result["winner"] is None
    g.next_round()
    assert g.word != first
    g.guess("Leo", next(iter(g._letters_in_word())))  # los dos pueden jugar


def test_options_are_validated():
    with pytest.raises(ValueError, match="necesitan estar los dos"):
        HangmanGame.from_options(["Ana"], {"mode": "turns"}, random.Random())
    with pytest.raises(ValueError):
        HangmanGame.from_options(["Ana", "Leo"], {"lives": 3}, random.Random())
    with pytest.raises(ValueError):
        HangmanGame.from_options(["Ana", "Leo"], {"mode": "otro"}, random.Random())
    assert HangmanGame.from_options(["Ana"], {"mode": "random"}, random.Random()).mode == "random"


def test_word_lists_only_use_valid_characters():
    from app.games.hangman import ALLOWED, MAX_WORD

    for words in WORDS.values():
        for w in words:
            assert ALLOWED.match(w) and len(w) <= MAX_WORD, w
