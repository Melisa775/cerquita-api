"""Murdoku: sudoku con asesinato.

Hay un plano de N×N casillas dividido en habitaciones, con muebles. Hay que
ubicar a N personas (los sospechosos y la víctima) de modo que en cada fila y
en cada columna haya exactamente una. Mesas, plantas y estantes no se pueden
ocupar; sillas y alfombras sí. Cada persona trae una pista. Cuando todos
están en su lugar, el asesino es el único sospechoso que quedó en la misma
habitación que la víctima.

Cada caso se genera al momento: habitaciones, muebles, una solución al azar
en la que exactamente un sospechoso comparte habitación con la víctima, y
luego se agregan pistas verdaderas hasta que la solución es la única posible
(un buscador con vuelta atrás cuenta las soluciones). Después se quitan las
pistas que sobran.

Modos:
  - "team" (juntos): un solo plano que los dos van llenando.
  - "race" (carrera): el mismo caso, cada uno en su plano; gana quien lo
    resuelva primero.
"""

import random
import time

from app.games.common import parse_rounds
from app.games.guesswho import CHARACTERS

LEVELS = {
    "facil": {"label": "Fácil", "size": 5, "rooms": 4},
    "normal": {"label": "Normal", "size": 6, "rooms": 5},
}
ROOM_NAMES = ["Cocina", "Sala", "Comedor", "Biblioteca", "Jardín", "Estudio", "Dormitorio", "Baño", "Terraza", "Garaje"]
BLOCKING = ("mesa", "planta", "estante")  # no se pueden ocupar
SEATS = ("silla", "alfombra")  # sí se pueden ocupar
OBJECT_NAMES = {"mesa": "una mesa", "planta": "una planta", "estante": "un estante", "silla": "una silla", "alfombra": "una alfombra"}
BINARY = ("same_room", "diff_room", "above", "left")
ORDINALS = ["primera", "segunda", "tercera", "cuarta", "quinta", "sexta"]
VICTIM = {
    "id": "victima", "name": "Don Ernesto", "genero": "hombre", "pelo": "calvo", "color": "canoso", "ojos": "azules",
    "gafas": True, "sombrero": None, "barba": False, "bigote": True, "aretes": False, "pecas": False,
    "piel": 0, "fondo": "#DADCE0",
}


# --- pistas ------------------------------------------------------------------
# Una pista es una tupla; la primera posición dice de qué tipo es.
#   ("room", p, k)        p está en la habitación k
#   ("not_room", p, k)    p no está en la habitación k
#   ("row", p, r) / ("col", p, c)
#   ("beside", p, obj)    p está junto (arriba, abajo o a un lado, en la misma habitación) a ese objeto
#   ("on", p, obj)        p está sobre una silla o una alfombra
#   ("corner", p)
#   ("same_room", p, q) / ("diff_room", p, q)
#   ("above", p, q)       p está en una fila más arriba que q
#   ("left", p, q)        p está en una columna más a la izquierda que q


class Case:
    def __init__(self, size: int, rooms: list[list[int]], room_names: list[str], objects: dict, people: list[dict]):
        self.size = size
        self.rooms = rooms
        self.room_names = room_names
        self.objects = objects  # (r, c) -> tipo
        self.people = people  # la víctima es la última

    def free(self, cell) -> bool:
        return self.objects.get(cell) not in BLOCKING

    def beside(self, cell, obj) -> bool:
        r, c = cell
        for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if self.objects.get((rr, cc)) == obj and self.rooms[rr][cc] == self.rooms[r][c]:
                return True
        return False

    def unary_ok(self, clue, cell) -> bool:
        kind = clue[0]
        r, c = cell
        if kind == "room":
            return self.rooms[r][c] == clue[2]
        if kind == "not_room":
            return self.rooms[r][c] != clue[2]
        if kind == "row":
            return r == clue[2]
        if kind == "col":
            return c == clue[2]
        if kind == "beside":
            return self.beside(cell, clue[2])
        if kind == "on":
            return self.objects.get(cell) == clue[2]
        if kind == "corner":
            return r in (0, self.size - 1) and c in (0, self.size - 1)
        return True

    def binary_ok(self, clue, a, b) -> bool:
        kind = clue[0]
        if kind == "same_room":
            return self.rooms[a[0]][a[1]] == self.rooms[b[0]][b[1]]
        if kind == "diff_room":
            return self.rooms[a[0]][a[1]] != self.rooms[b[0]][b[1]]
        if kind == "above":
            return a[0] < b[0]
        if kind == "left":
            return a[1] < b[1]
        return True

    def count_solutions(self, clues: list[tuple], limit: int = 2) -> int:
        """Cuántas ubicaciones cumplen todo (se detiene al llegar a `limit`)."""
        n = len(self.people)
        binary = [cl for cl in clues if cl[0] in BINARY]
        unary = [[cl for cl in clues if cl[0] not in BINARY and cl[1] == p] for p in range(n)]
        options = []
        for p in range(n):
            cells = [(r, c) for r in range(self.size) for c in range(self.size)
                     if self.free((r, c)) and all(self.unary_ok(cl, (r, c)) for cl in unary[p])]
            options.append(cells)
        order = sorted(range(n), key=lambda p: len(options[p]))
        placed: dict[int, tuple] = {}
        rows, cols = set(), set()
        found = 0

        def ok(p, cell):
            for cl in binary:
                a, b = cl[1], cl[2]
                if a == p and b in placed and not self.binary_ok(cl, cell, placed[b]):
                    return False
                if b == p and a in placed and not self.binary_ok(cl, placed[a], cell):
                    return False
            return True

        def search(i):
            nonlocal found
            if found >= limit:
                return
            if i == n:
                found += 1
                return
            p = order[i]
            for cell in options[p]:
                if cell[0] in rows or cell[1] in cols or not ok(p, cell):
                    continue
                placed[p] = cell
                rows.add(cell[0])
                cols.add(cell[1])
                search(i + 1)
                del placed[p]
                rows.discard(cell[0])
                cols.discard(cell[1])

        search(0)
        return found


def _rooms(size: int, count: int, rng: random.Random) -> list[list[int]]:
    """Divide el plano en habitaciones creciendo desde semillas al azar."""
    while True:
        grid = [[-1] * size for _ in range(size)]
        seeds = rng.sample([(r, c) for r in range(size) for c in range(size)], count)
        frontier = []
        for k, (r, c) in enumerate(seeds):
            grid[r][c] = k
            frontier.append((r, c))
        while frontier:
            r, c = frontier.pop(rng.randrange(len(frontier)))
            free = [(rr, cc) for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1))
                    if 0 <= rr < size and 0 <= cc < size and grid[rr][cc] == -1]
            if free:
                rr, cc = rng.choice(free)
                grid[rr][cc] = grid[r][c]
                frontier += [(r, c), (rr, cc)]
        sizes = [sum(row.count(k) for row in grid) for k in range(count)]
        if min(sizes) >= 3:
            return grid


def _describe(case: Case, clue: tuple) -> str:
    kind = clue[0]
    name = lambda i: case.people[i]["name"]  # noqa: E731
    if kind == "room":
        return f"Estaba en {_article(case.room_names[clue[2]])}."
    if kind == "not_room":
        return f"No estaba en {_article(case.room_names[clue[2]])}."
    if kind == "row":
        return f"Estaba en la {ORDINALS[clue[2]]} fila (de arriba hacia abajo)."
    if kind == "col":
        return f"Estaba en la {ORDINALS[clue[2]]} columna (de izquierda a derecha)."
    if kind == "beside":
        return f"Estaba junto a {OBJECT_NAMES[clue[2]]}."
    if kind == "on":
        o = "a" if case.people[clue[1]].get("genero") == "mujer" else "o"
        return f"Estaba sentad{o} en una silla." if clue[2] == "silla" else f"Estaba parad{o} sobre una alfombra."
    if kind == "corner":
        return "Estaba en una esquina."
    if kind == "same_room":
        return f"Estaba en la misma habitación que {name(clue[2])}."
    if kind == "diff_room":
        return f"No estaba en la misma habitación que {name(clue[2])}."
    if kind == "above":
        return f"Estaba más arriba que {name(clue[2])}."
    if kind == "left":
        return f"Estaba más a la izquierda que {name(clue[2])}."
    return ""


def _article(room: str) -> str:
    masc = room in ("Comedor", "Estudio", "Dormitorio", "Baño", "Jardín", "Garaje")
    return ("el " if masc else "la ") + room.lower()


def generate(level: str, rng: random.Random):
    """Devuelve (caso, solución, pistas, índice del asesino)."""
    cfg = LEVELS[level]
    n = cfg["size"]
    while True:
        rooms = _rooms(n, cfg["rooms"], rng)
        names = rng.sample(ROOM_NAMES, cfg["rooms"])
        # Solución: una persona por fila y columna
        perm = list(range(n))
        rng.shuffle(perm)
        cells = [(r, perm[r]) for r in range(n)]
        rng.shuffle(cells)
        victim_cell = cells[-1]
        same = [c for c in cells[:-1] if rooms[c[0]][c[1]] == rooms[victim_cell[0]][victim_cell[1]]]
        if len(same) != 1:
            continue
        murderer = cells.index(same[0])
        # Muebles: los que estorban, fuera de la solución; sillas y alfombras, donde sea
        empty = [(r, c) for r in range(n) for c in range(n) if (r, c) not in cells]
        objects = {}
        for cell in rng.sample(empty, n - 1):
            objects[cell] = rng.choice(BLOCKING)
        others = [(r, c) for r in range(n) for c in range(n) if (r, c) not in objects]
        for cell in rng.sample(others, 3):
            objects[cell] = rng.choice(SEATS)
        suspects = rng.sample([c for c in CHARACTERS.values()], n - 1)
        people = [*suspects, VICTIM]
        case = Case(n, rooms, names, objects, people)
        solution = dict(enumerate(cells))

        clues = _clues_for(case, solution, murderer, rng)
        if clues is not None:
            return case, solution, clues, murderer


def _candidates(case: Case, sol: dict, murderer: int) -> dict[int, list[tuple]]:
    n = len(case.people)
    victim = n - 1
    out = {p: [] for p in range(n)}
    for p, (r, c) in sol.items():
        k = case.rooms[r][c]
        out[p].append(("room", p, k))
        for other in range(len(case.room_names)):
            if other != k:
                out[p].append(("not_room", p, other))
        if r in (0, n - 1):
            out[p].append(("row", p, r))
        if c in (0, n - 1):
            out[p].append(("col", p, c))
        for obj in (*BLOCKING, *SEATS):
            if case.beside((r, c), obj):
                out[p].append(("beside", p, obj))
        if case.objects.get((r, c)) in SEATS:
            out[p].append(("on", p, case.objects[(r, c)]))
        if r in (0, n - 1) and c in (0, n - 1):
            out[p].append(("corner", p))
        for q, (r2, c2) in sol.items():
            if q == p:
                continue
            same = case.rooms[r2][c2] == k
            # Decir quién estaba con la víctima arruinaría el misterio
            if same and victim not in (p, q):
                out[p].append(("same_room", p, q))
            if not same:
                out[p].append(("diff_room", p, q))
            if r < r2:
                out[p].append(("above", p, q))
            if c < c2:
                out[p].append(("left", p, q))
    return out


def _clues_for(case: Case, sol: dict, murderer: int, rng: random.Random) -> list[tuple] | None:
    cands = _candidates(case, sol, murderer)
    for lst in cands.values():
        rng.shuffle(lst)
    n = len(case.people)
    clues: list[tuple] = []
    # Una pista por persona para empezar, y luego las que hagan falta, por turnos
    turn = 0
    while case.count_solutions(clues) > 1:
        p = turn % n
        turn += 1
        if not cands[p]:
            if not any(cands.values()):
                return None
            continue
        clues.append(cands[p].pop())
        if turn > 200:
            return None
    # Quitar las que sobran, sin dejar a nadie sin pista
    for clue in list(reversed(clues)):
        owner = clue[1]
        if sum(1 for c in clues if c[1] == owner) <= 1:
            continue
        trial = [c for c in clues if c is not clue]
        if case.count_solutions(trial) == 1:
            clues = trial
    return clues


class MurdokuGame:
    name = "murdoku"
    actions = {"md_place", "md_note", "md_clear", "next_round"}

    def __init__(
        self,
        players: list[str],
        mode: str = "team",
        level: str = "facil",
        rounds: int = 1,
        rng: random.Random | None = None,
        timings: dict | None = None,
        clock=time.monotonic,
    ):
        self.players = list(players)
        self.mode = mode
        self.level = level
        self.total_rounds = rounds
        self.rng = rng or random.Random()
        self.clock = clock
        self.phase = "idle"
        self.round = 0
        self.case: Case | None = None
        self.solution: dict[int, tuple] = {}
        self.clues: list[tuple] = []
        self.murderer = -1
        self.boards: dict[str, dict] = {}  # tablero -> {"placed": {pid: (r,c,quien)}, "notes": set}
        self.started_at = 0.0
        self.result: dict | None = None
        self.scores: dict[str, int] = {p: 0 for p in self.players}
        self.history: list[dict] = []

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        mode = options.get("mode", "team")
        if mode not in ("team", "race"):
            raise ValueError("Modo no válido")
        level = options.get("level", "facil")
        if level not in LEVELS:
            raise ValueError("Nivel no válido")
        return cls(players, mode=mode, level=level, rounds=parse_rounds(options, 1), rng=rng, timings=timings)

    # --- interfaz con la sala -------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase not in ("idle", "finished")

    timer_key = None
    timer_seconds = None

    def start(self) -> None:
        self.start_round()

    def on_timeout(self) -> None:
        pass

    def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "md_place":
            self.place(player, msg.get("person"), msg.get("cell"))
        elif kind == "md_note":
            self.note(player, msg.get("cell"))
        elif kind == "md_clear":
            self.clear(player)
        elif kind == "next_round":
            self.next_round()

    def remove_player(self, player: str) -> None:
        if player in self.players:
            self.players.remove(player)

    # --- tableros -------------------------------------------------------
    def _board_key(self, player: str) -> str:
        return "team" if self.mode == "team" else player

    def _board(self, player: str) -> dict:
        return self.boards.setdefault(self._board_key(player), {"placed": {}, "notes": set()})

    def _cell(self, raw) -> tuple[int, int]:
        try:
            r, c = int(raw[0]), int(raw[1])
        except (TypeError, ValueError, IndexError) as exc:
            raise ValueError("Casilla inválida") from exc
        if not (0 <= r < self.case.size and 0 <= c < self.case.size):
            raise ValueError("Casilla inválida")
        return r, c

    def _require_playing(self, player: str) -> None:
        if self.phase != "playing":
            raise ValueError("El caso ya está resuelto")
        if player not in self.players:
            raise ValueError("Este caso empezó antes de que entraras")
        if self.mode == "race" and player in (self.result or {}).get("solvers", []):
            raise ValueError("Ya resolviste este caso")

    # --- transiciones ---------------------------------------------------
    def start_round(self) -> None:
        if self.phase not in ("idle", "round_over"):
            raise ValueError("No se puede iniciar ronda ahora")
        if self.round >= self.total_rounds:
            raise ValueError("El juego ya terminó")
        self.round += 1
        self.case, self.solution, self.clues, self.murderer = generate(self.level, self.rng)
        self.boards = {}
        self.result = None
        self.started_at = self.clock()
        self.phase = "playing"

    def place(self, player: str, person, cell) -> None:
        """Ubica (o quita, si cell es None) a una persona en el plano."""
        self._require_playing(player)
        try:
            pid = int(person)
        except (TypeError, ValueError) as exc:
            raise ValueError("Persona inválida") from exc
        if not 0 <= pid < len(self.case.people):
            raise ValueError("Persona inválida")
        board = self._board(player)
        if cell is None:
            board["placed"].pop(pid, None)
            return
        r, c = self._cell(cell)
        if not self.case.free((r, c)):
            raise ValueError(f"Ahí hay {OBJECT_NAMES[self.case.objects[(r, c)]]}: no se puede ocupar")
        # Quien estuviera en esa casilla sale
        for other, (rr, cc, _) in list(board["placed"].items()):
            if (rr, cc) == (r, c):
                del board["placed"][other]
        board["placed"][pid] = (r, c, player)
        board["notes"].discard((r, c))
        self._check(player)

    def note(self, player: str, cell) -> None:
        """Marca o desmarca una casilla con una X (descartada)."""
        self._require_playing(player)
        r, c = self._cell(cell)
        board = self._board(player)
        if any((rr, cc) == (r, c) for rr, cc, _ in board["placed"].values()):
            return
        board["notes"].symmetric_difference_update({(r, c)})

    def clear(self, player: str) -> None:
        self._require_playing(player)
        self.boards[self._board_key(player)] = {"placed": {}, "notes": set()}

    def _check(self, player: str) -> None:
        board = self._board(player)
        placed = {p: (r, c) for p, (r, c, _) in board["placed"].items()}
        if placed != self.solution:
            return
        seconds = round(self.clock() - self.started_at, 1)
        if self.mode == "race":
            self.scores[player] = self.scores.get(player, 0) + 1
        self.result = {"solvers": [player], "winner": player if self.mode == "race" else None, "seconds": seconds,
                       "murderer": self.murderer}
        self.history.append({"round": self.round, "murderer": self.case.people[self.murderer]["name"],
                             "seconds": seconds, "winner": self.result["winner"]})
        self.phase = "round_over"

    def violations(self, player: str) -> list[int]:
        """Si el plano está lleno pero no es la solución, qué pistas no se cumplen."""
        board = self._board(player)
        placed = {p: (r, c) for p, (r, c, _) in board["placed"].items()}
        if len(placed) < len(self.case.people):
            return []
        bad = []
        for i, clue in enumerate(self.clues):
            if clue[0] in BINARY:
                if not self.case.binary_ok(clue, placed[clue[1]], placed[clue[2]]):
                    bad.append(i)
            elif not self.case.unary_ok(clue, placed[clue[1]]):
                bad.append(i)
        return bad

    def next_round(self) -> None:
        if self.phase != "round_over":
            raise ValueError("Todavía no hay siguiente caso")
        if self.round >= self.total_rounds:
            self.phase = "finished"
        else:
            self.start_round()

    # --- estado para los clientes ---------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        over = self.phase in ("round_over", "finished")
        case = self.case
        board = self._board(viewer) if viewer and self.phase == "playing" and viewer in self.players else {"placed": {}, "notes": set()}
        if over:
            board = {"placed": {p: (r, c, None) for p, (r, c) in self.solution.items()}, "notes": set()}
        progress = {}
        if self.mode == "race":
            progress = {p: len(self.boards.get(p, {"placed": {}})["placed"]) for p in self.players}
        clues_by_person = {i: [] for i in range(len(case.people))} if case else {}
        for i, clue in enumerate(self.clues):
            clues_by_person[clue[1]].append({"index": i, "text": _describe(case, clue), "data": list(clue)})
        return {
            "name": self.name,
            "phase": self.phase,
            "mode": self.mode,
            "level": self.level,
            "levelLabel": LEVELS[self.level]["label"],
            "round": self.round,
            "totalRounds": self.total_rounds,
            "players": self.players,
            "size": case.size if case else 0,
            "rooms": case.rooms if case else [],
            "roomNames": case.room_names if case else [],
            "objects": [{"cell": [r, c], "kind": k} for (r, c), k in case.objects.items()] if case else [],
            "people": [
                {**p, "index": i, "role": "victim" if i == len(case.people) - 1 else "suspect", "clues": clues_by_person[i]}
                for i, p in enumerate(case.people)
            ] if case else [],
            "placed": {str(p): {"cell": [r, c], "by": by} for p, (r, c, by) in board["placed"].items()},
            "notes": [[r, c] for r, c in sorted(board["notes"])],
            "violations": self.violations(viewer) if viewer in self.players and self.phase == "playing" else [],
            "progress": progress,
            "elapsedMs": int(((self.result or {}).get("seconds") or (self.clock() - self.started_at)) * 1000) if case else 0,
            "result": self.result,
            "scores": self.scores,
            "history": self.history if self.phase == "finished" else [],
            "options": {"mode": self.mode, "level": self.level, "rounds": self.total_rounds},
        }
