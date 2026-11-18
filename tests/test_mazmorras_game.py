import asyncio
import random

import pytest

from app.games.mazmorras import MazmorrasGame
from app.games.mazmorras_data import ADVENTURES, CLASSES, MONSTERS
from app.rooms import Room


def new_game(players=("Ana", "Leo"), seed=1, **options):
    g = MazmorrasGame.from_options(list(players), options, rng=random.Random(seed))
    g.start()
    return g


def pick_all(g, classes=("guerrero", "clerigo", "mago", "picaro")):
    people = [p for p in g.hero_order if not g.is_bot(p)]
    for p, c in zip(people, classes):
        g.handle(p, {"type": "mz_pick", "cls": c})


def test_data_is_consistent():
    for adv in ADVENTURES.values():
        rooms = adv["rooms"]
        assert adv["start"] in rooms
        assert sum(1 for r in rooms.values() if r.get("final")) == 1
        for rid, r in rooms.items():
            for e in r["exits"]:
                assert rid in rooms[e]["exits"], f"{rid} -> {e} is one-way"
            for m in r["monsters"]:
                assert m in MONSTERS
            if r.get("feature"):
                assert r["feature"]["ability"] in CLASSES["guerrero"]["mods"]


def test_options_and_creating_the_party():
    with pytest.raises(ValueError):
        MazmorrasGame.from_options(["Ana"], {"dm": "Ana"}, rng=random.Random())  # nobody left to play
    with pytest.raises(ValueError):
        MazmorrasGame.from_options(["Ana"], {"dm": "Zoe"}, rng=random.Random())
    with pytest.raises(ValueError):
        MazmorrasGame.from_options(["Ana"], {"adventure": "luna"}, rng=random.Random())
    g = new_game(("Ana", "Leo", "Sol"), dm="Sol")
    assert g.phase == "creating" and g.hero_order == ["Ana", "Leo"]
    with pytest.raises(ValueError):
        g.handle("Sol", {"type": "mz_pick", "cls": "mago"})  # the DM has no hero
    with pytest.raises(ValueError):
        g.handle("Ana", {"type": "mz_pick", "cls": "bardo"})
    g.handle("Ana", {"type": "mz_pick", "cls": "guerrero"})
    assert g.phase == "creating"
    g.handle("Leo", {"type": "mz_pick", "cls": "mago"})
    assert g.phase == "explore" and g.room == ADVENTURES["cripta"]["start"]
    s = g.snapshot("Sol")
    assert s["isDm"] and s["me"] is None
    assert s["heroes"][0]["maxHp"] == CLASSES["guerrero"]["hp"]


def test_companions_pick_by_themselves_and_alone_works():
    g = new_game(("Ana",), companions=2)
    assert len(g.companions) == 2 and all(g.picks[b] for b in g.companions)
    assert g.phase == "creating"
    g.handle("Ana", {"type": "mz_pick", "cls": "picaro"})
    assert g.phase == "explore" and len(g.heroes) == 3


def test_moving_into_monsters_starts_a_fight_and_exits_are_checked():
    g = new_game()
    pick_all(g)
    with pytest.raises(ValueError):
        g.handle("Ana", {"type": "mz_move", "room": "trono"})
    g.handle("Ana", {"type": "mz_move", "room": "sala_ratas"})
    assert g.phase == "combat"
    assert len(g.monsters) == 2 and set(g.order) == {"Ana", "Leo", "m1", "m2"}
    with pytest.raises(ValueError):
        g.handle("Ana", {"type": "mz_move", "room": "entrada"})  # no running away mid-fight
    not_turn = next(p for p in ("Ana", "Leo") if p != g.turn)
    if g.turn in ("Ana", "Leo"):
        with pytest.raises(ValueError):
            g.handle(not_turn, {"type": "mz_attack", "target": "m1"})


def play_fight(g):
    """People attack the first monster; the auto DM plays the monsters."""
    for _ in range(300):
        if g.phase != "combat":
            return
        if g.turn in g.heroes and not g.is_bot(g.turn):
            g.handle(g.turn, {"type": "mz_attack", "target": g.alive_monsters()[0]["id"]})
        else:
            assert g.play_bot()
    raise AssertionError("the fight never ended")


def test_a_whole_fight_gives_experience_and_clears_the_room():
    g = new_game(seed=4)
    pick_all(g)
    g.handle("Ana", {"type": "mz_move", "room": "sala_ratas"})
    play_fight(g)
    assert g.phase == "explore" or g.result == "defeat"
    if g.phase == "explore":
        assert "sala_ratas" in g.cleared
        assert all(h["xp"] == 50 and h["hp"] >= 1 for h in g.heroes.values())
        assert g.bot_move() is None  # people explore by themselves


def test_attack_rolls_and_criticals():
    g = new_game(seed=2)
    pick_all(g)
    g.handle("Ana", {"type": "mz_move", "room": "sala_ratas"})
    while g.turn not in g.heroes:
        g.play_bot()
    hero = g.turn
    g.rng = random.Random()
    g.rng.randint = lambda a, b: b  # always the highest roll: a natural 20
    m = g.alive_monsters()[0]
    g.handle(hero, {"type": "mz_attack", "target": m["id"]})
    assert g.last_roll["natural"] == 20 and g.last_roll["ok"]
    assert m["hp"] == 0  # a critical hit with max dice kills a rat
    assert any("CRÍTICO" in e["text"] or "20 natural" in e["text"] for e in g.log)


def test_features_rest_and_potions():
    g = new_game(seed=3)
    pick_all(g)
    g.handle("Leo", {"type": "mz_feature"})
    with pytest.raises(ValueError):
        g.handle("Ana", {"type": "mz_feature"})  # only once per room
    assert g.last_roll and g.last_roll["target"] == 10
    ana = g.heroes["Ana"]
    ana["hp"] = 2
    g.handle("Leo", {"type": "mz_potion", "target": "Ana"})
    assert ana["hp"] > 2 and g.potions == 1
    leo = g.heroes["Leo"]
    leo["hp"] = 1
    leo["slots"] = 0
    g.handle("Ana", {"type": "mz_rest"})
    assert leo["hp"] > 1 and leo["slots"] == 1 and g.rests == 1


def test_cleric_heals_and_raises_the_fallen():
    g = new_game(seed=5)
    pick_all(g)  # Ana guerrero, Leo clerigo
    g.handle("Ana", {"type": "mz_move", "room": "sala_ratas"})
    while g.turn != "Leo":
        if g.turn == "Ana":
            g.handle("Ana", {"type": "mz_defend"})
        else:
            g.play_bot()
        if g.phase != "combat":
            pytest.skip("the rats were beaten before the cleric's turn")
    g.heroes["Ana"]["hp"] = 0
    g.handle("Leo", {"type": "mz_power", "power": "curar_heridas", "target": "Ana"})
    assert g.heroes["Ana"]["hp"] >= 4 and g.heroes["Leo"]["slots"] == 1
    with pytest.raises(ValueError):
        g.handle("Leo", {"type": "mz_power", "power": "proyectil_magico", "target": "m1"})


def test_everyone_down_is_a_defeat():
    g = new_game(seed=6)
    pick_all(g)
    g.handle("Ana", {"type": "mz_move", "room": "sala_ratas"})
    for h in g.heroes.values():
        h["hp"] = 1
        h["ac"] = 1
    for _ in range(100):
        if g.phase != "combat":
            break
        if g.turn in g.heroes:
            g.handle(g.turn, {"type": "mz_defend"})
        else:
            g.play_bot()
    assert g.phase == "finished" and g.result == "defeat" and not g.in_progress
    with pytest.raises(ValueError):
        g.handle("Ana", {"type": "mz_rest"})


def test_person_dungeon_master_tools():
    g = new_game(("Ana", "Leo", "Sol"), dm="Sol")
    pick_all(g)
    with pytest.raises(ValueError):
        g.handle("Ana", {"type": "mz_narrate", "text": "hola"})
    g.handle("Sol", {"type": "mz_narrate", "text": "Un viento frío apaga una antorcha."})
    assert g.log[-1]["kind"] == "dm"
    g.handle("Sol", {"type": "mz_check", "hero": "Ana", "ability": "fue", "dc": 12, "reason": "Empujar la roca"})
    with pytest.raises(ValueError):
        g.handle("Leo", {"type": "mz_roll"})
    g.handle("Ana", {"type": "mz_roll"})
    assert g.pending_check is None and g.last_roll["target"] == 12
    g.handle("Sol", {"type": "mz_give"})
    assert g.potions == 3
    g.handle("Sol", {"type": "mz_hp", "hero": "Leo", "amount": -3})
    assert g.heroes["Leo"]["hp"] == CLASSES["clerigo"]["hp"] - 3
    # monsters wait for the DM: no automatic moves
    g.handle("Sol", {"type": "mz_spawn", "monster": "goblin"})
    assert g.phase == "combat"
    while g.turn in g.heroes:
        g.handle(g.turn, {"type": "mz_defend"})
    assert g.bot_move() is None
    g.handle("Sol", {"type": "mz_monster", "target": "Leo"})
    assert g.last_roll["label"] == "Ataque a Leo"


def test_the_cripta_key_silences_the_king():
    g = new_game(("Ana",), companions=1)
    g.handle("Ana", {"type": "mz_pick", "cls": "guerrero"})
    g.items.append("llave_hueso")
    g.room = "capilla"
    g.cleared.update({"capilla", "sala_ratas", "entrada"})
    g.handle("Ana", {"type": "mz_move", "room": "trono"})
    king = next(m for m in g.monsters if m["kind"] == "rey_esqueleto")
    assert king["special"] is None


@pytest.mark.parametrize("adventure", list(ADVENTURES))
def test_bots_play_whole_adventures(adventure):
    results = set()
    for seed in range(12):
        g = MazmorrasGame.from_options([], {"companions": 3, "adventure": adventure}, rng=random.Random(seed))
        g.start()
        for _ in range(3000):
            if not g.in_progress:
                break
            assert g.play_bot(), f"stuck in {g.phase}"
        assert g.phase == "finished"
        results.add(g.result)
    assert "victory" in results


async def test_room_plays_the_monsters_by_itself():
    room = Room("MAZMO", timings={"bot": 0.01})

    class Conn:
        async def send_json(self, data):
            self.last = data

    ana = Conn()
    await room.join("Ana", ana)
    await room.handle("Ana", {"type": "start_game", "game": "mazmorras", "companions": 1})
    await room.handle("Ana", {"type": "mz_pick", "cls": "guerrero"})
    await room.handle("Ana", {"type": "mz_move", "room": "sala_ratas"})
    for _ in range(200):
        g = room.game
        if g.phase != "combat":
            break
        if g.turn == "Ana":
            await room.handle("Ana", {"type": "mz_attack", "target": g.alive_monsters()[0]["id"]})
        await asyncio.sleep(0.02)
    assert room.game.phase == "explore" or room.game.result == "defeat"
    assert ana.last["game"]["name"] == "mazmorras"
    room.close()
