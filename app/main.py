import asyncio
import os

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.rooms import RoomError, RoomManager

EMPTY_ROOM_TTL_SECONDS = 120  # margen para recargar la página sin perder la sala

app = FastAPI(title="Cerquita API")
manager = RoomManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/rooms")
async def create_room():
    room = manager.create()
    _schedule_cleanup(room.code)  # por si nadie llega a entrar
    return {"code": room.code}


@app.get("/api/rooms/{code}")
def get_room(code: str):
    room = manager.get(code)
    if not room:
        raise HTTPException(404, "Esa sala no existe")
    return {"code": room.code, "players": room.players, "full": len(room.players) >= 2}


@app.websocket("/ws/{code}")
async def room_socket(ws: WebSocket, code: str, name: str = ""):
    await ws.accept()
    room = manager.get(code)
    if not room:
        await ws.send_json({"type": "error", "message": "Esa sala no existe", "fatal": True})
        await ws.close()
        return
    try:
        await room.join(name, ws)
    except RoomError as exc:
        await ws.send_json({"type": "error", "message": str(exc), "fatal": True})
        await ws.close()
        return

    player = name.strip()[:20]
    try:
        while True:
            msg = await ws.receive_json()
            try:
                await room.handle(player, msg)
            except RoomError as exc:
                await ws.send_json({"type": "error", "message": str(exc)})
    except (WebSocketDisconnect, ValueError):
        pass
    finally:
        await room.leave(player)
        if room.empty:
            _schedule_cleanup(room.code)


def _schedule_cleanup(code: str) -> None:
    async def later():
        await asyncio.sleep(EMPTY_ROOM_TTL_SECONDS)
        room = manager.get(code)
        if room:
            manager.discard_if_empty(room)

    try:
        asyncio.get_running_loop().create_task(later())
    except RuntimeError:
        pass  # sin bucle de eventos (p. ej. en algunos tests)
