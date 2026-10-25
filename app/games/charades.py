"""Caras y gestos.

Por turnos, uno actúa y el otro adivina en voz alta por la videollamada.
Quien actúa ve una carta (una palabra o frase y su categoría) y, contra el
reloj, la representa sin hablar. Cuando la pareja la adivina, toca
"¡Adivinó!"; si está muy difícil, "Pasar". Cada carta adivinada suma un
punto para quien actuó.

Flujo de cada turno:
  ready     -> quien actúa se prepara y le da a empezar
  acting    -> corre el reloj
  turn_over -> resumen de cartas adivinadas y pasadas
Tras el último turno la fase es "finished".
"""

import random
import re
from functools import cache
from pathlib import Path

from app.games.common import parse_rounds

DATA = Path(__file__).resolve().parents[1] / "data" / "caras_gestos.txt"
SECONDS_CHOICES = (60, 90, 120)
LEVELS = ("facil", "dificil", "mezcla")
HEADER = re.compile(r"^##\s*(.+?)\s*\((fácil|difícil)\)\s*$", re.IGNORECASE)


@cache
def deck() -> list[dict]:
    """Todas las cartas: [{"text", "category", "level"}]."""
    cards = []
    category = level = None
    for line in DATA.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("# "):
            continue
        header = HEADER.match(line)
        if header:
            category = header.group(1)
            level = "facil" if header.group(2).lower().startswith("f") else "dificil"
        elif category:
            cards.append({"text": line, "category": category, "level": level})
    return cards


class CharadesGame:
    name = "charades"
    actions = {"cg_start", "cg_hit", "cg_pass", "next_round"}

    def __init__(
        self,
        players: list[str],
        seconds: int = 90,
        level: str = "mezcla",
        show_category: bool = True,
        rounds: int = 2,
        rng: random.Random | None = None,
        timings: dict | None = None,
        cards: list[dict] | None = None,
    ):
        timings = timings or {}
        self.players = list(players)
        self.seconds = seconds
        self.act_seconds = timings.get("act", seconds)
        self.level = level
        self.show_category = show_category
        self.total_rounds = rounds
        self.rng = rng or random.Random()
        all_cards = cards or deck()
        self.pool = [c for c in all_cards if level == "mezcla" or c["level"] == level]
        self.rng.shuffle(self.pool)
        self.phase = "idle"
        self.turn = 0
        self.card: dict | None = None
        self.played: list[dict] = []  # cartas del turno: {..., "result": "hit"|"pass"}
        self.scores: dict[str, int] = {p: 0 for p in self.players}
        self.history: list[dict] = []

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        if len(players) < 2:
            raise ValueError("Caras y gestos se juega entre los dos. Esperen a que entre tu pareja.")
        try:
            seconds = int(options.get("seconds", 90))
        except (TypeError, ValueError) as exc:
            raise ValueError("Tiempo no válido") from exc
        if seconds not in SECONDS_CHOICES:
            raise ValueError("Elige 60, 90 o 120 segundos")
        level = options.get("level", "mezcla")
        if level not in LEVELS:
            raise ValueError("Dificultad no válida")
        return cls(
            players,
            seconds=seconds,
            level=level,
            show_category=bool(options.get("showCategory", True)),
            rounds=parse_rounds(options, 2),
            rng=rng,
            timings=timings,
        )

    # --- interfaz con la sala -------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase not in ("idle", "finished")

    @property
    def total_turns(self) -> int:
        return self.total_rounds * len(self.players)

    @property
    def actor(self) -> str | None:
        return self.players[(self.turn - 1) % len(self.players)] if self.players and self.turn else None

    @property
    def timer_key(self):
        return ("acting", self.turn) if self.phase == "acting" else None

    @property
    def timer_seconds(self) -> float | None:
        return self.act_seconds if self.phase == "acting" else None

    def start(self) -> None:
        self._start_turn()

    def on_timeout(self) -> None:
        if self.phase == "acting":
            self._end_turn()

    def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "cg_start":
            self.begin(player)
        elif kind == "cg_hit":
            self.resolve(player, "hit")
        elif kind == "cg_pass":
            self.resolve(player, "pass")
        elif kind == "next_round":
            self.next_round()

    def remove_player(self, player: str) -> None:
        if player in self.players:
            self.players.remove(player)

    # --- turnos ---------------------------------------------------------
    def _draw(self) -> dict:
        if not self.pool:  # se acabó el mazo: se baraja de nuevo
            all_cards = deck()
            self.pool = [c for c in all_cards if self.level == "mezcla" or c["level"] == self.level]
            self.rng.shuffle(self.pool)
        return self.pool.pop()

    def _start_turn(self) -> None:
        self.turn += 1
        self.card = None
        self.played = []
        self.phase = "ready"

    def begin(self, player: str) -> None:
        if self.phase != "ready":
            raise ValueError("El turno ya empezó")
        if player != self.actor:
            raise ValueError(f"Le toca actuar a {self.actor}")
        self.card = self._draw()
        self.phase = "acting"

    def resolve(self, player: str, result: str) -> None:
        if self.phase != "acting":
            raise ValueError("No hay ninguna carta en juego")
        if player != self.actor:
            raise ValueError("Solo quien actúa marca las cartas")
        self.played.append({**self.card, "result": result})
        if result == "hit":
            self.scores[player] = self.scores.get(player, 0) + 1
        self.card = self._draw()

    def _end_turn(self) -> None:
        hits = sum(1 for c in self.played if c["result"] == "hit")
        self.history.append({"turn": self.turn, "actor": self.actor, "hits": hits, "cards": self.played})
        self.card = None
        self.phase = "turn_over"

    def next_round(self) -> None:
        if self.phase != "turn_over":
            raise ValueError("Todavía no hay siguiente turno")
        if self.turn >= self.total_turns:
            self.phase = "finished"
        else:
            self._start_turn()

    # --- estado para los clientes ---------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        is_actor = viewer is not None and viewer == self.actor
        over = self.phase in ("turn_over", "finished")
        card = None
        if self.card and self.phase == "acting":
            if is_actor:
                card = self.card
            elif self.show_category:
                card = {"text": None, "category": self.card["category"], "level": self.card["level"]}
        return {
            "name": self.name,
            "phase": self.phase,
            "turn": self.turn,
            "totalTurns": self.total_turns,
            "players": self.players,
            "actor": self.actor,
            # Quien adivina ve la categoría (si está activado), nunca la carta.
            "card": card,
            # Las adivinadas se ven en vivo; las pasadas, solo al terminar el turno.
            "played": [c for c in self.played if over or is_actor or c["result"] == "hit"],
            "hits": sum(1 for c in self.played if c["result"] == "hit"),
            "seconds": self.act_seconds,
            "scores": self.scores,
            "history": self.history if self.phase == "finished" else [],
            "options": {
                "seconds": self.seconds,
                "level": self.level,
                "showCategory": self.show_category,
                "rounds": self.total_rounds,
            },
        }
