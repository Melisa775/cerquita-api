import random

from app.games.common import DEFAULT_ROUNDS, normalize, parse_rounds
from app.spelling import CHECKED as SPELL_CHECKED
from app.spelling import spelled_ok, suggestion

CATEGORIES = [
    ("nombre", "Nombre"),
    ("apellido", "Apellido"),
    ("ciudad", "Ciudad"),
    ("fruta", "Fruta"),
    ("color", "Color"),
    ("animal", "Animal"),
    ("cosa", "Cosa"),
]
CATEGORY_KEYS = [key for key, _ in CATEGORIES]
# Sin K, Ñ, Q, W, X, Y, Z: casi no hay frutas, colores ni ciudades con ellas.
LETTERS = "ABCDEFGHIJLMNOPRSTUV"
WRITE_SECONDS = 120
GRACE_SECONDS = 2  # margen para que llegue lo último que escribió cada uno
MAX_ANSWER = 40
UNIQUE_POINTS = 100
SHARED_POINTS = 50


class StopGame:
    name = "stop"
    actions = {"stop_answers", "stop_call", "stop_toggle", "next_round"}

    def __init__(
        self,
        players: list[str],
        rounds: int = DEFAULT_ROUNDS,
        rng: random.Random | None = None,
        timings: dict | None = None,
        spelling: bool = True,
    ):
        timings = timings or {}
        self.spelling = spelling
        self.write_seconds = timings.get("write", WRITE_SECONDS)
        self.grace_seconds = timings.get("grace", GRACE_SECONDS)
        self.players = list(players)
        self.total_rounds = rounds
        self.rng = rng or random.Random()
        self.phase = "idle"
        self.round = 0
        self.letter: str | None = None
        self.used_letters: list[str] = []
        self.answers: dict[str, dict[str, str]] = {}
        self.overrides: dict[tuple[str, str], bool] = {}
        self.stopped_by: str | None = None
        self.totals: dict[str, int] = {p: 0 for p in self.players}
        self.sheets: list[dict] = []

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        return cls(
            players,
            rounds=parse_rounds(options),
            rng=rng,
            timings=timings,
            spelling=bool(options.get("spelling", True)),
        )

    # --- interfaz con la sala -------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase not in ("idle", "finished")

    @property
    def timer_key(self):
        return (self.phase, self.round) if self.phase in ("writing", "stopping") else None

    @property
    def timer_seconds(self) -> float | None:
        return {"writing": self.write_seconds, "stopping": self.grace_seconds}.get(self.phase)

    def start(self) -> None:
        self.start_round()

    def on_timeout(self) -> None:
        if self.phase == "writing":
            self.phase = "stopping"  # se acabó el tiempo; nadie cantó Stop
        elif self.phase == "stopping":
            self.phase = "review"

    def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "stop_answers":
            self.save(player, msg.get("answers"))
        elif kind == "stop_call":
            self.call_stop(player, msg.get("answers"))
        elif kind == "stop_toggle":
            self.toggle(msg.get("player"), msg.get("category"))
        elif kind == "next_round":
            self.next_round()

    def remove_player(self, player: str) -> None:
        if player in self.players:
            self.players.remove(player)

    # --- transiciones ---------------------------------------------------
    def start_round(self) -> None:
        if self.phase not in ("idle", "review"):
            raise ValueError("No se puede iniciar ronda ahora")
        if self.round >= self.total_rounds:
            raise ValueError("El juego ya terminó")
        fresh = [c for c in LETTERS if c not in self.used_letters] or list(LETTERS)
        self.letter = self.rng.choice(fresh)
        self.used_letters.append(self.letter)
        self.round += 1
        self.answers = {p: {} for p in self.players}
        self.overrides = {}
        self.stopped_by = None
        self.phase = "writing"

    def save(self, player: str, answers) -> None:
        """Guarda el borrador de un jugador. Se ignora si la ronda ya cerró."""
        if player not in self.players:
            raise ValueError("Jugador desconocido")
        if self.phase not in ("writing", "stopping"):
            return  # llegó tarde: la ronda ya se está revisando
        if not isinstance(answers, dict):
            raise ValueError("Respuestas inválidas")
        self.answers[player] = {
            key: str(answers[key]).strip()[:MAX_ANSWER]
            for key in CATEGORY_KEYS
            if isinstance(answers.get(key), str) and answers[key].strip()
        }

    def call_stop(self, player: str, answers) -> None:
        if self.phase != "writing":
            raise ValueError("Ya no se puede cantar Stop")
        self.save(player, answers)
        if len(self.answers[player]) < len(CATEGORY_KEYS):
            raise ValueError("Llena todas las casillas para cantar ¡Stop!")
        self.stopped_by = player
        self.phase = "stopping"

    def toggle(self, target, category) -> None:
        """Anula una respuesta válida o valida una que el sistema rechazó."""
        if self.phase != "review":
            raise ValueError("Solo se puede corregir durante la revisión")
        if target not in self.players or category not in CATEGORY_KEYS:
            raise ValueError("Casilla inválida")
        if not self.answers.get(target, {}).get(category):
            raise ValueError("Una casilla vacía no se puede validar")
        key = (target, category)
        auto = self._auto_valid(target, category)
        new = not self._valid(target, category)
        if new == auto:
            self.overrides.pop(key, None)
        else:
            self.overrides[key] = new

    def next_round(self) -> None:
        if self.phase != "review":
            raise ValueError("Todavía no hay siguiente ronda")
        results = self.results()
        round_totals = self.round_totals(results)
        for p, pts in round_totals.items():
            self.totals[p] = self.totals.get(p, 0) + pts
        self.sheets.append({"round": self.round, "letter": self.letter, "answers": results, "totals": round_totals})
        if self.round >= self.total_rounds:
            self.phase = "finished"
        else:
            self.start_round()

    # --- puntaje --------------------------------------------------------
    def _issue(self, player: str, category: str) -> str | None:
        """Por qué el sistema no acepta la respuesta: empty, letter o spelling."""
        raw = self.answers.get(player, {}).get(category, "")
        answer = normalize(raw)
        if not answer:
            return "empty"
        if not answer.startswith(normalize(self.letter or "")):
            return "letter"
        if self.spelling and not spelled_ok(category, raw):
            return "spelling"
        return None

    def _auto_valid(self, player: str, category: str) -> bool:
        return self._issue(player, category) is None

    def _valid(self, player: str, category: str) -> bool:
        if not self.answers.get(player, {}).get(category):
            return False
        return self.overrides.get((player, category), self._auto_valid(player, category))

    def results(self) -> dict[str, dict[str, dict]]:
        out: dict[str, dict[str, dict]] = {}
        for p in self.players:
            out[p] = {}
            for cat in CATEGORY_KEYS:
                answer = self.answers.get(p, {}).get(cat, "")
                valid = self._valid(p, cat)
                points = 0
                if valid:
                    mine = normalize(answer)
                    shared = any(
                        q != p and self._valid(q, cat) and normalize(self.answers[q][cat]) == mine
                        for q in self.players
                    )
                    points = SHARED_POINTS if shared else UNIQUE_POINTS
                issue = self._issue(p, cat)
                out[p][cat] = {
                    "answer": answer,
                    "valid": valid,
                    "overridden": (p, cat) in self.overrides,
                    "points": points,
                    "issue": issue,
                    "suggestion": suggestion(cat, answer) if issue == "spelling" else None,
                }
        return out

    @staticmethod
    def round_totals(results: dict[str, dict[str, dict]]) -> dict[str, int]:
        return {p: sum(cell["points"] for cell in cells.values()) for p, cells in results.items()}

    # --- estado para los clientes ---------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        reviewing = self.phase == "review"
        results = self.results() if reviewing else None
        return {
            "name": self.name,
            "phase": self.phase,
            "round": self.round,
            "totalRounds": self.total_rounds,
            "letter": self.letter,
            "categories": [{"key": k, "label": label} for k, label in CATEGORIES],
            # Mientras escriben solo se informa cuántas casillas lleva cada uno.
            "filled": {p: len(self.answers.get(p, {})) for p in self.players},
            "stoppedBy": self.stopped_by,
            "results": results,
            "roundTotals": self.round_totals(results) if results else None,
            "sheets": self.sheets,
            "totals": self.totals,
            "writeSeconds": self.write_seconds,
            "graceSeconds": self.grace_seconds,
            "points": {"unique": UNIQUE_POINTS, "shared": SHARED_POINTS},
            "spellChecked": sorted(SPELL_CHECKED) if self.spelling else [],
            "options": {"rounds": self.total_rounds, "spelling": self.spelling},
        }
