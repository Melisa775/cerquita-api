"""Anzuelo: catch the liars (a bluffing trivia game for 3 to 6, bots included).

Every round one player is the fisher. Everybody else sees the question AND
its real answer, plus a secret role: one of them is the honest fish (their
card carries the true answer) and the rest are liars, who write a believable
fake answer. The fisher only sees the question and the answers, each on its
player's card, and goes catching liars one by one:

  - a liar caught: +1 for the fisher (and that liar scores nothing);
  - the honest one caught: the fisher loses what they had this round, and
    the honest fish gets +2 (they managed to sound like a liar);
  - the fisher can stop ("me planto") at any moment and keep their points;
  - catching every liar adds a bonus point.
Liars who weren't caught score +1 each. Everyone is the fisher once per
lap; one or two laps, most points wins.

Phases: write (liars write) -> fish (the fisher catches) -> reveal -> next
round, until "finished". Bots fill the table: as liars they say one of the
question's prepared fake answers; as fisher they catch at random and stop
in time.
"""

import random

from app.games.anzuelo_data import QUESTIONS
from app.games.common import normalize

BOT_NAMES = ["Coral 🤖", "Bagre 🤖", "Perla 🤖"]
MAX_ANSWER = 70
TIMES = {"write": 75, "fish": 120, "reveal": 14}


class AnzueloGame:
    name = "anzuelo"
    max_players = 6  # people and bots together
    actions = {"az_answer", "az_catch", "az_bank", "az_next"}

    def __init__(self, players, bots=None, laps=1, rng=None, timings=None, questions=None):
        self.rng = rng or random.Random()
        self.bots = list(bots or [])
        self.players = list(players) + self.bots
        if len(self.players) < 3:
            raise ValueError("Hacen falta al menos tres: agrega bots o invita a alguien más.")
        if len(self.players) > self.max_players:
            raise ValueError(f"Anzuelo es para máximo {self.max_players}, contando los bots")
        self.laps = laps
        self.timings = timings or {}
        self.questions = questions or QUESTIONS
        self.deck = list(range(len(self.questions)))
        self.rng.shuffle(self.deck)
        self.order = list(self.players)
        self.scores = {p: 0 for p in self.players}
        self.phase = "idle"
        self.round = 0
        self.guesser = None
        self.question = None  # (category, question, answer, fakes)
        self.roles = {}  # player -> "honest" | "liar"
        self.answers = {}  # player -> text (None while a liar is still writing)
        self.cards = []  # players in the order their cards are shown
        self.caught = []  # players caught, in order
        self.pending = 0  # the fisher's points this round (lost if they catch the honest fish)
        self.busted = False
        self.round_points = {}
        self.winners = []
        self.event = None  # the last catch, for the clients' animations
        self.event_id = 0

    @classmethod
    def from_options(cls, players, options, rng, timings=None):
        try:
            n_bots = int(options.get("bots", 0))
            laps = int(options.get("laps", 1))
        except (TypeError, ValueError) as exc:
            raise ValueError("Opciones no válidas") from exc
        if not 0 <= n_bots <= 3:
            raise ValueError("Pueden ser de 0 a 3 bots")
        if laps not in (1, 2):
            raise ValueError("Una o dos vueltas")
        taken = set(players)
        bots = [n for n in BOT_NAMES if n not in taken][:n_bots]
        return cls(players, bots=bots, laps=laps, rng=rng, timings=timings)

    # --- room interface -------------------------------------------------
    @property
    def in_progress(self):
        return self.phase not in ("idle", "finished")

    @property
    def timer_key(self):
        return (self.phase, self.round) if self.phase in TIMES else None

    @property
    def timer_seconds(self):
        return self.timings.get(f"az_{self.phase}", TIMES[self.phase])

    @property
    def total_rounds(self):
        return len(self.order) * self.laps

    def start(self):
        self.rng.shuffle(self.order)
        self._start_round()

    def remove_player(self, player):
        pass

    def on_timeout(self):
        if self.phase == "write":
            self._fill_missing()
            self.phase = "fish"
        elif self.phase == "fish":
            self._end_round()
        elif self.phase == "reveal":
            self._next_round()

    # --- rounds -----------------------------------------------------------
    def _start_round(self):
        self.guesser = self.order[self.round % len(self.order)]
        if not self.deck:
            self.deck = list(range(len(self.questions)))
            self.rng.shuffle(self.deck)
        self.question = self.questions[self.deck.pop()]
        fish = [p for p in self.order if p != self.guesser]
        honest = self.rng.choice(fish)
        self.roles = {p: ("honest" if p == honest else "liar") for p in fish}
        self.answers = {p: None for p in fish}
        self.answers[honest] = self.question[2]
        # bots lie with one of the prepared fake answers (all different)
        fakes = list(self.question[3])
        self.rng.shuffle(fakes)
        for p in fish:
            if p in self.bots and self.roles[p] == "liar":
                self.answers[p] = fakes.pop() if fakes else "No tengo idea, pero suena bien"
        self.cards = list(fish)
        self.rng.shuffle(self.cards)
        self.caught = []
        self.pending = 0
        self.busted = False
        self.round_points = {}
        self.event = None
        self.phase = "write"
        if all(v is not None for v in self.answers.values()):
            self.phase = "fish"

    def _fill_missing(self):
        """Liars who ran out of time get one of the prepared fake answers."""
        used = {normalize(v) for v in self.answers.values() if v}
        fakes = [f for f in self.question[3] if normalize(f) not in used]
        self.rng.shuffle(fakes)
        for p, v in self.answers.items():
            if v is None:
                self.answers[p] = fakes.pop() if fakes else "Se me olvidó qué iba a decir"

    def answer(self, player, text):
        if self.phase != "write":
            raise ValueError("Ya no se pueden escribir respuestas")
        if player == self.guesser:
            raise ValueError("Tú eres quien pesca esta ronda")
        if self.roles.get(player) != "liar":
            raise ValueError("Tu tarjeta ya trae la respuesta verdadera")
        text = " ".join(str(text or "").split())[:MAX_ANSWER]
        if not text:
            raise ValueError("Escribe una respuesta")
        key = normalize(text)
        if key == normalize(self.question[2]):
            raise ValueError("¡Esa es la respuesta verdadera! Inventa otra")
        if any(p != player and v and normalize(v) == key for p, v in self.answers.items()):
            raise ValueError("Alguien ya dijo eso: inventa otra")
        self.answers[player] = text
        if all(v is not None for v in self.answers.values()):
            self.phase = "fish"

    def catch(self, player, target):
        if self.phase != "fish":
            raise ValueError("Todavía no se puede pescar")
        if player != self.guesser:
            raise ValueError(f"Pesca {self.guesser}")
        if target not in self.cards or target in self.caught:
            raise ValueError("Esa tarjeta no se puede pescar")
        self.caught.append(target)
        self.event_id += 1
        if self.roles[target] == "honest":
            self.busted = True
            self.event = {"id": self.event_id, "player": target, "result": "honest"}
            self._end_round()
            return
        self.pending += 1
        self.event = {"id": self.event_id, "player": target, "result": "liar"}
        liars = [p for p, r in self.roles.items() if r == "liar"]
        if all(p in self.caught for p in liars):
            self.pending += 1  # every liar caught: bonus
            self._end_round()

    def bank(self, player):
        if self.phase != "fish":
            raise ValueError("Todavía no se puede pescar")
        if player != self.guesser:
            raise ValueError(f"Pesca {self.guesser}")
        self._end_round()

    def _end_round(self):
        points = {p: 0 for p in self.order}
        points[self.guesser] = 0 if self.busted else self.pending
        for p, role in self.roles.items():
            if role == "liar" and p not in self.caught:
                points[p] += 1
            if role == "honest" and self.busted:
                points[p] += 2
        for p, n in points.items():
            self.scores[p] += n
        self.round_points = points
        self.phase = "reveal"

    def _next_round(self):
        self.round += 1
        if self.round >= self.total_rounds:
            self.phase = "finished"
            top = max(self.scores.values())
            self.winners = [p for p in self.order if self.scores[p] == top]
            return
        self._start_round()

    def handle(self, player, msg):
        kind = msg.get("type")
        if self.phase == "finished":
            raise ValueError("La partida ya terminó")
        if player not in self.players:
            raise ValueError("No estás en esta partida")
        if kind == "az_answer":
            self.answer(player, msg.get("text"))
        elif kind == "az_catch":
            self.catch(player, msg.get("player"))
        elif kind == "az_bank":
            self.bank(player)
        elif kind == "az_next":
            if self.phase != "reveal":
                raise ValueError("La ronda todavía no termina")
            self._next_round()

    # --- bots ---------------------------------------------------------------
    def bot_move(self):
        """(bot, message) when a bot fisher has to act, else None."""
        if self.phase != "fish" or self.guesser not in self.bots:
            return None
        free = [p for p in self.cards if p not in self.caught]
        # stop with some points, more willing the more it already has
        if self.pending and self.rng.random() < 0.3 + 0.2 * self.pending:
            return self.guesser, {"type": "az_bank"}
        return self.guesser, {"type": "az_catch", "player": self.rng.choice(free)}

    def play_bot(self) -> bool:
        move = self.bot_move()
        if not move:
            return False
        bot, msg = move
        try:
            self.handle(bot, msg)
        except ValueError:
            self._end_round()
        return True

    # --- state for clients ----------------------------------------------------
    def snapshot(self, viewer=None):
        show_all = self.phase in ("reveal", "finished")
        q = self.question
        knows_answer = show_all or (viewer is not None and viewer != self.guesser and viewer in self.players)
        role = "guesser" if viewer == self.guesser else self.roles.get(viewer)
        cards = []
        if self.phase in ("fish", "reveal", "finished"):
            for p in self.cards:
                caught = p in self.caught
                cards.append({
                    "player": p,
                    "text": self.answers.get(p),
                    "caught": caught,
                    # a role shows once the card is caught, or when the round is over
                    "role": self.roles[p] if (caught or show_all) else None,
                })
        return {
            "name": self.name,
            "phase": self.phase,
            "players": self.order,
            "bots": self.bots,
            "round": self.round + 1,
            "rounds": self.total_rounds,
            "guesser": self.guesser,
            "turn": self.guesser if self.phase == "fish" else None,
            "seconds": self.timer_seconds if self.phase in TIMES else None,
            "scores": self.scores,
            "category": q[0] if q else None,
            "question": q[1] if q else None,
            "answer": q[2] if q and knows_answer else None,
            "myRole": role,
            "myAnswer": self.answers.get(viewer) if viewer in self.answers else None,
            "written": {p: v is not None for p, v in self.answers.items()} if self.phase == "write" else {},
            "cards": cards,
            "pending": self.pending,
            "busted": self.busted,
            "roles": self.roles if show_all else {},
            "roundPoints": self.round_points if show_all else {},
            "event": self.event,
            "winners": self.winners,
            "options": {"bots": len(self.bots), "laps": self.laps},
        }
