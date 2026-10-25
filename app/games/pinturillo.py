import random
import re
import time
from functools import cache
from pathlib import Path

from app.games.common import normalize, parse_rounds

DATA = Path(__file__).resolve().parents[1] / "data" / "pinturillo_palabras.txt"
DRAW_CHOICES = (60, 90, 120)
CHOOSE_SECONDS = 15
TURN_OVER_SECONDS = 6
HINT_AT = (0.5, 0.75)  # fracciones del tiempo en que se destapa una letra
CANVAS = 1000  # coordenadas lógicas del lienzo: 0..1000 x 0..750
MAX_STROKES = 2000
MAX_POINTS = 400  # por mensaje
COLORS = re.compile(r"^#[0-9a-fA-F]{6}$")


@cache
def word_list() -> list[str]:
    lines = DATA.read_text(encoding="utf-8").splitlines()
    return [line.strip().lower() for line in lines if line.strip() and not line.startswith("#")]


def _plain(text: str) -> str:
    return normalize(text).replace(" ", "")


def _levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _points(raw) -> list[list[int]]:
    if not isinstance(raw, list) or len(raw) > MAX_POINTS:
        raise ValueError("Trazo inválido")
    out = []
    for p in raw:
        try:
            x, y = int(p[0]), int(p[1])
        except (TypeError, ValueError, IndexError) as exc:
            raise ValueError("Trazo inválido") from exc
        out.append([min(max(x, 0), CANVAS), min(max(y, 0), CANVAS * 3 // 4)])
    return out


class PinturilloGame:
    name = "pinturillo"
    actions = {"pz_choose", "pz_stroke", "pz_points", "pz_undo", "pz_clear", "pz_guess", "next_round"}

    def __init__(
        self,
        players: list[str],
        draw_seconds: int = 90,
        rounds: int = 2,
        rng: random.Random | None = None,
        timings: dict | None = None,
        clock=time.monotonic,
        words: list[str] | None = None,
    ):
        timings = timings or {}
        self.players = list(players)
        self.draw_seconds = timings.get("draw", draw_seconds)
        self.choose_seconds = timings.get("choose", CHOOSE_SECONDS)
        self.turn_over_seconds = timings.get("turn_over", TURN_OVER_SECONDS)
        self.total_rounds = rounds
        self.rng = rng or random.Random()
        self.clock = clock
        self.words = words or word_list()
        self.used: set[str] = set()
        self.phase = "idle"
        self.turn = 0  # número de turno, desde 1
        self.choices: list[str] = []
        self.word = ""
        self.revealed: set[int] = set()  # posiciones destapadas como pista
        self.stage = 0  # 0 antes de la primera pista, 1 después, 2 después de la segunda
        self.strokes: list[dict] = []
        self.guesses: list[dict] = []
        self.phase_started = 0.0
        self.result: dict | None = None
        self.scores: dict[str, int] = {p: 0 for p in self.players}
        self.history: list[dict] = []

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        if len(players) < 2:
            raise ValueError("El Pinturillo se juega entre los dos. Esperen a que entre tu pareja.")
        try:
            seconds = int(options.get("drawSeconds", 90))
        except (TypeError, ValueError) as exc:
            raise ValueError("Tiempo no válido") from exc
        if seconds not in DRAW_CHOICES:
            raise ValueError("Elige 60, 90 o 120 segundos")
        return cls(players, draw_seconds=seconds, rounds=parse_rounds(options, 2), rng=rng, timings=timings)

    # --- interfaz con la sala -------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase not in ("idle", "finished")

    @property
    def total_turns(self) -> int:
        return self.total_rounds * len(self.players)

    @property
    def drawer(self) -> str | None:
        return self.players[(self.turn - 1) % len(self.players)] if self.players and self.turn else None

    @property
    def timer_key(self):
        if self.phase == "drawing":
            return ("drawing", self.turn, self.stage)
        if self.phase in ("choosing", "turn_over"):
            return (self.phase, self.turn)
        return None

    @property
    def timer_seconds(self) -> float | None:
        if self.phase == "choosing":
            return self.choose_seconds
        if self.phase == "turn_over":
            return self.turn_over_seconds
        if self.phase == "drawing":
            # El turno se parte en tramos: hasta la primera pista, la segunda y el final.
            marks = [0, *HINT_AT, 1]
            return self.draw_seconds * (marks[self.stage + 1] - marks[self.stage])
        return None

    def start(self) -> None:
        self._start_turn()

    def on_timeout(self) -> None:
        if self.phase == "choosing":
            self.choose(self.drawer, self.rng.randrange(len(self.choices)))
        elif self.phase == "drawing":
            if self.stage < len(HINT_AT):
                self._reveal_letter()
                self.stage += 1
            else:
                self._end_turn(guesser=None)
        elif self.phase == "turn_over":
            self.next_round()

    def handle(self, player: str, msg: dict):
        kind = msg.get("type")
        if kind == "pz_choose":
            self.choose(player, msg.get("index"))
        elif kind == "pz_stroke":
            return self.add_stroke(player, msg)
        elif kind == "pz_points":
            return self.add_points(player, msg)
        elif kind == "pz_undo":
            return self.undo(player)
        elif kind == "pz_clear":
            return self.clear(player)
        elif kind == "pz_guess":
            return self.guess(player, msg.get("text"))
        elif kind == "next_round":
            self.next_round()
        return None

    def remove_player(self, player: str) -> None:
        if player in self.players:
            self.players.remove(player)

    # --- turnos ---------------------------------------------------------
    def _start_turn(self) -> None:
        self.turn += 1
        fresh = [w for w in self.words if w not in self.used] or list(self.words)
        self.choices = self.rng.sample(fresh, min(3, len(fresh)))
        self.word = ""
        self.revealed = set()
        self.stage = 0
        self.strokes = []
        self.guesses = []
        self.result = None
        self.phase = "choosing"
        self.phase_started = self.clock()

    def choose(self, player: str, index) -> None:
        if self.phase != "choosing":
            raise ValueError("Ya se eligió la palabra")
        if player != self.drawer:
            raise ValueError("La palabra la elige quien dibuja")
        try:
            word = self.choices[int(index)]
        except (TypeError, ValueError, IndexError) as exc:
            raise ValueError("Elige una de las tres palabras") from exc
        self.word = word
        self.used.add(word)
        self.phase = "drawing"
        self.phase_started = self.clock()

    def _reveal_letter(self) -> None:
        hidden = [i for i, ch in enumerate(self.word) if ch != " " and i not in self.revealed]
        if len(hidden) > 2:  # nunca se destapa casi toda la palabra
            self.revealed.add(self.rng.choice(hidden))

    def _require_drawer(self, player: str) -> None:
        if self.phase != "drawing" or player != self.drawer:
            raise ValueError("Ahora no te toca dibujar")

    # --- dibujo ---------------------------------------------------------
    def add_stroke(self, player: str, msg: dict) -> dict:
        self._require_drawer(player)
        if len(self.strokes) >= MAX_STROKES:
            raise ValueError("El dibujo ya tiene demasiados trazos. Borra un poco.")
        color = str(msg.get("color", ""))
        if not COLORS.match(color):
            raise ValueError("Color inválido")
        try:
            size = min(max(int(msg.get("size", 6)), 1), 60)
        except (TypeError, ValueError) as exc:
            raise ValueError("Grosor inválido") from exc
        stroke = {"id": str(msg.get("id", ""))[:24], "color": color, "size": size, "points": _points(msg.get("points"))}
        self.strokes.append(stroke)
        return {"relay": {"kind": "stroke", "stroke": stroke}}

    def add_points(self, player: str, msg: dict) -> dict:
        self._require_drawer(player)
        sid = str(msg.get("id", ""))[:24]
        points = _points(msg.get("points"))
        for stroke in reversed(self.strokes):
            if stroke["id"] == sid:
                stroke["points"].extend(points)
                return {"relay": {"kind": "points", "id": sid, "points": points}}
        raise ValueError("Trazo desconocido")

    def undo(self, player: str) -> dict:
        self._require_drawer(player)
        if self.strokes:
            self.strokes.pop()
        return {"relay": {"kind": "undo"}}

    def clear(self, player: str) -> dict:
        self._require_drawer(player)
        self.strokes = []
        return {"relay": {"kind": "clear"}}

    # --- adivinar -------------------------------------------------------
    def guess(self, player: str, raw) -> dict | None:
        if self.phase != "drawing":
            raise ValueError("Ahora no se puede adivinar")
        if player == self.drawer:
            raise ValueError("Tú estás dibujando: no puedes adivinar")
        if player not in self.players:
            raise ValueError("Esta ronda empezó antes de que entraras")
        text = " ".join(str(raw or "").split())[:40]
        if not text:
            raise ValueError("Escribe tu intento")
        attempt, answer = _plain(text), _plain(self.word)
        if attempt == answer:
            self.guesses.append({"player": player, "text": None, "correct": True})
            self._end_turn(guesser=player)
            return None
        self.guesses.append({"player": player, "text": text, "correct": False})
        if len(answer) >= 4 and _levenshtein(attempt, answer) == 1:
            # El intento queda en el historial y solo quien lo escribió ve el aviso.
            return {"notice": f"¡Casi! «{text}» está muy cerca"}
        return None

    def _end_turn(self, guesser: str | None) -> None:
        points = {}
        if guesser:
            left = max(0.0, self.draw_seconds - (self.clock() - self.phase_started))
            points[guesser] = 50 + round(50 * left / self.draw_seconds)
            points[self.drawer] = 50
            for p, n in points.items():
                self.scores[p] = self.scores.get(p, 0) + n
        self.result = {"word": self.word, "guesser": guesser, "drawer": self.drawer, "points": points}
        self.history.append({"turn": self.turn, **self.result, "strokes": self.strokes})
        self.phase = "turn_over"
        self.phase_started = self.clock()

    def next_round(self) -> None:
        if self.phase != "turn_over":
            raise ValueError("Todavía no hay siguiente turno")
        if self.turn >= self.total_turns:
            self.phase = "finished"
        else:
            self._start_turn()

    # --- estado para los clientes ---------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        is_drawer = viewer is not None and viewer == self.drawer
        over = self.phase in ("turn_over", "finished")
        mask = [ch if (ch == " " or i in self.revealed or over or is_drawer) else None for i, ch in enumerate(self.word)]
        elapsed = self.clock() - self.phase_started
        ends_in = None
        if self.phase == "drawing":
            ends_in = max(0, int((self.draw_seconds - elapsed) * 1000))
        elif self.phase in ("choosing", "turn_over"):
            ends_in = max(0, int((self.timer_seconds - elapsed) * 1000))
        return {
            "name": self.name,
            "phase": self.phase,
            "turn": self.turn,
            "totalTurns": self.total_turns,
            "round": (self.turn - 1) // max(1, len(self.players)) + 1 if self.turn else 0,
            "totalRounds": self.total_rounds,
            "players": self.players,
            "drawer": self.drawer,
            # Las tres opciones solo las ve quien dibuja.
            "choices": self.choices if is_drawer and self.phase == "choosing" else [],
            "mask": mask,
            "strokes": self.strokes,
            "guesses": self.guesses,
            "turnEndsInMs": ends_in,
            "drawSeconds": self.draw_seconds,
            "result": self.result,
            "scores": self.scores,
            "history": [{k: v for k, v in h.items() if k != "strokes"} for h in self.history] if self.phase == "finished" else [],
            "drawings": [h["strokes"] for h in self.history] if self.phase == "finished" else [],
            "options": {"drawSeconds": self.draw_seconds, "rounds": self.total_rounds},
        }
