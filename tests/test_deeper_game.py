import random

import pytest

from app.games.deeper import LEVELS, DeeperGame, deck


def make(**kwargs):
    kwargs.setdefault("wildcards", False)
    g = DeeperGame(["Ana", "Leo"], rng=random.Random(3), **kwargs)
    g.start()
    return g


def next_card(g):
    g.handle("Ana", {"type": "dp_next", "at": g.count})


def test_deck_has_every_section_with_unique_cards():
    cards = deck()
    for level in LEVELS:
        assert len(cards[level]) >= 80
        assert any(c["kind"] == "both" for c in cards[level])
    assert len(cards["wildcard"]) >= 20
    texts = [c["text"] for section in cards.values() for c in section]
    assert len(texts) == len(set(texts))
    assert not any(t.startswith("[") for t in texts)


def test_turns_alternate_and_level_cards_come_from_the_level():
    g = make()
    assert g.phase == "cards" and g.level == "icebreaker"
    seen = []
    for _ in range(6):
        assert g.card["level"] == "icebreaker"
        seen.append(g.answerer)
        next_card(g)
    assert seen == ["Ana", "Leo"] * 3


def test_double_tap_is_ignored():
    g = make()
    at = g.count
    g.handle("Ana", {"type": "dp_next", "at": at})
    card = g.card
    g.handle("Leo", {"type": "dp_next", "at": at})  # same card they were both looking at
    assert g.card is card and g.count == at + 1


def test_cards_dont_repeat_until_the_level_runs_out():
    g = make()
    total = len(deck()["icebreaker"])
    ids = [g.card["id"]]
    for _ in range(total - 1):
        next_card(g)
        ids.append(g.card["id"])
    assert len(set(ids)) == total
    next_card(g)  # reshuffled, without repeating the card on screen
    assert g.card["id"] != ids[-1]


def test_skip_keeps_the_same_player():
    g = make()
    who, card = g.answerer, g.card
    g.handle("Leo", {"type": "dp_skip", "at": g.count})
    assert g.answerer == who and g.card is not card
    assert g.skipped == 1 and g.played["icebreaker"] == 1


def test_going_deeper_needs_both_votes():
    g = make()
    g.handle("Ana", {"type": "dp_deeper"})
    assert g.level == "icebreaker" and g.snapshot("Leo")["votes"]["deeper"] == ["Ana"]
    g.handle("Ana", {"type": "dp_deeper"})  # changed her mind
    assert g.votes["deeper"] == set()
    g.handle("Ana", {"type": "dp_deeper"})
    g.handle("Leo", {"type": "dp_deeper"})
    assert g.level == "deep" and g.card["level"] == "deep"
    assert g.votes["deeper"] == set()
    g.handle("Ana", {"type": "dp_deeper"})
    g.handle("Leo", {"type": "dp_deeper"})
    assert g.level == "deeper"
    with pytest.raises(ValueError, match="más profundo"):
        g.handle("Ana", {"type": "dp_deeper"})


def test_can_start_deeper():
    g = DeeperGame.from_options(["Ana", "Leo"], {"start": "deep"}, random.Random(1))
    g.start()
    assert g.level == "deep" and g.card["level"] in ("deep", "wildcard")
    with pytest.raises(ValueError):
        DeeperGame.from_options(["Ana", "Leo"], {"start": "hondo"}, random.Random(1))
    with pytest.raises(ValueError, match="entre los dos"):
        DeeperGame.from_options(["Ana"], {}, random.Random(1))


def test_saving_cards():
    g = make()
    first = g.card
    g.handle("Leo", {"type": "dp_save"})
    assert g.snapshot("Ana")["savedCurrent"]
    next_card(g)
    g.handle("Ana", {"type": "dp_save"})
    g.handle("Ana", {"type": "dp_save"})  # unsave
    assert [c["id"] for c in g.saved] == [first["id"]]


def test_wildcards_show_up_but_never_first_or_twice_in_a_row():
    g = make(wildcards=True)
    kinds = [g.card["kind"]]
    for _ in range(300):
        next_card(g)
        kinds.append(g.card["kind"])
    assert kinds[0] != "wildcard"
    assert 20 < kinds.count("wildcard") < 100
    assert not any(a == b == "wildcard" for a, b in zip(kinds, kinds[1:]))


def test_letters_stay_sealed_until_both_are_sent():
    g = make()
    g.handle("Ana", {"type": "dp_finish"})
    assert g.phase == "cards"
    g.handle("Leo", {"type": "dp_finish"})
    assert g.phase == "letters" and g.card is None
    with pytest.raises(ValueError, match="Escribe algo"):
        g.handle("Ana", {"type": "dp_letter", "text": "   "})
    g.handle("Ana", {"type": "dp_letter", "text": "Gracias por esta noche"})
    assert g.snapshot("Leo")["letters"] == {} and g.snapshot("Leo")["lettersSent"] == ["Ana"]
    assert g.snapshot("Ana")["letters"] == {"Ana": "Gracias por esta noche"}
    with pytest.raises(ValueError, match="Ya enviaste"):
        g.handle("Ana", {"type": "dp_letter", "text": "otra"})
    g.handle("Leo", {"type": "dp_letter", "text": "Te quiero"})
    assert g.phase == "finished"
    assert g.snapshot("Ana")["letters"] == {"Ana": "Gracias por esta noche", "Leo": "Te quiero"}


def test_without_letter_it_ends_right_away():
    g = make(letter=False)
    g.handle("Ana", {"type": "dp_finish"})
    g.handle("Leo", {"type": "dp_finish"})
    assert g.phase == "finished"
    with pytest.raises(ValueError):
        next_card(g)
