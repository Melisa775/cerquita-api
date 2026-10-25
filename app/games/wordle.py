import random
import re
from collections import Counter
from functools import cache
from pathlib import Path

from app.dictionary import spanish
from app.games.common import normalize, parse_rounds

DATA = Path(__file__).resolve().parents[1] / "data" / "wordle_respuestas.txt"
LENGTHS = (4, 5, 6)
MAX_TRIES = 6


@cache
def answers() -> dict[int, list[str]]:
    """Palabras secretas posibles, agrupadas por largo (sin tildes)."""
    out: dict[int, list[str]] = {n: [] for n in LENGTHS}
    for line in DATA.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            word = clean(line)
            if len(word) in out and word not in out[len(word)]:
                out[len(word)].append(word)
    return out


@cache
def originals() -> dict[str, str]:
    """Cómo se escribe cada palabra con tildes, para mostrarla al final."""
    lines = DATA.read_text(encoding="utf-8").splitlines()
    return {clean(line): line.strip().lower() for line in lines if line.strip() and not line.startswith("#")}


def clean(raw) -> str:
    return re.sub(r"[^a-zñ]", "", normalize(str(raw or "")))


def is_valid(word: str) -> bool:
    return word in spanish() or word in answers().get(len(word), [])


def score_guess(guess: str, answer: str) -> list[str]:
    """Marca cada letra. Con letras repetidas, solo se marcan tantas como haya."""
    marks = ["absent"] * len(guess)
    left = Counter()
    for i, (g, a) in enumerate(zip(guess, answer)):
        if g == a:
            marks[i] = "correct"
        else:
            left[a] += 1
    for i, g in enumerate(guess):
        if marks[i] != "correct" and left[g] > 0:
            marks[i] = "present"
            left[g] -= 1
    return marks


class WordleGame:
    name = "wordle"
    actions = {"wordle_guess", "wordle_draft", "next_round"}

    def __init__(
        self,
        players: list[str],
        mode: str = "duel",
        length: int = 5,
        rounds: int = 3,
        rng: random.Random | None = None,
        timings: dict | None = None,
        word_list: list[str] | None = None,
    ):
        self.players = list(players)
        self.mode = mode
        self.length = length
        self.total_rounds = rounds
        self.rng = rng or random.Random()
        self.word_list = word_list or answers()[length]
        self.used: set[str] = set()
        self.phase = "idle"
        self.round = 0
        self.answer = ""
        self.rows: dict[str, list[dict]] = {}  # duelo: tablero de cada uno
        self.team_rows: list[dict] = []  # juntos: un solo tablero
        self.solved_order: list[str] = []  # quién la sacó primero
        self.turn_index = 0
        self.draft = ""
        self.result: dict | None = None
        self.scores: dict[str, int] = {p: 0 for p in self.players}
        self.saved = 0
        self.history: list[dict] = []

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        mode = options.get("mode", "duel")
        if mode not in ("duel", "team"):
            raise ValueError("Modo no válido")
        try:
            length = int(options.get("length", 5))
        except (TypeError, ValueError) as exc:
            raise ValueError("Largo no válido") from exc
        if length not in LENGTHS:
            raise ValueError("Elige palabras de 4, 5 o 6 letras")
        return cls(players, mode=mode, length=length, rounds=parse_rounds(options, 3), rng=rng, timings=timings)

    # --- interfaz con la sala -------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase not in ("idle", "finished")

    timer_key = None  # sin reloj
    timer_seconds = None

    def start(self) -> None:
        self.start_round()

    def on_timeout(self) -> None:
        pass

    def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "wordle_guess":
            self.guess(player, msg.get("word"))
        elif kind == "wordle_draft":
            self.set_draft(player, msg.get("text"))
        elif kind == "next_round":
            self.next_round()

    def remove_player(self, player: str) -> None:
        if player in self.players:
            self.players.remove(player)

    # --- estado de la ronda --------------------------------------------
    @property
    def current(self) -> str | None:
        return self.players[self.turn_index % len(self.players)] if self.players else None

    def _done(self, player: str) -> bool:
        rows = self.rows.get(player, [])
        return player in self.solved_order or len(rows) >= MAX_TRIES

    # --- transiciones ---------------------------------------------------
    def start_round(self) -> None:
        if self.phase not in ("idle", "round_over"):
            raise ValueError("No se puede iniciar ronda ahora")
        if self.round >= self.total_rounds:
            raise ValueError("El juego ya terminó")
        fresh = [w for w in self.word_list if w not in self.used] or list(self.word_list)
        self.answer = self.rng.choice(fresh)
        self.used.add(self.answer)
        self.round += 1
        self.rows = {p: [] for p in self.players}
        self.team_rows = []
        self.solved_order = []
        self.turn_index = (self.round - 1) % max(1, len(self.players))
        self.draft = ""
        self.result = None
        self.phase = "playing"

    def set_draft(self, player: str, text) -> None:
        """Juntos: lo que está escribiendo quien tiene el turno, para que el otro lo vea."""
        if self.mode != "team" or self.phase != "playing" or player != self.current:
            return
        self.draft = clean(text)[: self.length]

    def guess(self, player: str, raw) -> None:
        if self.phase != "playing":
            raise ValueError("La ronda ya terminó")
        if player not in self.players:
            raise ValueError("Esta ronda empezó antes de que entraras")
        word = clean(raw)
        if len(word) != self.length:
            raise ValueError(f"La palabra tiene {self.length} letras")
        if self.mode == "team":
            if player != self.current:
                raise ValueError(f"Es el turno de {self.current}")
            if any(r["word"] == word for r in self.team_rows):
                raise ValueError("Ya probaron esa palabra")
        else:
            if self._done(player):
                raise ValueError("Ya terminaste esta ronda")
            if any(r["word"] == word for r in self.rows[player]):
                raise ValueError("Ya probaste esa palabra")
        if not is_valid(word):
            raise ValueError("No está en el diccionario")

        row = {"word": word, "marks": score_guess(word, self.answer), "player": player}
        if self.mode == "team":
            self.team_rows.append(row)
            self.draft = ""
            if word == self.answer or len(self.team_rows) >= MAX_TRIES:
                self._end_team(solved=word == self.answer)
            else:
                self.turn_index = (self.turn_index + 1) % len(self.players)
        else:
            self.rows[player].append(row)
            if word == self.answer:
                self.solved_order.append(player)
            if all(self._done(p) for p in self.players):
                self._end_duel()

    def _end_duel(self) -> None:
        solved = [p for p in self.solved_order]
        winner = None
        if solved:
            best = min(len(self.rows[p]) for p in solved)
            winner = next(p for p in solved if len(self.rows[p]) == best)  # empate: el primero
            self.scores[winner] = self.scores.get(winner, 0) + 1
        self.result = {
            "winner": winner,
            "tries": {p: len(self.rows[p]) for p in self.players},
            "solved": solved,
        }
        self._record()

    def _end_team(self, solved: bool) -> None:
        if solved:
            self.saved += 1
        self.result = {"solved": solved, "tries": len(self.team_rows), "by": self.team_rows[-1]["player"]}
        self._record()

    def _record(self) -> None:
        self.history.append({"round": self.round, "answer": self.answer, "result": self.result})
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
        boards = {}
        if self.mode == "duel":
            for p, rows in self.rows.items():
                if over or p == viewer:
                    boards[p] = rows
                else:
                    # Del otro solo se ven los colores, no las letras.
                    boards[p] = [{"word": None, "marks": r["marks"], "player": p} for r in rows]
        return {
            "name": self.name,
            "phase": self.phase,
            "mode": self.mode,
            "round": self.round,
            "totalRounds": self.total_rounds,
            "players": self.players,
            "length": self.length,
            "maxTries": MAX_TRIES,
            "boards": boards,
            "teamRows": self.team_rows,
            "solved": self.solved_order,
            "turn": self.current if self.mode == "team" and self.phase == "playing" else None,
            "draft": self.draft,
            "answer": originals().get(self.answer, self.answer) if over else None,
            "result": self.result,
            "scores": self.scores,
            "saved": self.saved,
            "history": self.history if self.phase == "finished" else [],
            "options": {"mode": self.mode, "length": self.length, "rounds": self.total_rounds},
        }
