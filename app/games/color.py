"""Juego "Color de memoria".

Flujo de cada ronda:
  memorize -> se muestra el color unos segundos
  guess    -> cada jugador recrea el color de memoria
  reveal   -> se muestran el color real, los intentos y los puntajes
Tras la última ronda la fase es "finished".

La clase es lógica pura (sin red ni temporizadores) para poder probarla;
la sala se encarga de los tiempos y de transmitir el estado.
"""

import random

from app.colors import HSB, random_color, score

MEMORIZE_SECONDS = 5
GUESS_SECONDS = 30
DEFAULT_ROUNDS = 5


class ColorGame:
    name = "color"

    def __init__(self, players: list[str], rounds: int = DEFAULT_ROUNDS, rng: random.Random | None = None):
        self.players = list(players)
        self.total_rounds = rounds
        self.rng = rng or random.Random()
        self.round = 0
        self.phase = "idle"
        self.target: HSB | None = None
        self.guesses: dict[str, HSB] = {}
        self.round_scores: dict[str, float] = {}
        self.totals: dict[str, float] = {p: 0.0 for p in self.players}
        self.history: list[dict] = []

    # --- transiciones -------------------------------------------------
    def start_round(self) -> None:
        if self.phase not in ("idle", "reveal"):
            raise ValueError("No se puede iniciar ronda ahora")
        if self.round >= self.total_rounds:
            raise ValueError("El juego ya terminó")
        self.round += 1
        self.phase = "memorize"
        self.target = random_color(self.rng)
        self.guesses = {}
        self.round_scores = {}

    def begin_guess(self) -> None:
        if self.phase != "memorize":
            raise ValueError("No se está memorizando")
        self.phase = "guess"

    def submit(self, player: str, color: HSB) -> bool:
        """Registra un intento. Devuelve True si ya respondieron todos."""
        if self.phase != "guess":
            raise ValueError("No es momento de adivinar")
        if player not in self.players:
            raise ValueError("Jugador desconocido")
        if player in self.guesses:
            raise ValueError("Ya enviaste tu color")
        self.guesses[player] = color
        return self.all_submitted()

    def all_submitted(self) -> bool:
        return all(p in self.guesses for p in self.players)

    def reveal(self) -> None:
        if self.phase != "guess":
            raise ValueError("No hay nada que revelar")
        assert self.target is not None
        for p in self.players:
            pts = score(self.target, self.guesses[p]) if p in self.guesses else 0.0
            self.round_scores[p] = pts
            self.totals[p] = round(self.totals[p] + pts, 2)
        self.history.append({
            "round": self.round,
            "target": self.target.to_dict(),
            "guesses": {p: g.to_dict() for p, g in self.guesses.items()},
            "scores": dict(self.round_scores),
        })
        self.phase = "finished" if self.round >= self.total_rounds else "reveal"

    def remove_player(self, player: str) -> None:
        if player in self.players:
            self.players.remove(player)

    # --- estado para los clientes ---------------------------------------
    def snapshot(self) -> dict:
        show_target = self.phase in ("memorize", "reveal", "finished")
        show_guesses = self.phase in ("reveal", "finished")
        return {
            "name": self.name,
            "phase": self.phase,
            "round": self.round,
            "totalRounds": self.total_rounds,
            "target": self.target.to_dict() if (show_target and self.target) else None,
            # Durante "guess" solo se revela QUIÉN ya respondió, no su color.
            "submitted": sorted(self.guesses),
            "guesses": {p: g.to_dict() for p, g in self.guesses.items()} if show_guesses else {},
            "roundScores": self.round_scores if show_guesses else {},
            "totals": self.totals,
            "history": self.history if self.phase == "finished" else [],
            "memorizeSeconds": MEMORIZE_SECONDS,
            "guessSeconds": GUESS_SECONDS,
        }
