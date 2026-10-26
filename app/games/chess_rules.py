"""Reglas del ajedrez, sin dependencias.

El tablero es una lista de 64 casillas: índice = fila * 8 + columna, con la
fila 0 = fila 1 del tablero (el lado de las blancas) y la columna 0 = a.
Las piezas son letras al estilo FEN: mayúsculas blancas (PNBRQK) y minúsculas
negras. Una casilla vacía es None.

Se generan jugadas pseudolegales y se descartan las que dejan al propio rey
en jaque. Los tests comparan con conteos "perft" conocidos, que cubren
enroques, capturas al paso, coronaciones y jaques descubiertos.
"""

from dataclasses import dataclass, field

FILES = "abcdefgh"
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

KNIGHT = [(1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)]
KING = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
ROOK_DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
BISHOP_DIRS = [(1, 1), (1, -1), (-1, 1), (-1, -1)]

# Notación en español: Rey, Dama, Torre, Alfil, Caballo
SPANISH = {"K": "R", "Q": "D", "R": "T", "B": "A", "N": "C"}


def sq(name: str) -> int:
    return (int(name[1]) - 1) * 8 + FILES.index(name[0])


def name(index: int) -> str:
    return FILES[index % 8] + str(index // 8 + 1)


def color_of(piece: str | None) -> str | None:
    if piece is None:
        return None
    return "w" if piece.isupper() else "b"


def other(color: str) -> str:
    return "b" if color == "w" else "w"


@dataclass(frozen=True)
class Move:
    frm: int
    to: int
    promotion: str | None = None  # "Q", "R", "B" o "N" (siempre en mayúscula)

    @property
    def uci(self) -> str:
        return name(self.frm) + name(self.to) + (self.promotion.lower() if self.promotion else "")


@dataclass
class Position:
    board: list
    turn: str = "w"
    castling: str = "KQkq"
    ep: int | None = None  # casilla a la que se puede capturar al paso
    halfmove: int = 0
    fullmove: int = 1
    _legal: list | None = field(default=None, repr=False, compare=False)

    # --- FEN --------------------------------------------------------------
    @classmethod
    def from_fen(cls, fen: str = START_FEN) -> "Position":
        parts = fen.split()
        board = [None] * 64
        for r, row in enumerate(parts[0].split("/")):
            rank = 7 - r
            f = 0
            for ch in row:
                if ch.isdigit():
                    f += int(ch)
                else:
                    board[rank * 8 + f] = ch
                    f += 1
        castling = "" if parts[2] == "-" else parts[2]
        ep = None if parts[3] == "-" else sq(parts[3])
        half = int(parts[4]) if len(parts) > 4 else 0
        full = int(parts[5]) if len(parts) > 5 else 1
        return cls(board, parts[1], castling, ep, half, full)

    def fen(self) -> str:
        rows = []
        for rank in range(7, -1, -1):
            row, empty = "", 0
            for f in range(8):
                p = self.board[rank * 8 + f]
                if p is None:
                    empty += 1
                else:
                    row += (str(empty) if empty else "") + p
                    empty = 0
            rows.append(row + (str(empty) if empty else ""))
        ep = name(self.ep) if self.ep is not None else "-"
        return f"{'/'.join(rows)} {self.turn} {self.castling or '-'} {ep} {self.halfmove} {self.fullmove}"

    # --- ataques ----------------------------------------------------------
    def king_square(self, color: str) -> int:
        k = "K" if color == "w" else "k"
        return self.board.index(k)

    def attacked(self, target: int, by: str) -> bool:
        """¿Alguna pieza de `by` ataca la casilla `target`?"""
        b = self.board
        r, f = divmod(target, 8)
        # peones: un peón blanco ataca hacia arriba, así que se busca abajo
        pr = r - 1 if by == "w" else r + 1
        pawn = "P" if by == "w" else "p"
        if 0 <= pr < 8:
            for df in (-1, 1):
                if 0 <= f + df < 8 and b[pr * 8 + f + df] == pawn:
                    return True
        knight = "N" if by == "w" else "n"
        for dr, df in KNIGHT:
            rr, ff = r + dr, f + df
            if 0 <= rr < 8 and 0 <= ff < 8 and b[rr * 8 + ff] == knight:
                return True
        king = "K" if by == "w" else "k"
        for dr, df in KING:
            rr, ff = r + dr, f + df
            if 0 <= rr < 8 and 0 <= ff < 8 and b[rr * 8 + ff] == king:
                return True
        straight = ("R", "Q") if by == "w" else ("r", "q")
        diagonal = ("B", "Q") if by == "w" else ("b", "q")
        for dirs, pieces in ((ROOK_DIRS, straight), (BISHOP_DIRS, diagonal)):
            for dr, df in dirs:
                rr, ff = r + dr, f + df
                while 0 <= rr < 8 and 0 <= ff < 8:
                    p = b[rr * 8 + ff]
                    if p is not None:
                        if p in pieces:
                            return True
                        break
                    rr += dr
                    ff += df
        return False

    def in_check(self, color: str | None = None) -> bool:
        color = color or self.turn
        return self.attacked(self.king_square(color), other(color))

    # --- generación -------------------------------------------------------
    def pseudo_moves(self):
        b, me = self.board, self.turn
        for i, p in enumerate(b):
            if p is None or color_of(p) != me:
                continue
            r, f = divmod(i, 8)
            kind = p.upper()
            if kind == "P":
                step = 8 if me == "w" else -8
                start_rank = 1 if me == "w" else 6
                last_rank = 7 if me == "w" else 0
                one = i + step
                if 0 <= one < 64 and b[one] is None:
                    yield from self._pawn_moves(i, one, last_rank)
                    two = one + step
                    if r == start_rank and b[two] is None:
                        yield Move(i, two)
                for df in (-1, 1):
                    if not 0 <= f + df < 8:
                        continue
                    t = one + df
                    if not 0 <= t < 64:
                        continue
                    if (b[t] is not None and color_of(b[t]) != me) or t == self.ep:
                        yield from self._pawn_moves(i, t, last_rank)
            elif kind in ("N", "K"):
                for dr, df in KNIGHT if kind == "N" else KING:
                    rr, ff = r + dr, f + df
                    if 0 <= rr < 8 and 0 <= ff < 8:
                        t = rr * 8 + ff
                        if color_of(b[t]) != me:
                            yield Move(i, t)
                if kind == "K":
                    yield from self._castles(i)
            else:
                dirs = {"R": ROOK_DIRS, "B": BISHOP_DIRS, "Q": ROOK_DIRS + BISHOP_DIRS}[kind]
                for dr, df in dirs:
                    rr, ff = r + dr, f + df
                    while 0 <= rr < 8 and 0 <= ff < 8:
                        t = rr * 8 + ff
                        if b[t] is None:
                            yield Move(i, t)
                        else:
                            if color_of(b[t]) != me:
                                yield Move(i, t)
                            break
                        rr += dr
                        ff += df

    @staticmethod
    def _pawn_moves(frm: int, to: int, last_rank: int):
        if to // 8 == last_rank:
            for promo in "QRBN":
                yield Move(frm, to, promo)
        else:
            yield Move(frm, to)

    def _castles(self, king_sq: int):
        me = self.turn
        rank = 0 if me == "w" else 7
        if king_sq != rank * 8 + 4 or self.in_check(me):
            return
        enemy = other(me)
        rights = self.castling
        b = self.board
        rook = "R" if me == "w" else "r"
        short, long = ("K", "Q") if me == "w" else ("k", "q")
        base = rank * 8
        if short in rights and b[base + 7] == rook and b[base + 5] is None and b[base + 6] is None:
            if not self.attacked(base + 5, enemy) and not self.attacked(base + 6, enemy):
                yield Move(king_sq, base + 6)
        if long in rights and b[base] == rook and b[base + 1] is None and b[base + 2] is None and b[base + 3] is None:
            if not self.attacked(base + 3, enemy) and not self.attacked(base + 2, enemy):
                yield Move(king_sq, base + 2)

    def push(self, move: Move) -> "Position":
        """Posición después de la jugada (no valida que sea legal)."""
        b = self.board[:]
        p = b[move.frm]
        me = self.turn
        kind = p.upper()
        captured = b[move.to]
        b[move.to] = (move.promotion if me == "w" else move.promotion.lower()) if move.promotion else p
        b[move.frm] = None
        ep = None
        if kind == "P":
            if move.to == self.ep:  # captura al paso: el peón capturado está detrás
                b[move.to + (-8 if me == "w" else 8)] = None
                captured = "p" if me == "w" else "P"
            if abs(move.to - move.frm) == 16:
                ep = (move.to + move.frm) // 2
        if kind == "K" and abs(move.to - move.frm) == 2:  # enroque: también se mueve la torre
            rank = move.frm // 8 * 8
            if move.to % 8 == 6:
                b[rank + 5], b[rank + 7] = b[rank + 7], None
            else:
                b[rank + 3], b[rank] = b[rank], None
        castling = self.castling
        for corner, right in ((0, "Q"), (7, "K"), (56, "q"), (63, "k")):
            if move.frm == corner or move.to == corner:
                castling = castling.replace(right, "")
        if kind == "K":
            castling = castling.replace("K", "").replace("Q", "") if me == "w" else castling.replace("k", "").replace("q", "")
        half = 0 if kind == "P" or captured else self.halfmove + 1
        full = self.fullmove + (1 if me == "b" else 0)
        return Position(b, other(me), castling, ep, half, full)

    def legal_moves(self) -> list:
        if self._legal is None:
            me = self.turn
            self._legal = [m for m in self.pseudo_moves() if not self.push(m).in_check(me)]
        return self._legal

    # --- estado de la partida ---------------------------------------------
    def is_capture(self, move: Move) -> bool:
        p = self.board[move.frm]
        return self.board[move.to] is not None or (p.upper() == "P" and move.to == self.ep)

    def insufficient_material(self) -> bool:
        """Ninguno de los dos puede dar mate: R vs R, R+A vs R, R+C vs R, o alfiles del mismo color."""
        minors = []
        for i, p in enumerate(self.board):
            if p is None or p.upper() == "K":
                continue
            if p.upper() in "PRQ":
                return False
            minors.append((p, i))
        if len(minors) <= 1:
            return True
        if all(p.upper() == "B" for p, _ in minors):
            shades = {(i // 8 + i % 8) % 2 for _, i in minors}
            return len(shades) == 1
        return False

    def can_mate(self, color: str) -> bool:
        """Para la derrota por tiempo: un rey solo nunca puede dar mate."""
        return any(p is not None and color_of(p) == color and p.upper() != "K" for p in self.board)

    def repetition_key(self) -> str:
        # La casilla al paso solo cuenta si de verdad se puede capturar al paso
        ep = self.ep
        if ep is not None and not any(m.to == ep and self.board[m.frm].upper() == "P" for m in self.legal_moves()):
            ep = None
        rows = "".join(p or "." for p in self.board)
        return f"{rows}{self.turn}{self.castling}{ep}"

    # --- notación ---------------------------------------------------------
    def san(self, move: Move) -> str:
        """Notación algebraica en español (R, D, T, A, C)."""
        p = self.board[move.frm]
        kind = p.upper()
        if kind == "K" and abs(move.to - move.frm) == 2:
            text = "O-O" if move.to % 8 == 6 else "O-O-O"
        else:
            capture = self.is_capture(move)
            if kind == "P":
                text = (FILES[move.frm % 8] + "x" if capture else "") + name(move.to)
                if move.promotion:
                    text += "=" + SPANISH[move.promotion]
            else:
                rivals = [
                    m for m in self.legal_moves()
                    if m.to == move.to and m.frm != move.frm and self.board[m.frm] == p
                ]
                dis = ""
                if rivals:
                    same_file = any(m.frm % 8 == move.frm % 8 for m in rivals)
                    same_rank = any(m.frm // 8 == move.frm // 8 for m in rivals)
                    if not same_file:
                        dis = FILES[move.frm % 8]
                    elif not same_rank:
                        dis = str(move.frm // 8 + 1)
                    else:
                        dis = name(move.frm)
                text = SPANISH[kind] + dis + ("x" if capture else "") + name(move.to)
        after = self.push(move)
        if after.in_check():
            text += "#" if not after.legal_moves() else "+"
        return text


def perft(pos: Position, depth: int) -> int:
    if depth == 0:
        return 1
    moves = pos.legal_moves()
    if depth == 1:
        return len(moves)
    return sum(perft(pos.push(m), depth - 1) for m in moves)
