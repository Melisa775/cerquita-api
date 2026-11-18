import random

from app.games.common import parse_rounds

# (id, name, traits). Traits: gender, hair (short, long, curly, updo, bald),
# hair color (black, brown, blond, red, gray), eyes (brown, blue, green),
# glasses, hat (None, cap, hat), beard, mustache, earrings, freckles. "skin" and
# "background" are only visual: there are no questions about skin.
_RAW = [
    ("camila", "Camila", "woman", "long", "brown", "brown", 0, None, 0, 0, 1, 0, 1, "#F6C9D0"),
    ("valentina", "Valentina", "woman", "long", "blond", "blue", 0, None, 0, 0, 1, 1, 0, "#CDE3F7"),
    ("sofia", "Sofía", "woman", "curly", "black", "brown", 1, None, 0, 0, 0, 0, 3, "#FBE3B5"),
    ("mariana", "Mariana", "woman", "short", "red", "green", 0, "cap", 0, 0, 0, 1, 0, "#D5EBD9"),
    ("lucia", "Lucía", "woman", "updo", "gray", "blue", 1, None, 0, 0, 1, 0, 1, "#E6DDF5"),
    ("daniela", "Daniela", "woman", "long", "black", "green", 0, "hat", 0, 0, 0, 0, 2, "#F9D9C3"),
    ("isabela", "Isabela", "woman", "updo", "brown", "brown", 0, None, 0, 0, 1, 0, 3, "#D9EEF0"),
    ("gabriela", "Gabriela", "woman", "curly", "blond", "green", 0, None, 0, 0, 0, 0, 1, "#F6C9D0"),
    ("paula", "Paula", "woman", "short", "black", "brown", 1, None, 0, 0, 1, 0, 2, "#FBE3B5"),
    ("sara", "Sara", "woman", "long", "red", "blue", 0, "hat", 0, 0, 0, 1, 0, "#D5EBD9"),
    ("juliana", "Juliana", "woman", "curly", "brown", "blue", 0, "cap", 0, 0, 1, 0, 2, "#E6DDF5"),
    ("laura", "Laura", "woman", "short", "blond", "brown", 1, None, 0, 0, 0, 0, 0, "#F9D9C3"),
    ("santiago", "Santiago", "man", "short", "black", "brown", 0, None, 1, 0, 0, 0, 2, "#CDE3F7"),
    ("mateo", "Mateo", "man", "curly", "brown", "green", 1, None, 0, 0, 0, 0, 1, "#FBE3B5"),
    ("sebastian", "Sebastián", "man", "bald", "gray", "blue", 1, None, 0, 1, 0, 0, 0, "#D9EEF0"),
    ("andres", "Andrés", "man", "short", "blond", "blue", 0, "cap", 0, 0, 0, 0, 1, "#F6C9D0"),
    ("felipe", "Felipe", "man", "short", "red", "green", 0, None, 1, 0, 0, 1, 0, "#E6DDF5"),
    ("tomas", "Tomás", "man", "long", "black", "brown", 0, "hat", 0, 0, 0, 0, 3, "#D5EBD9"),
    ("julian", "Julián", "man", "short", "brown", "brown", 0, None, 0, 1, 0, 0, 2, "#F9D9C3"),
    ("martin", "Martín", "man", "bald", "black", "brown", 1, None, 1, 0, 0, 0, 3, "#CDE3F7"),
    ("david", "David", "man", "curly", "black", "brown", 0, "cap", 0, 0, 1, 0, 2, "#FBE3B5"),
    ("nicolas", "Nicolás", "man", "short", "gray", "blue", 1, None, 1, 1, 0, 0, 1, "#D9EEF0"),
    ("samuel", "Samuel", "man", "updo", "brown", "green", 0, None, 1, 0, 0, 0, 2, "#F6C9D0"),
    ("alejandro", "Alejandro", "man", "curly", "blond", "blue", 0, "hat", 0, 0, 0, 1, 0, "#E6DDF5"),
]
CHARACTERS = {
    cid: {
        "id": cid, "name": name, "gender": gender, "hair": hair, "hairColor": hair_color, "eyes": eyes,
        "glasses": bool(glasses), "hat": hat, "beard": bool(beard), "mustache": bool(mustache),
        "earrings": bool(earrings), "freckles": bool(freckles), "skin": skin, "background": background,
    }
    for cid, name, gender, hair, hair_color, eyes, glasses, hat, beard, mustache, earrings, freckles, skin, background in _RAW
}

# Questions the app answers by itself: key -> (text shown to players, condition)
QUESTIONS = {
    "woman": ("¿Es mujer?", lambda c: c["gender"] == "woman"),
    "man": ("¿Es hombre?", lambda c: c["gender"] == "man"),
    "glasses": ("¿Tiene gafas?", lambda c: c["glasses"]),
    "hat": ("¿Tiene sombrero o gorra?", lambda c: c["hat"] is not None),
    "beard": ("¿Tiene barba?", lambda c: c["beard"]),
    "mustache": ("¿Tiene bigote?", lambda c: c["mustache"]),
    "earrings": ("¿Tiene aretes?", lambda c: c["earrings"]),
    "freckles": ("¿Tiene pecas?", lambda c: c["freckles"]),
    "bald": ("¿Es calvo?", lambda c: c["hair"] == "bald"),
    "long_hair": ("¿Tiene el pelo largo?", lambda c: c["hair"] == "long"),
    "short_hair": ("¿Tiene el pelo corto?", lambda c: c["hair"] == "short"),
    "curly_hair": ("¿Tiene el pelo rizado?", lambda c: c["hair"] == "curly"),
    "updo": ("¿Tiene el pelo recogido?", lambda c: c["hair"] == "updo"),
    "black_hair": ("¿Tiene el pelo negro?", lambda c: c["hairColor"] == "black"),
    "brown_hair": ("¿Tiene el pelo castaño?", lambda c: c["hairColor"] == "brown"),
    "blond": ("¿Es rubio o rubia?", lambda c: c["hairColor"] == "blond"),
    "red_hair": ("¿Es pelirrojo o pelirroja?", lambda c: c["hairColor"] == "red"),
    "gray_hair": ("¿Tiene canas?", lambda c: c["hairColor"] == "gray"),
    "blue_eyes": ("¿Tiene los ojos azules?", lambda c: c["eyes"] == "blue"),
    "green_eyes": ("¿Tiene los ojos verdes?", lambda c: c["eyes"] == "green"),
    "brown_eyes": ("¿Tiene los ojos cafés?", lambda c: c["eyes"] == "brown"),
}
BOARD_SIZES = (16, 24)
MAX_QUESTION = 120


class GuessWhoGame:
    name = "guesswho"
    max_players = 2
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
        self.pending: dict | None = None  # written question waiting for an answer
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

    # --- room interface -------------------------------------------------
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

    # --- helpers --------------------------------------------------------
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

    # --- transitions ----------------------------------------------------
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
        # Flip a character down (or back up) on your own board
        if self.phase != "playing" or player not in self.players:
            return
        if cid not in self.board:
            raise ValueError("Ese personaje no está en el tablero")
        mine = self.flipped[player]
        mine.symmetric_difference_update({cid})

    def ask(self, player: str, key) -> None:
        # Question from the list: the app answers it with the other player's character.
        self._require_turn(player)
        if key not in QUESTIONS:
            raise ValueError("Pregunta no válida")
        text, check = QUESTIONS[key]
        secret = CHARACTERS[self.secrets[self._other(player)]]
        self.log.append({"asker": player, "text": text, "answer": bool(check(secret)), "auto": True})
        self._pass_turn()

    def ask_free(self, player: str, raw) -> None:
        # Written question: waits for the partner to answer.
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
        # Final guess: right wins the round; wrong gives it to the other player.
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

    # --- state for clients ----------------------------------------------
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
            # Each player knows only their own character; both are revealed at the end.
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
