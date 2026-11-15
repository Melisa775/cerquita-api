# cerquita-api

Backend for [Cerquita](https://github.com/Melisa775/cerquita-web): Spanish-language games for long-distance couples, synced in real time.

FastAPI + WebSockets. Rooms live in memory; the server is the single source of truth for every game.

## How it works

```
 Browser A ────┐                         ┌── Browser B
               │  WebSocket /ws/{room}   │
               └──────►  FastAPI  ◄──────┘
                        Room (in memory)
                        ├─ players and connections
                        ├─ phase timers
                        └─ game logic (pure, tested)
```

- **The server is in charge.** Clients only send actions; the server validates them, advances the game and broadcasts a full state snapshot to both players. They can never drift out of sync and nobody can cheat.
- **Nothing leaks early.** While players are guessing, the real color never reaches the client, and the server only reports *who* has answered, not *what* they answered.
- **Logic is separate from the network.** Each game is a pure class with no networking or timers, so the rules are covered by fast tests. A game only declares whether its current phase has a time limit (`timer_key`, `timer_seconds`); `Room` takes care of the clock, locking and broadcasting. Adding a game means writing its class and registering it in `GAMES`.
- **Fair Stop.** In classic mode, while players write, only the number of filled boxes is shared. Answers are compared ignoring accents and case (`Medellín` = `medellin`, while ñ is kept as its own letter): 100 if unique, 50 if both wrote it, 0 if empty, not starting with the letter, or misspelled. Either player can reject or accept a box before moving on to the next letter.
- **Spell checking in Stop** (`app/spelling.py`). The city category is checked against about 59,000 GeoNames cities (almost every municipality in Colombia plus the world's large cities, including their Spanish names: Londres, Nueva York). Fruit, color, animal and thing are checked word by word against the dictionary, plus an editable list of extras (`app/data/stop_extra.txt`: uchuva, chigüiro, vinotinto…). First name and surname aren't checked. When something is misspelled, a correction is suggested by comparing phonetic keys, because in Spanish "girafa", "guayava" or "sapato" sound the same as the correct word.
- **Color memory with levels.** Normal, Hard and Expert change the time to look and to answer, how muted and dark the colors can be, and how strict the scoring is (the tolerance of the curve over ΔE). Expert also shows a distractor color and removes the color hints from the sliders.
- **Enredo de letras (Boggle) with a dictionary.** The server checks that each word can be formed from neighboring dice and looks it up in a dictionary of about 636,000 Spanish words (conjugations included). Boards are generated with dice designed for Spanish, and boards with fewer than 100 possible words are discarded; a solver walks the board with prefix pruning (binary search over the sorted list) in a few milliseconds and, at the end, shows the longest words nobody found.
- **Hangman without leaks.** In turns mode, the server sends the full word only to the player who chose it; the guesser only receives the revealed letters. Letters are compared ignoring accents ("o" reveals "ó"), but ñ counts as its own letter.
- **Two-player Wordle.** Secret words come from an editable list of about 470 common, nice words (`app/data/wordle_answers.txt`); any dictionary word is a valid guess. Colors are computed in two passes so repeated letters are marked correctly (if the word has a single L, only one L turns yellow). In duel mode, each player receives their own letters and only the other player's colors.
- **Word search.** Each puzzle is generated on the fly: the category's words are placed from longest to shortest, in the directions the level allows (Easy: right, down and diagonal; Normal: also backwards; Hard: all 8), spreading directions evenly across words, and the rest is filled with letters weighted by their frequency in Spanish so it looks natural. The server validates a selection by comparing the letters on the line, so a word counts whether it's found forwards or backwards.
- **Guess Who without cheating.** Each player only receives their own secret character and their own board; about the other player they only know how many characters are left. Questions from the list are answered by the server using the character's traits, so there are no wrong answers; a test checks that every question splits the board.
- **Pinturillo with lightweight events.** Sending the full room snapshot on every stroke would be very expensive, so a game can return a `relay`: the room forwards it as a `game_event` only to the other player. The full snapshot still includes the drawing, for anyone who reconnects. If a guess is one letter away from the word, the game returns a `notice` that only reaches whoever typed it ("¡Casi!"). Hints reveal a letter at half and at three quarters of the time.
- **Murdoku generated on the fly.** Each case grows rooms from random seeds, places furniture, picks a solution (one person per row and column) in which exactly one suspect shares a room with the victim, and adds true clues until a backtracking search confirms that solution is the only one; then it removes the redundant clues. No clue says directly who was with the victim. A 6×6 case is generated in about 100 ms.
- **Preguntados-style trivia.** The wheel spins on the server (clients only animate toward the slot they receive), so nobody can pick their category. The 365 questions live in `app/data/questions.json`, about 20 per category and level (easy, medium and hard), with the correct answer always listed first; the options are shuffled for every question and the answer doesn't reach the browser until it's revealed. A question from the same category isn't repeated until they've all been used. Since both players see the same buttons, "Girar" and "Seguir" send the spin or question they were looking at (`at`); if the other player already moved on, the tap is silently ignored.
- **Chess with its own engine.** The rules (`app/games/chess_rules.py`) are written from scratch, with no libraries: pseudo-legal moves filtered by whether they leave the king in check, castling, en passant, promotion, threefold repetition, the 50-move rule and insufficient material. They are validated with known *perft* counts (for example, 197,281 positions at 4 plies from the start and the "Kiwipete" position). The server sends legal moves only to the player whose turn it is, so the browser doesn't need to know the rules. Notation is in Spanish (R, D, T, A, C) and the clock uses the room's own timer.
- **Battleship without spying.** The server stores where every ship is and validates the fleet each client sends (inside the board, not overlapping and, with the classic rule, not touching even diagonally). Each player receives their full board and, of the other's, only the shots already fired and the ships already sunk; when a ship sinks, the surrounding cells are marked as water because nothing can be there.
- **Dominoes with automatic passes.** Each player's tiles only go to their owner (the other only knows how many there are) and the server computes the possible moves. If someone can neither play nor draw, they pass automatically; if both pass in a row, the game is blocked (tranque) and whoever holds fewer points wins. A test plays 30 full random games and checks that they always end and that no tile is ever lost or duplicated.
- **Colombian-style parqués.** Each piece is stored as its progress from the start (jail, 68-square track, 7-square home stretch, cielo) and its actual square is computed from each player's arm, so the rules don't depend on the drawing. The server rolls the dice and computes which pieces can move with each die; dice that can't be used are discarded automatically. The client rotates the board so each player sees their jail at the bottom.
- **Crosswords with server-side rules.** Each rack only goes to its owner. The server checks that the letters sit in one row or column, contiguous and touching what's already on the board, finds every word formed (the main one and the cross words) and looks them up in the dictionary; if any doesn't exist, the move is rejected without losing the turn. The board, premium squares and the distribution of the 100 tiles are original. Since the general dictionary starts at three letters, two-letter words come from a separate list (`app/data/short_words.txt`).
- **Una (UNO-style) for two.** A 108-card deck with two-player rules (Skip and Reverse give another turn; +2 and +4 make the other draw and give another turn), drawing with the option to play the drawn card, and optional stacking of +2 and +4. Calling "¡Una!" has a window: if someone is left with one card without calling it, the other can catch them until they make their own move. When the deck runs out the discard pile is reshuffled; a test plays 25 random games and checks that there are always 108 cards.
- **Mini golf with server-side physics.** A shot is an angle and a power; the server simulates it at 240 steps per second (walls, bumpers, sand, water, slopes, portals and the hole, which pulls a slow ball in slightly) and sends the path sampled at 60 frames per second so both browsers animate it identically. While someone aims, the direction and power travel as lightweight events (`relay`) so their partner sees it live. A test uses brute-force search to check that all nine holes can be sunk and that the ball never leaves the green.
- **Colonos (Catan-style) with its own geometry.** The board is 19 hexagons in axial coordinates; their 54 vertices and 72 edges are computed once and the rules follow from them: distance between settlements, connected roads (a rival settlement cuts the connection), coastal ports, production by number and the longest road via depth-first search. Terrains and numbers are shuffled without leaving two 6/8 next to each other. Each hand and each development card only goes to its owner, and the server sends the legal build spots, so the browser doesn't need the rules. A test plays full random games and checks that cards are never created or lost (bank + hands = 19 of each resource).
- **Más cerca, connection without pressure.** About 300 original questions in three levels (icebreaker, deep and deeper) plus wildcards with small actions, in an editable file (`app/data/deeper.txt`; a card starting with `[ambos]` is answered by both). Turns alternate, cards don't repeat until a level runs out, and wildcards show up now and then but never twice in a row. Going deeper and ending the game need both players' votes, so nobody is pushed further than they want. The closing letters are only sent to their author until both are written, and then revealed at the same time.
- **Each player sees only their own state.** The room builds a different snapshot for each connection, so in Enredo de letras each player receives their own words and only the other player's count.
- **Perceptual scoring.** Players pick colors in HSB (hue, saturation, brightness), but the distance is measured in CIELAB (ΔE76), which is closer to how the eye perceives the difference between colors.
- **Reconnection.** If someone disconnects mid-game, they keep their spot and can come back with the same name.

## API

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Service status |
| `POST` | `/api/rooms` | Creates a room and returns its code |
| `GET` | `/api/rooms/{code}` | Room info (players, whether it's full) |
| `WS` | `/ws/{code}?name=...` | Real-time connection to the room |

### WebSocket messages

Client → server:

```jsonc
// Room
{ "type": "start_game", "game": "color", "rounds": 5, "level": "normal" }   // normal | hard | expert
{ "type": "start_game", "game": "stop", "rounds": 5, "spelling": true }
{ "type": "start_game", "game": "toolate", "rounds": 5, "turnSeconds": 10, "letters": ["A", "B", "C", "D", "E"] }
{ "type": "start_game", "game": "boggle", "rounds": 3, "size": 4, "minutes": 3 }
{ "type": "start_game", "game": "hangman", "mode": "turns", "lives": 6, "rounds": 4 }  // turns | random
{ "type": "start_game", "game": "wordle", "mode": "duel", "length": 5, "rounds": 3 }   // duel | team
{ "type": "start_game", "game": "wordsearch", "mode": "race", "level": "normal", "rounds": 1 }  // race | team; easy | normal | hard
{ "type": "start_game", "game": "guesswho", "boardSize": 24, "rounds": 3 }   // 16 | 24
{ "type": "start_game", "game": "pinturillo", "drawSeconds": 90, "rounds": 2 }   // 60 | 90 | 120
{ "type": "start_game", "game": "charades", "level": "mixed", "seconds": 90, "rounds": 2, "showCategory": true }  // easy | hard | mixed
{ "type": "start_game", "game": "murdoku", "mode": "team", "level": "easy", "rounds": 1 }   // team | race; easy (5×5) | normal (6×6)
{ "type": "start_game", "game": "trivia", "mode": "crowns", "goal": 6, "seconds": 20, "questions": 10, "level": "mixed" }  // crowns (goal 3 | 6) | duel (10 | 15 | 20 questions); easy | medium | hard | mixed
{ "type": "start_game", "game": "chess", "timeControl": "5+3", "hints": true, "white": "Meli" }  // none | 3+2 | 5+3 | 10+0 | 15+10; white is optional (random otherwise)
{ "type": "start_game", "game": "battleship", "size": 10, "noTouch": true, "bonus": true }   // 8 | 10; noTouch: ships can't touch; bonus: hit again after a hit
{ "type": "start_game", "game": "domino", "goal": 100, "boneyard": true }   // goal 50 | 100 | 150; boneyard: with or without drawing
{ "type": "start_game", "game": "parques", "pieces": 4 }   // 2 | 4 pieces per player
{ "type": "start_game", "game": "crosswords", "check": true }   // check: validate against the dictionary
{ "type": "start_game", "game": "una", "goal": 0, "stacking": false }   // goal: 0 (single hand) | 200 | 500
{ "type": "start_game", "game": "golf", "holes": 9 }   // 3 | 6 | 9 holes
{ "type": "start_game", "game": "colonos", "goal": 10, "friendly": false }   // goal 8 | 10; friendly: friendly robber
{ "type": "start_game", "game": "deeper", "start": "icebreaker", "wildcards": true, "letter": true }   // icebreaker | deep | deeper; letter: closing letter
{ "type": "next_round" }
{ "type": "back_to_lobby" }

// Color memory
{ "type": "color_guess", "color": { "h": 210, "s": 60, "b": 80 } }

// Classic Stop
{ "type": "stop_answers", "answers": { "name": "Mariana", "fruit": "Mango" } }   // draft
{ "type": "stop_call", "answers": { ...all 7 boxes filled } }                  // Stop!
{ "type": "stop_toggle", "player": "Leo", "category": "thing" }                // reject or accept

// Timed Stop (toolate)
{ "type": "tl_reroll" }                    // another category
{ "type": "tl_begin" }
{ "type": "tl_pick", "letter": "M" }
{ "type": "tl_undo" }                      // ¡No vale!

// Hangman
{ "type": "hangman_word", "word": "corazón de melón", "hint": "Algo dulce" }   // the chooser
{ "type": "hangman_guess", "letter": "o" }
{ "type": "hangman_solve", "word": "corazon de melon" }    // solve attempt: a miss costs a life

// Two-player Wordle
{ "type": "wordle_guess", "word": "perro" }
{ "type": "wordle_draft", "text": "per" }                 // team: what the player on turn is typing

// Word search
{ "type": "ws_select", "start": [0, 3], "end": [0, 7] }  // selection in progress, so the other player sees it
{ "type": "ws_mark", "start": [0, 3], "end": [0, 7] }    // mark a word (forwards or backwards)
{ "type": "ws_give_up" }

// Guess Who
{ "type": "gw_ask", "question": "glasses" }             // from the list: the app answers
{ "type": "gw_ask_free", "text": "¿se parece a mí?" }  // free text: the partner answers
{ "type": "gw_answer", "yes": true }
{ "type": "gw_flip", "id": "camila" }                   // flip down or up on your own board
{ "type": "gw_guess", "id": "camila" }                  // final guess: a miss loses the round

// Pinturillo
{ "type": "pz_choose", "index": 0 }                     // one of the three words
{ "type": "pz_stroke", "id": "a1", "color": "#22252E", "size": 10, "points": [[120, 340]] }
{ "type": "pz_points", "id": "a1", "points": [[124, 338], [130, 335]] }
{ "type": "pz_undo" }  { "type": "pz_clear" }
{ "type": "pz_guess", "text": "búho" }

// Caras y gestos / charades (actor only)
{ "type": "cg_start" }  { "type": "cg_hit" }  { "type": "cg_pass" }

// Murdoku
{ "type": "md_place", "person": 2, "cell": [1, 3] }   // cell: null to remove
{ "type": "md_note", "cell": [0, 0] }                 // toggle an X mark
{ "type": "md_clear" }

// Trivia
{ "type": "tv_spin", "at": 3 }                  // spin the wheel (at: the spin being viewed)
{ "type": "tv_crown", "category": "art" }       // pick which crown to play for
{ "type": "tv_answer", "choice": 2 }            // option index
{ "type": "next_round", "at": 5 }               // in trivia, at: the question being viewed

// Chess
{ "type": "ch_move", "from": "e7", "to": "e8", "promotion": "q" }   // promotion only when promoting
{ "type": "ch_draw" }  { "type": "ch_draw_decline" }   // offer or accept a draw; decline
{ "type": "ch_undo" }  { "type": "ch_undo_decline" }   // request or accept an undo; decline
{ "type": "ch_resign" }

// Battleship
{ "type": "bn_place", "ships": [{ "id": "cruiser", "row": 4, "col": 0, "dir": "h" }, …] }  // the whole fleet
{ "type": "bn_unready" }                    // go back to moving ships
{ "type": "bn_fire", "row": 3, "col": 7 }

// Dominoes
{ "type": "dm_play", "tile": [3, 5], "side": "left" }   // side: left | right
{ "type": "dm_draw" }                                     // draw from the boneyard (only with no playable tile)

// Parqués (player on turn only)
{ "type": "pa_roll" }
{ "type": "pa_move", "piece": 2, "die": 0 }   // die: die index (0 or 1)
{ "type": "pa_release" }                     // with doubles: release pieces from jail
{ "type": "pa_bonus", "piece": 1 }           // third double: that piece goes to the cielo

// Crosswords (player on turn only)
{ "type": "cw_play", "tiles": [{ "r": 7, "c": 7, "letter": "A", "blank": false }, …] }
{ "type": "cw_exchange", "letters": ["Q", "X"] }
{ "type": "cw_pass" }

// Una
{ "type": "un_play", "card": 57, "color": "r" }   // color only for wild cards: r | y | g | b
{ "type": "un_draw" }  { "type": "un_pass" }       // draw; pass after drawing
{ "type": "un_una" }  { "type": "un_catch" }       // call ¡Una!; catch the other player

// Mini golf (player on turn only)
{ "type": "gf_aim", "angle": 1.57, "power": 0.6 }    // relayed to the partner, doesn't change state
{ "type": "gf_shoot", "angle": 1.57, "power": 0.6 }  // angle in radians; power from 0 to 1

// Colonos
{ "type": "co_place", "target": 12 }                       // initial placement: settlement vertex or road edge
{ "type": "co_roll" }  { "type": "co_end" }
{ "type": "co_build", "what": "road", "target": 40 }       // road (edge) | settlement | city (vertex)
{ "type": "co_discard", "cards": { "grain": 3, "wool": 1 } }
{ "type": "co_robber", "hex": 7 }
{ "type": "co_bank", "give": "wood", "get": "ore" }        // 4:1, or 3:1 / 2:1 with a port
{ "type": "co_offer", "give": { "wool": 2 }, "get": { "ore": 1 } }   // the partner replies co_accept | co_reject
{ "type": "co_buy_dev" }
{ "type": "co_play_dev", "card": "year_of_plenty", "resources": ["grain", "ore"] }   // knight | road_building | year_of_plenty | monopoly

// Más cerca
{ "type": "dp_next", "at": 4 }    // next card (at: the card being viewed, so a double tap is ignored)
{ "type": "dp_skip", "at": 4 }    // another card for the same player
{ "type": "dp_save" }             // save or unsave the current card
{ "type": "dp_deeper" }  { "type": "dp_finish" }   // vote (or cancel the vote) to go deeper / to end
{ "type": "dp_letter", "text": "Gracias por esta noche…" }   // closing letter, up to 1000 characters

// Enredo de letras (Boggle)
{ "type": "boggle_word", "word": "casa" }
{ "type": "boggle_done" }                  // I can't find any more
{ "type": "boggle_toggle", "word": "asos" } // accept or reject
```

Server → client: `room_state` (full room snapshot), `game_event` (small, very frequent changes, such as Pinturillo strokes) or `error` (`fatal: true` if the connection is refused).

## Running locally

Python 3.11+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1        # Mac/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --port 8000
```

Tests:

```bash
pytest
```

## Deploying

Works on any service that supports WebSockets (Render, Railway, Fly.io).

- **Install command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Environment variable:** `CORS_ORIGINS` with the frontend's public URL, for example `https://cerquita.vercel.app`

Rooms are stored in memory: run a single instance. If the service restarts, active rooms are lost.

## Structure

```
app/
  main.py          REST API + WebSocket
  rooms.py         rooms, connections and timers
  colors.py        HSB → RGB → CIELAB conversion and scoring
  games/color.py   Color memory
  games/stop.py    Classic Stop
  games/toolate.py Timed Stop and its categories
  games/boggle.py  Enredo de letras (Boggle): dice, paths, solver and scoring
  games/hangman.py Hangman: modes, accent-insensitive letters (ñ kept apart) and words by category
  games/wordle.py  Two-player Wordle: duel or team, colors with repeated letters counted correctly
  games/wordsearch.py Word search: generation by level, race or team
  games/guesswho.py Guess Who: characters, automatic and free-text questions
  games/pinturillo.py Pinturillo: turns, hints, strokes and speed-based scoring
  games/charades.py Caras y gestos (charades): deck by category and difficulty (data/charades.txt)
  games/murdoku.py Murdoku: case generator with a unique solution and a backtracking solver
  games/trivia.py  Trivia: wheel, crowns or duel, questions from data/questions.json
  games/chess_rules.py Chess rules: legal moves, Spanish notation, perft
  games/chess.py   Chess: colors, clock, draws, undo and game end
  games/battleship.py Battleship: validated fleets, shots and a private view of each board
  games/domino.py  Dominoes: dealing, opening, boneyard, passes, blocked games and points per hand
  games/parques.py Parqués: leaving jail on doubles, separate dice, safe squares, captures and cielo
  games/crosswords.py Crosswords: bag, racks, move validation and scoring with premium squares
  games/una.py     Una (UNO-style): deck, two-player specials, ¡Una! and points per hand
  games/golf.py    Mini golf: turns, strokes and scorecard
  games/golf_physics.py Mini golf physics (bounces, sand, water, slopes, portals)
  games/golf_courses.py The nine holes
  games/colonos.py Colonos: island geometry, placement, production, robber, trading, cards and awards
  games/deeper.py  Más cerca: question cards by level, wildcards, votes to go deeper and sealed closing letters
  dictionary.py    Spanish dictionary (data/words.txt.gz, MIT license)
  spelling.py      Stop spell checking: cities, dictionary, extras and suggestions
  data/            words, cities (GeoNames, CC BY 4.0), Stop extras and game decks (charades, trivia, Más cerca…)
scripts/
  build_cities.py  regenerates data/cities.txt.gz
tests/
```

## Author

Built by **Melisa Gomez Gomez** ([@Melisa775](https://github.com/Melisa775)).
