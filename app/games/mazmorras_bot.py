"""The automatic Dungeon Master and the bot companions of Mazmorras.

`next_move(game)` returns (actor, message) for the next automatic action:
  - "auto" plays the monsters when the system is the Dungeon Master;
  - a companion bot plays its hero's turn in a fight, rolls the checks it is
    asked for, and, when every hero is a bot, explores the dungeon too.
The room plays these one by one with a short pause, so people can follow.
"""

from collections import deque


def hp_ratio(h):
    return h["hp"] / h["max_hp"]


def fight_move(game, name):
    h = game.heroes[name]
    cls = h["cls"]
    monsters = game.alive_monsters()
    heroes = list(game.heroes.values())
    # the weakest enemy first (to finish it off), bosses when there's no easy kill
    target = min(monsters, key=lambda m: (m["hp"] > 12, m["hp"]))
    if cls == "clerigo" and h["slots"] > 0:
        down = [x for x in heroes if x["hp"] <= 0]
        hurt = [x for x in heroes if 0 < x["hp"] and hp_ratio(x) < 0.35]
        if down or hurt:
            who = (down or sorted(hurt, key=hp_ratio))[0]
            return {"type": "mz_power", "power": "curar_heridas", "target": who["name"]}
    if hp_ratio(h) < 0.3:
        if cls == "guerrero" and h["aliento"]:
            return {"type": "mz_power", "power": "segundo_aliento"}
        healer = any(x["cls"] == "clerigo" and x["hp"] > 0 and x["slots"] > 0 and x is not h for x in heroes)
        if game.potions > 0 and not healer:
            return {"type": "mz_potion", "target": name}
    if cls == "mago" and h["slots"] > 0:
        if len(monsters) >= 3:
            return {"type": "mz_power", "power": "ola_de_trueno"}
        boss = next((m for m in monsters if m["boss"]), None)
        if boss:
            return {"type": "mz_power", "power": "proyectil_magico", "target": boss["id"]}
    if cls == "clerigo" and target["ac"] >= 15:
        return {"type": "mz_power", "power": "llama_sagrada", "target": target["id"]}
    return {"type": "mz_attack", "target": target["id"]}


def explore_move(game):
    """Only used when every hero is a bot: try things, rest, walk on."""
    bots = [game.heroes[b] for b in game.companions if game.heroes[b]["hp"] > 0]
    room = game.adventure["rooms"][game.room]
    feat = room.get("feature")
    if feat and game.room not in game.features_done:
        best = max(bots, key=lambda x: game.hero_mod(x, feat["ability"]))
        return best["name"], {"type": "mz_feature"}
    heroes = list(game.heroes.values())
    avg = sum(hp_ratio(x) for x in heroes) / len(heroes)
    step = next_step(game)
    final_next = step and game.adventure["rooms"][step].get("final")
    if game.rests > 0 and (avg < 0.55 or (final_next and avg < 0.9)):
        return bots[0]["name"], {"type": "mz_rest"}
    low = [x for x in heroes if hp_ratio(x) < 0.4]
    if low and game.potions > 1:
        return bots[0]["name"], {"type": "mz_potion", "target": low[0]["name"]}
    return (bots[0]["name"], {"type": "mz_move", "room": step}) if step else None


def next_step(game):
    """First step toward the nearest room still to do (the final room last)."""
    rooms = game.adventure["rooms"]

    def todo(rid):
        r = rooms[rid]
        return rid not in game.cleared or (r.get("feature") and rid not in game.features_done)

    goals = [rid for rid in rooms if todo(rid) and rid != game.room]
    others = [rid for rid in goals if not rooms[rid].get("final")]
    goals = set(others or goals)
    prev = {game.room: None}
    queue = deque([game.room])
    while queue:
        cur = queue.popleft()
        if cur in goals:
            while prev[cur] != game.room:
                cur = prev[cur]
            return cur
        for nxt in rooms[cur]["exits"]:
            # never walk through the final room on the way to somewhere else
            if nxt not in prev and (nxt in goals or not rooms[nxt].get("final") or nxt in game.cleared):
                prev[nxt] = cur
                queue.append(nxt)
    return None


def next_move(game):
    if game.phase not in ("explore", "combat"):
        return None
    c = game.pending_check
    if c and game.is_bot(c["hero"]):
        return c["hero"], {"type": "mz_roll"}
    if game.phase == "combat":
        t = game.turn
        if t in game.heroes:
            return (t, fight_move(game, t)) if game.is_bot(t) else None
        return ("auto", {"type": "mz_monster"}) if game.dm == "auto" else None
    if game.companions and len(game.companions) == len(game.heroes):
        return explore_move(game)
    return None
