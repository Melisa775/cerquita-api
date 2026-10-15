# cerquita-api

Backend de [Cerquita](https://github.com/Melisa775/cerquita-web): juegos en español para parejas a distancia, sincronizados en tiempo real.

FastAPI + WebSockets. Las salas viven en memoria; el servidor es la única fuente de verdad del juego.

## Cómo funciona

```
 Navegador A ──┐                         ┌── Navegador B
               │  WebSocket /ws/{sala}   │
               └──────►  FastAPI  ◄──────┘
                        Sala (memoria)
                        ├─ jugadores y conexión
                        ├─ temporizadores de fase
                        └─ lógica del juego (pura, testeada)
```

- **El servidor manda.** Los clientes solo envían acciones; el servidor valida, avanza el juego y transmite una foto completa del estado a los dos. Así nunca quedan desincronizados y nadie puede hacer trampa.
- **Nada se filtra antes de tiempo.** Mientras adivinan, el color real no viaja al cliente, y solo se informa *quién* ya respondió, no *qué* respondió.
- **Lógica separada de la red.** `ColorGame` es una clase pura sin red ni temporizadores, así las reglas se prueban con tests rápidos. `Room` se encarga del tiempo y la transmisión.
- **Puntaje perceptual.** Los jugadores eligen en HSB (tono, saturación, brillo), pero la distancia se mide en CIELAB (ΔE76), que se parece a cómo el ojo percibe la diferencia entre colores.
- **Reconexión.** Si alguien se desconecta a mitad de juego, conserva su lugar y puede volver con el mismo nombre.

## API

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/api/health` | Estado del servicio |
| `POST` | `/api/rooms` | Crea una sala y devuelve su código |
| `GET` | `/api/rooms/{code}` | Información de la sala (jugadores, si está llena) |
| `WS` | `/ws/{code}?name=...` | Conexión en tiempo real a la sala |

### Mensajes por WebSocket

Cliente → servidor:

```json
{ "type": "start_game", "game": "color", "rounds": 5 }
{ "type": "color_guess", "color": { "h": 210, "s": 60, "b": 80 } }
{ "type": "next_round" }
{ "type": "back_to_lobby" }
```

Servidor → cliente: `room_state` (foto completa de la sala) o `error` (`fatal: true` si la conexión se rechaza).

## Correrlo en local

Python 3.11+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1        # Mac/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --port 8000
```

Pruebas:

```bash
pytest
```

## Desplegar

Funciona en cualquier servicio que soporte WebSockets (Render, Railway, Fly.io).

- **Comando de instalación:** `pip install -r requirements.txt`
- **Comando de inicio:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Variable de entorno:** `CORS_ORIGINS` con la URL pública del frontend, por ejemplo `https://cerquita.vercel.app`

Las salas se guardan en memoria: usa una sola instancia. Si el servicio se reinicia, las salas activas se pierden.

## Estructura

```
app/
  main.py          API REST + WebSocket
  rooms.py         salas, conexiones y temporizadores
  colors.py        conversión HSB → RGB → CIELAB y puntaje
  games/color.py   reglas del juego de color
tests/
```
