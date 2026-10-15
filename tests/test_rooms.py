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
    return Room("ABCDE", memorize_seconds=0.05, guess_seconds=0.2)


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
