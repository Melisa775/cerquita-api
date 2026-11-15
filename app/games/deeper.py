"""Más cerca: a question card game to know each other better and connect.

There is no score and no clock. The deck has three levels (icebreaker, deep
and deeper) plus optional wildcards, which are small actions instead of
questions. Players take turns: each card is for one of them (or for both, if
the card says so) and the other listens. Either player can draw the next
card, ask for another one, or save a card they liked.

Going one level deeper needs both players to agree: each one votes and the
level only changes when both have voted, so nobody is pushed further than
they want. Ending the game works the same way. With the closing letter
enabled, each player then writes a short message to the other; the letters
stay hidden until both have been sent and are revealed at the same time.

Phases:
  cards    -> drawing and answering cards
  letters  -> writing the closing letters (optional)
  finished -> summary with the saved cards and the letters
"""

import random
import re
from functools import cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "deeper.txt"
LEVELS = ("icebreaker", "deep", "deeper")
SECTIONS = LEVELS + ("wildcard",)
BOTH_PREFIX = "[ambos]"
WILDCARD_EVERY = 6  # on average, one wildcard every this many cards
LETTER_MAX = 1000
HEADER = re.compile(r"^##\s*(\w+)\s*$")


@cache
def deck() -> dict[str, list[dict]]:
    """Every card by section: {"icebreaker": [{"id", "level", "kind", "text"}], ...}."""
    cards: dict[str, list[dict]] = {s: [] for s in SECTIONS}
    section = None
    for line in DATA.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("# "):
            continue
        header = HEADER.match(line)
        if header:
            section = header.group(1).lower()
            if section not in cards:
                raise ValueError(f"Unknown section in deeper.txt: {section}")
            continue
        if section is None:
            continue
        if section == "wildcard":
            kind, text = "wildcard", line
        elif line.startswith(BOTH_PREFIX):
            kind, text = "both", line[len(BOTH_PREFIX):].strip()
        else:
            kind, text = "question", line
        cards[section].append({"id": f"{section}-{len(cards[section])}", "level": section, "kind": kind, "text": text})
    return cards


class DeeperGame:
    name = "deeper"
    actions = {"dp_next", "dp_skip", "dp_save", "dp_deeper", "dp_finish", "dp_letter"}

    def __init__(
        self,
        players: list[str],
        start: str = "icebreaker",
        wildcards: bool = True,
        letter: bool = True,
        rng: random.Random | None = None,
        cards: dict[str, list[dict]] | None = None,
    ):
        self.players = list(players)
        self.start_level = start
        self.wildcards = wildcards
        self.letter = letter
        self.rng = rng or random.Random()
        self.cards = cards or deck()
        self.pools: dict[str, list[dict]] = {}
        self.level = start
        self.phase = "idle"
        self.card: dict | None = None
        self.count = 0  # cards drawn so far; clients send it back as "at"
        self.turn = -1  # index of the player the current card is for
        self.since_wildcard = 0
        self.played = {lvl: 0 for lvl in LEVELS}
        self.skipped = 0
        self.saved: list[dict] = []
        self.votes: dict[str, set[str]] = {"deeper": set(), "finish": set()}
        self.letters: dict[str, str] = {}

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        if len(players) < 2:
            raise ValueError("Más cerca se juega entre los dos. Esperen a que entre tu pareja.")
        start = options.get("start", "icebreaker")
        if start not in LEVELS:
            raise ValueError("Nivel no válido")
        return cls(
            players,
            start=start,
            wildcards=bool(options.get("wildcards", True)),
            letter=bool(options.get("letter", True)),
            rng=rng,
        )

    # --- room interface -------------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase not in ("idle", "finished")

    # No clock: these conversations take the time they take.
    timer_key = None
    timer_seconds = None

    def on_timeout(self) -> None:
        pass

    def start(self) -> None:
        self.phase = "cards"
        self._next_card()

    def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "dp_letter":
            self.write_letter(player, msg.get("text"))
            return
        if self.phase != "cards":
            raise ValueError("Ya no hay cartas en juego")
        if kind in ("dp_next", "dp_skip") and msg.get("at") != self.count:
            return  # both tapped at once: the partner already moved on
        if kind == "dp_next":
            self._next_card()
        elif kind == "dp_skip":
            self.skip()
        elif kind == "dp_save":
            self.toggle_save()
        elif kind == "dp_deeper":
            self.vote(player, "deeper")
        elif kind == "dp_finish":
            self.vote(player, "finish")

    def remove_player(self, player: str) -> None:
        if player in self.players:
            self.players.remove(player)

    # --- cards ----------------------------------------------------------
    @property
    def answerer(self) -> str | None:
        return self.players[self.turn % len(self.players)] if self.players and self.turn >= 0 else None

    def _draw(self, section: str) -> dict:
        pool = self.pools.get(section)
        if not pool:  # first draw, or the section ran out: reshuffle it
            pool = list(self.cards[section])
            self.rng.shuffle(pool)
            if self.card in pool and len(pool) > 1:  # don't repeat the card on screen
                pool.remove(self.card)
                pool.insert(0, self.card)
            self.pools[section] = pool
        return pool.pop()

    def _pick_card(self) -> dict:
        use_wildcard = (
            self.wildcards
            and self.cards.get("wildcard")
            and self.count > 0
            and self.since_wildcard >= 2
            and self.rng.random() < 1 / WILDCARD_EVERY
        )
        if use_wildcard:
            self.since_wildcard = 0
            return self._draw("wildcard")
        self.since_wildcard += 1
        return self._draw(self.level)

    def _next_card(self) -> None:
        self.card = self._pick_card()
        self.count += 1
        self.turn += 1
        if self.card["kind"] != "wildcard":
            self.played[self.card["level"]] += 1

    def skip(self) -> None:
        """Another card for the same player: this one doesn't feel right now."""
        if self.card["kind"] != "wildcard":
            self.played[self.card["level"]] -= 1
        self.skipped += 1
        self.card = self._draw(self.card["level"])
        self.count += 1
        if self.card["kind"] != "wildcard":
            self.played[self.card["level"]] += 1

    def toggle_save(self) -> None:
        card = self.card
        if any(c["id"] == card["id"] for c in self.saved):
            self.saved = [c for c in self.saved if c["id"] != card["id"]]
        else:
            self.saved.append(card)

    def vote(self, player: str, what: str) -> None:
        if what == "deeper" and self.level == LEVELS[-1]:
            raise ValueError("Ya están en el nivel más profundo")
        votes = self.votes[what]
        if player in votes:
            votes.discard(player)  # changed their mind
            return
        votes.add(player)
        if not set(self.players) <= votes:
            return
        self.votes = {"deeper": set(), "finish": set()}
        if what == "deeper":
            self.level = LEVELS[LEVELS.index(self.level) + 1]
            self.since_wildcard = 0  # the new level opens with one of its questions
            self.card = self._draw(self.level)
            self.count += 1
            self.turn += 1
            self.played[self.level] += 1
        else:
            self.card = None
            self.phase = "letters" if self.letter else "finished"

    # --- closing letters ------------------------------------------------
    def write_letter(self, player: str, text) -> None:
        if self.phase != "letters":
            raise ValueError("Todavía no es momento de la carta final")
        if player in self.letters:
            raise ValueError("Ya enviaste tu carta")
        text = (text or "").strip() if isinstance(text, str) else ""
        if not text:
            raise ValueError("Escribe algo para tu pareja")
        if len(text) > LETTER_MAX:
            raise ValueError(f"La carta puede tener hasta {LETTER_MAX} caracteres")
        self.letters[player] = text
        if set(self.players) <= set(self.letters):
            self.phase = "finished"

    # --- state for clients ----------------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        finished = self.phase == "finished"
        return {
            "name": self.name,
            "phase": self.phase,
            "players": self.players,
            "level": self.level,
            "levels": list(LEVELS),
            "card": self.card,
            "count": self.count,
            "answerer": self.answerer,
            "saved": self.saved,
            "savedCurrent": bool(self.card) and any(c["id"] == self.card["id"] for c in self.saved),
            "played": self.played,
            "skipped": self.skipped,
            "votes": {k: sorted(v) for k, v in self.votes.items()},
            # Letters stay sealed until both are written; before that only who sent one.
            "lettersSent": sorted(self.letters),
            "letters": self.letters if finished else ({viewer: self.letters[viewer]} if viewer in self.letters else {}),
            "options": {"start": self.start_level, "wildcards": self.wildcards, "letter": self.letter},
        }
