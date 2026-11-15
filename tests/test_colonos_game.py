import random

import pytest

from app.games.colonos import BANK_EACH, GEO, RESOURCES, TERRAINS, ColonosGame, random_board


def make(goal=10, friendly=False, seed=3):
    g = ColonosGame(["Ana", "Leo"], goal=goal, friendly=friendly, rng=random.Random(seed))
    g.start()
    return g


def do_setup(g):
    """Coloca los cuatro pueblos iniciales en los primeros lugares legales."""
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
    # el vecino ya no es legal (regla de distancia)
    assert all(n not in g.legal_settlements(second, setup=True) for n in GEO["v_neighbors"][v])
    with pytest.raises(ValueError, match="pueblo que acabas"):
        g.place_setup(first, next(e for e in range(72) if v not in GEO["edges"][e]))
    do_setup(g)
    assert g.phase == "roll" and g.turn == first
    # el segundo pueblo dio un recurso por cada terreno productivo que toca
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
    me, rival = g.turn, g.other(g.turn)
    give(g, rival, madera=4, ladrillo=4)  # 8 o más cartas
    n = sum(g.hands[rival].values())
    g.roll(forced=(3, 4))
    assert g.phase == "discard" and g.discard_need[rival] == n // 2
    with pytest.raises(ValueError, match="exactamente"):
        g.discard(rival, {"madera": 1})
    g.discard(rival, {"madera": 4, "ladrillo": n // 2 - 4} if n // 2 >= 4 else {"madera": n // 2})
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
    give(g, p, madera=1, ladrillo=1)
    g.build(p, "road", e)
    assert g.roads[e] == p and g.hands[p]["madera"] == 0
    # una arista que no conecta no es legal
    far = next(x for x in range(72) if x not in g.roads and x not in g.legal_roads(p))
    give(g, p, madera=1, ladrillo=1)
    with pytest.raises(ValueError, match="conectar"):
        g.build(p, "road", far)
    city_spot = g.legal_cities(p)[0]
    give(g, p, trigo=2, piedra=3)
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
    give(g, p, madera=4)
    rate = g.rate(p, "madera")
    g.bank_trade(p, "madera", "piedra")
    assert g.hands[p]["madera"] == 4 - rate and g.hands[p]["piedra"] == 1
    # un pueblo en un puerto 2:1 de ladrillo baja la tasa
    port = next(pt for pt in g.ports if pt["kind"] == "ladrillo")
    v = GEO["edges"][port["edge"]][0]
    g.buildings[v] = {"owner": p, "kind": "settlement"}
    assert g.rate(p, "ladrillo") == 2


def test_offer_between_players():
    g = make()
    do_setup(g)
    a, b = g.turn, g.other(g.turn)
    g.phase = "main"
    give(g, a, lana=2)
    give(g, b, piedra=1)
    g.make_offer(a, {"lana": 2}, {"piedra": 1})
    assert g.snapshot(b)["offer"]["from"] == a
    with pytest.raises(ValueError):
        g.answer_offer(a, True)
    la, pb = g.hands[a]["lana"], g.hands[b]["piedra"]
    g.handle(b, {"type": "co_accept"})
    assert g.hands[a]["piedra"] >= 1 and g.hands[a]["lana"] == la - 2 and g.hands[b]["piedra"] == pb - 1
    g.make_offer(a, {"piedra": 1}, {"trigo": 5})
    g.handle(b, {"type": "co_reject"})
    assert g.offer is None
    conserved(g)


def test_dev_cards_rules():
    g = make()
    do_setup(g)
    p = g.turn
    g.phase = "main"
    give(g, p, lana=1, trigo=1, piedra=1)
    g.dev_deck.append("monopolio")
    g.buy_dev(p)
    assert g.devs[p][-1]["kind"] == "monopolio"
    with pytest.raises(ValueError, match="compraste"):
        g.play_dev(p, "monopolio", {"resource": "lana"})
    # al turno siguiente sí se puede
    g.end_turn(p)
    g.turn, g.turn_no, g.phase = p, g.turn_no + 1, "main"
    rival = g.other(p)
    give(g, rival, lana=3)
    n = g.hands[rival]["lana"]
    g.play_dev(p, "monopolio", {"resource": "lana"})
    assert g.hands[rival]["lana"] == 0 and g.hands[p]["lana"] >= n
    with pytest.raises(ValueError, match="una carta"):
        g.devs[p].append({"kind": "cosecha", "turn": 0})
        g.play_dev(p, "cosecha", {"resources": ["trigo", "trigo"]})
    conserved(g)


def test_knights_give_largest_army_and_robber():
    g = make()
    do_setup(g)
    p = g.turn
    for i in range(3):
        g.devs[p].append({"kind": "soldado", "turn": 0})
        g.dev_played = False
        g.phase = "roll"
        g.play_dev(p, "soldado", {})
        assert g.phase == "robber"
        g.move_robber(p, g.legal_robber_hexes()[0])
        assert g.phase == "roll"
    assert g.army == p and g.public_points(p) == 4


def test_longest_road_and_cut():
    g = make()
    do_setup(g)
    p = g.turn
    g.phase = "main"
    # extiende caminos gratis hasta tener 5 o más seguidos
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
                        playable = [c["kind"] for c in g.devs[p] if c["kind"] == "soldado" and c["turn"] < g.turn_no]
                        if playable and not g.dev_played and rng.random() < 0.5:
                            g.handle(p, {"type": "co_play_dev", "card": "soldado"})
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
