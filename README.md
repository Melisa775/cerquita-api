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
- **Lógica separada de la red.** Cada juego es una clase pura sin red ni temporizadores, así las reglas se prueban con tests rápidos. El juego solo declara si su fase actual tiene límite de tiempo (`timer_key`, `timer_seconds`); `Room` se encarga del reloj, el bloqueo y la transmisión. Agregar un juego es escribir su clase y registrarla en `GAMES`.
- **Stop justo.** En el clásico, mientras escriben solo viaja cuántas casillas lleva cada uno. Las respuestas se comparan sin tildes ni mayúsculas (`Medellín` = `medellin`, la ñ se respeta): 100 si es única, 50 si repiten, 0 si está vacía o no empieza por la letra. Cualquiera de los dos puede anular o validar una casilla antes de pasar de letra.
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

```jsonc
// Sala
{ "type": "start_game", "game": "color", "rounds": 5 }
{ "type": "start_game", "game": "stop", "rounds": 5 }
{ "type": "start_game", "game": "toolate", "rounds": 5, "turnSeconds": 10, "letters": ["A", "B", "C", "D", "E"] }
{ "type": "next_round" }
{ "type": "back_to_lobby" }

// Color de memoria
{ "type": "color_guess", "color": { "h": 210, "s": 60, "b": 80 } }

// Stop clásico
{ "type": "stop_answers", "answers": { "nombre": "Mariana", "fruta": "Mango" } }   // borrador
{ "type": "stop_call", "answers": { ...las 7 casillas llenas } }                   // ¡Stop!
{ "type": "stop_toggle", "player": "Leo", "category": "cosa" }                     // anular o validar

// Stop contrarreloj
{ "type": "tl_reroll" }                    // otra categoría
{ "type": "tl_begin" }
{ "type": "tl_pick", "letter": "M" }
{ "type": "tl_undo" }                      // ¡No vale!
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
  games/color.py   Color de memoria
  games/stop.py    Stop clásico
  games/toolate.py Stop contrarreloj y sus categorías
tests/
```
