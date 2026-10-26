"""Trivia, al estilo Preguntados.

Una ruleta con seis categorías (y una corona) decide de qué es cada
pregunta. Hay dos modos:

  coronas -> por turnos. Quien tiene el turno gira la ruleta y responde.
             Si acierta, sigue jugando y llena un medidor; con tres aciertos
             seguidos (o si la ruleta cae en la corona) elige una categoría
             y juega por su corona. Si falla, el turno pasa a la pareja.
             Gana quien junte primero las coronas de la meta (3 o 6).
  duelo    -> los dos responden la misma pregunta a la vez. Acertar da
             entre 50 y 100 puntos según la rapidez. Gana quien sume más
             al final de las preguntas.

Fases:
  spin        -> esperando que alguien gire (en coronas, solo quien tiene el turno)
  spinning    -> la ruleta gira (los clientes la animan); termina sola
  crown_pick  -> quien tiene el turno elige por qué corona jugar
  question    -> corre el reloj de la pregunta
  reveal      -> se muestra la respuesta correcta y lo que marcó cada uno
Al terminar, la fase es "finished".

Las preguntas viven en app/data/preguntas.json, cada una con su nivel
(facil, medio o dificil); la respuesta correcta es siempre la primera opción
del archivo y el orden se baraja en cada pregunta. En "mezcla" entran todas.
"""

import json
import random
import time
from functools import cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "preguntas.json"
CATEGORIES = ("geografia", "historia", "ciencia", "arte", "entretenimiento", "deportes")
CROWN = "corona"
WHEEL = CATEGORIES + (CROWN,)
MODES = ("coronas", "duelo")
GOALS = (3, 6)
SECONDS_CHOICES = (15, 20, 30)
QUESTION_CHOICES = (10, 15, 20)
LEVELS = ("facil", "medio", "dificil", "mezcla")
STREAK_FOR_CROWN = 3
SPIN_SECONDS = 3.2


@cache
def questions() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))


class TriviaGame:
    name = "trivia"
    actions = {"tv_spin", "tv_crown", "tv_answer", "next_round"}

    def __init__(
        self,
        players: list[str],
        mode: str = "coronas",
        goal: int = 6,
        seconds: int = 20,
        total_questions: int = 10,
        level: str = "mezcla",
        rng: random.Random | None = None,
        timings: dict | None = None,
        bank: list[dict] | None = None,
        clock=time.monotonic,
    ):
        timings = timings or {}
        self.players = list(players)
        self.mode = mode
        self.goal = goal
        self.seconds = seconds
        self.question_seconds = timings.get("question", seconds)
        self.spin_seconds = timings.get("spin", SPIN_SECONDS)
        self.total_questions = total_questions
        self.rng = rng or random.Random()
        self.clock = clock
        self.level = level
        self.bank = [q for q in (bank or questions()) if level == "mezcla" or q.get("level") == level]
        self.pools: dict[str, list[dict]] = {}
        self.phase = "idle"
        self.asked = 0  # preguntas hechas en la partida
        self.turn_index = 0  # en coronas, a quién le toca
        self.category: str | None = None  # resultado de la ruleta
        self.slot: str | None = None  # casilla en la que cayó (puede ser la corona)
        self.spin_id = 0
        self.for_crown = False
        self.question: dict | None = None  # {"id","category","question","options","answer"}
        self.answers: dict[str, dict] = {}  # jugador -> {"choice", "ms"}
        self.started_at = 0.0
        self.last: dict | None = None  # resultado de la última pregunta
        self.streak: dict[str, int] = {p: 0 for p in self.players}
        self.crowns: dict[str, list[str]] = {p: [] for p in self.players}
        self.scores: dict[str, int] = {p: 0 for p in self.players}
        self.correct: dict[str, int] = {p: 0 for p in self.players}
        self.history: list[dict] = []
        self.winner: str | None = None

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        if len(players) < 2:
            raise ValueError("La trivia se juega entre los dos. Esperen a que entre tu pareja.")
        mode = options.get("mode", "coronas")
        if mode not in MODES:
            raise ValueError("Modo no válido")
        try:
            goal = int(options.get("goal", 6))
            seconds = int(options.get("seconds", 20))
            total = int(options.get("questions", 10))
        except (TypeError, ValueError) as exc:
            raise ValueError("Opciones no válidas") from exc
        if goal not in GOALS:
            raise ValueError("La meta es 3 o 6 coronas")
        if seconds not in SECONDS_CHOICES:
            raise ValueError("Elige 15, 20 o 30 segundos por pregunta")
        if total not in QUESTION_CHOICES:
            raise ValueError("Elige 10, 15 o 20 preguntas")
        level = options.get("level", "mezcla")
        if level not in LEVELS:
            raise ValueError("Dificultad no válida")
        return cls(players, mode=mode, goal=goal, seconds=seconds, total_questions=total, level=level, rng=rng, timings=timings)

    # --- interfaz con la sala -------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase not in ("idle", "finished")

    @property
    def current(self) -> str | None:
        """En coronas, quien tiene el turno. En duelo no hay turnos."""
        if self.mode != "coronas" or not self.players:
            return None
        return self.players[self.turn_index % len(self.players)]

    @property
    def timer_key(self):
        if self.phase == "spinning":
            return ("spinning", self.spin_id)
        if self.phase == "question":
            return ("question", self.asked)
        return None

    @property
    def timer_seconds(self) -> float | None:
        if self.phase == "spinning":
            return self.spin_seconds
        if self.phase == "question":
            return self.question_seconds
        return None

    def start(self) -> None:
        self.phase = "spin"

    def on_timeout(self) -> None:
        if self.phase == "spinning":
            self._after_spin()
        elif self.phase == "question":
            self._reveal()

    def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        # Si los dos tocan "Girar" o "Seguir" casi al tiempo, el segundo toque
        # llega cuando ya se avanzó: se ignora en vez de mostrar un error.
        # El cliente manda en "at" el giro o la pregunta que estaba viendo.
        at = msg.get("at")
        if kind == "tv_spin" and at is not None and at != self.spin_id:
            return
        if kind == "next_round" and at is not None and (at != self.asked or self.phase != "reveal"):
            return
        if kind == "tv_spin":
            self.spin(player)
        elif kind == "tv_crown":
            self.choose_crown(player, msg.get("category"))
        elif kind == "tv_answer":
            self.answer(player, msg.get("choice"))
        elif kind == "next_round":
            self.next_round()

    def remove_player(self, player: str) -> None:
        if player in self.players:
            self.players.remove(player)

    # --- ruleta ----------------------------------------------------------
    def missing(self, player: str) -> list[str]:
        return [c for c in CATEGORIES if c not in self.crowns.get(player, [])]

    def _crown_ready(self, player: str) -> bool:
        return self.mode == "coronas" and self.streak.get(player, 0) >= STREAK_FOR_CROWN

    def spin(self, player: str) -> None:
        if self.phase != "spin":
            raise ValueError("Ahora no se puede girar")
        if self.mode == "coronas":
            if player != self.current:
                raise ValueError(f"Le toca girar a {self.current}")
            if self._crown_ready(player):
                raise ValueError("Llenaste el medidor: elige por qué corona vas")
            self.slot = self.rng.choice(WHEEL)
        else:
            self.slot = self.rng.choice(CATEGORIES)
        self.category = None if self.slot == CROWN else self.slot
        self.spin_id += 1
        self.phase = "spinning"

    def _after_spin(self) -> None:
        if self.slot == CROWN:
            self.phase = "crown_pick"
        else:
            self._ask(self.slot, for_crown=False)

    def choose_crown(self, player: str, category) -> None:
        if self.phase != "crown_pick":
            raise ValueError("Ahora no se elige corona")
        if player != self.current:
            raise ValueError(f"Elige {self.current}")
        if category not in self.missing(player):
            raise ValueError("Esa corona no está disponible")
        self._ask(category, for_crown=True)

    # --- preguntas -------------------------------------------------------
    def _draw(self, category: str) -> dict:
        pool = self.pools.get(category)
        if not pool:
            pool = [q for q in self.bank if q["category"] == category]
            self.rng.shuffle(pool)
            self.pools[category] = pool
        raw = pool.pop()
        order = list(range(len(raw["options"])))
        self.rng.shuffle(order)
        return {
            "id": raw["id"],
            "category": category,
            "level": raw.get("level"),
            "question": raw["question"],
            "options": [raw["options"][i] for i in order],
            "answer": order.index(raw["answer"]),
        }

    def _ask(self, category: str, for_crown: bool) -> None:
        self.category = category
        self.for_crown = for_crown
        self.question = self._draw(category)
        self.answers = {}
        self.asked += 1
        self.started_at = self.clock()
        self.phase = "question"

    def answer(self, player: str, choice) -> None:
        if self.phase != "question":
            raise ValueError("No hay ninguna pregunta en juego")
        if self.mode == "coronas" and player != self.current:
            raise ValueError(f"Responde {self.current}")
        if player in self.answers:
            raise ValueError("Ya respondiste")
        if not isinstance(choice, int) or isinstance(choice, bool) or not 0 <= choice < len(self.question["options"]):
            raise ValueError("Respuesta no válida")
        ms = int((self.clock() - self.started_at) * 1000)
        self.answers[player] = {"choice": choice, "ms": ms}
        expected = 1 if self.mode == "coronas" else len(self.players)
        if len(self.answers) >= expected:
            self._reveal()

    def _points(self, ms: int) -> int:
        """En duelo: 100 si responde al instante, 50 si responde al final."""
        total = self.question_seconds * 1000
        frac = min(max(ms / total, 0), 1) if total else 1
        return round(100 - 50 * frac)

    def _reveal(self) -> None:
        q = self.question
        results = {}
        for p in self.players:
            a = self.answers.get(p)
            ok = a is not None and a["choice"] == q["answer"]
            results[p] = {"choice": a["choice"] if a else None, "ms": a["ms"] if a else None, "ok": ok, "points": 0}
        self.last = {"by": self.current, "forCrown": self.for_crown, "results": results, "crownWon": None}

        if self.mode == "duelo":
            for p, r in results.items():
                if r["ok"]:
                    r["points"] = self._points(r["ms"])
                    self.scores[p] += r["points"]
                    self.correct[p] += 1
        else:
            p = self.current
            r = results[p]
            if r["ok"]:
                self.correct[p] += 1
                if self.for_crown:
                    self.crowns[p].append(q["category"])
                    self.last["crownWon"] = q["category"]
                    self.streak[p] = 0
                else:
                    self.streak[p] = min(self.streak[p] + 1, STREAK_FOR_CROWN)
            else:
                self.streak[p] = 0
            self.scores[p] = len(self.crowns[p])

        self.history.append({"n": self.asked, "question": q, "by": self.current, "forCrown": self.for_crown, "results": results})
        self.phase = "reveal"

    def next_round(self) -> None:
        if self.phase != "reveal":
            raise ValueError("Todavía no hay siguiente pregunta")
        if self.mode == "duelo":
            if self.asked >= self.total_questions:
                self._finish()
            else:
                self.phase = "spin"
            return
        p = self.current
        if len(self.crowns[p]) >= self.goal:
            self.winner = p
            self._finish()
            return
        if not self.last["results"][p]["ok"]:
            self.turn_index += 1
        self.phase = "crown_pick" if self._crown_ready(self.current) else "spin"

    def _finish(self) -> None:
        if self.mode == "duelo":
            best = max(self.scores.values(), default=0)
            leaders = [p for p, s in self.scores.items() if s == best]
            self.winner = leaders[0] if len(leaders) == 1 else None
        self.question = None
        self.phase = "finished"

    # --- estado para los clientes ---------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        q = self.question
        public_q = None
        if q and self.phase in ("question", "reveal"):
            public_q = {"id": q["id"], "category": q["category"], "level": q["level"], "question": q["question"], "options": q["options"]}
            if self.phase == "reveal":
                public_q["answer"] = q["answer"]
        answered = list(self.answers) if self.phase == "question" else []
        mine = self.answers.get(viewer, {}).get("choice") if viewer and self.phase == "question" else None
        return {
            "name": self.name,
            "phase": self.phase,
            "mode": self.mode,
            "players": self.players,
            "current": self.current,
            "slot": self.slot,
            "spinId": self.spin_id,
            "category": self.category,
            "forCrown": self.for_crown,
            "question": public_q,
            # Durante la pregunta solo se sabe quién respondió, no qué
            "answered": answered,
            "myChoice": mine,
            "last": self.last if self.phase in ("reveal", "finished") else None,
            "asked": self.asked,
            "totalQuestions": self.total_questions,
            "goal": self.goal,
            "streak": self.streak,
            "streakForCrown": STREAK_FOR_CROWN,
            "crowns": self.crowns,
            "scores": self.scores,
            "correct": self.correct,
            "seconds": self.question_seconds,
            "spinSeconds": self.spin_seconds,
            "winner": self.winner,
            "history": self.history if self.phase == "finished" else [],
            "options": {"mode": self.mode, "goal": self.goal, "seconds": self.seconds, "questions": self.total_questions, "level": self.level},
        }
