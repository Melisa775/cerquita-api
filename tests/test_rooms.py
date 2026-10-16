import asyncio

import pytest

from app.rooms import Room, RoomError, RoomManager


class FakeConn:
    def __init__(self):
        self.messages = []

    async def send_json(self, data):
        self.messages.append(data)

    @property
    def last(self):
        return self.messages[-1]


@pytest.fixture
def room():
    return Room("ABCDE", timings={"memorize": 0.05, "guess": 0.2})


async def test_join_limits(room):
    await room.join("Ana", FakeConn())
    await room.join("Leo", FakeConn())
    with pytest.raises(RoomError):
        await room.join("Tercero", FakeConn())
    with pytest.raises(RoomError):
        await room.join("Ana", FakeConn())
    with pytest.raises(RoomError):
        await room.join("   ", FakeConn())


async def test_round_runs_on_timers_and_reveals_when_both_answer(room):
    ana, leo = FakeConn(), FakeConn()
    await room.join("Ana", ana)
    await room.join("Leo", leo)

    await room.handle("Ana", {"type": "start_game", "game": "color", "rounds": 1})
    assert ana.last["game"]["phase"] == "memorize"
    assert leo.last["game"]["target"] is not None

    await asyncio.sleep(0.1)  # termina el tiempo de memorizar
    assert ana.last["game"]["phase"] == "guess"
    assert ana.last["phaseEndsInMs"] is not None

    await room.handle("Ana", {"type": "color_guess", "color": {"h": 10, "s": 50, "b": 50}})
    await room.handle("Leo", {"type": "color_guess", "color": {"h": 200, "s": 50, "b": 50}})
    state = leo.last["game"]
    assert state["phase"] == "finished"
    assert set(state["roundScores"]) == {"Ana", "Leo"}


async def test_guess_timeout_reveals_anyway(room):
    ana = FakeConn()
    await room.join("Ana", ana)
    await room.join("Leo", FakeConn())
    await room.handle("Ana", {"type": "start_game", "game": "color", "rounds": 2})
    await asyncio.sleep(0.4)
    assert ana.last["game"]["phase"] == "reveal"
    assert ana.last["game"]["roundScores"] == {"Ana": 0, "Leo": 0}

    await room.handle("Leo", {"type": "next_round"})
    assert ana.last["game"]["round"] == 2


async def test_invalid_actions(room):
    await room.join("Ana", FakeConn())
    with pytest.raises(RoomError):
        await room.handle("Ana", {"type": "start_game", "game": "ajedrez"})
    with pytest.raises(RoomError):
        await room.handle("Ana", {"type": "next_round"})
    with pytest.raises(RoomError):
        await room.handle("Ana", {"type": "baile"})


async def test_player_keeps_seat_during_game(room):
    await room.join("Ana", FakeConn())
    await room.join("Leo", FakeConn())
    await room.handle("Ana", {"type": "start_game", "game": "color"})
    await room.leave("Leo")
    assert room.players == ["Ana", "Leo"]
    snap = room.snapshot()
    assert {"name": "Leo", "online": False} in snap["players"]
    await room.join("Leo", FakeConn())  # se reconecta
    room.close()


async def test_manager_codes_are_unique():
    m = RoomManager()
    codes = {m.create().code for _ in range(50)}
    assert len(codes) == 50
    assert all(len(c) == 5 and "I" not in c and "O" not in c for c in codes)


async def test_stop_round_flow_over_the_room():
    room = Room("STOPS", timings={"write": 5, "grace": 0.05})
    ana, leo = FakeConn(), FakeConn()
    await room.join("Ana", ana)
    await room.join("Leo", leo)
    await room.handle("Ana", {"type": "start_game", "game": "stop", "rounds": 1})
    game = ana.last["game"]
    assert game["phase"] == "writing" and game["letter"]
    assert ana.last["phaseEndsInMs"] > 4000

    letter = game["letter"]
    answers = {c["key"]: f"{letter}x{c['key']}" for c in game["categories"]}
    await room.handle("Leo", {"type": "stop_answers", "answers": {"nombre": f"{letter}ia"}})
    assert ana.last["game"]["filled"]["Leo"] == 1
    await room.handle("Ana", {"type": "stop_call", "answers": answers})
    assert leo.last["game"]["phase"] == "stopping"
    assert leo.last["game"]["stoppedBy"] == "Ana"

    await asyncio.sleep(0.15)  # margen para recibir lo último
    state = leo.last["game"]
    assert state["phase"] == "review"
    assert state["roundTotals"] == {"Ana": 700, "Leo": 100}

    await room.handle("Leo", {"type": "stop_toggle", "player": "Ana", "category": "cosa"})
    assert leo.last["game"]["roundTotals"]["Ana"] == 600
    await room.handle("Ana", {"type": "next_round"})
    assert ana.last["game"]["phase"] == "finished"
    assert ana.last["game"]["totals"] == {"Ana": 600, "Leo": 100}


async def test_toolate_turn_timer_restarts_and_expires():
    room = Room("TURNO", timings={"turn": 0.15})
    ana, leo = FakeConn(), FakeConn()
    await room.join("Ana", ana)
    await room.join("Leo", leo)
    await room.handle("Ana", {"type": "start_game", "game": "toolate", "rounds": 1, "letters": list("ABCDEF")})
    assert ana.last["game"]["phase"] == "ready"
    assert ana.last["phaseEndsInMs"] is None

    await room.handle("Leo", {"type": "tl_begin"})
    await asyncio.sleep(0.1)
    await room.handle("Ana", {"type": "tl_pick", "letter": "B"})  # turno de Ana, reinicia el reloj
    await asyncio.sleep(0.1)
    assert ana.last["game"]["phase"] == "playing"  # 0.2 s en total, pero el reloj se reinició

    with pytest.raises(RoomError):
        await room.handle("Ana", {"type": "tl_pick", "letter": "C"})  # turno de Leo
    await asyncio.sleep(0.15)
    state = ana.last["game"]
    assert state["phase"] == "round_over"
    assert state["result"] == {"type": "timeout", "loser": "Leo"}
    assert state["scores"] == {"Ana": 1, "Leo": 0}


async def test_game_actions_are_checked_against_the_current_game(room):
    await room.join("Ana", FakeConn())
    with pytest.raises(RoomError, match="No hay juego"):
        await room.handle("Ana", {"type": "tl_pick", "letter": "A"})
    await room.handle("Ana", {"type": "start_game", "game": "color", "rounds": 1})
    with pytest.raises(RoomError, match="no es de este juego"):
        await room.handle("Ana", {"type": "stop_call", "answers": {}})
    with pytest.raises(RoomError):
        await room.handle("Ana", {"type": "start_game", "game": "toolate", "letters": ["A"]})
    assert room.game.name == "color"  # una opción inválida no cambia el juego
    room.close()


async def test_restarting_a_game_restarts_its_timer(room):
    ana = FakeConn()
    await room.join("Ana", ana)
    await room.handle("Ana", {"type": "start_game", "game": "color", "rounds": 1})
    await asyncio.sleep(0.03)
    await room.handle("Ana", {"type": "start_game", "game": "color", "rounds": 1})
    await asyncio.sleep(0.03)
    assert ana.last["game"]["phase"] == "memorize"  # el reloj viejo no avanzó el juego nuevo
    await asyncio.sleep(0.05)
    assert ana.last["game"]["phase"] == "guess"
    room.close()
