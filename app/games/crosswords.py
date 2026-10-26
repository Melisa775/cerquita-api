"""Palabras cruzadas para dos (al estilo Scrabble).

Cada uno tiene un atril de 7 letras que solo ve él. Por turnos se ponen
letras en una sola fila o columna del tablero de 15×15, formando palabras
que se cruzan con las que ya están. La primera jugada pasa por el centro.

Puntaje: la suma del valor de las letras de cada palabra formada (la
principal y las cruzadas nuevas). Las casillas de premio cuentan solo
cuando se pone una letra encima: DL y TL multiplican la letra, DP y TP la
palabra. Usar las 7 letras en una jugada suma 50 de bono.

En vez de jugar se puede cambiar letras (si quedan al menos 7 en la bolsa)
o pasar. La partida termina cuando alguien se queda sin letras y la bolsa
está vacía (suma lo que le quedó al otro), o tras cuatro turnos seguidos
sin puntos. Al final, a cada uno se le resta lo que tenga en el atril.

El tablero, los premios y el reparto de letras son propios: 100 fichas
según la frecuencia de las letras en español, con 2 comodines.
"""

import random
from functools import cache
from pathlib import Path

from app.dictionary import spanish

SHORT_WORDS = Path(__file__).resolve().parents[1] / "data" / "palabras_cortas.txt"

SIZE = 15
CENTER = (7, 7)
RACK = 7
BINGO = 50

# letra: (cantidad, valor)
TILES = {
    "A": (12, 1), "E": (12, 1), "O": (9, 1), "I": (6, 1), "S": (6, 1), "N": (5, 1), "R": (6, 1),
    "L": (5, 1), "U": (5, 1), "T": (4, 1), "D": (5, 2), "G": (2, 2), "C": (4, 3), "M": (3, 3),
    "B": (2, 3), "P": (2, 3), "F": (1, 4), "H": (2, 4), "V": (1, 4), "Y": (1, 4), "Q": (1, 5),
    "J": (1, 8), "Ñ": (1, 8), "X": (1, 8), "Z": (1, 10), "?": (2, 0),
}
VALUES = {k: v for k, (_, v) in TILES.items()}
LETTERS = set(TILES) - {"?"} | {"K", "W"}  # un comodín puede ser K o W


def _premiums() -> dict[tuple[int, int], str]:
    """Casillas de premio, simétricas: se define un octavo y se refleja."""
    octant = {
        "TP": [(0, 4)],
        "DP": [(1, 1), (3, 3), (2, 7)],
        "TL": [(1, 5), (5, 5)],
        "DL": [(0, 0), (2, 4), (3, 7), (6, 6)],
    }
    out = {}
    for kind, cells in octant.items():
        for r, c in cells:
            for a, b in ((r, c), (c, r)):
                for rr in (a, SIZE - 1 - a):
                    for cc in (b, SIZE - 1 - b):
                        out[(rr, cc)] = kind
    out[CENTER] = "DP"
    return out


PREMIUMS = _premiums()


@cache
def short_words() -> frozenset[str]:
    lines = SHORT_WORDS.read_text(encoding="utf-8").splitlines()
    return frozenset(w.strip() for w in lines if w.strip() and not w.startswith("#"))


def word_ok(word: str) -> bool:
    w = word.lower()
    return w in short_words() if len(w) == 2 else w in spanish()


class CrosswordsGame:
    name = "crosswords"
    actions = {"cw_play", "cw_exchange", "cw_pass"}

    def __init__(self, players: list[str], check: bool = True, rng: random.Random | None = None, timings: dict | None = None, words=None):
        self.players = list(players)
        self.check = check
        self.rng = rng or random.Random()
        self.words_ok = words or word_ok
        self.board: list[list[dict | None]] = [[None] * SIZE for _ in range(SIZE)]
        self.bag = [letter for letter, (n, _) in TILES.items() for _ in range(n)]
        self.rng.shuffle(self.bag)
        self.racks = {p: [] for p in self.players}
        self.scores = {p: 0 for p in self.players}
        self.phase = "idle"
        self.turn: str | None = None
        self.scoreless = 0
        self.last: dict | None = None
        self.history: list[dict] = []
        self.final: dict | None = None
        self.winner: str | None = None

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        if len(players) < 2:
            raise ValueError("Las palabras cruzadas se juegan entre los dos. Esperen a que entre tu pareja.")
        return cls(players, check=bool(options.get("check", True)), rng=rng)

    # --- interfaz con la sala -------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase == "playing"

    @property
    def timer_key(self):
        return None

    @property
    def timer_seconds(self):
        return None

    def start(self) -> None:
        for p in self.players:
            self._refill(p)
        self.turn = self.rng.choice(self.players)
        self.phase = "playing"
        if self.check:
            spanish()  # carga el diccionario antes de la primera jugada

    def on_timeout(self) -> None:
        pass

    def handle(self, player: str, msg: dict) -> None:
        if self.phase != "playing":
            raise ValueError("La partida ya terminó")
        if player != self.turn:
            raise ValueError(f"Le toca a {self.turn}")
        kind = msg.get("type")
        if kind == "cw_play":
            self.play(player, msg.get("tiles"))
        elif kind == "cw_exchange":
            self.exchange(player, msg.get("letters"))
        elif kind == "cw_pass":
            self.pass_turn(player)

    def remove_player(self, player: str) -> None:
        pass

    # --- utilidades -----------------------------------------------------
    def other(self, player: str) -> str:
        return next(p for p in self.players if p != player)

    def _refill(self, player: str) -> None:
        while len(self.racks[player]) < RACK and self.bag:
            self.racks[player].append(self.bag.pop())

    def _take_from_rack(self, player: str, letters: list[str]) -> list[str]:
        rack = self.racks[player][:]
        for letter in letters:
            if letter not in rack:
                raise ValueError("No tienes esas letras")
            rack.remove(letter)
        return rack

    # --- jugar ----------------------------------------------------------
    def evaluate(self, tiles) -> dict:
        """Revisa una jugada sin aplicarla. Devuelve palabras y puntaje."""
        if not isinstance(tiles, list) or not 1 <= len(tiles) <= RACK:
            raise ValueError("Pon entre 1 y 7 letras")
        placed: dict[tuple[int, int], dict] = {}
        for t in tiles:
            try:
                r, c = int(t["r"]), int(t["c"])
                letter = str(t["letter"]).upper()
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("Jugada no válida") from exc
            blank = bool(t.get("blank"))
            if not (0 <= r < SIZE and 0 <= c < SIZE):
                raise ValueError("Hay una letra fuera del tablero")
            if self.board[r][c] is not None or (r, c) in placed:
                raise ValueError("Esa casilla ya está ocupada")
            if letter not in LETTERS or (letter in ("K", "W") and not blank):
                raise ValueError("Letra no válida")
            placed[(r, c)] = {"letter": letter, "blank": blank}

        rows = {r for r, _ in placed}
        cols = {c for _, c in placed}
        if len(rows) > 1 and len(cols) > 1:
            raise ValueError("Las letras van en una sola fila o columna")
        horizontal = len(rows) == 1 and (len(placed) > 1 or self._has_neighbor_h(next(iter(placed))))
        cell_at = lambda r, c: placed.get((r, c)) or self.board[r][c]  # noqa: E731

        # sin huecos entre la primera y la última letra puesta
        if horizontal:
            r = next(iter(rows))
            lo, hi = min(cols), max(cols)
            if any(cell_at(r, c) is None for c in range(lo, hi + 1)):
                raise ValueError("Las letras tienen que quedar seguidas")
        else:
            c = next(iter(cols))
            lo, hi = min(rows), max(rows)
            if any(cell_at(r, c) is None for r in range(lo, hi + 1)):
                raise ValueError("Las letras tienen que quedar seguidas")

        empty_board = all(cell is None for row in self.board for cell in row)
        if empty_board:
            if CENTER not in placed:
                raise ValueError("La primera palabra tiene que pasar por el centro ★")
            if len(placed) < 2:
                raise ValueError("La primera palabra tiene que tener al menos dos letras")
        elif not any(
            self.board[rr][cc] is not None
            for r, c in placed
            for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1))
            if 0 <= rr < SIZE and 0 <= cc < SIZE
        ):
            raise ValueError("La palabra tiene que tocar las que ya están")

        def word_through(r, c, dr, dc):
            while 0 <= r - dr < SIZE and 0 <= c - dc < SIZE and cell_at(r - dr, c - dc):
                r, c = r - dr, c - dc
            cells = []
            while 0 <= r < SIZE and 0 <= c < SIZE and cell_at(r, c):
                cells.append((r, c))
                r, c = r + dr, c + dc
            return cells

        def score(cells):
            total, mult = 0, 1
            for (r, c) in cells:
                tile = cell_at(r, c)
                value = 0 if tile["blank"] else VALUES[tile["letter"]]
                if (r, c) in placed:
                    kind = PREMIUMS.get((r, c))
                    if kind == "DL":
                        value *= 2
                    elif kind == "TL":
                        value *= 3
                    elif kind == "DP":
                        mult *= 2
                    elif kind == "TP":
                        mult *= 3
                total += value
            return total * mult

        main_dir = (0, 1) if horizontal else (1, 0)
        cross_dir = (1, 0) if horizontal else (0, 1)
        first = next(iter(placed))
        words = []
        main = word_through(*first, *main_dir)
        if len(main) > 1:
            words.append(main)
        for (r, c) in placed:
            cross = word_through(r, c, *cross_dir)
            if len(cross) > 1:
                words.append(cross)
        if not words:
            raise ValueError("Forma una palabra de al menos dos letras")

        found = []
        total = 0
        for cells in words:
            text = "".join(cell_at(r, c)["letter"] for r, c in cells)
            pts = score(cells)
            found.append({"word": text, "points": pts, "cells": [list(x) for x in cells]})
            total += pts
        bingo = len(placed) == RACK
        if bingo:
            total += BINGO
        return {"placed": placed, "words": found, "score": total, "bingo": bingo}

    def _has_neighbor_h(self, cell) -> bool:
        r, c = cell
        return any(0 <= cc < SIZE and self.board[r][cc] is not None for cc in (c - 1, c + 1))

    def play(self, player: str, tiles) -> None:
        result = self.evaluate(tiles)
        needed = ["?" if t["blank"] else t["letter"] for t in result["placed"].values()]
        rest = self._take_from_rack(player, needed)
        if self.check:
            bad = [w["word"] for w in result["words"] if not self.words_ok(w["word"])]
            if bad:
                raise ValueError(f"No está en el diccionario: {', '.join(bad)}")
        for (r, c), tile in result["placed"].items():
            self.board[r][c] = {**tile, "by": player}
        self.racks[player] = rest
        self._refill(player)
        self.scores[player] += result["score"]
        self.scoreless = 0
        self.last = {
            "player": player, "action": "play", "score": result["score"], "bingo": result["bingo"],
            "words": [{"word": w["word"], "points": w["points"]} for w in result["words"]],
            "cells": [list(x) for x in result["placed"]],
        }
        self.history.append(self.last)
        if not self.racks[player] and not self.bag:
            self._finish(out=player)
            return
        self.turn = self.other(player)

    def exchange(self, player: str, letters) -> None:
        if len(self.bag) < RACK:
            raise ValueError("Solo se puede cambiar si quedan al menos 7 letras en la bolsa")
        if not isinstance(letters, list) or not letters:
            raise ValueError("Elige las letras que quieres cambiar")
        letters = [str(x).upper() for x in letters]
        rest = self._take_from_rack(player, letters)
        new = [self.bag.pop() for _ in letters]
        self.bag.extend(letters)
        self.rng.shuffle(self.bag)
        self.racks[player] = rest + new
        self.last = {"player": player, "action": "exchange", "count": len(letters)}
        self.history.append(self.last)
        self._scoreless_turn(player)

    def pass_turn(self, player: str) -> None:
        self.last = {"player": player, "action": "pass"}
        self.history.append(self.last)
        self._scoreless_turn(player)

    def _scoreless_turn(self, player: str) -> None:
        self.scoreless += 1
        if self.scoreless >= 4:
            self._finish(out=None)
        else:
            self.turn = self.other(player)

    def _finish(self, out: str | None) -> None:
        left = {p: sum(VALUES[x] for x in self.racks[p]) for p in self.players}
        for p in self.players:
            self.scores[p] -= left[p]
        if out:
            self.scores[out] += left[self.other(out)]
        self.final = {"out": out, "left": left}
        best = max(self.scores.values())
        leaders = [p for p, s in self.scores.items() if s == best]
        self.winner = leaders[0] if len(leaders) == 1 else None
        self.turn = None
        self.phase = "finished"

    # --- estado para los clientes ---------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        finished = self.phase == "finished"
        return {
            "name": self.name,
            "phase": self.phase,
            "players": self.players,
            "turn": self.turn,
            "board": self.board,
            "rack": self.racks.get(viewer, []) if viewer in self.racks else [],
            "racks": {p: self.racks[p] for p in self.players} if finished else None,
            "rackCounts": {p: len(self.racks[p]) for p in self.players},
            "bag": len(self.bag),
            "scores": self.scores,
            "last": self.last,
            "history": [
                {k: v for k, v in h.items() if k != "cells"} for h in self.history[-30:]
            ],
            "final": self.final,
            "winner": self.winner,
            "premiums": [[r, c, k] for (r, c), k in sorted(PREMIUMS.items())],
            "values": VALUES,
            "options": {"check": self.check},
        }
