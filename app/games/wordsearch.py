"""Sopa de letras compartida.

Los dos ven la misma sopa y buscan las mismas palabras de una categoría.
Para marcar una palabra se arrastra desde su primera letra hasta la última
(o se tocan las dos puntas). Mientras uno arrastra, el otro ve en vivo por
dónde va.

Dos modos:
  - "race" (carrera): cada palabra es de quien la encuentre primero.
  - "team" (juntos): las buscan entre los dos y se mide cuánto tardan.

Niveles: el tamaño de la sopa y las direcciones posibles.
  facil   10×10: derecha, abajo y diagonal hacia abajo
  normal  12×12: además al revés (izquierda, arriba) y diagonal hacia arriba
  dificil 14×14: las 8 direcciones
Las direcciones se reparten por igual entre las palabras, para que no
salgan casi todas horizontales o verticales.
"""

import random
import time
import unicodedata

from app.games.common import parse_rounds
from app.games.hangman import WORDS as HANGMAN_WORDS

LEVELS = {
    "facil": {"label": "Fácil", "size": 10, "words": 8, "dirs": [(0, 1), (1, 0), (1, 1)]},
    "normal": {
        "label": "Normal", "size": 12, "words": 10,
        "dirs": [(0, 1), (1, 0), (1, 1), (-1, 1), (0, -1), (-1, 0)],
    },
    "dificil": {
        "label": "Difícil", "size": 14, "words": 12,
        "dirs": [(0, 1), (1, 0), (1, 1), (-1, 1), (0, -1), (-1, 0), (-1, -1), (1, -1)],
    },
}

EXTRA_THEMES = {
    "Colores": ["rojo", "azul", "verde", "amarillo", "morado", "rosado", "naranja", "blanco", "negro", "gris",
                "dorado", "celeste", "violeta", "turquesa", "lila"],
    "En la playa": ["arena", "ola", "sol", "toalla", "concha", "cangrejo", "palmera", "coco", "sombrilla",
                    "gafas", "bloqueador", "barco", "gaviota", "helado", "castillo"],
    "Sentimientos": ["amor", "alegría", "ternura", "calma", "nostalgia", "ilusión", "orgullo", "cariño",
                     "confianza", "paciencia", "gratitud", "emoción", "felicidad", "esperanza"],
}

# Letras de relleno con la frecuencia del español, para que la sopa se vea natural
FILLER = "AAAAAAAAAAAAEEEEEEEEEEEEEOOOOOOOOIIIIIIUUUUSSSSSSSRRRRRRNNNNNNLLLLLDDDDDCCCCTTTTMMMPPBBGVYQHFZJÑ"


def to_letters(word: str) -> str:
    """'Alegría' -> 'ALEGRIA'; la Ñ se conserva."""
    out = []
    for ch in word.upper():
        if ch == "Ñ":
            out.append(ch)
        else:
            out.append("".join(c for c in unicodedata.normalize("NFD", ch) if unicodedata.category(c) != "Mn"))
    return "".join(c for c in "".join(out) if c.isalpha())


def themes(size: int) -> dict[str, list[str]]:
    """Categorías con palabras de una sola pieza que quepan en la sopa."""
    out = {}
    for name, words in {**HANGMAN_WORDS, **EXTRA_THEMES}.items():
        fit = [w for w in words if " " not in w and "-" not in w and 3 <= len(to_letters(w)) <= size]
        if len(fit) >= 8:
            out[name] = fit
    return out


def build(size: int, words: list[str], dirs: list[tuple[int, int]], rng: random.Random):
    """Coloca las palabras (las largas primero) y rellena el resto.

    Cada palabra recibe una dirección de una lista barajada que recorre
    todas las permitidas, y se prueban solo los puntos de partida donde cabe
    en esa dirección. Si no hay espacio, se intenta con las demás.
    """
    grid = [[""] * size for _ in range(size)]
    placed = []
    turns = []
    for word in sorted(words, key=lambda w: -len(to_letters(w))):
        letters = to_letters(word)
        if not turns:
            turns = list(dirs)
            rng.shuffle(turns)
        preferred = turns.pop()
        others = [d for d in dirs if d != preferred]
        rng.shuffle(others)
        for dr, dc in [preferred, *others]:
            n = len(letters) - 1
            rows = range(max(0, -dr * n), size - max(0, dr * n))
            cols = range(max(0, -dc * n), size - max(0, dc * n))
            starts = [(r, c) for r in rows for c in cols]
            rng.shuffle(starts)
            spot = next(
                (
                    cells
                    for r, c in starts
                    for cells in [[(r + dr * i, c + dc * i) for i in range(len(letters))]]
                    if all(grid[rr][cc] in ("", letters[i]) for i, (rr, cc) in enumerate(cells))
                ),
                None,
            )
            if spot:
                for i, (rr, cc) in enumerate(spot):
                    grid[rr][cc] = letters[i]
                placed.append({"word": word, "letters": letters, "cells": spot})
                break
    for r in range(size):
        for c in range(size):
            if not grid[r][c]:
                grid[r][c] = rng.choice(FILLER)
    return ["".join(row) for row in grid], placed


def line_cells(start, end) -> list[tuple[int, int]] | None:
    """Casillas en línea recta (horizontal, vertical o diagonal) entre dos puntas."""
    (r1, c1), (r2, c2) = start, end
    dr, dc = r2 - r1, c2 - c1
    steps = max(abs(dr), abs(dc))
    if steps == 0 or not (dr == 0 or dc == 0 or abs(dr) == abs(dc)):
        return None
    sr, sc = (dr > 0) - (dr < 0), (dc > 0) - (dc < 0)
    return [(r1 + sr * i, c1 + sc * i) for i in range(steps + 1)]


def parse_point(raw, size: int) -> tuple[int, int]:
    try:
        r, c = int(raw[0]), int(raw[1])
    except (TypeError, ValueError, IndexError, KeyError) as exc:
        raise ValueError("Selección inválida") from exc
    if not (0 <= r < size and 0 <= c < size):
        raise ValueError("Selección inválida")
    return r, c


class WordSearchGame:
    name = "wordsearch"
    actions = {"ws_select", "ws_mark", "ws_give_up", "next_round"}

    def __init__(
        self,
        players: list[str],
        mode: str = "race",
        level: str = "normal",
        rounds: int = 1,
        rng: random.Random | None = None,
        timings: dict | None = None,
        clock=time.monotonic,
    ):
        self.players = list(players)
        self.mode = mode
        self.level = level
        self.config = LEVELS[level]
        self.size = self.config["size"]
        self.total_rounds = rounds
        self.rng = rng or random.Random()
        self.clock = clock
        self.used_themes: list[str] = []
        self.phase = "idle"
        self.round = 0
        self.theme = ""
        self.grid: list[str] = []
        self.placed: list[dict] = []
        self.found: dict[str, dict] = {}  # palabra -> {player, cells}
        self.selecting: dict[str, dict] = {}  # selección en curso de cada uno
        self.started_at = 0.0
        self.elapsed: float | None = None
        self.gave_up = False
        self.scores: dict[str, int] = {p: 0 for p in self.players}
        self.history: list[dict] = []

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        mode = options.get("mode", "race")
        if mode not in ("race", "team"):
            raise ValueError("Modo no válido")
        level = options.get("level", "normal")
        if level not in LEVELS:
            raise ValueError("Nivel no válido")
        return cls(players, mode=mode, level=level, rounds=parse_rounds(options, 1), rng=rng, timings=timings)

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
        if kind == "ws_select":
            self.select(player, msg.get("start"), msg.get("end"))
        elif kind == "ws_mark":
            self.mark(player, msg.get("start"), msg.get("end"))
        elif kind == "ws_give_up":
            self.give_up()
        elif kind == "next_round":
            self.next_round()

    def remove_player(self, player: str) -> None:
        if player in self.players:
            self.players.remove(player)

    # --- transiciones ---------------------------------------------------
    def start_round(self) -> None:
        if self.phase not in ("idle", "round_over"):
            raise ValueError("No se puede iniciar ronda ahora")
        if self.round >= self.total_rounds:
            raise ValueError("El juego ya terminó")
        options = themes(self.size)
        fresh = [t for t in options if t not in self.used_themes] or list(options)
        self.theme = self.rng.choice(fresh)
        self.used_themes.append(self.theme)
        words = self.rng.sample(options[self.theme], min(self.config["words"], len(options[self.theme])))
        self.grid, self.placed = build(self.size, words, self.config["dirs"], self.rng)
        self.round += 1
        self.found = {}
        self.selecting = {}
        self.started_at = self.clock()
        self.elapsed = None
        self.gave_up = False
        self.phase = "playing"

    def select(self, player: str, start, end) -> None:
        """Selección en curso, solo para que el otro la vea. None la borra."""
        if self.phase != "playing" or player not in self.players:
            return
        if start is None:
            self.selecting.pop(player, None)
            return
        s = parse_point(start, self.size)
        e = parse_point(end if end is not None else start, self.size)
        self.selecting[player] = {"start": s, "end": e}

    def mark(self, player: str, start, end) -> None:
        if self.phase != "playing":
            raise ValueError("La ronda ya terminó")
        if player not in self.players:
            raise ValueError("Esta ronda empezó antes de que entraras")
        self.selecting.pop(player, None)
        cells = line_cells(parse_point(start, self.size), parse_point(end, self.size))
        if not cells:
            raise ValueError("Marca en línea recta")
        text = "".join(self.grid[r][c] for r, c in cells)
        for item in self.placed:
            if item["word"] in self.found:
                continue
            if text == item["letters"] or text[::-1] == item["letters"]:
                self.found[item["word"]] = {"player": player, "cells": cells}
                if self.mode == "race":
                    self.scores[player] = self.scores.get(player, 0) + 1
                if len(self.found) == len(self.placed):
                    self._end_round()
                return
        if any(text in (f, f[::-1]) for f in (i["letters"] for i in self.placed if i["word"] in self.found)):
            raise ValueError("Esa ya la encontraron")
        raise ValueError("Esa no es una de las palabras")

    def give_up(self) -> None:
        if self.phase != "playing":
            raise ValueError("La ronda ya terminó")
        self.gave_up = True
        self._end_round()

    def _end_round(self) -> None:
        self.elapsed = round(self.clock() - self.started_at, 1)
        self.selecting = {}
        by_player = {p: sum(1 for f in self.found.values() if f["player"] == p) for p in self.players}
        self.history.append({
            "round": self.round,
            "theme": self.theme,
            "found": len(self.found),
            "total": len(self.placed),
            "byPlayer": by_player,
            "seconds": self.elapsed,
            "gaveUp": self.gave_up,
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
        over = self.phase in ("round_over", "finished")
        elapsed = self.elapsed if self.elapsed is not None else (self.clock() - self.started_at if self.round else 0)
        return {
            "name": self.name,
            "phase": self.phase,
            "mode": self.mode,
            "level": self.level,
            "levelLabel": self.config["label"],
            "round": self.round,
            "totalRounds": self.total_rounds,
            "players": self.players,
            "theme": self.theme,
            "size": self.size,
            "grid": self.grid,
            "words": [i["word"] for i in sorted(self.placed, key=lambda i: to_letters(i["word"]))],
            "found": {w: {"player": f["player"], "cells": f["cells"]} for w, f in self.found.items()},
            # Las que nadie encontró solo se revelan al terminar la ronda.
            "missing": [{"word": i["word"], "cells": i["cells"]} for i in self.placed if i["word"] not in self.found]
            if over else [],
            "selecting": {p: s for p, s in self.selecting.items() if p != viewer},
            "elapsedMs": int(elapsed * 1000),
            "gaveUp": self.gave_up,
            "scores": self.scores,
            "history": self.history if self.phase == "finished" else [],
            "options": {"mode": self.mode, "level": self.level, "rounds": self.total_rounds},
        }
