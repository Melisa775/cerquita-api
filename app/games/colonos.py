"""Colonos: an island-settling game for two (Catan-style).

The board is an island of 19 hexes laid out at random: forests (wood), hills
(brick), pastures (wool), fields (grain), mountains (ore) and one desert.
Each hex has a number; when the dice show it, the surrounding settlements and
cities produce.

  - Setup: two settlements with a road each, in snake order: A, B, B, A.
    The second settlement yields one card per terrain it touches.
  - On your turn you roll, produce, and then build, trade or play a
    development card.
  - On a 7 nobody produces: anyone with more than 7 cards discards half, and
    the roller moves the robber (blocking a hex) and steals a card.
  - Costs: road = wood + brick; settlement = wood + brick + wool + grain;
    city = 2 grain + 3 ore; development card = wool + grain + ore.
  - Trading: 4:1 with the bank, 3:1 or 2:1 with ports, and with the partner
    by proposing an exchange they accept or decline.
  - Points: settlement 1, city 2, longest road (5+) 2, largest army
    (3+ knights) 2, plus victory point cards. You win by reaching the goal
    on your own turn.

The server keeps each hand private; of the other player only the card count is known.
"""

import math
import random

RESOURCES = ("wood", "brick", "wool", "grain", "ore")
TERRAINS = {"forest": "wood", "hills": "brick", "pasture": "wool", "fields": "grain", "mountains": "ore", "desert": None}
TERRAIN_BAG = ["forest"] * 4 + ["pasture"] * 4 + ["fields"] * 4 + ["hills"] * 3 + ["mountains"] * 3 + ["desert"]
NUMBERS = [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]
PORT_KINDS = ["3:1"] * 4 + list(RESOURCES)
COSTS = {
    "road": {"wood": 1, "brick": 1},
    "settlement": {"wood": 1, "brick": 1, "wool": 1, "grain": 1},
    "city": {"grain": 2, "ore": 3},
    "dev": {"wool": 1, "grain": 1, "ore": 1},
}
PIECES = {"road": 15, "settlement": 5, "city": 4}
DEV_DECK = ["knight"] * 14 + ["victory_point"] * 5 + ["road_building"] * 2 + ["year_of_plenty"] * 2 + ["monopoly"] * 2
BANK_EACH = 19
GOALS = (8, 10)


# --- board geometry ----------------------------------------------------------
def build_geometry():
    """Pointy-top hexes of radius 2, with their vertices and edges."""
    hexes = [(q, r) for q in range(-2, 3) for r in range(-2, 3) if abs(q + r) <= 2]
    hexes.sort(key=lambda h: (h[1], h[0]))
    vkey: dict[tuple, int] = {}
    vertices: list[list[float]] = []
    hex_vertices = []
    for q, r in hexes:
        cx, cy = math.sqrt(3) * (q + r / 2), 1.5 * r
        ring = []
        for i in range(6):
            a = math.radians(60 * i - 30)
            x, y = cx + math.cos(a), cy + math.sin(a)
            k = (round(x, 3), round(y, 3))
            if k not in vkey:
                vkey[k] = len(vertices)
                vertices.append([round(x, 4), round(y, 4)])
            ring.append(vkey[k])
        hex_vertices.append(ring)
    ekey: dict[tuple, int] = {}
    edges: list[tuple[int, int]] = []
    edge_hexes: dict[int, list[int]] = {}
    for h, ring in enumerate(hex_vertices):
        for i in range(6):
            a, b = sorted((ring[i], ring[(i + 1) % 6]))
            if (a, b) not in ekey:
                ekey[(a, b)] = len(edges)
                edges.append((a, b))
            edge_hexes.setdefault(ekey[(a, b)], []).append(h)
    v_hexes = [[] for _ in vertices]
    for h, ring in enumerate(hex_vertices):
        for v in ring:
            v_hexes[v].append(h)
    v_edges = [[] for _ in vertices]
    v_neighbors = [[] for _ in vertices]
    for e, (a, b) in enumerate(edges):
        v_edges[a].append(e)
        v_edges[b].append(e)
        v_neighbors[a].append(b)
        v_neighbors[b].append(a)
    centers = [[round(math.sqrt(3) * (q + r / 2), 4), round(1.5 * r, 4)] for q, r in hexes]
    # coast edges, sorted around the island
    coast = [e for e, hs in edge_hexes.items() if len(hs) == 1]

    def angle(e):
        a, b = edges[e]
        mx = (vertices[a][0] + vertices[b][0]) / 2
        my = (vertices[a][1] + vertices[b][1]) / 2
        return math.atan2(my, mx)

    coast.sort(key=angle)
    return {
        "hexes": hexes, "centers": centers, "hex_vertices": hex_vertices, "vertices": vertices,
        "edges": edges, "v_hexes": v_hexes, "v_edges": v_edges, "v_neighbors": v_neighbors, "coast": coast,
    }


GEO = build_geometry()


def hex_neighbors(i: int) -> list[int]:
    q, r = GEO["hexes"][i]
    out = []
    for dq, dr in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)):
        if (q + dq, r + dr) in GEO["hexes"]:
            out.append(GEO["hexes"].index((q + dq, r + dr)))
    return out


def random_board(rng: random.Random) -> dict:
    """Random terrains and numbers, never leaving two 6/8 next to each other."""
    while True:
        terrains = TERRAIN_BAG[:]
        rng.shuffle(terrains)
        nums = NUMBERS[:]
        rng.shuffle(nums)
        numbers, it = [], iter(nums)
        for t in terrains:
            numbers.append(None if t == "desert" else next(it))
        hot = [i for i, n in enumerate(numbers) if n in (6, 8)]
        if all(j not in hex_neighbors(i) for i in hot for j in hot if i != j):
            break
    kinds = PORT_KINDS[:]
    rng.shuffle(kinds)
    coast = GEO["coast"]
    ports = []
    for i, kind in enumerate(kinds):
        e = coast[round(i * len(coast) / len(kinds)) % len(coast)]
        ports.append({"edge": e, "kind": kind})
    return {"terrains": terrains, "numbers": numbers, "ports": ports}


def empty_hand() -> dict:
    return {r: 0 for r in RESOURCES}


class ColonosGame:
    name = "colonos"
    max_players = 2
    actions = {
        "co_place", "co_roll", "co_build", "co_end", "co_discard", "co_robber",
        "co_bank", "co_offer", "co_accept", "co_reject", "co_cancel", "co_buy_dev", "co_play_dev",
    }

    def __init__(self, players: list[str], goal: int = 10, friendly: bool = False, rng: random.Random | None = None, timings: dict | None = None, board: dict | None = None):
        self.players = list(players)
        self.goal = goal
        self.friendly = friendly
        self.rng = rng or random.Random()
        b = board or random_board(self.rng)
        self.terrains = b["terrains"]
        self.numbers = b["numbers"]
        self.ports = b["ports"]
        self.robber = self.terrains.index("desert")
        self.buildings: dict[int, dict] = {}  # vertex -> {"owner", "kind"}
        self.roads: dict[int, str] = {}  # edge -> owner
        self.hands = {p: empty_hand() for p in self.players}
        self.bank = {r: BANK_EACH for r in RESOURCES}
        self.dev_deck = DEV_DECK[:]
        self.rng.shuffle(self.dev_deck)
        self.devs = {p: [] for p in self.players}  # [{"kind", "turn"}]
        self.knights = {p: 0 for p in self.players}
        self.longest: str | None = None
        self.longest_len = {p: 0 for p in self.players}
        self.army: str | None = None
        self.phase = "idle"
        self.turn: str | None = None
        self.turn_no = 0
        self.setup_order: list[str] = []
        self.setup_step = 0
        self.setup_need = "settlement"  # or "road"
        self.last_setup_vertex: int | None = None
        self.dice: list[int] | None = None
        self.roll_id = 0
        self.discard_need: dict[str, int] = {}
        self.after_robber = "main"
        self.dev_played = False
        self.free_roads = 0
        self.offer: dict | None = None
        self.log: list[dict] = []
        self.last_steal: dict | None = None
        self.winner: str | None = None

    @classmethod
    def from_options(cls, players, options, rng, timings=None):
        if len(players) < 2:
            raise ValueError("Colonos se juega entre los dos. Esperen a que entre tu pareja.")
        try:
            goal = int(options.get("goal", 10))
        except (TypeError, ValueError) as exc:
            raise ValueError("Meta no válida") from exc
        if goal not in GOALS:
            raise ValueError("La meta es 8 o 10 puntos")
        return cls(players, goal=goal, friendly=bool(options.get("friendly", False)), rng=rng)

    # --- room interface -------------------------------------------------
    @property
    def in_progress(self):
        return self.phase not in ("idle", "finished")

    @property
    def timer_key(self):
        return None

    @property
    def timer_seconds(self):
        return None

    def start(self):
        first = self.rng.choice(self.players)
        second = self.other(first)
        self.setup_order = [first, second, second, first]
        self.turn = first
        self.phase = "setup"

    def on_timeout(self):
        pass

    def remove_player(self, player):
        pass

    def handle(self, player, msg):
        kind = msg.get("type")
        if self.phase == "finished":
            raise ValueError("La partida ya terminó")
        if kind == "co_discard":
            self.discard(player, msg.get("cards"))
            return
        if kind in ("co_accept", "co_reject"):
            self.answer_offer(player, kind == "co_accept")
            return
        if player != self.turn:
            raise ValueError(f"Le toca a {self.turn}")
        if kind == "co_place":
            self.place_setup(player, msg.get("target"))
        elif kind == "co_roll":
            self.roll()
        elif kind == "co_build":
            self.build(player, msg.get("what"), msg.get("target"))
        elif kind == "co_end":
            self.end_turn(player)
        elif kind == "co_robber":
            self.move_robber(player, msg.get("hex"))
        elif kind == "co_bank":
            self.bank_trade(player, msg.get("give"), msg.get("get"))
        elif kind == "co_offer":
            self.make_offer(player, msg.get("give"), msg.get("get"))
        elif kind == "co_cancel":
            self.offer = None
        elif kind == "co_buy_dev":
            self.buy_dev(player)
        elif kind == "co_play_dev":
            self.play_dev(player, msg.get("card"), msg)
        self._check_win(player)

    # --- helpers --------------------------------------------------------
    def other(self, player):
        return next(p for p in self.players if p != player)

    def _log(self, **entry):
        self.log.append(entry)

    def _pay(self, player, cost):
        hand = self.hands[player]
        if any(hand[r] < n for r, n in cost.items()):
            raise ValueError("No te alcanzan las cartas")
        for r, n in cost.items():
            hand[r] -= n
            self.bank[r] += n

    def _give(self, player, res, n=1):
        n = min(n, self.bank[res])
        self.hands[player][res] += n
        self.bank[res] -= n
        return n

    def pieces_left(self, player, kind):
        if kind == "road":
            used = sum(1 for o in self.roads.values() if o == player)
        else:
            used = sum(1 for b in self.buildings.values() if b["owner"] == player and b["kind"] == kind)
        return PIECES[kind] - used

    # --- placement rules ------------------------------------------------
    def _distance_ok(self, v):
        return v not in self.buildings and all(n not in self.buildings for n in GEO["v_neighbors"][v])

    def _road_touches(self, player, e):
        """Does the edge connect to one of the player's roads or buildings? (never through rival buildings)"""
        for v in GEO["edges"][e]:
            b = self.buildings.get(v)
            if b and b["owner"] == player:
                return True
            if b and b["owner"] != player:
                continue  # a rival building cuts the connection at this vertex
            if any(self.roads.get(x) == player for x in GEO["v_edges"][v] if x != e):
                return True
        return False

    def legal_settlements(self, player, setup=False):
        out = []
        for v in range(len(GEO["vertices"])):
            if not self._distance_ok(v):
                continue
            if setup or any(self.roads.get(e) == player for e in GEO["v_edges"][v]):
                out.append(v)
        return out

    def legal_roads(self, player, setup_vertex=None):
        out = []
        for e in range(len(GEO["edges"])):
            if e in self.roads:
                continue
            if setup_vertex is not None:
                if setup_vertex in GEO["edges"][e]:
                    out.append(e)
            elif self._road_touches(player, e):
                out.append(e)
        return out

    def legal_cities(self, player):
        return [v for v, b in self.buildings.items() if b["owner"] == player and b["kind"] == "settlement"]

    # --- initial placement ----------------------------------------------
    def place_setup(self, player, target):
        if self.phase != "setup":
            raise ValueError("La colocación inicial ya terminó")
        if not isinstance(target, int):
            raise ValueError("Lugar no válido")
        if self.setup_need == "settlement":
            if target not in self.legal_settlements(player, setup=True):
                raise ValueError("Ahí no se puede poner un pueblo (tiene que estar a dos caminos de otro)")
            self.buildings[target] = {"owner": player, "kind": "settlement"}
            self.last_setup_vertex = target
            self.setup_need = "road"
            self._log(player=player, action="settlement")
            if self.setup_step >= 2:  # second settlement: produces right away
                got = []
                for h in GEO["v_hexes"][target]:
                    res = TERRAINS[self.terrains[h]]
                    if res and self._give(player, res):
                        got.append(res)
                self._log(player=player, action="initial", got=got)
            return
        if target not in self.legal_roads(player, setup_vertex=self.last_setup_vertex):
            raise ValueError("El camino tiene que salir del pueblo que acabas de poner")
        self.roads[target] = player
        self._log(player=player, action="road")
        self.setup_step += 1
        self.setup_need = "settlement"
        if self.setup_step == len(self.setup_order):
            self.turn = self.setup_order[0]
            self.turn_no = 1
            self.phase = "roll"
        else:
            self.turn = self.setup_order[self.setup_step]

    # --- dice and production --------------------------------------------
    def roll(self, forced=None):
        if self.phase != "roll":
            raise ValueError("Ya lanzaste los dados")
        self.dice = list(forced) if forced else [self.rng.randint(1, 6), self.rng.randint(1, 6)]
        self.roll_id += 1
        total = sum(self.dice)
        self._log(player=self.turn, action="roll", dice=self.dice[:])
        if total == 7:
            self.discard_need = {p: sum(self.hands[p].values()) // 2 for p in self.players if sum(self.hands[p].values()) > 7}
            self.after_robber = "main"
            self.phase = "discard" if self.discard_need else "robber"
            return
        self._produce(total)
        self.phase = "main"

    def _produce(self, total):
        demand = {r: {p: 0 for p in self.players} for r in RESOURCES}
        for h, n in enumerate(self.numbers):
            if n != total or h == self.robber:
                continue
            res = TERRAINS[self.terrains[h]]
            for v in GEO["hex_vertices"][h]:
                b = self.buildings.get(v)
                if b:
                    demand[res][b["owner"]] += 2 if b["kind"] == "city" else 1
        produced = {p: {} for p in self.players}
        for res, per in demand.items():
            total_need = sum(per.values())
            if not total_need:
                continue
            takers = [p for p, n in per.items() if n]
            if total_need <= self.bank[res]:
                for p in takers:
                    produced[p][res] = self._give(p, res, per[p])
            elif len(takers) == 1:  # the bank runs short: a single taker gets whatever is left
                produced[takers[0]][res] = self._give(takers[0], res, per[takers[0]])
        self._log(player=self.turn, action="produce", got={p: {r: n for r, n in g.items() if n} for p, g in produced.items()})

    def discard(self, player, cards):
        if self.phase != "discard" or player not in self.discard_need:
            raise ValueError("No tienes que botar cartas")
        if not isinstance(cards, dict):
            raise ValueError("Elige las cartas")
        cards = {r: int(cards.get(r, 0)) for r in RESOURCES}
        if any(n < 0 for n in cards.values()) or sum(cards.values()) != self.discard_need[player]:
            raise ValueError(f"Tienes que botar exactamente {self.discard_need[player]}")
        self._pay(player, {r: n for r, n in cards.items() if n})
        del self.discard_need[player]
        self._log(player=player, action="discard", count=sum(cards.values()))
        if not self.discard_need:
            self.phase = "robber"

    def legal_robber_hexes(self):
        out = []
        for h in range(len(GEO["hexes"])):
            if h == self.robber:
                continue
            if self.friendly:
                owners = {self.buildings[v]["owner"] for v in GEO["hex_vertices"][h] if v in self.buildings}
                if any(o != self.turn and self.public_points(o) <= 2 for o in owners):
                    continue
            out.append(h)
        return out or [h for h in range(len(GEO["hexes"])) if h != self.robber]

    def move_robber(self, player, hex_index):
        if self.phase != "robber":
            raise ValueError("Ahora no se mueve el ladrón")
        if hex_index not in self.legal_robber_hexes():
            raise ValueError("Ahí no se puede poner el ladrón")
        self.robber = hex_index
        rival = self.other(player)
        touches = any(self.buildings.get(v, {}).get("owner") == rival for v in GEO["hex_vertices"][hex_index])
        stolen = None
        if touches:
            pool = [r for r in RESOURCES for _ in range(self.hands[rival][r])]
            if pool:
                stolen = self.rng.choice(pool)
                self.hands[rival][stolen] -= 1
                self.hands[player][stolen] += 1
        self._log(player=player, action="robber", hex=hex_index, stole=bool(stolen))
        self.last_steal = {"thief": player, "victim": rival, "res": stolen}
        self.phase = self.after_robber

    # --- building -------------------------------------------------------
    def build(self, player, what, target):
        if self.phase == "road_building":
            if what != "road":
                raise ValueError("Primero pon los caminos gratis")
        elif self.phase != "main":
            raise ValueError("Primero lanza los dados")
        if what not in ("road", "settlement", "city") or not isinstance(target, int):
            raise ValueError("Construcción no válida")
        if self.pieces_left(player, what) <= 0:
            raise ValueError("Ya no te quedan piezas de ese tipo")
        if what == "road":
            if target not in self.legal_roads(player):
                raise ValueError("El camino tiene que conectar con lo tuyo")
            if self.phase == "road_building":
                self.free_roads -= 1
            else:
                self._pay(player, COSTS["road"])
            self.roads[target] = player
            self._update_longest()
            if self.phase == "road_building" and (self.free_roads <= 0 or not self.legal_roads(player) or self.pieces_left(player, "road") <= 0):
                self.free_roads = 0
                self.phase = "main" if self.dice else "roll"
        elif what == "settlement":
            if target not in self.legal_settlements(player):
                raise ValueError("El pueblo tiene que estar en tu camino y a dos caminos de cualquier otro")
            self._pay(player, COSTS["settlement"])
            self.buildings[target] = {"owner": player, "kind": "settlement"}
            self._update_longest()  # a settlement can cut the other player's road
        else:
            if target not in self.legal_cities(player):
                raise ValueError("Solo puedes mejorar tus pueblos a ciudad")
            self._pay(player, COSTS["city"])
            self.buildings[target]["kind"] = "city"
        self._log(player=player, action="build", what=what)

    def end_turn(self, player):
        if self.phase != "main":
            raise ValueError("Primero lanza los dados" if self.phase == "roll" else "Termina lo que estás haciendo")
        self.offer = None
        self.turn = self.other(player)
        self.turn_no += 1
        self.dice = None
        self.dev_played = False
        self.phase = "roll"

    # --- trading --------------------------------------------------------
    def rate(self, player, res):
        best = 4
        for port in self.ports:
            a, b = GEO["edges"][port["edge"]]
            if any(self.buildings.get(v, {}).get("owner") == player for v in (a, b)):
                if port["kind"] == "3:1":
                    best = min(best, 3)
                elif port["kind"] == res:
                    best = 2
        return best

    def bank_trade(self, player, give, get):
        if self.phase != "main":
            raise ValueError("Comercia después de lanzar los dados")
        if give not in RESOURCES or get not in RESOURCES or give == get:
            raise ValueError("Cambio no válido")
        if self.bank[get] < 1:
            raise ValueError("El banco no tiene de esa")
        self._pay(player, {give: self.rate(player, give)})
        self._give(player, get)
        self._log(player=player, action="bank", give=give, get=get, rate=self.rate(player, give))

    def _clean(self, cards):
        if not isinstance(cards, dict):
            raise ValueError("Cambio no válido")
        out = {}
        for r in RESOURCES:
            try:
                n = int(cards.get(r, 0))
            except (TypeError, ValueError) as exc:
                raise ValueError("Cambio no válido") from exc
            if n < 0:
                raise ValueError("Cambio no válido")
            if n:
                out[r] = n
        return out

    def make_offer(self, player, give, get):
        if self.phase != "main":
            raise ValueError("Comercia después de lanzar los dados")
        give, get = self._clean(give), self._clean(get)
        if not give or not get:
            raise ValueError("Pon qué das y qué pides")
        if any(self.hands[player][r] < n for r, n in give.items()):
            raise ValueError("No tienes lo que ofreces")
        self.offer = {"from": player, "give": give, "get": get}
        self._log(player=player, action="offer")

    def answer_offer(self, player, accept):
        if not self.offer or self.offer["from"] == player:
            raise ValueError("No hay ninguna oferta para ti")
        o = self.offer
        self.offer = None
        if not accept:
            self._log(player=player, action="reject")
            return
        a, b = o["from"], player
        if any(self.hands[a][r] < n for r, n in o["give"].items()):
            raise ValueError(f"{a} ya no tiene lo que ofreció")
        if any(self.hands[b][r] < n for r, n in o["get"].items()):
            raise ValueError("No tienes lo que te piden")
        for r, n in o["give"].items():
            self.hands[a][r] -= n
            self.hands[b][r] += n
        for r, n in o["get"].items():
            self.hands[b][r] -= n
            self.hands[a][r] += n
        self._log(player=player, action="accept")

    # --- development cards ----------------------------------------------
    def buy_dev(self, player):
        if self.phase != "main":
            raise ValueError("Compra después de lanzar los dados")
        if not self.dev_deck:
            raise ValueError("Ya no quedan cartas de desarrollo")
        self._pay(player, COSTS["dev"])
        card = self.dev_deck.pop()
        self.devs[player].append({"kind": card, "turn": self.turn_no})
        self._log(player=player, action="buy_dev")

    def play_dev(self, player, kind, msg):
        if self.phase not in ("roll", "main"):
            raise ValueError("Ahora no puedes jugar cartas")
        if self.dev_played:
            raise ValueError("Solo una carta de desarrollo por turno")
        if kind == "victory_point":
            raise ValueError("Las cartas de punto cuentan solas")
        if kind != "knight" and self.phase == "roll":
            raise ValueError("Antes de lanzar solo puedes jugar un soldado")
        card = next((c for c in self.devs[player] if c["kind"] == kind and c["turn"] < self.turn_no), None)
        if not card:
            raise ValueError("No tienes esa carta (o la compraste en este turno)")
        if kind == "year_of_plenty":
            picks = msg.get("resources")
            if not isinstance(picks, list) or len(picks) != 2 or any(r not in RESOURCES for r in picks):
                raise ValueError("Elige dos recursos")
            if any(self.bank[r] < picks.count(r) for r in picks):
                raise ValueError("El banco no tiene esos recursos")
        if kind == "monopoly" and msg.get("resource") not in RESOURCES:
            raise ValueError("Elige un recurso")
        self.devs[player].remove(card)
        self.dev_played = True
        self._log(player=player, action="dev", card=kind)
        if kind == "knight":
            self.knights[player] += 1
            self._update_army()
            self.after_robber = self.phase
            self.phase = "robber"
        elif kind == "road_building":
            self.free_roads = min(2, self.pieces_left(player, "road"))
            if self.free_roads and self.legal_roads(player):
                self.phase = "road_building"
        elif kind == "year_of_plenty":
            for r in msg["resources"]:
                self._give(player, r)
        elif kind == "monopoly":
            res = msg["resource"]
            rival = self.other(player)
            n = self.hands[rival][res]
            self.hands[rival][res] = 0
            self.hands[player][res] += n
            self._log(player=player, action="monopoly", resource=res, count=n)

    # --- awards and points ----------------------------------------------
    def _update_army(self):
        for p in self.players:
            if self.knights[p] >= 3 and (self.army is None or self.knights[p] > self.knights[self.army]):
                self.army = p

    def road_length(self, player) -> int:
        mine = [e for e, o in self.roads.items() if o == player]
        if not mine:
            return 0
        best = 0

        def blocked(v):
            b = self.buildings.get(v)
            return b is not None and b["owner"] != player

        def dfs(v, used, length):
            nonlocal best
            best = max(best, length)
            if length and blocked(v):
                return
            for e in GEO["v_edges"][v]:
                if e in used or self.roads.get(e) != player:
                    continue
                a, b = GEO["edges"][e]
                used.add(e)
                dfs(b if a == v else a, used, length + 1)
                used.discard(e)

        for e in mine:
            for v in GEO["edges"][e]:
                dfs(v, set(), 0)
        return best

    def _update_longest(self):
        for p in self.players:
            self.longest_len[p] = self.road_length(p)
        holder = self.longest
        if holder and self.longest_len[holder] < 5:
            holder = None  # lost the award because their road was cut
        for p in self.players:
            n = self.longest_len[p]
            if n >= 5 and (holder is None or n > self.longest_len[holder]):
                holder = p
        if holder is None:
            # if nobody holds it, it goes to the only player with 5+
            cands = [p for p in self.players if self.longest_len[p] >= 5]
            if len(cands) == 1:
                holder = cands[0]
        self.longest = holder

    def public_points(self, player) -> int:
        pts = sum(2 if b["kind"] == "city" else 1 for b in self.buildings.values() if b["owner"] == player)
        if self.longest == player:
            pts += 2
        if self.army == player:
            pts += 2
        return pts

    def points(self, player) -> int:
        return self.public_points(player) + sum(1 for c in self.devs[player] if c["kind"] == "victory_point")

    def _check_win(self, player):
        if self.phase != "finished" and player == self.turn and self.points(player) >= self.goal:
            self.winner = player
            self.phase = "finished"
            self._log(player=player, action="win")

    # --- state for clients ----------------------------------------------
    def snapshot(self, viewer=None):
        me_turn = viewer == self.turn and self.phase != "finished"
        finished = self.phase == "finished"
        legal = {}
        if me_turn:
            if self.phase == "setup":
                if self.setup_need == "settlement":
                    legal["settlement"] = self.legal_settlements(viewer, setup=True)
                else:
                    legal["road"] = self.legal_roads(viewer, setup_vertex=self.last_setup_vertex)
            elif self.phase in ("main", "road_building"):
                legal["road"] = self.legal_roads(viewer) if self.pieces_left(viewer, "road") > 0 else []
                if self.phase == "main":
                    legal["settlement"] = self.legal_settlements(viewer) if self.pieces_left(viewer, "settlement") > 0 else []
                    legal["city"] = self.legal_cities(viewer) if self.pieces_left(viewer, "city") > 0 else []
            elif self.phase == "robber":
                legal["robber"] = self.legal_robber_hexes()
        players = {}
        for p in self.players:
            players[p] = {
                "cards": sum(self.hands[p].values()),
                "devCount": len(self.devs[p]),
                "knights": self.knights[p],
                "road": self.longest_len[p],
                "points": self.points(p) if (p == viewer or finished) else self.public_points(p),
                "pieces": {k: self.pieces_left(p, k) for k in PIECES},
            }
        return {
            "name": self.name,
            "phase": self.phase,
            "players": self.players,
            "turn": self.turn,
            "turnNo": self.turn_no,
            "setupNeed": self.setup_need if self.phase == "setup" else None,
            "board": {
                "hexes": [{"center": GEO["centers"][i], "terrain": self.terrains[i], "number": self.numbers[i]} for i in range(len(GEO["hexes"]))],
                "vertices": GEO["vertices"],
                "edges": GEO["edges"],
                "ports": [{**p, "vertices": list(GEO["edges"][p["edge"]])} for p in self.ports],
                "robber": self.robber,
            },
            "buildings": {str(v): b for v, b in self.buildings.items()},
            "roads": {str(e): o for e, o in self.roads.items()},
            "hand": self.hands.get(viewer) if viewer in self.hands else None,
            "devs": [{"kind": c["kind"], "fresh": c["turn"] >= self.turn_no} for c in self.devs.get(viewer, [])],
            "rates": {r: self.rate(viewer, r) for r in RESOURCES} if viewer in self.hands else None,
            "playersInfo": players,
            "bank": self.bank,
            "devDeck": len(self.dev_deck),
            "dice": self.dice,
            "rollId": self.roll_id,
            "discardNeed": self.discard_need,
            "legal": legal,
            "freeRoads": self.free_roads,
            "devPlayed": self.dev_played,
            "offer": self.offer,
            "longest": self.longest,
            "army": self.army,
            "goal": self.goal,
            "log": self.log[-10:],
            # what the robber stole: only the thief and the victim know
            "stolen": self.last_steal if self.last_steal and viewer in (self.last_steal["thief"], self.last_steal["victim"]) else None,
            "winner": self.winner,
            "costs": COSTS,
            "options": {"goal": self.goal, "friendly": self.friendly},
        }
