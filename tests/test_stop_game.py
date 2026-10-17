import random

import pytest

from app.games.common import normalize
from app.games.stop import CATEGORY_KEYS, LETTERS, StopGame


def make_game(rounds=2, letter="M", spelling=False):
    g = StopGame(["Ana", "Leo"], rounds=rounds, rng=random.Random(1), spelling=spelling)
    g.start()
    g.letter = letter  # fija la letra para que los tests sean legibles
    return g


FULL_M = {
    "nombre": "Melisa", "apellido": "Martínez", "ciudad": "Medellín", "fruta": "Mango",
    "color": "Morado", "animal": "Mono", "cosa": "Mesa",
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
        g.call_stop("Ana", {**FULL_M, "cosa": "  "})
    assert g.phase == "writing"
    g.call_stop("Ana", FULL_M)
    assert g.phase == "stopping" and g.stopped_by == "Ana"


def test_drafts_are_not_leaked_while_writing():
    g = make_game()
    g.save("Leo", {"nombre": "Mario", "fruta": "Mora"})
    snap = g.snapshot()
    assert snap["filled"] == {"Ana": 0, "Leo": 2}
    assert snap["results"] is None
    assert "Mario" not in str(snap)


def test_scoring_unique_shared_empty_and_wrong_letter():
    g = make_game()
    g.call_stop("Ana", FULL_M)
    # Leo manda lo último que alcanzó a escribir durante el margen
    g.save("Leo", {"nombre": "Mario", "apellido": "martinez", "ciudad": "Bogotá", "fruta": "MANGO"})
    g.on_timeout()
    assert g.phase == "review"

    r = g.results()
    assert r["Ana"]["nombre"]["points"] == 100
    assert r["Leo"]["nombre"]["points"] == 100
    assert r["Ana"]["apellido"]["points"] == 50  # Martínez == martinez
    assert r["Leo"]["fruta"]["points"] == 50
    assert r["Leo"]["ciudad"]["valid"] is False and r["Leo"]["ciudad"]["points"] == 0
    assert r["Leo"]["ciudad"]["issue"] == "letter"
    assert r["Ana"]["ciudad"]["points"] == 100  # la de Leo no cuenta
    assert r["Leo"]["color"]["points"] == 0  # vacía
    assert g.round_totals(r) == {"Ana": 600, "Leo": 200}


def test_players_can_veto_or_accept_answers():
    g = make_game()
    g.call_stop("Ana", FULL_M)
    g.save("Leo", {"animal": "Mono", "cosa": "El martillo"})
    g.on_timeout()
    assert g.results()["Ana"]["animal"]["points"] == 50

    g.toggle("Leo", "animal")  # Ana dice que no vale
    r = g.results()
    assert r["Leo"]["animal"]["valid"] is False
    assert r["Ana"]["animal"]["points"] == 100  # ahora es única

    g.toggle("Leo", "cosa")  # "El martillo" no empieza por M, pero lo aceptan
    assert g.results()["Leo"]["cosa"]["points"] == 100

    g.toggle("Leo", "animal")  # se arrepienten: vuelve a lo automático
    assert ("Leo", "animal") not in g.overrides

    with pytest.raises(ValueError):
        g.toggle("Leo", "color")  # vacía


def test_sheets_keep_a_row_per_letter_and_totals_accumulate():
    g = make_game(rounds=2)
    g.call_stop("Ana", FULL_M)
    g.on_timeout()
    g.next_round()
    assert g.phase == "writing" and g.round == 2
    assert g.sheets[0]["letter"] == "M"
    assert g.sheets[0]["totals"] == {"Ana": 700, "Leo": 0}
    assert g.totals == {"Ana": 700, "Leo": 0}

    g.on_timeout()  # se acabó el tiempo sin que nadie cantara Stop
    assert g.phase == "stopping" and g.stopped_by is None
    g.on_timeout()
    g.next_round()
    assert g.phase == "finished"
    assert len(g.snapshot()["sheets"]) == 2


def test_late_drafts_after_review_are_ignored():
    g = make_game()
    g.call_stop("Ana", FULL_M)
    g.on_timeout()
    g.save("Leo", {"nombre": "Mario"})  # llegó tarde
    assert g.results()["Leo"]["nombre"]["answer"] == ""
    with pytest.raises(ValueError):
        g.save("Intruso", {})


def test_answers_are_trimmed_and_unknown_boxes_dropped():
    g = make_game()
    g.save("Ana", {"nombre": "  Mía  ", "pais": "México", "cosa": 5, "fruta": "x" * 100})
    assert g.answers["Ana"] == {"nombre": "Mía", "fruta": "x" * 40}
    assert set(CATEGORY_KEYS) >= set(g.answers["Ana"])


def test_spelling_is_checked_except_for_names():
    g = make_game(letter="A", spelling=True)
    g.call_stop("Ana", {
        "nombre": "Axzqwe", "apellido": "Arbelaez", "ciudad": "Armenia", "fruta": "Aguacate",
        "color": "Amarilo", "animal": "Ardilla", "cosa": "Arbol",
    })
    g.save("Leo", {"ciudad": "Armeniaa", "animal": "Avestrus", "fruta": "Arandano verde"})
    g.on_timeout()
    r = g.results()
    assert r["Ana"]["nombre"]["valid"]  # los nombres no se revisan
    assert r["Ana"]["ciudad"]["valid"] and r["Ana"]["animal"]["valid"]
    assert r["Ana"]["color"]["issue"] == "spelling"
    assert r["Ana"]["color"]["suggestion"] == "amarillo"
    assert r["Leo"]["ciudad"]["issue"] == "spelling"
    assert r["Leo"]["ciudad"]["suggestion"] == "armenia"
    assert r["Leo"]["animal"]["suggestion"] == "avestruz"
    assert r["Leo"]["fruta"]["valid"]  # varias palabras, todas bien escritas

    g.toggle("Ana", "color")  # la dan por buena igual
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
