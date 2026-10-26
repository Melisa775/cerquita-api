"""Mini golf para dos (al estilo del de Plato).

Por turnos, cada uno tira su bola en el mismo hoyo: se apunta jalando hacia
atrás como una cauchera. El servidor simula el tiro (golf_physics.py) y le
manda el camino a los dos para que lo animen igual. Mientras alguien apunta,
la dirección y la fuerza le llegan en vivo a su pareja como eventos livianos.

En cada hoyo se turnan los tiros (quien ya metió la bola no tira más). Caer
al agua suma un golpe y la bola vuelve a donde estaba. Con 10 golpes la bola
se levanta. Gana quien termine el recorrido con menos golpes.
"""

import math
import random

from app.games.golf_courses import COURSES
from app.games.golf_physics import simulate

MAX_STROKES = 10
HOLE_CHOICES = (3, 6, 9)


class GolfGame:
    name = "golf"
    actions = {"gf_shoot", "gf_aim", "next_round"}

    def __init__(self, players: list[str], holes: int = 9, rng: random.Random | None = None, timings: dict | None = None):
        self.players = list(players)
        self.rng = rng or random.Random()
        self.courses = COURSES[:holes]
        self.hole = 0
        self.phase = "idle"
        self.balls: dict[str, list[float]] = {}
        self.strokes: dict[str, int] = {}
        self.done: dict[str, bool] = {}
        self.turn: str | None = None
        self.shot_id = 0
        self.last_shot: dict | None = None
        self.card: list[dict] = []  # golpes por hoyo
        self.first = self.rng.choice(self.players)
        self.winner: str | None = None

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        if len(players) < 2:
            raise ValueError("El mini golf se juega entre los dos. Esperen a que entre tu pareja.")
        try:
            holes = int(options.get("holes", 9))
        except (TypeError, ValueError) as exc:
            raise ValueError("Número de hoyos no válido") from exc
        if holes not in HOLE_CHOICES:
            raise ValueError("Elige 3, 6 o 9 hoyos")
        return cls(players, holes=holes, rng=rng)

    # --- interfaz con la sala -------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase in ("playing", "hole_over")

    @property
    def timer_key(self):
        return None

    @property
    def timer_seconds(self):
        return None

    def start(self) -> None:
        self._start_hole()

    def on_timeout(self) -> None:
        pass

    def handle(self, player: str, msg: dict):
        kind = msg.get("type")
        if kind == "next_round":
            self.next_hole()
            return None
        if self.phase != "playing":
            raise ValueError("Este hoyo ya terminó")
        if player != self.turn:
            raise ValueError(f"Le toca a {self.turn}")
        if kind == "gf_aim":
            # solo se reenvía a la pareja: no cambia el estado
            try:
                angle, power = float(msg.get("angle")), float(msg.get("power"))
            except (TypeError, ValueError):
                return {"relay": {"kind": "aim", "player": player, "angle": 0, "power": 0}}
            return {"relay": {"kind": "aim", "player": player, "angle": round(angle, 3), "power": round(max(0, min(1, power)), 3)}}
        if kind == "gf_shoot":
            self.shoot(player, msg.get("angle"), msg.get("power"))
        return None

    def remove_player(self, player: str) -> None:
        pass

    # --- hoyos ----------------------------------------------------------
    @property
    def course(self) -> dict:
        return self.courses[self.hole]

    def _start_hole(self) -> None:
        tee = self.course["tee"]
        self.balls = {p: [float(tee[0]), float(tee[1])] for p in self.players}
        self.strokes = {p: 0 for p in self.players}
        self.done = {p: False for p in self.players}
        # se alterna quién empieza cada hoyo
        start = (self.players.index(self.first) + self.hole) % len(self.players)
        self.turn = self.players[start]
        self.last_shot = None
        self.phase = "playing"

    def other(self, player: str) -> str:
        return next(p for p in self.players if p != player)

    def shoot(self, player: str, angle, power) -> None:
        try:
            angle = float(angle)
            power = float(power)
        except (TypeError, ValueError) as exc:
            raise ValueError("Tiro no válido") from exc
        if not math.isfinite(angle) or not 0.02 <= power <= 1.0:
            raise ValueError("Jala un poco más para tirar")
        start = self.balls[player][:]
        sim = simulate(self.course, start, angle, power)
        self.strokes[player] += 1
        penalty = sim["result"] == "water"
        if penalty:
            self.strokes[player] += 1
        self.balls[player] = sim["end"]
        if sim["result"] == "holed":
            self.done[player] = True
        elif self.strokes[player] >= MAX_STROKES:
            self.strokes[player] = MAX_STROKES
            self.done[player] = True
        self.shot_id += 1
        self.last_shot = {
            "id": self.shot_id,
            "player": player,
            "from": start,
            "path": sim["path"],
            "events": sim["events"],
            "result": sim["result"],
            "penalty": penalty,
            "strokes": self.strokes[player],
            "pickedUp": self.done[player] and sim["result"] != "holed",
        }
        if all(self.done.values()):
            self._end_hole()
            return
        rival = self.other(player)
        self.turn = rival if not self.done[rival] else player

    def _end_hole(self) -> None:
        self.card.append({"hole": self.hole + 1, "name": self.course["name"], "par": self.course["par"], "strokes": dict(self.strokes)})
        self.turn = None
        self.phase = "hole_over"
        if self.hole == len(self.courses) - 1:
            totals = self.totals()
            best = min(totals.values())
            leaders = [p for p, t in totals.items() if t == best]
            self.winner = leaders[0] if len(leaders) == 1 else None
            self.phase = "finished"

    def next_hole(self) -> None:
        if self.phase != "hole_over":
            raise ValueError("El hoyo todavía no termina")
        self.hole += 1
        self._start_hole()

    def totals(self) -> dict[str, int]:
        return {p: sum(h["strokes"][p] for h in self.card) for p in self.players}

    # --- estado para los clientes ---------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        return {
            "name": self.name,
            "phase": self.phase,
            "players": self.players,
            "hole": self.hole,
            "holes": len(self.courses),
            "course": self.course,
            "balls": self.balls,
            "strokes": self.strokes,
            "done": self.done,
            "turn": self.turn,
            "lastShot": self.last_shot,
            "card": self.card,
            "totals": self.totals(),
            "winner": self.winner,
            "maxStrokes": MAX_STROKES,
            "options": {"holes": len(self.courses)},
        }
