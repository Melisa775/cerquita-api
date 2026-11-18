"""Battleship ("Batalla naval").

Each player places their fleet in secret on a grid, then they take turns
shooting at the other one: miss, hit or sunk. First to sink every ship of
the partner wins.

Phases:
  placing -> each player places their ships and marks "ready"
  battle  -> turn-based shooting
When it ends the phase is "finished" and both fleets are revealed.

Options:
  size      -> 8 or 10 cells per side (the fleet depends on the size)
  noTouch   -> ships may not touch, not even diagonally (the classic
               Spanish "hundir la flota" rule). With it, sinking a ship
               marks the surrounding cells as water.
  bonus     -> a hit lets you shoot again

The server keeps every ship's position and sends each player only their own
data: of the other board they only know the shots they have already fired.
"""

import random

FLEETS = {
    10: [("carrier", "Portaaviones", 5), ("battleship", "Acorazado", 4), ("cruiser", "Crucero", 3),
         ("submarine", "Submarino", 3), ("destroyer", "Destructor", 2)],
    8: [("battleship", "Acorazado", 4), ("cruiser", "Crucero", 3), ("submarine", "Submarino", 3),
        ("destroyer", "Destructor", 2), ("patrol_boat", "Lancha", 2)],
}
DIRS = {"h": (0, 1), "v": (1, 0)}


def ship_cells(row: int, col: int, length: int, direction: str) -> list[tuple[int, int]]:
    dr, dc = DIRS[direction]
    return [(row + dr * i, col + dc * i) for i in range(length)]


def neighbors(cells, size: int) -> set[tuple[int, int]]:
    """Cells around a ship (including diagonals), excluding the ship itself."""
    around = set()
    for r, c in cells:
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                rr, cc = r + dr, c + dc
                if 0 <= rr < size and 0 <= cc < size:
                    around.add((rr, cc))
    return around - set(cells)


def validate_fleet(ships: list[dict], size: int, no_touch: bool) -> list[dict]:
    """Validate a fleet sent by a client and return it normalized."""
    fleet = {sid: length for sid, _, length in FLEETS[size]}
    if not isinstance(ships, list) or len(ships) != len(fleet):
        raise ValueError("Ubica todos los barcos")
    taken: dict[tuple[int, int], str] = {}
    result = []
    for ship in ships:
        if not isinstance(ship, dict):
            raise ValueError("Barco no válido")
        sid = ship.get("id")
        if sid not in fleet or any(s["id"] == sid for s in result):
            raise ValueError("Barco no válido")
        direction = ship.get("dir")
        row, col = ship.get("row"), ship.get("col")
        if direction not in DIRS or not all(isinstance(v, int) and not isinstance(v, bool) for v in (row, col)):
            raise ValueError("Barco no válido")
        cells = ship_cells(row, col, fleet[sid], direction)
        if any(not (0 <= r < size and 0 <= c < size) for r, c in cells):
            raise ValueError("Hay un barco por fuera del tablero")
        for cell in cells:
            if cell in taken:
                raise ValueError("Hay barcos encima de otros")
        result.append({"id": sid, "row": row, "col": col, "dir": direction, "length": fleet[sid], "cells": cells})
        for cell in cells:
            taken[cell] = sid
    if no_touch:
        for ship in result:
            for cell in neighbors(ship["cells"], size):
                if cell in taken and taken[cell] != ship["id"]:
                    raise ValueError("Con esta regla los barcos no se pueden tocar")
    return result


def random_fleet(size: int, no_touch: bool, rng: random.Random) -> list[dict]:
    """A random valid fleet (used by tests)."""
    while True:
        placed, blocked = [], set()
        ok = True
        for sid, _, length in FLEETS[size]:
            options = []
            for d in DIRS:
                for r in range(size):
                    for c in range(size):
                        cells = ship_cells(r, c, length, d)
                        if all(0 <= rr < size and 0 <= cc < size and (rr, cc) not in blocked for rr, cc in cells):
                            options.append((r, c, d, cells))
            if not options:
                ok = False
                break
            r, c, d, cells = rng.choice(options)
            placed.append({"id": sid, "row": r, "col": c, "dir": d})
            blocked |= set(cells)
            if no_touch:
                blocked |= neighbors(cells, size)
        if ok:
            return placed


class BattleshipGame:
    name = "battleship"
    max_players = 2
    actions = {"bn_place", "bn_unready", "bn_fire"}

    def __init__(
        self,
        players: list[str],
        size: int = 10,
        no_touch: bool = True,
        bonus: bool = True,
        rng: random.Random | None = None,
        timings: dict | None = None,
    ):
        self.players = list(players)
        self.size = size
        self.no_touch = no_touch
        self.bonus = bonus
        self.rng = rng or random.Random()
        self.phase = "idle"
        self.fleets: dict[str, list[dict]] = {}  # player -> ships with their cells
        self.ready: dict[str, bool] = {p: False for p in self.players}
        # shots each player RECEIVED: (row, col) -> "water" | "hit"
        self.shots: dict[str, dict[tuple[int, int], str]] = {p: {} for p in self.players}
        # cells automatically marked as water around a sunk ship
        self.auto_water: dict[str, set] = {p: set() for p in self.players}
        self.turn: str | None = None
        self.last_shot: dict | None = None
        self.winner: str | None = None
        self.stats = {p: {"shots": 0, "hits": 0} for p in self.players}

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        if len(players) < 2:
            raise ValueError("La batalla naval se juega entre los dos. Esperen a que entre tu pareja.")
        try:
            size = int(options.get("size", 10))
        except (TypeError, ValueError) as exc:
            raise ValueError("Tamaño no válido") from exc
        if size not in FLEETS:
            raise ValueError("El tablero es de 8 o de 10")
        return cls(players, size=size, no_touch=bool(options.get("noTouch", True)), bonus=bool(options.get("bonus", True)), rng=rng)

    # --- room interface -------------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase in ("placing", "battle")

    @property
    def timer_key(self):
        return None

    @property
    def timer_seconds(self):
        return None

    def start(self) -> None:
        self.phase = "placing"

    def on_timeout(self) -> None:
        pass

    def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "bn_place":
            self.place(player, msg.get("ships"))
        elif kind == "bn_unready":
            self.unready(player)
        elif kind == "bn_fire":
            self.fire(player, msg.get("row"), msg.get("col"))

    def remove_player(self, player: str) -> None:
        pass  # the seat is kept so they can come back

    # --- placement ------------------------------------------------------
    def opponent(self, player: str) -> str:
        return next(p for p in self.players if p != player)

    def place(self, player: str, ships) -> None:
        if self.phase != "placing":
            raise ValueError("Ya no se pueden mover los barcos")
        self.fleets[player] = validate_fleet(ships, self.size, self.no_touch)
        self.ready[player] = True
        if all(self.ready.get(p) for p in self.players):
            self.turn = self.rng.choice(self.players)
            self.phase = "battle"

    def unready(self, player: str) -> None:
        if self.phase != "placing":
            raise ValueError("La batalla ya empezó")
        self.ready[player] = False

    # --- shots ----------------------------------------------------------
    def _ship_at(self, player: str, cell):
        return next((s for s in self.fleets[player] if cell in s["cells"]), None)

    def _sunk(self, player: str, ship: dict) -> bool:
        return all(self.shots[player].get(c) == "hit" for c in ship["cells"])

    def fire(self, player: str, row, col) -> None:
        if self.phase != "battle":
            raise ValueError("Todavía no empieza la batalla")
        if player != self.turn:
            raise ValueError(f"Le toca disparar a {self.turn}")
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (row, col)) or not (0 <= row < self.size and 0 <= col < self.size):
            raise ValueError("Disparo fuera del tablero")
        target = self.opponent(player)
        cell = (row, col)
        if cell in self.shots[target] or cell in self.auto_water[target]:
            raise ValueError("Ya disparaste ahí")
        ship = self._ship_at(target, cell)
        self.stats[player]["shots"] += 1
        result = "water"
        sunk = None
        if ship:
            self.shots[target][cell] = "hit"
            self.stats[player]["hits"] += 1
            result = "hit"
            if self._sunk(target, ship):
                result = "sunk"
                sunk = ship["id"]
                if self.no_touch:
                    for around in neighbors(ship["cells"], self.size):
                        if around not in self.shots[target]:
                            self.auto_water[target].add(around)
        else:
            self.shots[target][cell] = "water"
        self.last_shot = {"by": player, "row": row, "col": col, "result": result, "ship": sunk}
        if all(self._sunk(target, s) for s in self.fleets[target]):
            self.winner = player
            self.phase = "finished"
            return
        if result == "water" or not self.bonus:
            self.turn = target

    # --- state for clients ----------------------------------------------
    def _public_ship(self, ship: dict, owner: str) -> dict:
        return {"id": ship["id"], "row": ship["row"], "col": ship["col"], "dir": ship["dir"], "length": ship["length"], "sunk": self._sunk(owner, ship)}

    def _board_view(self, owner: str, reveal: bool) -> dict:
        """What is visible of `owner`'s board: shots received and ships (all of them, or only sunk ones)."""
        ships = self.fleets.get(owner, [])
        shown = [self._public_ship(s, owner) for s in ships if reveal or self._sunk(owner, s)]
        return {
            "shots": [[r, c, v] for (r, c), v in sorted(self.shots[owner].items())],
            "autoWater": sorted([r, c] for r, c in self.auto_water[owner]),
            "ships": shown,
            "afloat": sum(1 for s in ships if not self._sunk(owner, s)),
        }

    def snapshot(self, viewer: str | None = None) -> dict:
        finished = self.phase == "finished"
        boards = {}
        for p in self.players:
            boards[p] = self._board_view(p, reveal=finished or p == viewer)
        fleet = [{"id": sid, "name": label, "length": length} for sid, label, length in FLEETS[self.size]]
        return {
            "name": self.name,
            "phase": self.phase,
            "players": self.players,
            "size": self.size,
            "fleet": fleet,
            "ready": self.ready,
            "turn": self.turn,
            "boards": boards,
            "lastShot": self.last_shot,
            "winner": self.winner,
            "stats": self.stats,
            "options": {"size": self.size, "noTouch": self.no_touch, "bonus": self.bonus},
        }
