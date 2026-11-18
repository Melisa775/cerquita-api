import asyncio
import random
import string
import time
from typing import Protocol

from app.games.battleship import BattleshipGame
from app.games.boggle import BoggleGame
from app.games.charades import CharadesGame
from app.games.chess import ChessGame
from app.games.color import ColorGame
from app.games.colonos import ColonosGame
from app.games.crosswords import CrosswordsGame
from app.games.deeper import DeeperGame
from app.games.domino import DominoGame
from app.games.golf import GolfGame
from app.games.guesswho import GuessWhoGame
from app.games.hangman import HangmanGame
from app.games.murdoku import MurdokuGame
from app.games.parques import ParquesGame
from app.games.pinturillo import PinturilloGame
from app.games.stop import StopGame
from app.games.toolate import TooLateGame
from app.games.trivia import TriviaGame
from app.games.una import UnaGame
from app.games.wordle import WordleGame
from app.games.wordsearch import WordSearchGame

MAX_PLAYERS = 6  # people in a room; each game has its own max_players
CODE_ALPHABET = "".join(c for c in string.ascii_uppercase if c not in "IO")
GAMES = {cls.name: cls for cls in (ColorGame, StopGame, TooLateGame, BoggleGame, HangmanGame, WordleGame, WordSearchGame, GuessWhoGame, PinturilloGame, CharadesGame, MurdokuGame, TriviaGame, ChessGame, BattleshipGame, DominoGame, ParquesGame, CrosswordsGame, UnaGame, GolfGame, ColonosGame, DeeperGame)}
GAME_ACTIONS = set().union(*(cls.actions for cls in GAMES.values()))


class Connection(Protocol):
    async def send_json(self, data: dict) -> None: ...


class RoomError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code  # lets the client tell apart errors it can retry


class Room:
    """A room for up to MAX_PLAYERS people (most games are for two).

    Games are plain classes: they receive actions, update their state and
    report whether their current phase has a time limit (`timer_key` and
    `timer_seconds`). The room handles networking, locking and timers, so
    adding a game only requires registering it in GAMES.
    """

    def __init__(self, code: str, timings: dict | None = None):
        self.code = code
        self.timings = timings or {}  # lets tests speed up the timers
        self.connections: dict[str, Connection] = {}
        self.order: list[str] = []  # join order; the first one is the host
        self.game = None
        self._timer: asyncio.Task | None = None
        self._timer_for: tuple | None = None  # (game, phase key)
        self._phase_ends_at: float | None = None
        self._lock = asyncio.Lock()

    # --- players --------------------------------------------------------
    @property
    def players(self) -> list[str]:
        return list(self.order)

    async def join(self, name: str, conn: Connection) -> None:
        name = name.strip()[:20]
        if not name:
            raise RoomError("Escribe tu nombre")
        if name in self.connections:
            # Usually the same player reconnecting before the old connection closed: the client retries
            raise RoomError("Ese nombre ya está en la sala", code="name_taken")
        if name not in self.order and len(self.order) >= MAX_PLAYERS:
            raise RoomError("La sala está llena")
        self.connections[name] = conn
        if name not in self.order:
            self.order.append(name)
        await self.broadcast()

    async def leave(self, name: str) -> None:
        self.connections.pop(name, None)
        # With no game in progress the seat is freed. During a game it is
        # kept so the player can reconnect with the same name.
        if self.game is None or not self.game.in_progress:
            if name in self.order:
                self.order.remove(name)
            if self.game:
                self.game.remove_player(name)
        await self.broadcast()

    @property
    def empty(self) -> bool:
        return not self.connections

    # --- actions --------------------------------------------------------
    async def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        relay = None
        notice = None
        async with self._lock:
            if kind == "start_game":
                self._start_game(msg)
            elif kind == "back_to_lobby":
                self.game = None
            elif kind in GAME_ACTIONS:
                if not self.game:
                    raise RoomError("No hay juego en curso")
                if kind not in self.game.actions:
                    raise RoomError("Esa acción no es de este juego")
                try:
                    result = self.game.handle(player, msg)
                except ValueError as exc:
                    raise RoomError(str(exc)) from exc
                if isinstance(result, dict):
                    relay = result.get("relay")
                    notice = result.get("notice")
            else:
                raise RoomError("Acción desconocida")
            self._sync_timer()
            if relay is not None:
                # Very frequent changes (like Pinturillo strokes) travel as a small
                # event instead of the full room snapshot.
                await self.relay(player, relay)
            else:
                await self.broadcast()
            if notice and player in self.connections:
                # Notice only for the player who acted (e.g. "so close!" in Pinturillo)
                await self.connections[player].send_json({"type": "error", "message": notice})

    def _start_game(self, msg: dict) -> None:
        cls = GAMES.get(msg.get("game"))
        if not cls:
            raise RoomError("Juego no disponible")
        limit = getattr(cls, "max_players", 2)
        if len(self.players) > limit:
            raise RoomError(f"Este juego es para máximo {limit} jugadores y en la sala hay {len(self.players)}", code="too_many_players")
        try:
            game = cls.from_options(self.players, msg, rng=random.Random(), timings=self.timings)
        except ValueError as exc:
            raise RoomError(str(exc)) from exc
        game.start()
        self.game = game

    # --- timers ---------------------------------------------------------
    def _sync_timer(self) -> None:
        """Start, restart or cancel the timer according to the game phase."""
        game = self.game
        key = game.timer_key if game else None
        wanted = (game, key) if key is not None else None
        if wanted == self._timer_for:
            return
        self._cancel_timer()
        if wanted is None:
            return
        seconds = game.timer_seconds
        self._timer_for = wanted
        self._phase_ends_at = time.monotonic() + seconds

        async def runner():
            await asyncio.sleep(seconds)
            async with self._lock:
                if self.game is game and game.timer_key == key:
                    game.on_timeout()
                    self._sync_timer()
                    await self.broadcast()

        self._timer = asyncio.create_task(runner())

    def _cancel_timer(self) -> None:
        current = asyncio.current_task()
        if self._timer and not self._timer.done() and self._timer is not current:
            self._timer.cancel()
        self._timer = None
        self._timer_for = None
        self._phase_ends_at = None

    def close(self) -> None:
        self._cancel_timer()

    # --- state ----------------------------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        """Room snapshot. Some games show each player only their own data."""
        ends_in = None
        if self._phase_ends_at is not None:
            ends_in = max(0, int((self._phase_ends_at - time.monotonic()) * 1000))
        return {
            "type": "room_state",
            "code": self.code,
            "players": [{"name": p, "online": p in self.connections} for p in self.order],
            "host": self.order[0] if self.order else None,
            "game": self.game.snapshot(viewer) if self.game else None,
            "phaseEndsInMs": ends_in,
        }

    async def relay(self, sender: str, event: dict) -> None:
        msg = {"type": "game_event", "event": event}
        for name, conn in list(self.connections.items()):
            if name == sender:
                continue
            try:
                await conn.send_json(msg)
            except Exception:
                self.connections.pop(name, None)

    async def broadcast(self) -> None:
        dead = []
        for name, conn in list(self.connections.items()):
            try:
                await conn.send_json(self.snapshot(name))
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
