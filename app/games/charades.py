"""Charades ("Caras y gestos").

Players take turns: one acts and the other guesses out loud over the video
call. The actor sees a card (a word or phrase and its category) and acts it
out against the clock without speaking. When the partner gets it, the actor
taps "¡Adivinó!"; if it is too hard, "Pasar". Each guessed card is a point
for the actor.

Turn flow:
  ready     -> the actor gets ready and taps start
  acting    -> the clock runs
  turn_over -> summary of guessed and passed cards
After the last turn the phase is "finished".
"""

import random
import re
from functools import cache
from pathlib import Path

from app.games.common import parse_rounds

DATA = Path(__file__).resolve().parents[1] / "data" / "charades.txt"
SECONDS_CHOICES = (60, 90, 120)
LEVELS = ("easy", "hard", "mixed")
HEADER = re.compile(r"^##\s*(.+?)\s*\((easy|hard)\)\s*$", re.IGNORECASE)


@cache
def deck() -> list[dict]:
    """Every card: [{"text", "category", "level"}]."""
    cards = []
    category = level = None
    for line in DATA.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("# "):
            continue
        header = HEADER.match(line)
        if header:
            category = header.group(1)
            level = header.group(2).lower()
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
        level: str = "mixed",
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
        self.pool = [c for c in all_cards if level == "mixed" or c["level"] == level]
        self.rng.shuffle(self.pool)
        self.phase = "idle"
        self.turn = 0
        self.card: dict | None = None
        self.played: list[dict] = []  # cards of this turn: {..., "result": "hit"|"pass"}
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
        level = options.get("level", "mixed")
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

    # --- room interface -------------------------------------------------
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

    # --- turns ----------------------------------------------------------
    def _draw(self) -> dict:
        if not self.pool:  # deck ran out: reshuffle
            all_cards = deck()
            self.pool = [c for c in all_cards if self.level == "mixed" or c["level"] == self.level]
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

    # --- state for clients ----------------------------------------------
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
            # The guesser sees the category (if enabled), never the card.
            "card": card,
            # Guessed cards are shown live; passed ones only when the turn ends.
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
