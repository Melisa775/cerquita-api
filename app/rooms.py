import asyncio
import random
import string
import time
from typing import Protocol

from app.colors import HSB
from app.games import color as color_game
from app.games.color import ColorGame

MAX_PLAYERS = 2
CODE_ALPHABET = "".join(c for c in string.ascii_uppercase if c not in "IO")  
GAMES = {"color"}


class Connection(Protocol):
    async def send_json(self, data: dict) -> None: ...


class RoomError(Exception):
    pass


class Room:
    def __init__(self, code: str, memorize_seconds: float | None = None, guess_seconds: float | None = None):
        self.code = code
        self.connections: dict[str, Connection] = {}
        self.order: list[str] = []  # orden de llegada; el primero es anfitrión
        self.game: ColorGame | None = None
        self.memorize_seconds = memorize_seconds if memorize_seconds is not None else color_game.MEMORIZE_SECONDS
        self.guess_seconds = guess_seconds if guess_seconds is not None else color_game.GUESS_SECONDS
        self._timer: asyncio.Task | None = None
        self._phase_ends_at: float | None = None
        self._lock = asyncio.Lock()

    # --- jugadores ------------------------------------------------------
    @property
    def players(self) -> list[str]:
        return list(self.order)

    async def join(self, name: str, conn: Connection) -> None:
        name = name.strip()[:20]
        if not name:
            raise RoomError("Escribe tu nombre")
        if name in self.connections:
            raise RoomError("Ese nombre ya está en la sala")
        if name not in self.order and len(self.order) >= MAX_PLAYERS:
            raise RoomError("La sala está llena")
        self.connections[name] = conn
        if name not in self.order:
            self.order.append(name)
        await self.broadcast()

    async def leave(self, name: str) -> None:
        self.connections.pop(name, None)
        # Si no hay juego en curso, libera el lugar. Si lo hay, se conserva
        # para que pueda reconectarse con el mismo nombre.
        if self.game is None or self.game.phase in ("idle", "finished"):
            if name in self.order:
                self.order.remove(name)
            if self.game:
                self.game.remove_player(name)
        await self.broadcast()

    @property
    def empty(self) -> bool:
        return not self.connections

    # --- acciones -------------------------------------------------------
    async def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        async with self._lock:
            if kind == "start_game":
                await self._start_game(msg)
            elif kind == "next_round":
                await self._next_round()
            elif kind == "color_guess":
                await self._color_guess(player, msg)
            elif kind == "back_to_lobby":
                self._cancel_timer()
                self.game = None
                self._phase_ends_at = None
                await self.broadcast()
            else:
                raise RoomError("Acción desconocida")

    async def _start_game(self, msg: dict) -> None:
        if msg.get("game") not in GAMES:
            raise RoomError("Juego no disponible")
        rounds = int(msg.get("rounds", color_game.DEFAULT_ROUNDS))
        if not 1 <= rounds <= 10:
            raise RoomError("Elige entre 1 y 10 rondas")
        self._cancel_timer()
        self.game = ColorGame(self.players, rounds=rounds, rng=random.Random())
        await self._start_round()

    async def _next_round(self) -> None:
        if not self.game or self.game.phase != "reveal":
            raise RoomError("Todavía no hay siguiente ronda")
        await self._start_round()

    async def _start_round(self) -> None:
        assert self.game
        self.game.start_round()
        self._schedule(self.memorize_seconds, self._end_memorize)
        await self.broadcast()

    async def _end_memorize(self) -> None:
        async with self._lock:
            if self.game and self.game.phase == "memorize":
                self.game.begin_guess()
                self._schedule(self.guess_seconds, self._end_guess)
                await self.broadcast()

    async def _end_guess(self) -> None:
        async with self._lock:
            if self.game and self.game.phase == "guess":
                self._reveal()
                await self.broadcast()

    async def _color_guess(self, player: str, msg: dict) -> None:
        if not self.game:
            raise RoomError("No hay juego en curso")
        try:
            guess = HSB.from_dict(msg.get("color") or {})
            done = self.game.submit(player, guess)
        except ValueError as exc:
            raise RoomError(str(exc)) from exc
        if done:
            self._reveal()
        await self.broadcast()

    def _reveal(self) -> None:
        assert self.game
        self._cancel_timer()
        self._phase_ends_at = None
        self.game.reveal()

    # --- temporizadores -------------------------------------------------
    def _schedule(self, seconds: float, callback) -> None:
        self._cancel_timer()
        self._phase_ends_at = time.monotonic() + seconds

        async def runner():
            await asyncio.sleep(seconds)
            await callback()

        self._timer = asyncio.create_task(runner())

    def _cancel_timer(self) -> None:
        current = asyncio.current_task()
        if self._timer and not self._timer.done() and self._timer is not current:
            self._timer.cancel()
        self._timer = None

    def close(self) -> None:
        self._cancel_timer()

    # --- estado ---------------------------------------------------------
    def snapshot(self) -> dict:
        ends_in = None
        if self._phase_ends_at is not None:
            ends_in = max(0, int((self._phase_ends_at - time.monotonic()) * 1000))
        return {
            "type": "room_state",
            "code": self.code,
            "players": [{"name": p, "online": p in self.connections} for p in self.order],
            "host": self.order[0] if self.order else None,
            "game": self.game.snapshot() if self.game else None,
            "phaseEndsInMs": ends_in,
        }

    async def broadcast(self) -> None:
        state = self.snapshot()
        dead = []
        for name, conn in list(self.connections.items()):
            try:
                await conn.send_json(state)
            except Exception:
                dead.append(name)
        for name in dead:
            self.connections.pop(name, None)


class RoomManager:
    def __init__(self, rng: random.Random | None = None):
        self.rooms: dict[str, Room] = {}
        self.rng = rng or random.Random()

    def create(self) -> Room:
        for _ in range(100):
            code = "".join(self.rng.choice(CODE_ALPHABET) for _ in range(5))
            if code not in self.rooms:
                room = Room(code)
                self.rooms[code] = room
                return room
        raise RoomError("No se pudo crear la sala")

    def get(self, code: str) -> Room | None:
        return self.rooms.get(code.upper())

    def discard_if_empty(self, room: Room) -> None:
        if room.empty and self.rooms.get(room.code) is room:
            room.close()
            del self.rooms[room.code]
