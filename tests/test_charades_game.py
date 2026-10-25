import random

import pytest

from app.games.charades import CharadesGame, deck


def make(rounds=1, level="mezcla", show_category=True):
    g = CharadesGame(["Ana", "Leo"], seconds=60, level=level, show_category=show_category, rounds=rounds, rng=random.Random(1))
    g.start()
    return g


def test_deck_has_categories_and_both_levels():
    cards = deck()
    assert len(cards) > 150
    assert {c["level"] for c in cards} == {"facil", "dificil"}
    assert len({c["category"] for c in cards}) >= 7
    assert {"text": "pisar un lego", "category": "Acciones", "level": "dificil"} in cards


def test_actor_must_start_and_only_they_see_the_card():
    g = make()
    assert g.phase == "ready" and g.actor == "Ana"
    with pytest.raises(ValueError, match="actuar a Ana"):
        g.begin("Leo")
    g.begin("Ana")
    ana, leo = g.snapshot("Ana"), g.snapshot("Leo")
    assert ana["card"]["text"]
    assert leo["card"] == {"text": None, "category": g.card["category"], "level": g.card["level"]}
    assert g.timer_key == ("acting", 1)


def test_category_can_be_hidden():
    g = make(show_category=False)
    g.begin("Ana")
    assert g.snapshot("Leo")["card"] is None


def test_hits_score_and_passes_stay_hidden_until_the_end():
    g = make()
    g.begin("Ana")
    first = g.card["text"]
    g.resolve("Ana", "hit")
    g.resolve("Ana", "pass")
    with pytest.raises(ValueError):
        g.resolve("Leo", "hit")
    assert g.scores["Ana"] == 1
    leo = g.snapshot("Leo")
    assert [c["text"] for c in leo["played"]] == [first] and leo["hits"] == 1
    assert len(g.snapshot("Ana")["played"]) == 2
    g.on_timeout()
    assert g.phase == "turn_over" and len(g.snapshot("Leo")["played"]) == 2


def test_turns_alternate_and_game_finishes():
    g = make(rounds=1)
    g.begin("Ana")
    g.on_timeout()
    g.next_round()
    assert g.actor == "Leo" and g.phase == "ready"
    g.begin("Leo")
    g.resolve("Leo", "hit")
    g.on_timeout()
    g.next_round()
    assert g.phase == "finished"
    assert [h["hits"] for h in g.snapshot()["history"]] == [0, 1]


def test_levels_filter_the_deck_and_cards_do_not_repeat():
    g = make(level="facil")
    g.begin("Ana")
    seen = set()
    for _ in range(30):
        assert g.card["level"] == "facil"
        seen.add(g.card["text"])
        g.resolve("Ana", "pass")
    assert len(seen) == 30


def test_options_are_validated():
    with pytest.raises(ValueError, match="entre los dos"):
        CharadesGame.from_options(["Ana"], {}, random.Random())
    with pytest.raises(ValueError):
        CharadesGame.from_options(["Ana", "Leo"], {"seconds": 5}, random.Random())
    with pytest.raises(ValueError):
        CharadesGame.from_options(["Ana", "Leo"], {"level": "imposible"}, random.Random())
