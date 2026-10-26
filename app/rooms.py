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
from app.games.crosswords import CrosswordsGame
from app.games.domino import DominoGame
from app.games.guesswho import GuessWhoGame
from app.games.hangman import HangmanGame
from app.games.murdoku import MurdokuGame
from app.games.parques import ParquesGame
from app.games.pinturillo import PinturilloGame
from app.games.stop import StopGame
from app.games.toolate import TooLateGame
from app.games.trivia import TriviaGame
from app.games.wordle import WordleGame
from app.games.wordsearch import WordSearchGame

MAX_PLAYERS = 2
CODE_ALPHABET = "".join(c for c in string.ascii_uppercase if c not in "IO")
GAMES = {cls.name: cls for cls in (ColorGame, StopGame, TooLateGame, BoggleGame, HangmanGame, WordleGame, WordSearchGame, GuessWhoGame, PinturilloGame, CharadesGame, MurdokuGame, TriviaGame, ChessGame, BattleshipGame, DominoGame, ParquesGame, CrosswordsGame)}
GAME_ACTIONS = set().union(*(cls.actions for cls in GAMES.values()))


class Connection(Protocol):
    async def send_json(self, data: dict) -> None: ...


class RoomError(Exception):
    pass


class Room:
    """Sala de dos jugadores.

    Los juegos son clases puras: reciben acciones, cambian su estado y dicen
    si su fase actual tiene un límite de tiempo (`timer_key` y
    `timer_seconds`). La sala se encarga de la red, del bloqueo y de los
    temporizadores, así que agregar un juego no exige tocar este archivo
    más allá de registrarlo en GAMES.
    """

    def __init__(self, code: str, timings: dict | None = None):
        self.code = code
        self.timings = timings or {}  # para acelerar los tiempos en tests
        self.connections: dict[str, Connection] = {}
        self.order: list[str] = []  # orden de llegada; el primero es anfitrión
        self.game = None
        self._timer: asyncio.Task | None = None
        self._timer_for: tuple | None = None  # (juego, clave de la fase)
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
        if self.game is None or not self.game.in_progress:
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
                # Cambios muy frecuentes (como los trazos del Pinturillo) viajan
                # como un evento pequeño en vez de la foto completa de la sala.
                await self.relay(player, relay)
            else:
                await self.broadcast()
            if notice and player in self.connections:
                # Aviso solo para quien hizo la acción (p. ej. "¡casi!" en el Pinturillo)
                await self.connections[player].send_json({"type": "error", "message": notice})

    def _start_game(self, msg: dict) -> None:
        cls = GAMES.get(msg.get("game"))
        if not cls:
            raise RoomError("Juego no disponible")
        try:
            game = cls.from_options(self.players, msg, rng=random.Random(), timings=self.timings)
        except ValueError as exc:
            raise RoomError(str(exc)) from exc
        game.start()
        self.game = game

    # --- temporizadores -------------------------------------------------
    def _sync_timer(self) -> None:
        """Arranca, reinicia o cancela el reloj según la fase del juego."""
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

    # --- estado ---------------------------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        """Foto de la sala. Algunos juegos le muestran a cada jugador solo lo suyo."""
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
