"""Enredo de letras (estilo Boggle).

Se lanza un tablero de dados con letras. Contra el reloj, cada uno arma
palabras uniendo letras vecinas (también en diagonal) sin repetir un dado
en la misma palabra. Al final:
  - las palabras que encontraron los dos se tachan y no suman,
  - las que no están en el diccionario no suman, pero cualquiera de los dos
    puede darlas por buenas (y anular una que sí esté),
  - el resto suma según su largo.

Flujo de cada ronda:
  playing -> buscan palabras (cada uno ve solo las suyas)
  review  -> se comparan las listas y se muestran las que se escaparon
Tras la última ronda la fase es "finished".
"""

import random
import re

from app.dictionary import Dictionary, spanish
from app.games.common import normalize, parse_rounds

# Dados pensados para el español: muchas vocales, la S, la R y la N
# frecuentes, y un dado con las letras difíciles (la Q siempre trae su U).
DICE_4 = [
    "AEASRN", "EAOLRS", "EOANTD", "AEICSL",
    "OEARMN", "EIATSP", "AOEDNR", "UOECLS",
    "EAIMRT", "OAUNSL", "EAODCR", "IEASPT",
    "AEOBGV", "UIEFHM", "EAOLND", "Q|JZÑYC",
]
DICE_5 = DICE_4 + [
    "AEIOSN", "EAORLT", "AEUSRC", "OEIDNM", "AEOLSR",
    "IAETNP", "EOARBC", "AUESLD", "EIOGVR",
]
SCORES = {3: 1, 4: 1, 5: 2, 6: 3, 7: 5}  # 8 letras o más: 11
LONG_WORD_POINTS = 11
MIN_SOLUTIONS = {4: 100, 5: 250}  # para no repartir tableros pobres
MAX_MISSED_SHOWN = 15


def points_for(word: str) -> int:
    return SCORES.get(len(word), LONG_WORD_POINTS if len(word) > 7 else 0)


def clean_word(raw) -> str:
    return re.sub(r"[^a-zñ]", "", normalize(str(raw or "")))


def neighbors(size: int) -> list[list[int]]:
    out = []
    for i in range(size * size):
        r, c = divmod(i, size)
        out.append([
            rr * size + cc
            for rr in range(r - 1, r + 2)
            for cc in range(c - 1, c + 2)
            if (rr, cc) != (r, c) and 0 <= rr < size and 0 <= cc < size
        ])
    return out


def find_path(board: list[str], size: int, word: str) -> list[int] | None:
    """Casillas que forman la palabra, o None si no se puede armar."""
    nbrs = neighbors(size)

    def dfs(i: int, rest: str, used: int) -> list[int] | None:
        tok = board[i]
        if not rest.startswith(tok):
            return None
        rest = rest[len(tok):]
        if not rest:
            return [i]
        for j in nbrs[i]:
            if not used >> j & 1:
                path = dfs(j, rest, used | 1 << j)
                if path:
                    return [i, *path]
        return None

    for start in range(len(board)):
        path = dfs(start, word, 1 << start)
        if path:
            return path
    return None


def solve(board: list[str], size: int, dictionary: Dictionary, min_len: int) -> set[str]:
    """Todas las palabras del diccionario que se pueden armar en el tablero."""
    nbrs = neighbors(size)
    found: set[str] = set()

    def dfs(i: int, prefix: str, used: int) -> None:
        word = prefix + board[i]
        if not dictionary.has_prefix(word):
            return
        if len(word) >= min_len and word in dictionary:
            found.add(word)
        for j in nbrs[i]:
            if not used >> j & 1:
                dfs(j, word, used | 1 << j)

    for start in range(len(board)):
        dfs(start, "", 1 << start)
    return found


def roll(size: int, rng: random.Random) -> list[str]:
    dice = list(DICE_4 if size == 4 else DICE_5)
    rng.shuffle(dice)
    board = []
    for die in dice:
        faces = die.replace("Q|", "Q")
        face = rng.choice(faces)
        board.append("qu" if face == "Q" else face.lower())
    return board


class BoggleGame:
    name = "boggle"
    actions = {"boggle_word", "boggle_done", "boggle_toggle", "next_round"}

    def __init__(
        self,
        players: list[str],
        size: int = 4,
        minutes: int = 3,
        rounds: int = 3,
        rng: random.Random | None = None,
        timings: dict | None = None,
        dictionary: Dictionary | None = None,
        board: list[str] | None = None,
    ):
        timings = timings or {}
        self.players = list(players)
        self.size = size
        self.minutes = minutes
        self.play_seconds = timings.get("play", minutes * 60)
        self.min_len = 3 if size == 4 else 4
        self.total_rounds = rounds
        self.rng = rng or random.Random()
        self.dictionary = dictionary or spanish()
        self._fixed_board = board  # para tests
        self.phase = "idle"
        self.round = 0
        self.board: list[str] = []
        self.solutions: set[str] = set()
        self.words: dict[str, list[str]] = {}
        self.done: set[str] = set()
        self.overrides: dict[str, bool] = {}
        self.totals: dict[str, int] = {p: 0 for p in self.players}
        self.history: list[dict] = []

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        try:
            size = int(options.get("size", 4))
            minutes = int(options.get("minutes", 3))
        except (TypeError, ValueError) as exc:
            raise ValueError("Opciones inválidas") from exc
        if size not in (4, 5):
            raise ValueError("El tablero es de 4×4 o 5×5")
        if minutes not in (2, 3, 4):
            raise ValueError("Elige 2, 3 o 4 minutos")
        return cls(players, size=size, minutes=minutes, rounds=parse_rounds(options, 3), rng=rng, timings=timings)

    # --- interfaz con la sala -------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase not in ("idle", "finished")

    @property
    def timer_key(self):
        return ("playing", self.round) if self.phase == "playing" else None

    @property
    def timer_seconds(self) -> float | None:
        return self.play_seconds if self.phase == "playing" else None

    def start(self) -> None:
        self.start_round()

    def on_timeout(self) -> None:
        if self.phase == "playing":
            self.phase = "review"

    def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "boggle_word":
            self.add_word(player, msg.get("word"))
        elif kind == "boggle_done":
            self.finish(player)
        elif kind == "boggle_toggle":
            self.toggle(msg.get("word"))
        elif kind == "next_round":
            self.next_round()

    def remove_player(self, player: str) -> None:
        if player in self.players:
            self.players.remove(player)

    # --- transiciones ---------------------------------------------------
    def _new_board(self) -> tuple[list[str], set[str]]:
        if self._fixed_board:
            return self._fixed_board, solve(self._fixed_board, self.size, self.dictionary, self.min_len)
        best: tuple[list[str], set[str]] | None = None
        for _ in range(40):
            board = roll(self.size, self.rng)
            found = solve(board, self.size, self.dictionary, self.min_len)
            if best is None or len(found) > len(best[1]):
                best = (board, found)
            if len(found) >= MIN_SOLUTIONS[self.size]:
                break
        assert best
        return best

    def start_round(self) -> None:
        if self.phase not in ("idle", "review"):
            raise ValueError("No se puede iniciar ronda ahora")
        if self.round >= self.total_rounds:
            raise ValueError("El juego ya terminó")
        self.round += 1
        self.board, self.solutions = self._new_board()
        self.words = {p: [] for p in self.players}
        self.done = set()
        self.overrides = {}
        self.phase = "playing"

    def add_word(self, player: str, raw) -> None:
        if self.phase != "playing":
            raise ValueError("Se acabó el tiempo")
        if player not in self.players:
            raise ValueError("Esta ronda empezó antes de que entraras")
        word = clean_word(raw)
        if len(word) < self.min_len:
            raise ValueError(f"Las palabras tienen mínimo {self.min_len} letras")
        if word in self.words[player]:
            raise ValueError("Ya tienes esa palabra")
        if find_path(self.board, self.size, word) is None:
            raise ValueError("Esa palabra no se puede armar en el tablero")
        self.words[player].append(word)

    def finish(self, player: str) -> None:
        """'Ya no encuentro más'. Si todos terminan, se revisa antes de tiempo."""
        if self.phase != "playing" or player not in self.players:
            return
        self.done.add(player)
        if all(p in self.done for p in self.players):
            self.phase = "review"

    def toggle(self, raw) -> None:
        if self.phase != "review":
            raise ValueError("Solo se puede corregir durante la revisión")
        word = clean_word(raw)
        lists = [w for p in self.players for w in self.words.get(p, []) if w == word]
        if not lists:
            raise ValueError("Nadie escribió esa palabra")
        if len(lists) > 1:
            raise ValueError("Las palabras que encontraron los dos no cuentan")
        new = not self._valid(word)
        if new == (word in self.dictionary):
            self.overrides.pop(word, None)
        else:
            self.overrides[word] = new

    def next_round(self) -> None:
        if self.phase != "review":
            raise ValueError("Todavía no hay siguiente ronda")
        results = self.results()
        round_totals = self.round_totals(results)
        for p, pts in round_totals.items():
            self.totals[p] = self.totals.get(p, 0) + pts
        best = {}
        for p, items in results.items():
            ok = [i["word"] for i in items if i["status"] == "ok"]
            best[p] = max(ok, key=lambda w: (len(w), w)) if ok else None
        self.history.append({"round": self.round, "totals": round_totals, "best": best, "found": {p: len(i) for p, i in results.items()}})
        if self.round >= self.total_rounds:
            self.phase = "finished"
        else:
            self.start_round()

    # --- puntaje --------------------------------------------------------
    def _valid(self, word: str) -> bool:
        return self.overrides.get(word, word in self.dictionary)

    def results(self) -> dict[str, list[dict]]:
        seen: dict[str, int] = {}
        for p in self.players:
            for w in self.words.get(p, []):
                seen[w] = seen.get(w, 0) + 1
        out = {}
        for p in self.players:
            items = []
            for w in self.words.get(p, []):
                if seen[w] > 1:
                    status = "shared"
                elif self._valid(w):
                    status = "ok"
                else:
                    status = "invalid"
                items.append({
                    "word": w,
                    "status": status,
                    "points": points_for(w) if status == "ok" else 0,
                    "known": w in self.dictionary,
                    "overridden": w in self.overrides,
                })
            out[p] = items
        return out

    @staticmethod
    def round_totals(results: dict[str, list[dict]]) -> dict[str, int]:
        return {p: sum(i["points"] for i in items) for p, items in results.items()}

    def missed(self) -> list[str]:
        found = {w for words in self.words.values() for w in words}
        return sorted(self.solutions - found, key=lambda w: (-len(w), w))[:MAX_MISSED_SHOWN]

    # --- estado para los clientes ---------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        reviewing = self.phase == "review"
        results = self.results() if reviewing else None
        mine = [{"word": w, "known": w in self.dictionary} for w in self.words.get(viewer, [])] if viewer else []
        return {
            "name": self.name,
            "phase": self.phase,
            "round": self.round,
            "totalRounds": self.total_rounds,
            "size": self.size,
            "minLength": self.min_len,
            "board": [t.capitalize() if len(t) > 1 else t.upper() for t in self.board],
            # Mientras juegan, cada uno recibe solo sus palabras; del otro, cuántas lleva.
            "mine": mine if self.phase == "playing" else [],
            "counts": {p: len(self.words.get(p, [])) for p in self.players},
            "done": sorted(self.done),
            "results": results,
            "roundTotals": self.round_totals(results) if results else None,
            "missed": self.missed() if reviewing else [],
            "possible": len(self.solutions) if reviewing else None,
            "totals": self.totals,
            "history": self.history,
            "playSeconds": self.play_seconds,
            "scores": {"3": 1, "4": 1, "5": 2, "6": 3, "7": 5, "8+": LONG_WORD_POINTS},
            "options": {"size": self.size, "minutes": self.minutes, "rounds": self.total_rounds},
        }
