"""Parqués (the Colombian race game) for two.

The board is a cross with a 68-square loop (17 per arm). Each player has a
jail in a corner and a home stretch down the middle of their arm: 7 squares
and then heaven ("cielo"). The two colors sit in opposite corners.

Rules:
  - Two dice are rolled. Each die moves a piece separately (the same piece
    or two different ones). A die that cannot be used is lost.
  - Leaving jail requires doubles: every jailed piece moves to the exit. With
    no pieces out, you get three tries to roll doubles.
  - Doubles give another roll. The third doubles in a row is a bonus: one
    piece goes straight to heaven and the turn ends.
  - Landing on a rival piece sends it to jail, except on safe squares.
    Leaving jail does capture whoever sits on your exit square.
  - Entering heaven requires the exact number.
  - First to get every piece to heaven wins.

Each piece is stored as its progress from the exit:
  -1 jail · 0..63 loop · 64..70 home stretch · 71 heaven
"""

import random

LOOP = 68
ARM = 17
TO_ENTRY = 63  # steps from the exit to the square where the home stretch begins
HOME = 71  # heaven
EXIT_OFFSET = 13  # exit square of each arm (next to its jail)
SAFE_OFFSETS = (4, 13)  # safe squares of each arm
SAFE = {ARM * k + o for k in range(4) for o in SAFE_OFFSETS}
SEATS = {2: (0, 2), 3: (0, 1, 2), 4: (0, 1, 2, 3)}  # arms by number of players (two face each other)


class ParquesGame:
    name = "parques"
    max_players = 4
    actions = {"pa_roll", "pa_move", "pa_release", "pa_bonus"}

    def __init__(self, players: list[str], pieces: int = 4, rng: random.Random | None = None, timings: dict | None = None):
        self.players = list(players)
        self.rng = rng or random.Random()
        self.n_pieces = pieces
        seats = SEATS.get(len(self.players), (0, 2, 1, 3))
        self.arm = {p: seats[i] for i, p in enumerate(self.players)}
        self.pieces = {p: [-1] * pieces for p in self.players}
        self.phase = "idle"
        self.turn: str | None = None
        self.dice: list[int] | None = None
        self.unused: list[int] = []  # indexes of unused dice
        self.pairs_in_row = 0
        self.attempts = 0  # tries to roll doubles while everything is in jail
        self.log: list[dict] = []
        self.winner: str | None = None
        self.roll_id = 0

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        if len(players) < 2:
            raise ValueError("El parqués se juega entre los dos. Esperen a que entre tu pareja.")
        try:
            pieces = int(options.get("pieces", 4))
        except (TypeError, ValueError) as exc:
            raise ValueError("Número de fichas no válido") from exc
        if pieces not in (2, 4):
            raise ValueError("Se juega con 2 o 4 fichas")
        return cls(players, pieces=pieces, rng=rng)

    # --- room interface -------------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase in ("roll", "move", "bonus")

    @property
    def timer_key(self):
        return None

    @property
    def timer_seconds(self):
        return None

    def start(self) -> None:
        self.turn = self.rng.choice(self.players)
        self.phase = "roll"

    def on_timeout(self) -> None:
        pass

    def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        if player != self.turn:
            raise ValueError(f"Le toca a {self.turn}")
        if kind == "pa_roll":
            self.roll()
        elif kind == "pa_move":
            self.move(msg.get("piece"), msg.get("die"))
        elif kind == "pa_release":
            self.release()
        elif kind == "pa_bonus":
            self.bonus(msg.get("piece"))

    def remove_player(self, player: str) -> None:
        pass

    # --- geometry -------------------------------------------------------
    def next_player(self, player: str) -> str:
        return self.players[(self.players.index(player) + 1) % len(self.players)]

    def exit_square(self, player: str) -> int:
        return ARM * self.arm[player] + EXIT_OFFSET

    def square(self, player: str, progress: int) -> int | None:
        """Loop square (0..67) of a piece, or None if it is not on the loop."""
        if 0 <= progress <= TO_ENTRY:
            return (self.exit_square(player) + progress) % LOOP
        return None

    # --- dice -----------------------------------------------------------
    def roll(self, forced: tuple[int, int] | None = None) -> None:
        if self.phase != "roll":
            raise ValueError("Primero mueve tus fichas")
        me = self.turn
        self.dice = list(forced) if forced else [self.rng.randint(1, 6), self.rng.randint(1, 6)]
        self.roll_id += 1
        pair = self.dice[0] == self.dice[1]
        self.log.append({"player": me, "action": "roll", "dice": self.dice[:]})
        free = [i for i, p in enumerate(self.pieces[me]) if 0 <= p < HOME]
        if pair:
            self.pairs_in_row += 1
            if self.pairs_in_row == 3:
                self.unused = []
                self.phase = "bonus"
                return
        if not free:
            # everything in jail (or heaven): only doubles help
            if pair:
                self._release_all()
                self.unused = []
                self.attempts = 0
                self.phase = "roll"  # doubles: roll again
                return
            self.attempts += 1
            if self.attempts >= 3:
                self.log.append({"player": me, "action": "no_luck"})
                self._next_turn()
            return
        self.attempts = 0
        self.unused = [0, 1]
        self.phase = "move"
        self._drop_dead_dice()

    def _release_all(self) -> None:
        me = self.turn
        jailed = [i for i, p in enumerate(self.pieces[me]) if p == -1]
        if not jailed:
            return
        for i in jailed:
            self.pieces[me][i] = 0
        self.log.append({"player": me, "action": "release", "count": len(jailed)})
        self._capture(self.exit_square(me), on_exit=True)

    def release(self) -> None:
        """With doubles and pieces out: spend both dice to release the jailed pieces."""
        if self.phase != "move" or not self.can_release:
            raise ValueError("Para salir de la cárcel necesitas pares sin usar")
        self._release_all()
        self.unused = []
        self._after_dice()

    @property
    def can_release(self) -> bool:
        return (
            self.phase == "move"
            and self.dice is not None
            and self.dice[0] == self.dice[1]
            and self.unused == [0, 1]
            and -1 in self.pieces[self.turn]
        )

    # --- moves ----------------------------------------------------------
    def legal_moves(self) -> list[dict]:
        if self.phase != "move":
            return []
        me = self.turn
        moves = []
        for d in self.unused:
            steps = self.dice[d]
            for i, prog in enumerate(self.pieces[me]):
                if 0 <= prog < HOME and prog + steps <= HOME:
                    moves.append({"piece": i, "die": d, "to": prog + steps})
        return moves

    def move(self, piece, die) -> None:
        if self.phase != "move":
            raise ValueError("Primero lanza los dados")
        match = next((m for m in self.legal_moves() if m["piece"] == piece and m["die"] == die), None)
        if not match:
            raise ValueError("Esa ficha no puede moverse con ese dado")
        me = self.turn
        self.pieces[me][piece] = match["to"]
        self.unused.remove(die)
        self.log.append({"player": me, "action": "move", "piece": piece, "steps": self.dice[die], "to": match["to"]})
        sq = self.square(me, match["to"])
        if sq is not None:
            self._capture(sq)
        if all(p == HOME for p in self.pieces[me]):
            self.winner = me
            self.phase = "finished"
            return
        self._drop_dead_dice()

    def _capture(self, sq: int, on_exit: bool = False) -> None:
        if sq in SAFE and not on_exit:
            return
        me = self.turn
        count = 0
        for rival in self.players:
            if rival == me:
                continue
            caught = [i for i, p in enumerate(self.pieces[rival]) if self.square(rival, p) == sq]
            for i in caught:
                self.pieces[rival][i] = -1
            count += len(caught)
        if count:
            self.log.append({"player": me, "action": "capture", "count": count})

    def _drop_dead_dice(self) -> None:
        """Drop dice that can no longer be used and close the move if nothing is left."""
        if self.phase != "move":
            return
        usable = {m["die"] for m in self.legal_moves()}
        keep_for_release = self.can_release
        lost = [d for d in self.unused if d not in usable]
        if lost and not keep_for_release:
            self.unused = [d for d in self.unused if d in usable]
            self.log.append({"player": self.turn, "action": "lost", "dice": [self.dice[d] for d in lost]})
        if not self.unused or (not usable and not keep_for_release):
            self.unused = []
            self._after_dice()

    def _after_dice(self) -> None:
        if self.dice and self.dice[0] == self.dice[1] and self.phase != "finished":
            self.phase = "roll"  # doubles: another turn
        else:
            self._next_turn()

    def bonus(self, piece) -> None:
        if self.phase != "bonus":
            raise ValueError("No tienes premio")
        me = self.turn
        if not isinstance(piece, int) or not 0 <= piece < self.n_pieces or self.pieces[me][piece] == HOME:
            raise ValueError("Elige una ficha que no esté en el cielo")
        self.pieces[me][piece] = HOME
        self.log.append({"player": me, "action": "bonus", "piece": piece})
        if all(p == HOME for p in self.pieces[me]):
            self.winner = me
            self.phase = "finished"
            return
        self._next_turn()

    def _next_turn(self) -> None:
        self.turn = self.next_player(self.turn)
        self.unused = []
        self.pairs_in_row = 0
        self.attempts = 0
        self.phase = "roll"

    # --- state for clients ----------------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        me_turn = viewer == self.turn
        return {
            "name": self.name,
            "phase": self.phase,
            "players": self.players,
            "arms": self.arm,
            "pieces": self.pieces,
            "squares": {p: [self.square(p, x) for x in self.pieces[p]] for p in self.players},
            "turn": self.turn,
            "dice": self.dice,
            "rollId": self.roll_id,
            "unused": self.unused,
            "moves": self.legal_moves() if me_turn else [],
            "canRelease": self.can_release if me_turn else False,
            "attemptsLeft": 3 - self.attempts if self.phase == "roll" and not any(0 <= p < HOME for p in self.pieces.get(self.turn, [])) else None,
            "pairsInRow": self.pairs_in_row,
            "log": self.log[-8:],
            "winner": self.winner,
            "safe": sorted(SAFE),
            "options": {"pieces": self.n_pieces},
        }
