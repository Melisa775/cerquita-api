"""Stop contrarreloj (estilo Too Late).

Hay un tablero de letras y una categoría. Por turnos, cada jugador dice en
voz alta una palabra de la categoría y toca la letra con la que empieza:
esa letra se apaga y el reloj vuelve a empezar para el otro. Si a alguien
se le acaba el tiempo, pierde la ronda y el otro gana un punto. Si entre
los dos apagan todas las letras, lo lograron y ganan un punto cada uno.

Flujo de cada ronda:
  ready      -> se muestra la categoría; se puede cambiar antes de empezar
  playing    -> turnos contrarreloj
  round_over -> se acabó el tiempo o completaron el tablero
Tras la última ronda la fase es "finished".
"""

import random

from app.games.common import DEFAULT_ROUNDS, parse_rounds

ALPHABET = "ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"
DEFAULT_OFF = set("KÑQWXYZ")
DEFAULT_LETTERS = [c for c in ALPHABET if c not in DEFAULT_OFF]
MIN_LETTERS = 5
TURN_CHOICES = (5, 10, 15, 20)
DEFAULT_TURN = 10

CATEGORIES = [
    # Las clásicas
    "Acciones",
    "Lugares",
    "Objetos",
    "Nombres de mujer",
    "Nombres de hombre",
    "Cosas que encuentras en una habitación",
    "Cosas que encuentras en un baño",
    "Series o películas",
    # Para la casa y el día a día
    "Cosas que hay en la nevera",
    "Cosas de la cocina",
    "Cosas que hay en un supermercado",
    "Cosas que se pierden fácilmente",
    "Cosas que caben en un bolsillo",
    "Cosas que se pueden romper",
    "Cosas redondas",
    "Cosas que hacen ruido",
    "Cosas pegajosas",
    "Cosas que pican",
    "Cosas que huelen rico",
    "Cosas que huelen feo",
    "Cosas que dan miedo",
    "Cosas que hay en el cielo",
    "Cosas que hay en una playa",
    "Cosas de una fiesta",
    "Cosas que llevarías a una isla desierta",
    "Cosas que empacarías para un viaje",
    "Cosas que haces un domingo",
    "Excusas para no contestar el teléfono",
    # Para parejas
    "Planes para una cita",
    "Regalos para tu pareja",
    "Apodos cariñosos",
    "Cosas que dirías en una primera cita",
    "Lugares a los que quieren viajar juntos",
    "Cosas que extrañas cuando están lejos",
    # Cultura y comida
    "Comidas colombianas",
    "Postres",
    "Bebidas",
    "Frutas y verduras",
    "Marcas",
    "Cantantes o bandas",
    "Canciones",
    "Personajes de dibujos animados",
    "Superhéroes o villanos",
    "Videojuegos o juegos de mesa",
    "Profesiones",
    "Deportes",
    "Países",
    "Animales",
    "Partes del cuerpo",
    "Instrumentos musicales",
    "Cosas del colegio",
]


class TooLateGame:
    name = "toolate"
    actions = {"tl_reroll", "tl_begin", "tl_pick", "tl_undo", "next_round"}

    def __init__(
        self,
        players: list[str],
        letters: list[str] | None = None,
        turn_seconds: int = DEFAULT_TURN,
        rounds: int = DEFAULT_ROUNDS,
        rng: random.Random | None = None,
        timings: dict | None = None,
    ):
        timings = timings or {}
        self.players = list(players)
        self.letters = list(letters or DEFAULT_LETTERS)
        self.turn_seconds = turn_seconds
        self.turn_timer = timings.get("turn", turn_seconds)
        self.total_rounds = rounds
        self.rng = rng or random.Random()
        self.phase = "idle"
        self.round = 0
        self.category: str | None = None
        self.used_categories: list[str] = []
        self.used: list[dict] = []  # [{"letter": "M", "player": "Ana"}]
        self.turn_index = 0
        self.turn_id = 0  # cambia en cada turno para reiniciar el reloj
        self.result: dict | None = None
        self.scores: dict[str, int] = {p: 0 for p in self.players}
        self.history: list[dict] = []

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        raw = options.get("letters", DEFAULT_LETTERS)
        if not isinstance(raw, list) or not all(isinstance(c, str) for c in raw):
            raise ValueError("Letras inválidas")
        chosen = {c.strip().upper() for c in raw}
        letters = [c for c in ALPHABET if c in chosen]  # orden del alfabeto, sin repetidas
        if len(letters) < MIN_LETTERS:
            raise ValueError(f"Deja al menos {MIN_LETTERS} letras activas")
        try:
            turn = int(options.get("turnSeconds", DEFAULT_TURN))
        except (TypeError, ValueError) as exc:
            raise ValueError("Tiempo por turno no válido") from exc
        if turn not in TURN_CHOICES:
            raise ValueError("Tiempo por turno no válido")
        return cls(players, letters=letters, turn_seconds=turn, rounds=parse_rounds(options), rng=rng, timings=timings)

    # --- interfaz con la sala -------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase not in ("idle", "finished")

    @property
    def timer_key(self):
        return ("turn", self.turn_id) if self.phase == "playing" else None

    @property
    def timer_seconds(self) -> float | None:
        return self.turn_timer if self.phase == "playing" else None

    @property
    def current(self) -> str | None:
        return self.players[self.turn_index % len(self.players)] if self.players else None

    def start(self) -> None:
        self.start_round()

    def on_timeout(self) -> None:
        if self.phase != "playing":
            return
        loser = self.current
        for p in self.players:
            if p != loser:
                self.scores[p] = self.scores.get(p, 0) + 1
        self._end_round({"type": "timeout", "loser": loser})

    def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "tl_reroll":
            self.reroll()
        elif kind == "tl_begin":
            self.begin()
        elif kind == "tl_pick":
            self.pick(player, msg.get("letter"))
        elif kind == "tl_undo":
            self.undo()
        elif kind == "next_round":
            self.next_round()

    def remove_player(self, player: str) -> None:
        if player in self.players:
            self.players.remove(player)

    # --- transiciones ---------------------------------------------------
    def _new_category(self) -> str:
        fresh = [c for c in CATEGORIES if c not in self.used_categories and c != self.category]
        if not fresh:
            self.used_categories = []
            fresh = [c for c in CATEGORIES if c != self.category]
        choice = self.rng.choice(fresh)
        self.used_categories.append(choice)
        return choice

    def start_round(self) -> None:
        if self.phase not in ("idle", "round_over"):
            raise ValueError("No se puede iniciar ronda ahora")
        if self.round >= self.total_rounds:
            raise ValueError("El juego ya terminó")
        self.round += 1
        self.category = self._new_category()
        self.used = []
        self.result = None
        # Empieza cada ronda alguien distinto
        self.turn_index = (self.round - 1) % max(1, len(self.players))
        self.phase = "ready"

    def reroll(self) -> None:
        if self.phase != "ready":
            raise ValueError("La categoría solo se cambia antes de empezar")
        self.category = self._new_category()

    def begin(self) -> None:
        if self.phase != "ready":
            raise ValueError("La ronda ya empezó")
        self.phase = "playing"
        self.turn_id += 1

    def pick(self, player: str, letter) -> None:
        if self.phase != "playing":
            raise ValueError("La ronda no está en juego")
        if player != self.current:
            raise ValueError("No es tu turno")
        letter = str(letter or "").strip().upper()
        if letter not in self.letters:
            raise ValueError("Esa letra no está en el tablero")
        if any(u["letter"] == letter for u in self.used):
            raise ValueError("Esa letra ya salió")
        self.used.append({"letter": letter, "player": player})
        if len(self.used) == len(self.letters):
            for p in self.players:
                self.scores[p] = self.scores.get(p, 0) + 1
            self._end_round({"type": "completed"})
            return
        self.turn_index = (self.turn_index + 1) % len(self.players)
        self.turn_id += 1

    def undo(self) -> None:
        """¡No vale! Devuelve la última letra y el turno a quien la tocó."""
        if self.phase != "playing":
            raise ValueError("La ronda no está en juego")
        if not self.used:
            raise ValueError("Todavía no han tocado ninguna letra")
        last = self.used.pop()
        if last["player"] in self.players:
            self.turn_index = self.players.index(last["player"])
        self.turn_id += 1

    def _end_round(self, result: dict) -> None:
        self.result = result
        self.history.append({
            "round": self.round,
            "category": self.category,
            "letters": len(self.used),
            "result": result,
        })
        self.phase = "round_over"

    def next_round(self) -> None:
        if self.phase != "round_over":
            raise ValueError("Todavía no hay siguiente ronda")
        if self.round >= self.total_rounds:
            self.phase = "finished"
        else:
            self.start_round()

    # --- estado para los clientes ---------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        return {
            "name": self.name,
            "phase": self.phase,
            "round": self.round,
            "totalRounds": self.total_rounds,
            "category": self.category,
            "alphabet": list(ALPHABET),
            "letters": self.letters,
            "used": self.used,
            "turn": self.current if self.phase in ("ready", "playing") else None,
            "turnId": self.turn_id,
            "turnSeconds": self.turn_timer,
            "result": self.result,
            "scores": self.scores,
            "history": self.history,
            "options": {"rounds": self.total_rounds, "letters": self.letters, "turnSeconds": self.turn_seconds},
        }
