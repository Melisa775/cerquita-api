import asyncio
import random

import pytest

from app.games.anzuelo import AnzueloGame
from app.games.anzuelo_data import QUESTIONS
from app.rooms import Room

Q = [("Prueba", "¿De qué color es el caballo blanco?", "Blanco", ["Negro", "Café", "Gris"])]


def new(players=("Ana", "Leo", "Sol"), seed=1, **kw):
    g = AnzueloGame(list(players), rng=random.Random(seed), questions=Q * 20, **kw)
    g.start()
    return g


def liars(g):
    return [p for p, r in g.roles.items() if r == "liar"]


def honest(g):
    return next(p for p, r in g.roles.items() if r == "honest")


def write_all(g):
    for i, p in enumerate(liars(g)):
        if g.answers[p] is None:
            g.handle(p, {"type": "az_answer", "text": f"Mentira número {i}"})


def test_question_bank_is_well_formed():
    assert len(QUESTIONS) >= 90
    seen = set()
    for cat, q, a, fakes in QUESTIONS:
        assert cat and q.endswith("?") and a and len(fakes) >= 3
        assert a not in fakes and len(set(fakes)) == len(fakes)
        assert q not in seen
        seen.add(q)


def test_options():
    with pytest.raises(ValueError):
        AnzueloGame.from_options(["Ana", "Leo"], {}, rng=random.Random())  # two people need a bot
    g = AnzueloGame.from_options(["Ana", "Leo"], {"bots": 1, "laps": 2}, rng=random.Random())
    assert len(g.players) == 3 and g.bots and g.total_rounds == 6
    with pytest.raises(ValueError):
        AnzueloGame.from_options(["Ana", "B", "C", "D", "E"], {"bots": 3}, rng=random.Random())  # 8 > 6


def test_roles_and_what_each_one_sees():
    g = new(("Ana", "Leo", "Sol", "Mar"))
    assert g.phase == "write"
    fish = [p for p in g.order if p != g.guesser]
    assert sorted(g.roles) == sorted(fish) and list(g.roles.values()).count("honest") == 1
    s_guesser = g.snapshot(g.guesser)
    assert s_guesser["answer"] is None and s_guesser["myRole"] == "guesser" and s_guesser["roles"] == {}
    h = honest(g)
    s_h = g.snapshot(h)
    assert s_h["answer"] == "Blanco" and s_h["myRole"] == "honest" and s_h["myAnswer"] == "Blanco"
    l = liars(g)[0]
    assert g.snapshot(l)["myRole"] == "liar" and g.snapshot(l)["cards"] == []


def test_liars_cannot_tell_the_truth_or_copy():
    g = new(("Ana", "Leo", "Sol", "Mar"))
    a, b = liars(g)
    with pytest.raises(ValueError, match="verdadera"):
        g.handle(a, {"type": "az_answer", "text": "  blanco "})
    with pytest.raises(ValueError):
        g.handle(honest(g), {"type": "az_answer", "text": "otra cosa"})
    with pytest.raises(ValueError):
        g.handle(g.guesser, {"type": "az_answer", "text": "otra cosa"})
    g.handle(a, {"type": "az_answer", "text": "Gris perla"})
    with pytest.raises(ValueError, match="ya dijo"):
        g.handle(b, {"type": "az_answer", "text": "gris PERLA"})
    g.handle(b, {"type": "az_answer", "text": "Plateado"})
    assert g.phase == "fish" and len(g.snapshot(g.guesser)["cards"]) == 3


def test_catching_every_liar_scores_with_bonus():
    g = new(("Ana", "Leo", "Sol", "Mar"))
    write_all(g)
    fisher = g.guesser
    with pytest.raises(ValueError):
        g.handle(liars(g)[0], {"type": "az_catch", "player": liars(g)[1]})
    for p in liars(g):
        g.handle(fisher, {"type": "az_catch", "player": p})
    assert g.phase == "reveal"
    assert g.round_points[fisher] == 3  # two liars + bonus
    assert all(g.round_points[p] == 0 for p in liars(g)) and g.round_points[honest(g)] == 0
    assert g.snapshot(fisher)["roles"]  # everything shows at the end of the round


def test_catching_the_honest_fish_loses_the_round():
    g = new(("Ana", "Leo", "Sol", "Mar"))
    write_all(g)
    fisher, (l1, l2), h = g.guesser, liars(g), honest(g)
    g.handle(fisher, {"type": "az_catch", "player": l1})
    assert g.pending == 1 and g.snapshot(fisher)["cards"][g.cards.index(l1)]["role"] == "liar"
    g.handle(fisher, {"type": "az_catch", "player": h})
    assert g.phase == "reveal" and g.busted
    assert g.round_points == {fisher: 0, l1: 0, l2: 1, h: 2}


def test_banking_keeps_points_and_rounds_rotate_until_the_end():
    g = new(("Ana", "Leo", "Sol"))
    fishers = []
    while g.phase != "finished":
        fishers.append(g.guesser)
        write_all(g)
        g.handle(g.guesser, {"type": "az_catch", "player": liars(g)[0]})
        if g.phase == "fish":
            g.handle(g.guesser, {"type": "az_bank"})
        g.handle("Ana", {"type": "az_next"})
    assert sorted(fishers) == ["Ana", "Leo", "Sol"]  # everyone fished once
    assert g.winners and sum(g.scores.values()) > 0


def test_timeouts_fill_missing_answers_and_move_on():
    g = new(("Ana", "Leo", "Sol", "Mar"))
    g.handle(liars(g)[0], {"type": "az_answer", "text": "Gris"})  # same as a fake: the filler picks another
    g.on_timeout()
    assert g.phase == "fish" and all(g.answers.values())
    assert len({v.lower() for v in g.answers.values()}) == 3
    g.on_timeout()
    assert g.phase == "reveal"
    g.on_timeout()
    assert g.round == 1 and g.phase == "write"


def test_bots_lie_by_themselves_and_fish_alone():
    g = AnzueloGame(["Ana"], bots=["Coral 🤖", "Bagre 🤖", "Perla 🤖"], rng=random.Random(5), questions=Q * 10)
    g.start()
    for _ in range(200):
        if g.phase == "finished":
            break
        if g.phase == "write":
            write_all(g)
        elif g.phase == "fish":
            if g.guesser == "Ana":
                g.handle("Ana", {"type": "az_bank"})
            else:
                assert g.play_bot()
        elif g.phase == "reveal":
            g.handle("Ana", {"type": "az_next"})
    assert g.phase == "finished"


async def test_room_plays_anzuelo_with_bots():
    room = Room("PESCA", timings={"bot": 0.01})

    class Conn:
        async def send_json(self, data):
            self.last = data

    ana, leo = Conn(), Conn()
    await room.join("Ana", ana)
    await room.join("Leo", leo)
    await room.handle("Ana", {"type": "start_game", "game": "anzuelo", "bots": 1})
    g = room.game
    assert g.name == "anzuelo" and len(g.players) == 3
    assert ana.last["game"]["question"]
    room.close()
