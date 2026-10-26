import random

import pytest

from app.games.chess import ChessGame
from app.games.chess_rules import Move, Position, perft, sq


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make(fen=None, control="libre", clock=None, timings=None):
    g = ChessGame(["Ana", "Leo"], white="Ana", time_control=control, rng=random.Random(1), clock=clock or Clock(), fen=fen, timings=timings)
    g.start()
    return g


def play(g, *moves):
    for m in moves:
        g.move(g.player_to_move, m[:2], m[2:4], m[4:] or None)


# --- reglas ---------------------------------------------------------------
@pytest.mark.parametrize(
    "fen,expected",
    [
        ("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", [20, 400, 8902]),
        ("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", [48, 2039]),
        ("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812]),
        ("r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", [6, 264, 9467]),
        ("rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", [44, 1486]),
    ],
)
def test_perft_matches_known_counts(fen, expected):
    pos = Position.from_fen(fen)
    assert [perft(pos, d + 1) for d in range(len(expected))] == expected


def test_fen_round_trip():
    fen = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
    assert Position.from_fen(fen).fen() == fen


def test_spanish_notation():
    pos = Position.from_fen()
    assert pos.san(Move(sq("g1"), sq("f3"))) == "Cf3"
    assert pos.san(Move(sq("e2"), sq("e4"))) == "e4"
    # dos caballos pueden ir a d2: se desambigua por columna
    pos = Position.from_fen("4k3/8/8/8/8/5N2/8/1N2K3 w - - 0 1")
    assert pos.san(Move(sq("b1"), sq("d2"))) == "Cbd2"
    # enroques y coronación con jaque
    pos = Position.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert pos.san(Move(sq("e1"), sq("g1"))) == "O-O"
    assert pos.san(Move(sq("e1"), sq("c1"))) == "O-O-O"
    pos = Position.from_fen("4k3/1P6/8/8/8/8/8/4K3 w - - 0 1")
    assert pos.san(Move(sq("b7"), sq("b8"), "Q")) == "b8=D+"


# --- partida --------------------------------------------------------------
def test_fools_mate():
    g = make()
    play(g, "f2f3", "e7e5", "g2g4", "d8h4")
    assert g.phase == "finished"
    assert g.result["winner"] == "Leo" and g.result["reason"] == "mate"
    assert g.snapshot()["moves"] == ["f3", "e5", "g4", "Dh4#"]


def test_turns_and_illegal_moves():
    g = make()
    with pytest.raises(ValueError, match="turno"):
        g.move("Leo", "e7", "e5")
    with pytest.raises(ValueError, match="legal"):
        g.move("Ana", "e2", "e5")
    with pytest.raises(ValueError):
        g.move("Ana", "z9", "e5")


def test_only_the_player_to_move_gets_legal_moves():
    g = make()
    assert len(g.snapshot("Ana")["legal"]["g1"]) == 2
    assert g.snapshot("Leo")["legal"] == {}


def test_en_passant_and_capture_list():
    g = make()
    play(g, "e2e4", "a7a6", "e4e5", "d7d5", "e5d6")
    snap = g.snapshot()
    assert snap["board"][sq("d5")] is None and snap["board"][sq("d6")] == "P"
    assert snap["moves"][-1] == "exd6" and snap["captured"]["w"] == ["p"]


def test_promotion_choice_defaults_to_queen():
    g = make("4k3/1P6/8/8/8/8/8/4K3 w - - 0 1")
    g.move("Ana", "b7", "b8", "n")
    assert g.pos.board[sq("b8")] == "N"
    g = make("4k3/1P6/8/8/8/8/8/4K3 w - - 0 1")
    g.move("Ana", "b7", "b8")
    assert g.pos.board[sq("b8")] == "Q"


def test_stalemate():
    g = make("7k/8/6Q1/8/8/8/8/K7 w - - 0 1")
    g.move("Ana", "g6", "f7")
    assert g.result["reason"] == "ahogado" and g.result["winner"] is None


def test_threefold_repetition():
    g = make()
    play(g, "g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1", "f6g8")
    assert g.result["reason"] == "repeticion"


def test_insufficient_material():
    g = make("4k3/8/8/8/8/8/3q4/4K3 w - - 0 1")
    g.move("Ana", "e1", "d2")
    assert g.result["reason"] == "material"


def test_draw_offer_and_resign():
    g = make()
    g.handle("Ana", {"type": "ch_draw"})
    assert g.snapshot()["drawOffer"] == "Ana"
    g.handle("Leo", {"type": "ch_draw_decline"})
    assert g.draw_offer is None
    g.handle("Ana", {"type": "ch_draw"})
    g.handle("Leo", {"type": "ch_draw"})
    assert g.result["reason"] == "acuerdo"
    g = make()
    g.handle("Leo", {"type": "ch_resign"})
    assert g.result == {"winner": "Ana", "reason": "abandono", "text": "abandono"}


def test_a_move_cancels_pending_offers():
    g = make()
    g.handle("Leo", {"type": "ch_draw"})
    play(g, "e2e4")
    assert g.draw_offer is None


def test_undo_takes_back_the_requesters_last_move():
    g = make()
    play(g, "e2e4", "e7e5")
    g.handle("Leo", {"type": "ch_undo"})  # Leo deshace su e5
    g.handle("Ana", {"type": "ch_undo"})  # Ana acepta
    assert g.snapshot()["moves"] == ["e4"] and g.pos.turn == "b"
    g.handle("Ana", {"type": "ch_undo"})  # la última jugada es de Ana: se deshace solo su e4
    g.handle("Leo", {"type": "ch_undo"})
    assert g.moves == [] and g.pos.turn == "w"
    with pytest.raises(ValueError):
        g.handle("Ana", {"type": "ch_undo"})


def test_undo_two_plies_when_it_is_your_turn():
    g = make()
    play(g, "e2e4", "e7e5", "g1f3", "b8c6")
    g.handle("Ana", {"type": "ch_undo"})
    g.handle("Leo", {"type": "ch_undo_decline"})
    assert g.undo_request is None
    g.handle("Ana", {"type": "ch_undo"})
    g.handle("Leo", {"type": "ch_undo"})
    assert g.snapshot()["moves"] == ["e4", "e5"] and g.pos.turn == "w"


def test_clock_starts_after_both_move_and_adds_increment():
    clock = Clock()
    g = make(control="3+2", clock=clock)
    assert g.timer_key is None
    clock.t = 10
    play(g, "e2e4")
    clock.t = 20
    play(g, "e7e5")
    assert g.remaining == {"w": 180, "b": 180} and g.timer_key is not None
    clock.t = 25
    play(g, "g1f3")
    assert g.remaining["w"] == 180 - 5 + 2
    clock.t = 30
    assert g.snapshot()["clocks"] == {"w": 177000, "b": 175000}
    assert g.timer_seconds == 175


def test_timeout_loses_but_lone_king_cannot_win_on_time():
    clock = Clock()
    g = make(control="3+2", clock=clock)
    play(g, "e2e4", "e7e5")
    g.on_timeout()
    assert g.result["winner"] == "Leo" and g.result["reason"] == "tiempo"

    g = make("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1", control="3+2", clock=Clock())
    play(g, "e2e3", "e8d7")
    g.on_timeout()
    assert g.result["winner"] is None and g.result["reason"] == "tiempo_material"


def test_white_option_and_validation():
    g = ChessGame.from_options(["Ana", "Leo"], {"white": "Leo", "timeControl": "5+3"}, random.Random())
    assert g.colors == {"Leo": "w", "Ana": "b"}
    with pytest.raises(ValueError):
        ChessGame.from_options(["Ana", "Leo"], {"timeControl": "1+0"}, random.Random())
    with pytest.raises(ValueError):
        ChessGame.from_options(["Ana"], {}, random.Random())
