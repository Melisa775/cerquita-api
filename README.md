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
- **Stop justo.** En el clásico, mientras escriben solo viaja cuántas casillas lleva cada uno. Las respuestas se comparan sin tildes ni mayúsculas (`Medellín` = `medellin`, la ñ se respeta): 100 si es única, 50 si repiten, 0 si está vacía, no empieza por la letra o está mal escrita. Cualquiera de los dos puede anular o validar una casilla antes de pasar de letra.
- **Revisión de ortografía en el Stop** (`app/spelling.py`). Ciudad se busca en unas 59.000 ciudades de GeoNames (casi todos los municipios de Colombia y las ciudades grandes del mundo, también con su nombre en español: Londres, Nueva York). Fruta, color, animal y cosa se revisan palabra por palabra contra el diccionario, más una lista editable de extras (`app/data/stop_extra.txt`: uchuva, chigüiro, vinotinto…). Nombre y apellido no se revisan. Si algo está mal escrito se sugiere la corrección comparando claves fonéticas, porque en español "girafa", "guayava" o "sapato" suenan igual que la palabra correcta.
- **Color de memoria con niveles.** Normal, Difícil y Experto cambian el tiempo para mirar y responder, qué tan apagados y oscuros pueden ser los colores y qué tan exigente es el puntaje (la tolerancia de la curva sobre ΔE). Experto además muestra un color distractor y quita las pistas de color de los deslizadores.
- **Enredo de letras con diccionario.** El servidor valida que cada palabra se pueda armar con dados vecinos y la compara con un diccionario de unas 636.000 palabras en español (incluye conjugaciones). Los tableros se generan con dados pensados para el español y se descartan los que tienen menos de 100 palabras posibles; un buscador recorre el tablero con poda por prefijos (búsqueda binaria sobre la lista ordenada) en pocos milisegundos y al final muestra las palabras más largas que nadie encontró.
- **Ahorcado sin filtraciones.** En el modo por turnos, el servidor le manda la palabra completa solo a quien la eligió; a quien adivina le llegan únicamente las letras descubiertas. Las letras se comparan sin tildes (la «o» destapa la «ó»), pero la ñ cuenta como letra propia.
- **Wordle a dúo.** Las palabras secretas salen de una lista editable de unas 470 palabras comunes y bonitas (`app/data/wordle_respuestas.txt`); como intento vale cualquier palabra del diccionario. Los colores se calculan en dos pasadas para que las letras repetidas se marquen bien (si la palabra tiene una sola L, solo una L sale amarilla). En duelo, a cada jugador le llegan sus letras y del otro solo los colores.
- **Sopa de letras.** Cada sopa se genera al momento: las palabras de la categoría se colocan de la más larga a la más corta, en las direcciones que permite el nivel (Fácil: derecha, abajo y diagonal; Normal: también al revés; Difícil: las 8) y repartiendo las direcciones por igual entre las palabras, y el resto se rellena con letras según su frecuencia en español para que se vea natural. El servidor valida lo que se marca comparando las letras de la línea, así que vale encontrar una palabra al derecho o al revés.
- **Adivina quién sin trampas.** Cada uno recibe solo su personaje secreto y su propio tablero; del otro solo sabe cuántos personajes le quedan. Las preguntas de la lista se responden en el servidor con los rasgos del personaje, así que no hay respuestas equivocadas; un test verifica que cada pregunta divida el tablero.
- **Pinturillo con eventos livianos.** Mandar la foto completa de la sala con cada trazo sería carísimo, así que un juego puede devolver un `relay`: la sala lo reenvía como `game_event` solo al otro jugador. La foto completa sigue incluyendo el dibujo, para quien se reconecta. Si un intento queda a una letra de la palabra, el juego devuelve un `notice` que solo le llega a quien lo escribió ("¡Casi!"). Las pistas destapan una letra a la mitad y a los tres cuartos del tiempo.
- **Murdoku generado al momento.** Cada caso arma habitaciones creciendo desde semillas al azar, pone muebles, escoge una solución (una persona por fila y columna) en la que exactamente un sospechoso comparte habitación con la víctima, y agrega pistas verdaderas hasta que un buscador con vuelta atrás confirme que esa es la única solución posible; después quita las que sobran. Ninguna pista dice directamente quién estaba con la víctima. Un caso de 6×6 se genera en unos 100 ms.
- **Trivia al estilo Preguntados.** La ruleta gira en el servidor (los clientes solo animan hacia la casilla que les llega), así nadie puede elegir su categoría. Las 365 preguntas viven en `app/data/preguntas.json`, unas 20 por categoría y nivel (fácil, medio y difícil), con la respuesta correcta siempre de primera; el orden de las opciones se baraja en cada pregunta y la respuesta no viaja al navegador hasta que se revela. No se repite una pregunta de la misma categoría hasta agotarlas. Como los dos ven los mismos botones, «Girar» y «Seguir» mandan el giro o la pregunta que estaban viendo (`at`); si el otro ya avanzó, el toque se ignora en silencio.
- **Ajedrez con motor propio.** Las reglas (`app/games/chess_rules.py`) están escritas desde cero, sin librerías: jugadas pseudolegales filtradas por si dejan al rey en jaque, enroque, captura al paso, coronación, triple repetición, regla de los 50 movimientos y material insuficiente. Se validan con conteos *perft* conocidos (por ejemplo, 197.281 posiciones a 4 jugadas desde el inicio y la posición «Kiwipete»). El servidor le manda las jugadas legales solo a quien tiene el turno, así el navegador no necesita saber las reglas. La notación va en español (R, D, T, A, C) y el reloj usa el mismo temporizador de la sala.
- **Cada jugador ve solo lo suyo.** La sala arma una foto distinta para cada conexión, así en Enredo de letras cada uno recibe sus palabras y del otro solo cuántas lleva.
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
{ "type": "start_game", "game": "color", "rounds": 5, "level": "normal" }   // normal | dificil | experto
{ "type": "start_game", "game": "stop", "rounds": 5, "spelling": true }
{ "type": "start_game", "game": "toolate", "rounds": 5, "turnSeconds": 10, "letters": ["A", "B", "C", "D", "E"] }
{ "type": "start_game", "game": "boggle", "rounds": 3, "size": 4, "minutes": 3 }
{ "type": "start_game", "game": "hangman", "mode": "turns", "lives": 6, "rounds": 4 }  // turns | random
{ "type": "start_game", "game": "wordle", "mode": "duel", "length": 5, "rounds": 3 }   // duel | team
{ "type": "start_game", "game": "wordsearch", "mode": "race", "level": "normal", "rounds": 1 }  // race | team; facil | normal | dificil
{ "type": "start_game", "game": "guesswho", "boardSize": 24, "rounds": 3 }   // 16 | 24
{ "type": "start_game", "game": "pinturillo", "drawSeconds": 90, "rounds": 2 }   // 60 | 90 | 120
{ "type": "start_game", "game": "charades", "level": "mezcla", "seconds": 90, "rounds": 2, "showCategory": true }  // facil | dificil | mezcla
{ "type": "start_game", "game": "murdoku", "mode": "team", "level": "facil", "rounds": 1 }   // team | race; facil (5×5) | normal (6×6)
{ "type": "start_game", "game": "trivia", "mode": "coronas", "goal": 6, "seconds": 20, "questions": 10, "level": "mezcla" }  // coronas (meta 3 | 6) | duelo (10 | 15 | 20 preguntas); facil | medio | dificil | mezcla
{ "type": "start_game", "game": "chess", "timeControl": "5+3", "hints": true, "white": "Meli" }  // libre | 3+2 | 5+3 | 10+0 | 15+10; white opcional (si no, al azar)
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

// Ahorcado
{ "type": "hangman_word", "word": "corazón de melón", "hint": "Algo dulce" }   // quien elige
{ "type": "hangman_guess", "letter": "o" }
{ "type": "hangman_solve", "word": "corazon de melon" }    // arriesgar: si falla, cuesta una vida

// Wordle a dúo
{ "type": "wordle_guess", "word": "perro" }
{ "type": "wordle_draft", "text": "per" }                 // juntos: lo que escribe quien tiene el turno

// Sopa de letras
{ "type": "ws_select", "start": [0, 3], "end": [0, 7] }  // selección en curso, para que el otro la vea
{ "type": "ws_mark", "start": [0, 3], "end": [0, 7] }    // marcar una palabra (al derecho o al revés)
{ "type": "ws_give_up" }

// Adivina quién
{ "type": "gw_ask", "question": "gafas" }               // de la lista: responde la app
{ "type": "gw_ask_free", "text": "¿se parece a mí?" }  // escrita: responde la pareja
{ "type": "gw_answer", "yes": true }
{ "type": "gw_flip", "id": "camila" }                   // bajar o subir en el tablero propio
{ "type": "gw_guess", "id": "camila" }                  // arriesgar: si falla, pierde la ronda

// Pinturillo
{ "type": "pz_choose", "index": 0 }                     // una de las tres palabras
{ "type": "pz_stroke", "id": "a1", "color": "#22252E", "size": 10, "points": [[120, 340]] }
{ "type": "pz_points", "id": "a1", "points": [[124, 338], [130, 335]] }
{ "type": "pz_undo" }  { "type": "pz_clear" }
{ "type": "pz_guess", "text": "búho" }

// Caras y gestos (solo quien actúa)
{ "type": "cg_start" }  { "type": "cg_hit" }  { "type": "cg_pass" }

// Murdoku
{ "type": "md_place", "person": 2, "cell": [1, 3] }   // cell: null para quitar
{ "type": "md_note", "cell": [0, 0] }                 // marcar o desmarcar una X
{ "type": "md_clear" }

// Trivia
{ "type": "tv_spin", "at": 3 }                  // girar la ruleta (at: giro que se estaba viendo)
{ "type": "tv_crown", "category": "arte" }      // elegir por qué corona jugar
{ "type": "tv_answer", "choice": 2 }            // índice de la opción
{ "type": "next_round", "at": 5 }               // en la trivia, at: pregunta que se estaba viendo

// Ajedrez
{ "type": "ch_move", "from": "e7", "to": "e8", "promotion": "q" }   // promotion solo al coronar
{ "type": "ch_draw" }  { "type": "ch_draw_decline" }   // ofrecer o aceptar tablas; rechazar
{ "type": "ch_undo" }  { "type": "ch_undo_decline" }   // pedir o aceptar deshacer; rechazar
{ "type": "ch_resign" }

// Enredo de letras
{ "type": "boggle_word", "word": "casa" }
{ "type": "boggle_done" }                  // ya no encuentro más
{ "type": "boggle_toggle", "word": "asos" } // aceptar o anular
```

Servidor → cliente: `room_state` (foto completa de la sala), `game_event` (cambios pequeños y muy frecuentes, como los trazos del Pinturillo) o `error` (`fatal: true` si la conexión se rechaza).

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
  games/boggle.py  Enredo de letras: dados, caminos, buscador y puntaje
  games/hangman.py Ahorcado: modos, letras sin tildes (la ñ aparte) y palabras por categoría
  games/wordle.py  Wordle a dúo: duelo o juntos, colores con letras repetidas bien contadas
  games/wordsearch.py Sopa de letras: generación por niveles, carrera o juntos
  games/guesswho.py Adivina quién: personajes, preguntas automáticas y escritas
  games/pinturillo.py Pinturillo: turnos, pistas, trazos y puntaje por rapidez
  games/charades.py Caras y gestos: mazo por categoría y dificultad (data/caras_gestos.txt)
  games/murdoku.py Murdoku: generador de casos con solución única y buscador con vuelta atrás
  games/trivia.py  Trivia: ruleta, coronas o duelo, preguntas de data/preguntas.json
  games/chess_rules.py Reglas del ajedrez: jugadas legales, notación en español, perft
  games/chess.py   Ajedrez: colores, reloj, tablas, deshacer y final de la partida
  dictionary.py    diccionario de español (data/palabras.txt.gz, licencia MIT)
  spelling.py      ortografía del Stop: ciudades, diccionario, extras y sugerencias
  data/            palabras, ciudades (GeoNames, CC BY 4.0) y extras del Stop
scripts/
  build_ciudades.py  regenera data/ciudades.txt.gz
tests/
```
