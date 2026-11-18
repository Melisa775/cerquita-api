"""Bots for Colonos: simple but sensible players.

`next_bot_move(game)` looks at the game and, if a bot has to act, returns
(bot, message): the same kind of message a person would send. The room
plays those one by one with a short pause, so people can follow along.

How the bots think, roughly:
  - Spots are worth the dice odds of their numbers ("pips": 6 and 8 are
    worth 5, 2 and 12 are worth 1), plus a little for variety and ports.
  - On their turn they roll, then build the best thing they can afford
    (city > settlement > road toward a good spot > development card),
    trading with the bank when a single card is missing.
  - The robber goes where it hurts the leader most, never on their own land.
  - They accept a person's offer only if it gives them something they need
    for less than they give, and never help someone about to win.
"""

from app.games.colonos import COSTS, GEO, RESOURCES, TERRAINS

PIPS = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
MAX_ACTIONS = 14  # per turn, so a bot never loops forever


def pips(game, h):
    n = game.numbers[h]
    return PIPS.get(n, 0) if n else 0


def vertex_value(game, v, player=None):
    """How good a spot is: production odds, variety, and what the player lacks."""
    total = 0.0
    kinds = set()
    for h in GEO["v_hexes"][v]:
        res = TERRAINS[game.terrains[h]]
        if not res:
            continue
        p = pips(game, h)
        if h == game.robber:
            p *= 0.4
        total += p
        kinds.add(res)
    total += len(kinds) * 0.8
    if player:
        # resources this player doesn't produce yet are worth more
        mine = produced_kinds(game, player)
        total += sum(1.2 for k in kinds if k not in mine)
    for port in game.ports:
        if v in GEO["edges"][port["edge"]]:
            total += 1.5 if port["kind"] == "3:1" else 1.0
    return total


def produced_kinds(game, player):
    out = set()
    for v, b in game.buildings.items():
        if b["owner"] == player:
            for h in GEO["v_hexes"][v]:
                res = TERRAINS[game.terrains[h]]
                if res:
                    out.add(res)
    return out


def can_pay(hand, cost):
    return all(hand[r] >= n for r, n in cost.items())


def missing(hand, cost):
    return {r: n - hand[r] for r, n in cost.items() if hand[r] < n}


# --- the decisions -----------------------------------------------------------


def setup_move(game, bot):
    if game.setup_need == "settlement":
        spots = game.legal_settlements(bot, setup=True)
        best = max(spots, key=lambda v: vertex_value(game, v, bot))
        return {"type": "co_place", "target": best}
    # the road points toward the best free spot two steps away
    v = game.last_setup_vertex
    roads = game.legal_roads(bot, setup_vertex=v)

    def score(e):
        a, b = GEO["edges"][e]
        far = b if a == v else a
        options = [n for n in GEO["v_neighbors"][far] if n != v and game._distance_ok(n)]
        return max((vertex_value(game, n) for n in options), default=0)

    return {"type": "co_place", "target": max(roads, key=score)}


def discard_move(game, bot):
    need = game.discard_need[bot]
    hand = dict(game.hands[bot])
    drop = {r: 0 for r in RESOURCES}
    for _ in range(need):
        # throw away from the biggest pile, keeping what a city or settlement needs
        r = max(RESOURCES, key=lambda x: hand[x] - (1 if x in ("grain", "ore") else 0))
        hand[r] -= 1
        drop[r] += 1
    return {"type": "co_discard", "cards": drop}


def robber_move(game, bot):
    leader_pts = {p: game.public_points(p) for p in game.players}

    def hurt(h):
        owners = [game.buildings[v] for v in GEO["hex_vertices"][h] if v in game.buildings]
        if any(b["owner"] == bot for b in owners):
            return -100
        score = 0.0
        for b in owners:
            score += pips(game, h) * (2 if b["kind"] == "city" else 1) * (1 + leader_pts[b["owner"]] / 4)
        return score

    return {"type": "co_robber", "hex": max(game.legal_robber_hexes(), key=hurt)}


def steal_move(game, bot):
    victim = max(game.steal_from, key=lambda p: (game.public_points(p), sum(game.hands[p].values())))
    return {"type": "co_steal", "victim": victim}


def offer_answer(game, bot):
    o = game.offer
    hand = game.hands[bot]
    if any(hand[r] < n for r, n in o["get"].items()):
        return {"type": "co_reject"}
    if game.points(o["from"]) >= game.goal - 2:
        return {"type": "co_reject"}  # don't help someone about to win
    target = goal_cost(game, bot)
    useful = sum(min(n, missing(hand, target).get(r, 0)) for r, n in o["give"].items())
    cost = sum(o["get"].values())
    gives_needed = any(r in target and hand[r] - n < target[r] for r, n in o["get"].items())
    if useful and useful >= cost and not gives_needed:
        return {"type": "co_accept"}
    return {"type": "co_reject"}


def goal_cost(game, bot):
    """What the bot is saving up for."""
    if game.legal_cities(bot) and game.pieces_left(bot, "city") > 0:
        return COSTS["city"]
    if game.legal_settlements(bot) and game.pieces_left(bot, "settlement") > 0:
        return COSTS["settlement"]
    return COSTS["road"] if game.pieces_left(bot, "road") > 0 else COSTS["dev"]


def best_road(game, bot):
    roads = game.legal_roads(bot)
    if not roads:
        return None

    def score(e):
        best = 0
        for v in GEO["edges"][e]:
            if game._distance_ok(v):
                best = max(best, vertex_value(game, v, bot) + 2)
            for n in GEO["v_neighbors"][v]:
                if game._distance_ok(n):
                    best = max(best, vertex_value(game, n, bot))
        return best + game.rng.random() * 0.1

    return max(roads, key=score)


def trade_for(game, bot, cost):
    """A bank trade that brings the bot one card closer to `cost`, if any."""
    hand = game.hands[bot]
    need = missing(hand, cost)
    if not need:
        return None
    get = next((r for r in need if game.bank[r] > 0), None)
    if not get:
        return None
    for give in sorted(RESOURCES, key=lambda r: -hand[r]):
        if give == get:
            continue
        keep = cost.get(give, 0)
        if hand[give] - game.rate(bot, give) >= keep:
            return {"type": "co_bank", "give": give, "get": get}
    return None


def main_move(game, bot):
    hand = game.hands[bot]
    if game._bot_actions >= MAX_ACTIONS:
        return {"type": "co_end"}
    # a development card first, when it clearly helps
    playable = {c["kind"] for c in game.devs[bot] if c["turn"] < game.turn_no}
    if not game.dev_played:
        if "monopoly" in playable:
            res = max(RESOURCES, key=lambda r: sum(game.hands[p][r] for p in game.players if p != bot))
            if sum(game.hands[p][res] for p in game.players if p != bot) >= 3:
                return {"type": "co_play_dev", "card": "monopoly", "resource": res}
        if "road_building" in playable and game.legal_roads(bot) and game.pieces_left(bot, "road") >= 2:
            return {"type": "co_play_dev", "card": "road_building"}
        if "year_of_plenty" in playable:
            need = missing(hand, goal_cost(game, bot))
            picks = [r for r, n in need.items() for _ in range(n)][:2]
            while len(picks) < 2:
                picks.append(min(RESOURCES, key=lambda r: hand[r]))
            if all(game.bank[r] >= picks.count(r) for r in picks):
                return {"type": "co_play_dev", "card": "year_of_plenty", "resources": picks}
        if "knight" in playable and any(game.buildings.get(v, {}).get("owner") == bot for v in GEO["hex_vertices"][game.robber]):
            return {"type": "co_play_dev", "card": "knight"}
    # build
    if game.pieces_left(bot, "city") > 0 and can_pay(hand, COSTS["city"]) and game.legal_cities(bot):
        v = max(game.legal_cities(bot), key=lambda x: vertex_value(game, x))
        return {"type": "co_build", "what": "city", "target": v}
    spots = game.legal_settlements(bot) if game.pieces_left(bot, "settlement") > 0 else []
    if spots and can_pay(hand, COSTS["settlement"]):
        return {"type": "co_build", "what": "settlement", "target": max(spots, key=lambda v: vertex_value(game, v, bot))}
    # roads only when there's nowhere to settle yet (or to chase the longest road)
    if not spots and game.pieces_left(bot, "road") > 0 and can_pay(hand, COSTS["road"]):
        e = best_road(game, bot)
        if e is not None:
            return {"type": "co_build", "what": "road", "target": e}
    # trade one step closer to the goal
    t = trade_for(game, bot, goal_cost(game, bot))
    if t:
        return t
    if game.dev_deck and can_pay(hand, COSTS["dev"]) and not can_pay(hand, COSTS["city"]):
        return {"type": "co_buy_dev"}
    return {"type": "co_end"}


def roll_move(game, bot):
    playable = {c["kind"] for c in game.devs[bot] if c["turn"] < game.turn_no}
    robbed = any(game.buildings.get(v, {}).get("owner") == bot for v in GEO["hex_vertices"][game.robber])
    if "knight" in playable and robbed and not game.dev_played:
        return {"type": "co_play_dev", "card": "knight"}
    return {"type": "co_roll"}


def next_bot_move(game):
    """(bot, message) for the next bot action, or None if it's not a bot's moment."""
    if not game.bots or game.phase in ("idle", "finished"):
        return None
    # discards and offers can involve bots even on someone else's turn
    if game.phase == "discard":
        bot = next((b for b in game.bots if b in game.discard_need), None)
        return (bot, discard_move(game, bot)) if bot else None
    if game.offer and game.offer["from"] not in game.bots:
        bot = next((b for b in game.bots if b not in game.offer["rejected"]), None)
        if bot:
            return bot, offer_answer(game, bot)
    bot = game.turn
    if bot not in game.bots:
        return None
    if game.offer:  # its own offer: never happens, but don't get stuck
        return bot, {"type": "co_cancel"}
    if game.phase == "setup":
        return bot, setup_move(game, bot)
    if game.phase == "roll":
        return bot, roll_move(game, bot)
    if game.phase == "robber":
        return bot, robber_move(game, bot)
    if game.phase == "steal":
        return bot, steal_move(game, bot)
    if game.phase == "road_building":
        e = best_road(game, bot)
        return bot, ({"type": "co_build", "what": "road", "target": e} if e is not None else {"type": "co_end"})
    if game.phase == "main":
        return bot, main_move(game, bot)
    return None
