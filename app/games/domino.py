"""Dominoes for two, with a double-six set (28 tiles).

Each player gets 7 tiles and the other 14 stay in the boneyard. Players take
turns placing a tile that matches one of the two open ends of the line.

  with boneyard     -> with no playable tile you draw until you can play;
                       if the boneyard is empty, you pass.
  without boneyard  -> with no playable tile you pass.

Passing is automatic: if a player has no move and nothing to draw, the turn
goes straight back to the other player.

A hand ends when someone runs out of tiles ("domino") or nobody can play
("blocked"; the lower hand total wins). The hand winner scores the pips left
in the other player's hand. The game ends when someone reaches the goal.

In the first hand, the player with the highest double leads with it; if
nobody has a double, the highest tile leads. In later hands the previous
hand's winner leads with any tile.
"""

import random

TILES = [(a, b) for a in range(7) for b in range(a, 7)]
GOALS = (50, 100, 150)


def pips(tiles) -> int:
    return sum(a + b for a, b in tiles)


def norm(tile) -> tuple[int, int]:
    a, b = tile
    return (a, b) if a <= b else (b, a)


class DominoGame:
    name = "domino"
    max_players = 2
    actions = {"dm_play", "dm_draw", "next_round"}

    def __init__(
        self,
        players: list[str],
        goal: int = 100,
        boneyard: bool = True,
        rng: random.Random | None = None,
        timings: dict | None = None,
    ):
        self.players = list(players)
        self.goal = goal
        self.use_boneyard = boneyard
        self.rng = rng or random.Random()
        self.scores = {p: 0 for p in self.players}
        self.phase = "idle"
        self.hand_no = 0
        self.hands: dict[str, list[tuple[int, int]]] = {}
        self.pool: list[tuple[int, int]] = []
        self.line: list[tuple[int, int]] = []  # oriented tiles: (left, right)
        self.turn: str | None = None
        self.forced: tuple[int, int] | None = None  # tile that must lead
        self.next_starter: str | None = None
        self.passes = 0
        self.log: list[dict] = []  # latest actions of the hand
        self.result: dict | None = None
        self.history: list[dict] = []
        self.winner: str | None = None

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        if len(players) < 2:
            raise ValueError("El dominó se juega entre los dos. Esperen a que entre tu pareja.")
        try:
            goal = int(options.get("goal", 100))
        except (TypeError, ValueError) as exc:
            raise ValueError("Meta no válida") from exc
        if goal not in GOALS:
            raise ValueError("La meta es 50, 100 o 150 puntos")
        return cls(players, goal=goal, boneyard=bool(options.get("boneyard", True)), rng=rng)

    # --- room interface -------------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase in ("playing", "hand_over")

    @property
    def timer_key(self):
        return None

    @property
    def timer_seconds(self):
        return None

    def start(self) -> None:
        self._deal()

    def on_timeout(self) -> None:
        pass

    def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "dm_play":
            self.play(player, msg.get("tile"), msg.get("side"))
        elif kind == "dm_draw":
            self.draw(player)
        elif kind == "next_round":
            self.next_hand()

    def remove_player(self, player: str) -> None:
        pass

    # --- dealing ----------------------------------------------------------
    def other(self, player: str) -> str:
        return next(p for p in self.players if p != player)

    def _deal(self) -> None:
        tiles = TILES[:]
        self.rng.shuffle(tiles)
        self.hands = {p: sorted(tiles[i * 7:(i + 1) * 7]) for i, p in enumerate(self.players)}
        self.pool = tiles[14:]
        self.line = []
        self.passes = 0
        self.log = []
        self.result = None
        self.hand_no += 1
        self.forced = None
        if self.next_starter:
            self.turn = self.next_starter
        else:
            self.turn, self.forced = self._opening()
        self.phase = "playing"

    def _opening(self):
        best = None
        for p in self.players:
            for t in self.hands[p]:
                rank = (1 if t[0] == t[1] else 0, t[0] + t[1], t[1])
                if best is None or rank > best[0]:
                    best = (rank, p, t)
        return best[1], best[2]

    # --- moves ------------------------------------------------------------
    @property
    def ends(self) -> tuple[int, int] | None:
        return (self.line[0][0], self.line[-1][1]) if self.line else None

    def moves_for(self, player: str) -> list[dict]:
        """Possible moves: [{"tile": [a, b], "sides": ["left", "right"]}]."""
        out = []
        for t in self.hands.get(player, []):
            if self.forced and t != self.forced:
                continue
            if not self.line:
                out.append({"tile": list(t), "sides": ["left"]})
                continue
            left, right = self.ends
            sides = []
            if left in t:
                sides.append("left")
            if right in t:
                sides.append("right")
            if sides:
                out.append({"tile": list(t), "sides": sides})
        return out

    def play(self, player: str, tile, side) -> None:
        if self.phase != "playing":
            raise ValueError("La mano ya terminó")
        if player != self.turn:
            raise ValueError(f"Le toca a {self.turn}")
        try:
            t = norm((int(tile[0]), int(tile[1])))
        except (TypeError, ValueError, IndexError) as exc:
            raise ValueError("Ficha no válida") from exc
        if t not in self.hands[player]:
            raise ValueError("No tienes esa ficha")
        options = next((m["sides"] for m in self.moves_for(player) if tuple(m["tile"]) == t), None)
        if not options:
            raise ValueError("Esa ficha no pega en la línea" if not self.forced else f"Tienes que salir con el {t[0]}|{t[1]}")
        if side not in options:
            side = options[0] if len(options) == 1 else None
        if side is None:
            raise ValueError("Elige en qué lado la pones")
        a, b = t
        if not self.line:
            self.line = [(a, b)]
        elif side == "left":
            left = self.line[0][0]
            self.line.insert(0, (a, b) if b == left else (b, a))
        else:
            right = self.line[-1][1]
            self.line.append((a, b) if a == right else (b, a))
        self.hands[player].remove(t)
        self.forced = None
        self.passes = 0
        self.log.append({"player": player, "action": "play", "tile": [a, b], "side": side})
        if not self.hands[player]:
            self._end_hand(player, "domino")
            return
        self.turn = self.other(player)
        self._auto_pass()

    def draw(self, player: str) -> None:
        if self.phase != "playing":
            raise ValueError("La mano ya terminó")
        if player != self.turn:
            raise ValueError(f"Le toca a {self.turn}")
        if not self.use_boneyard:
            raise ValueError("En esta partida no se roba")
        if self.moves_for(player):
            raise ValueError("Tienes con qué jugar")
        if not self.pool:
            raise ValueError("El pozo está vacío")
        tile = self.pool.pop()
        self.hands[player].append(tile)
        self.hands[player].sort()
        self.log.append({"player": player, "action": "draw"})
        self._auto_pass()

    def _auto_pass(self) -> None:
        """If the player on turn can neither play nor draw, they pass automatically."""
        while self.phase == "playing" and not self.moves_for(self.turn):
            if self.use_boneyard and self.pool:
                return  # they have to draw
            self.passes += 1
            self.log.append({"player": self.turn, "action": "pass"})
            if self.passes >= 2:
                self._blocked()
                return
            self.turn = self.other(self.turn)

    def _blocked(self) -> None:
        counts = {p: pips(self.hands[p]) for p in self.players}
        a, b = self.players
        if counts[a] == counts[b]:
            self._end_hand(None, "blocked")
        else:
            self._end_hand(a if counts[a] < counts[b] else b, "blocked")

    def _end_hand(self, winner: str | None, reason: str) -> None:
        counts = {p: pips(self.hands[p]) for p in self.players}
        points = counts[self.other(winner)] if winner else 0
        if winner:
            self.scores[winner] += points
            self.next_starter = winner
        elif not self.next_starter:
            self.next_starter = self.turn
        self.result = {"winner": winner, "reason": reason, "points": points, "pips": counts}
        self.history.append({"hand": self.hand_no, **self.result})
        self.turn = None
        self.phase = "hand_over"
        if winner and self.scores[winner] >= self.goal:
            self.winner = winner
            self.phase = "finished"

    def next_hand(self) -> None:
        if self.phase != "hand_over":
            raise ValueError("La mano todavía no termina")
        self._deal()

    # --- state for clients ----------------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        over = self.phase in ("hand_over", "finished")
        hands = {}
        for p in self.players:
            tiles = self.hands.get(p, [])
            hands[p] = [list(t) for t in tiles] if (over or p == viewer) else None
        my_moves = self.moves_for(viewer) if viewer and self.phase == "playing" and viewer == self.turn else []
        must_draw = bool(viewer == self.turn and self.phase == "playing" and not my_moves and self.use_boneyard and self.pool)
        return {
            "name": self.name,
            "phase": self.phase,
            "players": self.players,
            "handNo": self.hand_no,
            "turn": self.turn,
            "line": [list(t) for t in self.line],
            "ends": list(self.ends) if self.ends else None,
            "hands": hands,
            "counts": {p: len(self.hands.get(p, [])) for p in self.players},
            "pool": len(self.pool),
            "moves": my_moves,
            "mustDraw": must_draw,
            "forced": list(self.forced) if self.forced else None,
            "log": self.log[-6:],
            "result": self.result,
            "scores": self.scores,
            "goal": self.goal,
            "winner": self.winner,
            "history": self.history,
            "options": {"goal": self.goal, "boneyard": self.use_boneyard},
        }
