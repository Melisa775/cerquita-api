"""Una: juego de cartas para dos al estilo UNO.

Mazo de 108 cartas: cuatro colores (rojo, amarillo, verde, azul), cada uno
con un 0, dos de cada número del 1 al 9, dos "Salta", dos "Reversa" y dos
"+2"; además 4 comodines y 4 comodines "+4".

  - Se reparten 7 cartas. Por turnos se juega una carta del mismo color o
    del mismo número/símbolo que la de arriba, o un comodín (y se elige color).
  - Si no puedes (o no quieres) jugar, robas una. Si la que robaste sirve,
    puedes jugarla; si no, pasa el turno.
  - Entre dos, "Salta" y "Reversa" hacen lo mismo: vuelves a jugar. El
    "+2" y el "+4" hacen robar al otro y también vuelves a jugar.
  - Con la opción de acumular, a un +2 se le puede responder con otro +2 (o
    un +4) y el que no pueda responder roba todo lo acumulado.
  - Al quedarte con una carta hay que decir "¡Una!". Si no lo dices y tu
    pareja te pilla antes de hacer su jugada, robas 2.
  - Gana la mano quien se quede sin cartas y suma los puntos de las cartas
    del otro (números: su valor; especiales: 20; comodines: 50).
"""

import random

COLORS = ("r", "y", "g", "b")
ACTIONS = ("skip", "reverse", "draw2")
HAND = 7
GOALS = (0, 200, 500)  # 0 = una sola mano


def build_deck() -> list[dict]:
    cards = []
    for color in COLORS:
        cards.append({"color": color, "value": "0"})
        for v in [str(n) for n in range(1, 10)] + list(ACTIONS):
            cards += [{"color": color, "value": v}, {"color": color, "value": v}]
    cards += [{"color": None, "value": "wild"} for _ in range(4)]
    cards += [{"color": None, "value": "wild4"} for _ in range(4)]
    return [{"id": i, **c} for i, c in enumerate(cards)]


def points(card: dict) -> int:
    if card["value"].isdigit():
        return int(card["value"])
    return 50 if card["value"] in ("wild", "wild4") else 20


class UnaGame:
    name = "una"
    actions = {"un_play", "un_draw", "un_pass", "un_una", "un_catch", "next_round"}

    def __init__(self, players: list[str], goal: int = 0, stacking: bool = False, rng: random.Random | None = None, timings: dict | None = None):
        self.players = list(players)
        self.goal = goal
        self.stacking = stacking
        self.rng = rng or random.Random()
        self.scores = {p: 0 for p in self.players}
        self.phase = "idle"
        self.round = 0
        self.hands: dict[str, list[dict]] = {}
        self.pile: list[dict] = []
        self.discard: list[dict] = []
        self.color: str | None = None  # color vigente (importa tras un comodín)
        self.turn: str | None = None
        self.drawn: dict | None = None  # carta recién robada que se puede jugar
        self.pending = 0  # cartas acumuladas por +2/+4 (con la opción de acumular)
        self.said_una: dict[str, bool] = {}
        self.catchable: str | None = None  # quien se quedó con una carta sin decirlo
        self.log: list[dict] = []
        self.result: dict | None = None
        self.winner: str | None = None
        self.starter_index = self.rng.randrange(len(self.players))

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        if len(players) < 2:
            raise ValueError("Este juego es entre los dos. Esperen a que entre tu pareja.")
        try:
            goal = int(options.get("goal", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("Meta no válida") from exc
        if goal not in GOALS:
            raise ValueError("Meta no válida")
        return cls(players, goal=goal, stacking=bool(options.get("stacking", False)), rng=rng)

    # --- interfaz con la sala -------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase in ("playing", "round_over")

    @property
    def timer_key(self):
        return None

    @property
    def timer_seconds(self):
        return None

    def start(self) -> None:
        self._deal()

    def on_timeout(self) -> None:
        pass

    def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "next_round":
            self.next_round()
            return
        if self.phase != "playing":
            raise ValueError("La mano ya terminó")
        if kind == "un_una":
            self.say_una(player)
        elif kind == "un_catch":
            self.catch(player)
        elif player != self.turn:
            raise ValueError(f"Le toca a {self.turn}")
        elif kind == "un_play":
            self.play(player, msg.get("card"), msg.get("color"))
        elif kind == "un_draw":
            self.draw(player)
        elif kind == "un_pass":
            self.pass_turn(player)

    def remove_player(self, player: str) -> None:
        pass

    # --- reparto ----------------------------------------------------------
    def other(self, player: str) -> str:
        return next(p for p in self.players if p != player)

    def _deal(self) -> None:
        deck = build_deck()
        self.rng.shuffle(deck)
        self.hands = {p: [deck.pop() for _ in range(HAND)] for p in self.players}
        # la primera carta del descarte es un número
        first = next(i for i in range(len(deck) - 1, -1, -1) if deck[i]["value"].isdigit())
        top = deck.pop(first)
        self.discard = [top]
        self.pile = deck
        self.color = top["color"]
        self.round += 1
        self.turn = self.players[(self.starter_index + self.round - 1) % len(self.players)]
        self.drawn = None
        self.pending = 0
        self.said_una = {p: False for p in self.players}
        self.catchable = None
        self.log = []
        self.result = None
        self.phase = "playing"

    def _take(self, player: str, n: int) -> list[dict]:
        got = []
        for _ in range(n):
            if not self.pile:
                if len(self.discard) <= 1:
                    break  # no quedan cartas en ningún lado
                top = self.discard.pop()
                self.pile = self.discard
                self.rng.shuffle(self.pile)
                self.discard = [top]
            card = self.pile.pop()
            self.hands[player].append(card)
            got.append(card)
        if got:
            self.said_una[player] = False
            if self.catchable == player:
                self.catchable = None
        return got

    # --- jugadas ----------------------------------------------------------
    @property
    def top(self) -> dict:
        return self.discard[-1]

    def playable(self, card: dict) -> bool:
        if self.pending:
            # bajo ataque acumulado solo se responde con +2 sobre +2, o con +4
            return card["value"] == "wild4" or (card["value"] == "draw2" and self.top["value"] == "draw2")
        if card["color"] is None:
            return True
        return card["color"] == self.color or card["value"] == self.top["value"]

    def playable_ids(self, player: str) -> list[int]:
        if self.phase != "playing" or player != self.turn:
            return []
        if self.drawn:
            return [self.drawn["id"]] if self.playable(self.drawn) else []
        return [c["id"] for c in self.hands[player] if self.playable(c)]

    def _close_catch_window(self, actor: str) -> None:
        # Cuando el otro hace su jugada, ya no se puede pillar a quien no dijo "¡Una!"
        if self.catchable and self.catchable != actor:
            self.catchable = None

    def play(self, player: str, card_id, color=None) -> None:
        card = next((c for c in self.hands[player] if c["id"] == card_id), None)
        if card is None:
            raise ValueError("No tienes esa carta")
        if self.drawn and card["id"] != self.drawn["id"]:
            raise ValueError("Ya robaste: solo puedes jugar la carta que robaste o pasar")
        if not self.playable(card):
            raise ValueError("Esa carta no se puede jugar ahora")
        if card["color"] is None and color not in COLORS:
            raise ValueError("Elige un color")
        self._close_catch_window(player)
        self.hands[player].remove(card)
        self.discard.append(card)
        self.color = color if card["color"] is None else card["color"]
        self.drawn = None
        self.log.append({"player": player, "action": "play", "card": card, "color": self.color})
        rival = self.other(player)

        if not self.hands[player]:
            self._end_round(player, card)
            return
        if len(self.hands[player]) == 1 and not self.said_una[player]:
            self.catchable = player

        value = card["value"]
        if value in ("draw2", "wild4"):
            amount = 2 if value == "draw2" else 4
            if self.stacking:
                self.pending += amount
                self.turn = rival
                return
            got = self._take(rival, amount)
            self.log.append({"player": rival, "action": "drew", "count": len(got), "forced": True})
            return  # el otro pierde el turno: sigues tú
        if value in ("skip", "reverse"):
            return  # entre dos, vuelves a jugar
        self.turn = rival

    def draw(self, player: str) -> None:
        if self.drawn:
            raise ValueError("Ya robaste: juega la carta o pasa")
        self._close_catch_window(player)
        if self.pending:
            got = self._take(player, self.pending)
            self.log.append({"player": player, "action": "drew", "count": len(got), "forced": True})
            self.pending = 0
            self.turn = self.other(player)
            return
        got = self._take(player, 1)
        self.log.append({"player": player, "action": "drew", "count": len(got)})
        if got and self.playable(got[0]):
            self.drawn = got[0]
        else:
            self.turn = self.other(player)

    def pass_turn(self, player: str) -> None:
        if not self.drawn:
            raise ValueError("Primero roba una carta")
        self.drawn = None
        self.log.append({"player": player, "action": "pass"})
        self.turn = self.other(player)

    # --- ¡Una! ------------------------------------------------------------
    def say_una(self, player: str) -> None:
        n = len(self.hands[player])
        if n == 2 and player == self.turn and self.playable_ids(player):
            self.said_una[player] = True
        elif n == 1 and self.catchable == player:
            self.said_una[player] = True
            self.catchable = None
        else:
            raise ValueError("Se dice cuando te queda una carta (o vas a quedar con una)")
        self.log.append({"player": player, "action": "una"})

    def catch(self, player: str) -> None:
        target = self.other(player)
        if self.catchable != target:
            raise ValueError("No hay a quién pillar")
        got = self._take(target, 2)
        self.catchable = None
        self.log.append({"player": player, "action": "catch", "target": target, "count": len(got)})

    # --- fin de la mano ---------------------------------------------------
    def _end_round(self, winner: str, last_card: dict) -> None:
        loser = self.other(winner)
        # si la última carta era +2/+4, el otro igual roba antes de contar
        if last_card["value"] in ("draw2", "wild4"):
            self._take(loser, (2 if last_card["value"] == "draw2" else 4) + self.pending)
            self.pending = 0
        gained = sum(points(c) for c in self.hands[loser])
        self.scores[winner] += gained
        self.result = {"winner": winner, "points": gained}
        self.turn = None
        self.catchable = None
        self.phase = "round_over"
        if self.goal == 0 or self.scores[winner] >= self.goal:
            self.winner = winner
            self.phase = "finished"

    def next_round(self) -> None:
        if self.phase != "round_over":
            raise ValueError("La mano todavía no termina")
        self._deal()

    # --- estado para los clientes ---------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        over = self.phase in ("round_over", "finished")
        return {
            "name": self.name,
            "phase": self.phase,
            "players": self.players,
            "round": self.round,
            "turn": self.turn,
            "hand": self.hands.get(viewer, []),
            "hands": self.hands if over else None,
            "counts": {p: len(self.hands.get(p, [])) for p in self.players},
            "top": self.top if self.discard else None,
            "discardCount": len(self.discard),
            "color": self.color,
            "pile": len(self.pile),
            "playable": self.playable_ids(viewer) if viewer else [],
            "drawn": self.drawn["id"] if self.drawn and viewer == self.turn else None,
            "pending": self.pending,
            "saidUna": self.said_una,
            "catchable": self.catchable,
            "log": self.log[-8:],
            "result": self.result,
            "scores": self.scores,
            "winner": self.winner,
            "options": {"goal": self.goal, "stacking": self.stacking},
        }
