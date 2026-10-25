import random

from app.games.common import parse_rounds

# (id, nombre, rasgos). Rasgos: genero, pelo (corto, largo, rizado, recogido,
# calvo), color (negro, castano, rubio, pelirrojo, canoso), ojos (cafes,
# azules, verdes), gafas, sombrero (None, gorra, sombrero), barba, bigote,
# aretes, pecas. "piel" y "fondo" son solo visuales: no hay preguntas sobre la piel.
_RAW = [
    ("camila", "Camila", "mujer", "largo", "castano", "cafes", 0, None, 0, 0, 1, 0, 1, "#F6C9D0"),
    ("valentina", "Valentina", "mujer", "largo", "rubio", "azules", 0, None, 0, 0, 1, 1, 0, "#CDE3F7"),
    ("sofia", "Sofía", "mujer", "rizado", "negro", "cafes", 1, None, 0, 0, 0, 0, 3, "#FBE3B5"),
    ("mariana", "Mariana", "mujer", "corto", "pelirrojo", "verdes", 0, "gorra", 0, 0, 0, 1, 0, "#D5EBD9"),
    ("lucia", "Lucía", "mujer", "recogido", "canoso", "azules", 1, None, 0, 0, 1, 0, 1, "#E6DDF5"),
    ("daniela", "Daniela", "mujer", "largo", "negro", "verdes", 0, "sombrero", 0, 0, 0, 0, 2, "#F9D9C3"),
    ("isabela", "Isabela", "mujer", "recogido", "castano", "cafes", 0, None, 0, 0, 1, 0, 3, "#D9EEF0"),
    ("gabriela", "Gabriela", "mujer", "rizado", "rubio", "verdes", 0, None, 0, 0, 0, 0, 1, "#F6C9D0"),
    ("paula", "Paula", "mujer", "corto", "negro", "cafes", 1, None, 0, 0, 1, 0, 2, "#FBE3B5"),
    ("sara", "Sara", "mujer", "largo", "pelirrojo", "azules", 0, "sombrero", 0, 0, 0, 1, 0, "#D5EBD9"),
    ("juliana", "Juliana", "mujer", "rizado", "castano", "azules", 0, "gorra", 0, 0, 1, 0, 2, "#E6DDF5"),
    ("laura", "Laura", "mujer", "corto", "rubio", "cafes", 1, None, 0, 0, 0, 0, 0, "#F9D9C3"),
    ("santiago", "Santiago", "hombre", "corto", "negro", "cafes", 0, None, 1, 0, 0, 0, 2, "#CDE3F7"),
    ("mateo", "Mateo", "hombre", "rizado", "castano", "verdes", 1, None, 0, 0, 0, 0, 1, "#FBE3B5"),
    ("sebastian", "Sebastián", "hombre", "calvo", "canoso", "azules", 1, None, 0, 1, 0, 0, 0, "#D9EEF0"),
    ("andres", "Andrés", "hombre", "corto", "rubio", "azules", 0, "gorra", 0, 0, 0, 0, 1, "#F6C9D0"),
    ("felipe", "Felipe", "hombre", "corto", "pelirrojo", "verdes", 0, None, 1, 0, 0, 1, 0, "#E6DDF5"),
    ("tomas", "Tomás", "hombre", "largo", "negro", "cafes", 0, "sombrero", 0, 0, 0, 0, 3, "#D5EBD9"),
    ("julian", "Julián", "hombre", "corto", "castano", "cafes", 0, None, 0, 1, 0, 0, 2, "#F9D9C3"),
    ("martin", "Martín", "hombre", "calvo", "negro", "cafes", 1, None, 1, 0, 0, 0, 3, "#CDE3F7"),
    ("david", "David", "hombre", "rizado", "negro", "cafes", 0, "gorra", 0, 0, 1, 0, 2, "#FBE3B5"),
    ("nicolas", "Nicolás", "hombre", "corto", "canoso", "azules", 1, None, 1, 1, 0, 0, 1, "#D9EEF0"),
    ("samuel", "Samuel", "hombre", "recogido", "castano", "verdes", 0, None, 1, 0, 0, 0, 2, "#F6C9D0"),
    ("alejandro", "Alejandro", "hombre", "rizado", "rubio", "azules", 0, "sombrero", 0, 0, 0, 1, 0, "#E6DDF5"),
]
CHARACTERS = {
    cid: {
        "id": cid, "name": name, "genero": genero, "pelo": pelo, "color": color, "ojos": ojos,
        "gafas": bool(gafas), "sombrero": sombrero, "barba": bool(barba), "bigote": bool(bigote),
        "aretes": bool(aretes), "pecas": bool(pecas), "piel": piel, "fondo": fondo,
    }
    for cid, name, genero, pelo, color, ojos, gafas, sombrero, barba, bigote, aretes, pecas, piel, fondo in _RAW
}

# Preguntas que la app responde sola: clave -> (texto, condición)
QUESTIONS = {
    "mujer": ("¿Es mujer?", lambda c: c["genero"] == "mujer"),
    "hombre": ("¿Es hombre?", lambda c: c["genero"] == "hombre"),
    "gafas": ("¿Tiene gafas?", lambda c: c["gafas"]),
    "sombrero": ("¿Tiene sombrero o gorra?", lambda c: c["sombrero"] is not None),
    "barba": ("¿Tiene barba?", lambda c: c["barba"]),
    "bigote": ("¿Tiene bigote?", lambda c: c["bigote"]),
    "aretes": ("¿Tiene aretes?", lambda c: c["aretes"]),
    "pecas": ("¿Tiene pecas?", lambda c: c["pecas"]),
    "calvo": ("¿Es calvo?", lambda c: c["pelo"] == "calvo"),
    "largo": ("¿Tiene el pelo largo?", lambda c: c["pelo"] == "largo"),
    "corto": ("¿Tiene el pelo corto?", lambda c: c["pelo"] == "corto"),
    "rizado": ("¿Tiene el pelo rizado?", lambda c: c["pelo"] == "rizado"),
    "recogido": ("¿Tiene el pelo recogido?", lambda c: c["pelo"] == "recogido"),
    "negro": ("¿Tiene el pelo negro?", lambda c: c["color"] == "negro"),
    "castano": ("¿Tiene el pelo castaño?", lambda c: c["color"] == "castano"),
    "rubio": ("¿Es rubio o rubia?", lambda c: c["color"] == "rubio"),
    "pelirrojo": ("¿Es pelirrojo o pelirroja?", lambda c: c["color"] == "pelirrojo"),
    "canoso": ("¿Tiene canas?", lambda c: c["color"] == "canoso"),
    "ojos_azules": ("¿Tiene los ojos azules?", lambda c: c["ojos"] == "azules"),
    "ojos_verdes": ("¿Tiene los ojos verdes?", lambda c: c["ojos"] == "verdes"),
    "ojos_cafes": ("¿Tiene los ojos cafés?", lambda c: c["ojos"] == "cafes"),
}
BOARD_SIZES = (16, 24)
MAX_QUESTION = 120


class GuessWhoGame:
    name = "guesswho"
    actions = {"gw_flip", "gw_ask", "gw_ask_free", "gw_answer", "gw_guess", "next_round"}

    def __init__(
        self,
        players: list[str],
        board_size: int = 24,
        rounds: int = 3,
        rng: random.Random | None = None,
        timings: dict | None = None,
    ):
        self.players = list(players)
        self.board_size = board_size
        self.total_rounds = rounds
        self.rng = rng or random.Random()
        self.phase = "idle"
        self.round = 0
        self.board: list[str] = []
        self.secrets: dict[str, str] = {}
        self.flipped: dict[str, set[str]] = {}
        self.turn_index = 0
        self.pending: dict | None = None  # pregunta escrita esperando respuesta
        self.log: list[dict] = []
        self.result: dict | None = None
        self.scores: dict[str, int] = {p: 0 for p in self.players}
        self.history: list[dict] = []

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        if len(players) < 2:
            raise ValueError("Adivina quién se juega entre los dos. Esperen a que entre tu pareja.")
        try:
            size = int(options.get("boardSize", 24))
        except (TypeError, ValueError) as exc:
            raise ValueError("Tablero no válido") from exc
        if size not in BOARD_SIZES:
            raise ValueError("El tablero es de 16 o 24 personajes")
        return cls(players, board_size=size, rounds=parse_rounds(options, 3), rng=rng, timings=timings)

    # --- interfaz con la sala -------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase not in ("idle", "finished")

    timer_key = None
    timer_seconds = None

    def start(self) -> None:
        self.start_round()

    def on_timeout(self) -> None:
        pass

    def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "gw_flip":
            self.flip(player, msg.get("id"))
        elif kind == "gw_ask":
            self.ask(player, msg.get("question"))
        elif kind == "gw_ask_free":
            self.ask_free(player, msg.get("text"))
        elif kind == "gw_answer":
            self.answer(player, msg.get("yes"))
        elif kind == "gw_guess":
            self.guess(player, msg.get("id"))
        elif kind == "next_round":
            self.next_round()

    def remove_player(self, player: str) -> None:
        if player in self.players:
            self.players.remove(player)

    # --- ayudas ---------------------------------------------------------
    @property
    def current(self) -> str | None:
        return self.players[self.turn_index % len(self.players)] if self.players else None

    def _other(self, player: str) -> str:
        return next(p for p in self.players if p != player)

    def _require_turn(self, player: str) -> None:
        if self.phase != "playing":
            raise ValueError("La ronda ya terminó")
        if player not in self.players:
            raise ValueError("Esta ronda empezó antes de que entraras")
        if self.pending:
            raise ValueError("Primero hay que responder la pregunta")
        if player != self.current:
            raise ValueError(f"Es el turno de {self.current}")

    def _pass_turn(self) -> None:
        self.turn_index = (self.turn_index + 1) % len(self.players)

    # --- transiciones ---------------------------------------------------
    def start_round(self) -> None:
        if self.phase not in ("idle", "round_over"):
            raise ValueError("No se puede iniciar ronda ahora")
        if self.round >= self.total_rounds:
            raise ValueError("El juego ya terminó")
        self.round += 1
        ids = list(CHARACTERS)
        self.board = sorted(self.rng.sample(ids, self.board_size), key=lambda i: CHARACTERS[i]["name"])
        picks = self.rng.sample(self.board, len(self.players))
        self.secrets = dict(zip(self.players, picks))
        self.flipped = {p: set() for p in self.players}
        self.turn_index = (self.round - 1) % len(self.players)
        self.pending = None
        self.log = []
        self.result = None
        self.phase = "playing"

    def flip(self, player: str, cid) -> None:
        #Bajar o volver a subir un personaje en el tablero propio
        if self.phase != "playing" or player not in self.players:
            return
        if cid not in self.board:
            raise ValueError("Ese personaje no está en el tablero")
        mine = self.flipped[player]
        mine.symmetric_difference_update({cid})

    def ask(self, player: str, key) -> None:
        #Pregunta de la lista: la responde la app con el personaje del otro.
        self._require_turn(player)
        if key not in QUESTIONS:
            raise ValueError("Pregunta no válida")
        text, check = QUESTIONS[key]
        secret = CHARACTERS[self.secrets[self._other(player)]]
        self.log.append({"asker": player, "text": text, "answer": bool(check(secret)), "auto": True})
        self._pass_turn()

    def ask_free(self, player: str, raw) -> None:
        #Pregunta escrita: queda esperando a que la pareja responda.
        self._require_turn(player)
        text = " ".join(str(raw or "").split())[:MAX_QUESTION]
        if len(text) < 3:
            raise ValueError("Escribe la pregunta")
        if not text.endswith("?"):
            text += "?"
        if not text.startswith("¿"):
            text = "¿" + text
        self.pending = {"asker": player, "text": text}

    def answer(self, player: str, yes) -> None:
        if self.phase != "playing" or not self.pending:
            raise ValueError("No hay ninguna pregunta pendiente")
        if player == self.pending["asker"] or player not in self.players:
            raise ValueError("Le toca responder a tu pareja")
        self.log.append({**self.pending, "answer": bool(yes), "auto": False})
        self.pending = None
        self._pass_turn()

    def guess(self, player: str, cid) -> None:
        #Arriesgar: si acierta gana la ronda; si falla, la gana el otro.
        self._require_turn(player)
        if cid not in self.board:
            raise ValueError("Ese personaje no está en el tablero")
        other = self._other(player)
        correct = self.secrets[other] == cid
        winner = player if correct else other
        self.scores[winner] = self.scores.get(winner, 0) + 1
        self.result = {"guesser": player, "guess": cid, "correct": correct, "winner": winner, "questions": len(self.log)}
        self.history.append({"round": self.round, **self.result, "secrets": dict(self.secrets)})
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
        over = self.phase in ("round_over", "finished")
        return {
            "name": self.name,
            "phase": self.phase,
            "round": self.round,
            "totalRounds": self.total_rounds,
            "players": self.players,
            "characters": [CHARACTERS[c] for c in self.board],
            "cast": list(CHARACTERS.values()) if self.phase == "finished" else [],
            # Cada uno conoce solo su personaje; al final se revelan los dos.
            "mySecret": self.secrets.get(viewer) if viewer else None,
            "secrets": self.secrets if over else {},
            "flipped": sorted(self.flipped.get(viewer, set())) if viewer else [],
            "remaining": {p: len(self.board) - len(f) for p, f in self.flipped.items()},
            "turn": self.current if self.phase == "playing" else None,
            "pending": self.pending,
            "log": self.log,
            "questions": [{"key": k, "text": t} for k, (t, _) in QUESTIONS.items()],
            "result": self.result,
            "scores": self.scores,
            "history": self.history if self.phase == "finished" else [],
            "options": {"boardSize": self.board_size, "rounds": self.total_rounds},
        }
