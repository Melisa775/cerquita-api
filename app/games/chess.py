"""Ajedrez entre los dos.

Las reglas están en chess_rules.py; aquí va la partida: quién lleva cada
color, el reloj, el historial con notación en español, las ofertas de
tablas y de deshacer, y cómo termina:

  mate, abandono, tiempo, ahogado, tablas acordadas, triple repetición,
  regla de los 50 movimientos o material insuficiente.

Con reloj, el tiempo empieza a correr cuando cada uno ya hizo su primera
jugada (como en las plataformas en línea). Si a alguien se le acaba el
tiempo pero su rival solo tiene el rey, es tablas.
"""

import random
import time

from app.games.chess_rules import Move, Position, color_of, name, other, sq

# minutos + segundos de incremento por jugada
TIME_CONTROLS = {"libre": None, "3+2": (3, 2), "5+3": (5, 3), "10+0": (10, 0), "15+10": (15, 10)}
REASONS = {
    "mate": "jaque mate",
    "abandono": "abandono",
    "tiempo": "tiempo",
    "ahogado": "rey ahogado",
    "acuerdo": "tablas de mutuo acuerdo",
    "repeticion": "triple repetición",
    "cincuenta": "regla de los 50 movimientos",
    "material": "material insuficiente",
    "tiempo_material": "tiempo, pero sin material para dar mate",
}


class ChessGame:
    name = "chess"
    actions = {"ch_move", "ch_resign", "ch_draw", "ch_draw_decline", "ch_undo", "ch_undo_decline"}

    def __init__(
        self,
        players: list[str],
        white: str | None = None,
        time_control: str = "libre",
        hints: bool = True,
        rng: random.Random | None = None,
        timings: dict | None = None,
        clock=time.monotonic,
        fen: str | None = None,
    ):
        self.players = list(players)
        self.rng = rng or random.Random()
        if white not in self.players:
            white = self.rng.choice(self.players)
        black = next(p for p in self.players if p != white)
        self.colors = {white: "w", black: "b"}
        self.time_control = time_control
        self.hints = hints
        self.clock = clock
        control = TIME_CONTROLS[time_control]
        timings = timings or {}
        if control:
            base = timings.get("base", control[0] * 60)
            self.increment = timings.get("increment", control[1])
            self.remaining = {"w": float(base), "b": float(base)}
        else:
            self.increment = 0
            self.remaining = None
        self.turn_started = self.clock()
        self.positions = [Position.from_fen(fen) if fen else Position.from_fen()]
        self.keys = [self.positions[0].repetition_key()]
        self.moves: list[dict] = []  # {"san", "from", "to", "piece", "captured", "color"}
        self.phase = "idle"
        self.result: dict | None = None
        self.draw_offer: str | None = None
        self.undo_request: str | None = None
        self.version = 0  # cambia con cada jugada o deshacer (reinicia el reloj)

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        if len(players) < 2:
            raise ValueError("El ajedrez se juega entre los dos. Esperen a que entre tu pareja.")
        control = options.get("timeControl", "libre")
        if control not in TIME_CONTROLS:
            raise ValueError("Ritmo de juego no válido")
        white = options.get("white")
        if white is not None and white not in players:
            white = None
        return cls(players, white=white, time_control=control, hints=bool(options.get("hints", True)), rng=rng, timings=timings)

    # --- interfaz con la sala -------------------------------------------
    @property
    def pos(self) -> Position:
        return self.positions[-1]

    @property
    def in_progress(self) -> bool:
        return self.phase == "playing"

    @property
    def player_to_move(self) -> str:
        return next(p for p, c in self.colors.items() if c == self.pos.turn)

    @property
    def clock_running(self) -> bool:
        return self.remaining is not None and self.phase == "playing" and len(self.moves) >= 2

    def _left(self, color: str) -> float:
        left = self.remaining[color]
        if self.clock_running and color == self.pos.turn:
            left -= self.clock() - self.turn_started
        return max(0.0, left)

    @property
    def timer_key(self):
        return ("clock", self.version) if self.clock_running else None

    @property
    def timer_seconds(self) -> float | None:
        return self._left(self.pos.turn) if self.clock_running else None

    def start(self) -> None:
        self.phase = "playing"
        self.turn_started = self.clock()

    def on_timeout(self) -> None:
        if not self.clock_running:
            return
        loser = self.pos.turn
        self.remaining[loser] = 0.0
        winner_color = other(loser)
        if self.pos.can_mate(winner_color):
            self._finish(self._player(winner_color), "tiempo")
        else:
            self._finish(None, "tiempo_material")

    def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        if self.phase != "playing":
            raise ValueError("La partida ya terminó")
        if kind == "ch_move":
            self.move(player, msg.get("from"), msg.get("to"), msg.get("promotion"))
        elif kind == "ch_resign":
            self._finish(self._player(other(self.colors[player])), "abandono")
        elif kind == "ch_draw":
            self.offer_draw(player)
        elif kind == "ch_draw_decline":
            if self.draw_offer and self.draw_offer != player:
                self.draw_offer = None
        elif kind == "ch_undo":
            self.ask_undo(player)
        elif kind == "ch_undo_decline":
            if self.undo_request and self.undo_request != player:
                self.undo_request = None

    def remove_player(self, player: str) -> None:
        pass  # el puesto se conserva: si alguien se va, la sala lo espera

    # --- jugadas ----------------------------------------------------------
    def _player(self, color: str) -> str:
        return next(p for p, c in self.colors.items() if c == color)

    def move(self, player: str, frm, to, promotion=None) -> None:
        if self.colors.get(player) != self.pos.turn:
            raise ValueError("No es tu turno")
        try:
            frm_i, to_i = sq(frm), sq(to)
        except (TypeError, ValueError, IndexError) as exc:
            raise ValueError("Jugada no válida") from exc
        promo = promotion.upper() if isinstance(promotion, str) else None
        candidates = [m for m in self.pos.legal_moves() if m.frm == frm_i and m.to == to_i]
        if not candidates:
            raise ValueError("Esa jugada no es legal")
        if candidates[0].promotion:
            match = [m for m in candidates if m.promotion == (promo or "Q")]
            if not match:
                raise ValueError("Coronación no válida")
            mv = match[0]
        else:
            mv = candidates[0]
        self._apply(mv)

    def _apply(self, mv: Move) -> None:
        pos = self.pos
        color = pos.turn
        piece = pos.board[mv.frm]
        captured = pos.board[mv.to]
        if piece.upper() == "P" and mv.to == pos.ep:
            captured = "p" if color == "w" else "P"
        san = pos.san(mv)
        if self.clock_running:
            self.remaining[color] = self._left(color) + self.increment
        after = pos.push(mv)
        self.positions.append(after)
        self.keys.append(after.repetition_key())
        self.moves.append({"san": san, "from": name(mv.frm), "to": name(mv.to), "piece": piece, "captured": captured, "color": color})
        self.draw_offer = None
        self.undo_request = None
        self.version += 1
        self.turn_started = self.clock()
        self._check_end()

    def _check_end(self) -> None:
        pos = self.pos
        if not pos.legal_moves():
            if pos.in_check():
                self._finish(self._player(other(pos.turn)), "mate")
            else:
                self._finish(None, "ahogado")
        elif pos.insufficient_material():
            self._finish(None, "material")
        elif self.keys.count(self.keys[-1]) >= 3:
            self._finish(None, "repeticion")
        elif pos.halfmove >= 100:
            self._finish(None, "cincuenta")

    def _finish(self, winner: str | None, reason: str) -> None:
        if self.remaining is not None and self.phase == "playing":
            for c in ("w", "b"):
                self.remaining[c] = self._left(c)
        self.result = {"winner": winner, "reason": reason, "text": REASONS[reason]}
        self.draw_offer = None
        self.undo_request = None
        self.version += 1
        self.phase = "finished"

    # --- ofertas ----------------------------------------------------------
    def offer_draw(self, player: str) -> None:
        if self.draw_offer and self.draw_offer != player:
            self._finish(None, "acuerdo")
        else:
            self.draw_offer = player

    def ask_undo(self, player: str) -> None:
        if self.undo_request and self.undo_request != player:
            self._undo(self.undo_request)
            return
        if not self.moves:
            raise ValueError("Todavía no hay jugadas para deshacer")
        mine = self.colors[player]
        if self.moves[-1]["color"] != mine and len(self.moves) < 2:
            raise ValueError("Todavía no has jugado")
        self.undo_request = player

    def _undo(self, requester: str) -> None:
        """Deshace la última jugada de quien pidió (y la respuesta del otro, si ya la hizo)."""
        mine = self.colors[requester]
        plies = 1 if self.moves[-1]["color"] == mine else 2
        for _ in range(min(plies, len(self.moves))):
            self.moves.pop()
            self.positions.pop()
            self.keys.pop()
        self.undo_request = None
        self.draw_offer = None
        self.version += 1
        self.turn_started = self.clock()

    # --- estado para los clientes ---------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        pos = self.pos
        playing = self.phase == "playing"
        legal: dict[str, list[str]] = {}
        if playing and viewer is not None and self.colors.get(viewer) == pos.turn:
            for m in pos.legal_moves():
                targets = legal.setdefault(name(m.frm), [])
                if name(m.to) not in targets:
                    targets.append(name(m.to))
        check = name(pos.king_square(pos.turn)) if pos.in_check() else None
        last = self.moves[-1] if self.moves else None
        captured = {"w": [], "b": []}  # piezas que capturó cada color
        for m in self.moves:
            if m["captured"]:
                captured[m["color"]].append(m["captured"])
        clocks = None
        if self.remaining is not None:
            clocks = {c: round(self._left(c) * 1000) for c in ("w", "b")}
        return {
            "name": self.name,
            "phase": self.phase,
            "players": self.players,
            "colors": self.colors,
            "board": pos.board,
            "turn": pos.turn,
            "toMove": self.player_to_move,
            "legal": legal,
            "check": check,
            "lastMove": {"from": last["from"], "to": last["to"]} if last else None,
            "moves": [m["san"] for m in self.moves],
            "captured": captured,
            "clocks": clocks,
            "clockRunning": self.clock_running,
            "increment": self.increment,
            "result": self.result,
            "drawOffer": self.draw_offer,
            "undoRequest": self.undo_request,
            "fen": pos.fen(),
            "options": {"timeControl": self.time_control, "hints": self.hints},
        }
