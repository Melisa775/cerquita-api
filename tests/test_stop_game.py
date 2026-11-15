import random

import pytest

from app.games.common import normalize
from app.games.stop import CATEGORY_KEYS, LETTERS, StopGame


def make_game(rounds=2, letter="M", spelling=False):
    g = StopGame(["Ana", "Leo"], rounds=rounds, rng=random.Random(1), spelling=spelling)
    g.start()
    g.letter = letter  # fix the letter so the tests are readable
    return g


FULL_M = {
    "name": "Melisa", "surname": "Martínez", "city": "Medellín", "fruit": "Mango",
    "color": "Morado", "animal": "Mono", "thing": "Mesa",
}


def test_normalize_ignores_accents_case_and_signs_but_keeps_enie():
    assert normalize("  Medellín ") == "medellin"
    assert normalize("ÑANDÚ") == "ñandu"
    assert normalize("San-Andrés!") == "sanandres"
    assert normalize("   ") == ""


def test_letters_do_not_repeat_within_a_game():
    g = StopGame(["Ana"], rounds=10, rng=random.Random(3))
    g.start()
    seen = [g.letter]
    for _ in range(9):
        g.on_timeout()
        g.on_timeout()
        g.next_round()
        seen.append(g.letter)
    assert len(set(seen)) == 10
    assert all(c in LETTERS for c in seen)


def test_cannot_call_stop_with_empty_boxes():
    g = make_game()
    with pytest.raises(ValueError):
        g.call_stop("Ana", {**FULL_M, "thing": "  "})
    assert g.phase == "writing"
    g.call_stop("Ana", FULL_M)
    assert g.phase == "stopping" and g.stopped_by == "Ana"


def test_drafts_are_not_leaked_while_writing():
    g = make_game()
    g.save("Leo", {"name": "Mario", "fruit": "Mora"})
    snap = g.snapshot()
    assert snap["filled"] == {"Ana": 0, "Leo": 2}
    assert snap["results"] is None
    assert "Mario" not in str(snap)


def test_scoring_unique_shared_empty_and_wrong_letter():
    g = make_game()
    g.call_stop("Ana", FULL_M)
    # Leo sends what he managed to type during the grace period
    g.save("Leo", {"name": "Mario", "surname": "martinez", "city": "Bogotá", "fruit": "MANGO"})
    g.on_timeout()
    assert g.phase == "review"

    r = g.results()
    assert r["Ana"]["name"]["points"] == 100
    assert r["Leo"]["name"]["points"] == 100
    assert r["Ana"]["surname"]["points"] == 50  # Martínez == martinez
    assert r["Leo"]["fruit"]["points"] == 50
    assert r["Leo"]["city"]["valid"] is False and r["Leo"]["city"]["points"] == 0
    assert r["Leo"]["city"]["issue"] == "letter"
    assert r["Ana"]["city"]["points"] == 100  # Leo's doesn't count
    assert r["Leo"]["color"]["points"] == 0  # empty
    assert g.round_totals(r) == {"Ana": 600, "Leo": 200}


def test_players_can_veto_or_accept_answers():
    g = make_game()
    g.call_stop("Ana", FULL_M)
    g.save("Leo", {"animal": "Mono", "thing": "El martillo"})
    g.on_timeout()
    assert g.results()["Ana"]["animal"]["points"] == 50

    g.toggle("Leo", "animal")  # Ana says it doesn't count
    r = g.results()
    assert r["Leo"]["animal"]["valid"] is False
    assert r["Ana"]["animal"]["points"] == 100  # now it's unique

    g.toggle("Leo", "thing")  # "El martillo" doesn't start with M, but they accept it
    assert g.results()["Leo"]["thing"]["points"] == 100

    g.toggle("Leo", "animal")  # they change their mind: back to automatic
    assert ("Leo", "animal") not in g.overrides

    with pytest.raises(ValueError):
        g.toggle("Leo", "color")  # empty


def test_sheets_keep_a_row_per_letter_and_totals_accumulate():
    g = make_game(rounds=2)
    g.call_stop("Ana", FULL_M)
    g.on_timeout()
    g.next_round()
    assert g.phase == "writing" and g.round == 2
    assert g.sheets[0]["letter"] == "M"
    assert g.sheets[0]["totals"] == {"Ana": 700, "Leo": 0}
    assert g.totals == {"Ana": 700, "Leo": 0}

    g.on_timeout()  # time ran out without anyone calling Stop
    assert g.phase == "stopping" and g.stopped_by is None
    g.on_timeout()
    g.next_round()
    assert g.phase == "finished"
    assert len(g.snapshot()["sheets"]) == 2


def test_late_drafts_after_review_are_ignored():
    g = make_game()
    g.call_stop("Ana", FULL_M)
    g.on_timeout()
    g.save("Leo", {"name": "Mario"})  # arrived late
    assert g.results()["Leo"]["name"]["answer"] == ""
    with pytest.raises(ValueError):
        g.save("Intruso", {})


def test_answers_are_trimmed_and_unknown_boxes_dropped():
    g = make_game()
    g.save("Ana", {"name": "  Mía  ", "pais": "México", "thing": 5, "fruit": "x" * 100})
    assert g.answers["Ana"] == {"name": "Mía", "fruit": "x" * 40}
    assert set(CATEGORY_KEYS) >= set(g.answers["Ana"])


def test_spelling_is_checked_except_for_names():
    g = make_game(letter="A", spelling=True)
    g.call_stop("Ana", {
        "name": "Axzqwe", "surname": "Arbelaez", "city": "Armenia", "fruit": "Aguacate",
        "color": "Amarilo", "animal": "Ardilla", "thing": "Arbol",
    })
    g.save("Leo", {"city": "Armeniaa", "animal": "Avestrus", "fruit": "Arandano verde"})
    g.on_timeout()
    r = g.results()
    assert r["Ana"]["name"]["valid"]  # names aren't checked
    assert r["Ana"]["city"]["valid"] and r["Ana"]["animal"]["valid"]
    assert r["Ana"]["color"]["issue"] == "spelling"
    assert r["Ana"]["color"]["suggestion"] == "amarillo"
    assert r["Leo"]["city"]["issue"] == "spelling"
    assert r["Leo"]["city"]["suggestion"] == "armenia"
    assert r["Leo"]["animal"]["suggestion"] == "avestruz"
    assert r["Leo"]["fruit"]["valid"]  # several words, all spelled correctly

    g.toggle("Ana", "color")  # they accept it anyway
    assert g.results()["Ana"]["color"]["points"] == 100


def test_spelling_can_be_turned_off():
    g = StopGame.from_options(["Ana"], {"spelling": False}, random.Random(1))
    g.start()
    g.letter = "A"
    g.save("Ana", {"color": "Amarilo"})
    g.on_timeout()
    g.on_timeout()
    assert g.results()["Ana"]["color"]["valid"]
    assert g.snapshot()["spellChecked"] == []
