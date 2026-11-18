import random

import pytest

from app.games.colonos import BANK_EACH, GEO, RESOURCES, TERRAINS, ColonosGame, random_board


def make(goal=10, friendly=False, seed=3):
    g = ColonosGame(["Ana", "Leo"], goal=goal, friendly=friendly, rng=random.Random(seed))
    g.start()
    return g


def do_setup(g):
    """Place the four initial settlements on the first legal spots."""
    while g.phase == "setup":
        p = g.turn
        if g.setup_need == "settlement":
            g.place_setup(p, g.legal_settlements(p, setup=True)[0])
        else:
            g.place_setup(p, g.legal_roads(p, setup_vertex=g.last_setup_vertex)[0])


def give(g, player, **cards):
    for r, n in cards.items():
        g.hands[player][r] += n
        g.bank[r] -= n


def conserved(g):
    for r in RESOURCES:
        assert g.bank[r] + sum(g.hands[p][r] for p in g.players) == BANK_EACH, r


def test_board_is_random_but_balanced():
    for seed in range(20):
        b = random_board(random.Random(seed))
        assert sorted(b["numbers"], key=lambda n: n or 0).count(None) == 1
        hot = [i for i, n in enumerate(b["numbers"]) if n in (6, 8)]
        from app.games.colonos import hex_neighbors
        assert all(j not in hex_neighbors(i) for i in hot for j in hot if i != j)
        assert len({p["edge"] for p in b["ports"]}) == 9


def test_snake_setup_and_initial_resources():
    g = make()
    first, second = g.setup_order[0], g.setup_order[1]
    assert g.setup_order == [first, second, second, first]
    with pytest.raises(ValueError, match="Le toca"):
        g.handle(second, {"type": "co_place", "target": 0})
    v = g.legal_settlements(first, setup=True)[0]
    g.place_setup(first, v)
    # the neighbor is no longer legal (distance rule)
    assert all(n not in g.legal_settlements(second, setup=True) for n in GEO["v_neighbors"][v])
    with pytest.raises(ValueError, match="pueblo que acabas"):
        g.place_setup(first, next(e for e in range(72) if v not in GEO["edges"][e]))
    do_setup(g)
    assert g.phase == "roll" and g.turn == first
    # the second settlement gave one resource per productive terrain it touches
    for p in g.players:
        second_v = [vv for vv, b in g.buildings.items() if b["owner"] == p][-1]
        expected = sum(1 for h in GEO["v_hexes"][second_v] if TERRAINS[g.terrains[h]])
        assert sum(g.hands[p].values()) == expected
    conserved(g)


def test_production_and_cities_double():
    g = make()
    do_setup(g)
    for p in g.players:
        for r in RESOURCES:
            g.bank[r] += g.hands[p][r]
            g.hands[p][r] = 0
    v, b = next(iter(g.buildings.items()))
    h = next(h for h in GEO["v_hexes"][v] if g.numbers[h] and h != g.robber)
    res = TERRAINS[g.terrains[h]]
    before = g.hands[b["owner"]][res]
    b["kind"] = "city"
    g.turn = g.turn
    g.roll(forced=(g.numbers[h] // 2, g.numbers[h] - g.numbers[h] // 2))
    assert g.hands[b["owner"]][res] >= before + 2
    conserved(g)


def test_seven_discard_and_robber_steal():
    g = make()
    do_setup(g)
    me, rival = g.turn, g.next_player(g.turn)
    give(g, rival, wood=4, brick=4)  # 8 or more cards
    n = sum(g.hands[rival].values())
    g.roll(forced=(3, 4))
    assert g.phase == "discard" and g.discard_need[rival] == n // 2
    with pytest.raises(ValueError, match="exactamente"):
        g.discard(rival, {"wood": 1})
    g.discard(rival, {"wood": 4, "brick": n // 2 - 4} if n // 2 >= 4 else {"wood": n // 2})
    assert g.phase == "robber"
    target = next(h for h in g.legal_robber_hexes() if any(g.buildings.get(v, {}).get("owner") == rival for v in GEO["hex_vertices"][h]))
    cards_before = sum(g.hands[rival].values())
    g.move_robber(me, target)
    assert g.robber == target and g.phase == "main"
    assert sum(g.hands[rival].values()) == cards_before - 1
    assert g.snapshot(me)["stolen"]["res"] and g.snapshot(rival)["stolen"] and g.snapshot(None)["stolen"] is None
    conserved(g)


def test_building_rules_and_costs():
    g = make()
    do_setup(g)
    p = g.turn
    g.roll(forced=(1, 1)) if g.phase == "roll" else None
    if g.phase != "main":
        g.phase = "main"
    for r in RESOURCES:
        g.bank[r] += g.hands[p][r]
        g.hands[p][r] = 0
    e = g.legal_roads(p)[0]
    with pytest.raises(ValueError, match="alcanzan"):
        g.build(p, "road", e)
    give(g, p, wood=1, brick=1)
    g.build(p, "road", e)
    assert g.roads[e] == p and g.hands[p]["wood"] == 0
    # an edge that doesn't connect is not legal
    far = next(x for x in range(72) if x not in g.roads and x not in g.legal_roads(p))
    give(g, p, wood=1, brick=1)
    with pytest.raises(ValueError, match="conectar"):
        g.build(p, "road", far)
    city_spot = g.legal_cities(p)[0]
    give(g, p, grain=2, ore=3)
    g.build(p, "city", city_spot)
    assert g.buildings[city_spot]["kind"] == "city"
    conserved(g)


def test_bank_and_port_rates():
    g = make()
    do_setup(g)
    p = g.turn
    g.phase = "main"
    for r in RESOURCES:
        g.bank[r] += g.hands[p][r]
        g.hands[p][r] = 0
    give(g, p, wood=4)
    rate = g.rate(p, "wood")
    g.bank_trade(p, "wood", "ore")
    assert g.hands[p]["wood"] == 4 - rate and g.hands[p]["ore"] == 1
    # a settlement on a 2:1 brick port lowers the rate
    port = next(pt for pt in g.ports if pt["kind"] == "brick")
    v = GEO["edges"][port["edge"]][0]
    g.buildings[v] = {"owner": p, "kind": "settlement"}
    assert g.rate(p, "brick") == 2


def test_offer_between_players():
    g = make()
    do_setup(g)
    a, b = g.turn, g.next_player(g.turn)
    g.phase = "main"
    give(g, a, wool=2)
    give(g, b, ore=1)
    g.make_offer(a, {"wool": 2}, {"ore": 1})
    assert g.snapshot(b)["offer"]["from"] == a
    with pytest.raises(ValueError):
        g.answer_offer(a, True)
    la, pb = g.hands[a]["wool"], g.hands[b]["ore"]
    g.handle(b, {"type": "co_accept"})
    assert g.hands[a]["ore"] >= 1 and g.hands[a]["wool"] == la - 2 and g.hands[b]["ore"] == pb - 1
    g.make_offer(a, {"ore": 1}, {"grain": 5})
    g.handle(b, {"type": "co_reject"})
    assert g.offer is None
    conserved(g)


def test_dev_cards_rules():
    g = make()
    do_setup(g)
    p = g.turn
    g.phase = "main"
    give(g, p, wool=1, grain=1, ore=1)
    g.dev_deck.append("monopoly")
    g.buy_dev(p)
    assert g.devs[p][-1]["kind"] == "monopoly"
    with pytest.raises(ValueError, match="compraste"):
        g.play_dev(p, "monopoly", {"resource": "wool"})
    # on the next turn it's allowed
    g.end_turn(p)
    g.turn, g.turn_no, g.phase = p, g.turn_no + 1, "main"
    rival = g.next_player(p)
    give(g, rival, wool=3)
    n = g.hands[rival]["wool"]
    g.play_dev(p, "monopoly", {"resource": "wool"})
    assert g.hands[rival]["wool"] == 0 and g.hands[p]["wool"] >= n
    with pytest.raises(ValueError, match="una carta"):
        g.devs[p].append({"kind": "year_of_plenty", "turn": 0})
        g.play_dev(p, "year_of_plenty", {"resources": ["grain", "grain"]})
    conserved(g)


def test_knights_give_largest_army_and_robber():
    g = make()
    do_setup(g)
    p = g.turn
    for i in range(3):
        g.devs[p].append({"kind": "knight", "turn": 0})
        g.dev_played = False
        g.phase = "roll"
        g.play_dev(p, "knight", {})
        assert g.phase == "robber"
        g.move_robber(p, g.legal_robber_hexes()[0])
        assert g.phase == "roll"
    assert g.army == p and g.public_points(p) == 4


def test_longest_road_and_cut():
    g = make()
    do_setup(g)
    p = g.turn
    g.phase = "main"
    # builds free roads until there are 5 or more in a row
    for _ in range(12):
        if g.road_length(p) >= 5:
            break
        cands = g.legal_roads(p)
        best = max(cands, key=lambda e: (g.roads.__setitem__(e, p), g.road_length(p), g.roads.pop(e))[1])
        g.roads[best] = p
        g._update_longest()
    assert g.road_length(p) >= 5 and g.longest == p


def test_random_full_games_finish_and_conserve_cards():
    finished = 0
    for seed in range(6):
        g = ColonosGame(["Ana", "Leo"], goal=8, rng=random.Random(seed))
        g.start()
        rng = random.Random(seed)
        for _ in range(6000):
            if g.phase == "finished":
                finished += 1
                break
            if g.phase == "discard":
                for p, n in list(g.discard_need.items()):
                    pool = [r for r in RESOURCES for _ in range(g.hands[p][r])]
                    rng.shuffle(pool)
                    pick = {}
                    for r in pool[:n]:
                        pick[r] = pick.get(r, 0) + 1
                    g.handle(p, {"type": "co_discard", "cards": pick})
                continue
            p = g.turn
            snap = g.snapshot(p)
            legal = snap["legal"]
            if g.phase == "setup":
                kind = "settlement" if g.setup_need == "settlement" else "road"
                g.handle(p, {"type": "co_place", "target": rng.choice(legal[kind])})
            elif g.phase == "roll":
                g.handle(p, {"type": "co_roll"})
            elif g.phase == "robber":
                g.handle(p, {"type": "co_robber", "hex": rng.choice(legal["robber"])})
            elif g.phase == "road_building":
                g.handle(p, {"type": "co_build", "what": "road", "target": rng.choice(legal["road"])})
            else:
                hand = g.hands[p]
                done = False
                for what in ("city", "settlement", "road"):
                    cost = snap["costs"][what]
                    if legal.get(what) and all(hand[r] >= n for r, n in cost.items()) and (what != "road" or rng.random() < 0.6):
                        g.handle(p, {"type": "co_build", "what": what, "target": rng.choice(legal[what])})
                        done = True
                        break
                if not done and all(hand[r] >= n for r, n in snap["costs"]["dev"].items()) and g.dev_deck and rng.random() < 0.5:
                    g.handle(p, {"type": "co_buy_dev"})
                    done = True
                if not done:
                    rich = max(RESOURCES, key=lambda r: hand[r])
                    poor = min(RESOURCES, key=lambda r: hand[r])
                    if hand[rich] >= g.rate(p, rich) and rich != poor and g.bank[poor] and rng.random() < 0.7:
                        g.handle(p, {"type": "co_bank", "give": rich, "get": poor})
                    else:
                        playable = [c["kind"] for c in g.devs[p] if c["kind"] == "knight" and c["turn"] < g.turn_no]
                        if playable and not g.dev_played and rng.random() < 0.5:
                            g.handle(p, {"type": "co_play_dev", "card": "knight"})
                        else:
                            g.handle(p, {"type": "co_end"})
            conserved(g)
            assert all(len([1 for b in g.buildings.values() if b["owner"] == pl]) <= 9 for pl in g.players)
    assert finished >= 5


def test_options():
    rng = random.Random()
    assert ColonosGame.from_options(["Ana", "Leo"], {"goal": 8, "friendly": True}, rng).friendly
    with pytest.raises(ValueError):
        ColonosGame.from_options(["Ana", "Leo"], {"goal": 12}, rng)
    with pytest.raises(ValueError):
        ColonosGame.from_options(["Ana"], {}, rng)


# --- more players and bots ------------------------------------------------------


def test_setup_snakes_through_four_players():
    g = ColonosGame(["Ana", "Leo", "Sol", "Mar"], rng=random.Random(5))
    g.start()
    assert g.setup_order == g.order + g.order[::-1] and len(g.setup_order) == 8
    assert g.turn == g.order[0]


def test_bots_fill_the_table_and_play_a_whole_game_alone():
    g = ColonosGame.from_options([], {"goal": 8, "bots": 3}, rng=random.Random(11))
    assert g.bots == g.players and len(g.players) == 3
    g.start()
    steps = 0
    while g.phase != "finished" and steps < 20000:
        assert g.play_bot(), f"a bot got stuck in phase {g.phase}"
        steps += 1
    assert g.phase == "finished" and g.winner in g.bots


def test_bot_waits_for_people_and_answers_offers():
    g = ColonosGame.from_options(["Ana"], {"goal": 10, "bots": 1}, rng=random.Random(3))
    g.start()
    # play the setup: Ana by hand (best legal spot), the bot by itself
    while g.phase == "setup":
        if g.turn == "Ana":
            if g.setup_need == "settlement":
                g.handle("Ana", {"type": "co_place", "target": g.legal_settlements("Ana", setup=True)[0]})
            else:
                g.handle("Ana", {"type": "co_place", "target": g.legal_roads("Ana", setup_vertex=g.last_setup_vertex)[0]})
        else:
            assert g.play_bot()
    if g.turn != "Ana":
        while g.turn != "Ana":
            assert g.play_bot()
    assert g.bot_move() is None  # Ana's turn: the bot waits
    g.handle("Ana", {"type": "co_roll"})
    if g.phase == "main":
        bot = g.bots[0]
        g.hands["Ana"] = {r: 3 for r in RESOURCES}
        g.hands[bot] = {r: 2 for r in RESOURCES}
        g.handle("Ana", {"type": "co_offer", "give": {"wood": 1}, "get": {"ore": 3}})
        assert g.bot_move()[0] == bot
        g.play_bot()
        assert g.offer is None  # a bad deal: declined, and with one rival the offer closes


def test_robber_on_several_rivals_lets_you_choose():
    g = ColonosGame(["Ana", "Leo", "Sol"], rng=random.Random(2))
    g.start()
    h = next(i for i, t in enumerate(g.terrains) if t != "desert")
    ring = GEO["hex_vertices"][h]
    g.buildings = {ring[0]: {"owner": "Leo", "kind": "settlement"}, ring[3]: {"owner": "Sol", "kind": "settlement"}}
    g.hands["Leo"]["wood"] = 2
    g.hands["Sol"]["ore"] = 1
    g.turn, g.phase, g.after_robber = "Ana", "robber", "main"
    g.move_robber("Ana", h)
    assert g.phase == "steal" and set(g.steal_from) == {"Leo", "Sol"}
    g.handle("Ana", {"type": "co_steal", "victim": "Sol"})
    assert g.hands["Ana"]["ore"] == 1 and g.phase == "main"


def test_offer_is_open_to_everyone_and_monopoly_takes_from_all():
    g = ColonosGame(["Ana", "Leo", "Sol"], rng=random.Random(2))
    g.start()
    g.phase, g.turn = "main", "Ana"
    for p in g.players:
        g.hands[p] = {r: 2 for r in RESOURCES}
    g.make_offer("Ana", {"wood": 1}, {"ore": 1})
    g.answer_offer("Leo", False)
    assert g.offer is not None  # Sol can still take it
    g.answer_offer("Sol", True)
    assert g.hands["Sol"]["wood"] == 3 and g.offer is None
    g.devs["Ana"] = [{"kind": "monopoly", "turn": 0}]
    g.turn_no = 1
    g.play_dev("Ana", "monopoly", {"resource": "grain"})
    assert g.hands["Ana"]["grain"] == 6 and g.hands["Leo"]["grain"] == 0 and g.hands["Sol"]["grain"] == 0
