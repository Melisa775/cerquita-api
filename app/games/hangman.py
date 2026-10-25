"""Ahorcado.

Dos modos:
  - "turns" (nos turnamos): en cada ronda uno escribe una palabra o frase
    corta, con una pista opcional, y el otro la adivina letra por letra. Si
    la adivina gana un punto; si se le acaban las vidas, el punto es para
    quien la eligió. Los papeles se alternan.
  - "random" (Cerquita elige): sale una palabra al azar de una categoría y
    los dos la adivinan juntos, compartiendo las vidas.

Las letras se comparan sin tildes (la "a" destapa también la "á"), pero la
ñ es su propia letra.

Flujo de cada ronda:
  choosing   -> (solo en "turns") quien elige escribe la palabra
  guessing   -> se adivinan letras o se arriesga la palabra completa
  round_over -> se revela la palabra
Tras la última ronda la fase es "finished".
"""

import random
import re
import unicodedata

from app.games.common import normalize, parse_rounds

LIVES_CHOICES = (6, 8, 10)
DEFAULT_LIVES = 6
MAX_WORD = 30
MAX_HINT = 60
MIN_LETTERS = 3
ALLOWED = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ \-]*$")
LETTERS = set("abcdefghijklmnñopqrstuvwxyz")

WORDS = {
    "Animales": [
        "mariposa", "jirafa", "pingüino", "colibrí", "tortuga", "murciélago", "camaleón",
        "hipopótamo", "ardilla", "delfín", "guacamaya", "chigüiro", "flamenco", "pulpo", "búho",
    ],
    "Comida colombiana": [
        "arepa", "bandeja paisa", "ajiaco", "sancocho", "empanada", "buñuelo", "natilla",
        "lechona", "tamal", "pandebono", "almojábana", "changua", "patacón", "arroz con coco",
    ],
    "Frutas": [
        "maracuyá", "guanábana", "pitahaya", "mandarina", "granadilla", "uchuva", "papaya",
        "guayaba", "mamoncillo", "lulo", "sandía", "frambuesa", "mango biche", "feijoa",
    ],
    "Cosas de la casa": [
        "almohada", "lavadora", "escoba", "nevera", "cortina", "licuadora", "espejo",
        "sofá", "lámpara", "tostadora", "ventilador", "perchero", "cobija", "control remoto",
    ],
    "Lugares de Colombia": [
        "cartagena", "medellín", "guatapé", "san andrés", "barichara", "villa de leyva",
        "santa marta", "salento", "leticia", "caño cristales", "popayán", "mompox", "tayrona",
    ],
    "Para una cita": [
        "picnic", "cine en casa", "atardecer", "chocolate", "serenata", "karaoke",
        "baile", "helado", "fotografía", "cena con velas", "paseo en bicicleta", "rompecabezas",
    ],
    "Cosas que se extrañan": [
        "abrazo", "videollamada", "carta", "perfume", "risas", "canción", "mensaje",
        "reencuentro", "aeropuerto", "maleta", "cuenta regresiva", "buenos días",
    ],
    "Profesiones": [
        "astronauta", "bombero", "veterinaria", "programadora", "panadero", "arquitecta",
        "fotógrafo", "enfermero", "carpintero", "piloto", "periodista", "científica",
    ],
    "Deportes": [
        "fútbol", "baloncesto", "natación", "ciclismo", "patinaje", "voleibol",
        "tenis de mesa", "escalada", "atletismo", "surf", "boxeo", "ajedrez",
    ],
    "Naturaleza": [
        "cascada", "volcán", "arcoíris", "páramo", "frailejón", "relámpago",
        "manglar", "girasol", "orquídea", "montaña", "neblina", "luciérnaga",
    ],
    "Música e instrumentos": [
        "guitarra", "acordeón", "tambor", "maracas", "violín", "trompeta",
        "vallenato", "cumbia", "salsa", "flauta", "piano", "champeta",
    ],
    "Viajes": [
        "pasaporte", "equipaje", "aeropuerto", "mochila", "hostal", "brújula",
        "souvenir", "excursión", "crucero", "postal", "mapa", "bloqueador",
    ],
}


def base_letter(ch: str) -> str:
    """'Á' -> 'a', 'ü' -> 'u', 'Ñ' -> 'ñ'. Lo que no sea letra queda igual."""
    low = ch.lower()
    if low == "ñ":
        return "ñ"
    stripped = "".join(c for c in unicodedata.normalize("NFD", low) if unicodedata.category(c) != "Mn")
    return stripped


def clean_word(raw) -> str:
    return re.sub(r"\s+", " ", str(raw or "")).strip()


class HangmanGame:
    name = "hangman"
    actions = {"hangman_word", "hangman_guess", "hangman_solve", "next_round"}

    def __init__(
        self,
        players: list[str],
        mode: str = "turns",
        lives: int = DEFAULT_LIVES,
        rounds: int = 4,
        rng: random.Random | None = None,
        timings: dict | None = None,
        words: dict[str, list[str]] | None = None,
    ):
        self.players = list(players)
        self.mode = mode
        self.lives = lives
        self.total_rounds = rounds
        self.rng = rng or random.Random()
        self.words = words or WORDS
        self.used_words: set[str] = set()
        self.phase = "idle"
        self.round = 0
        self.setter: str | None = None
        self.word = ""
        self.hint = ""
        self.category: str | None = None
        self.guessed: list[str] = []  # letras probadas, en orden
        self.wrong_solves: list[str] = []  # palabras arriesgadas que no eran
        self.result: dict | None = None
        self.scores: dict[str, int] = {p: 0 for p in self.players}
        self.saved = 0  # modo "random": palabras que salvaron juntos
        self.history: list[dict] = []

    @classmethod
    def from_options(cls, players: list[str], options: dict, rng: random.Random, timings: dict | None = None):
        mode = options.get("mode", "turns")
        if mode not in ("turns", "random"):
            raise ValueError("Modo no válido")
        if mode == "turns" and len(players) < 2:
            raise ValueError("Para turnarse necesitan estar los dos. Prueben «Cerquita elige».")
        try:
            lives = int(options.get("lives", DEFAULT_LIVES))
        except (TypeError, ValueError) as exc:
            raise ValueError("Vidas no válidas") from exc
        if lives not in LIVES_CHOICES:
            raise ValueError("Vidas no válidas")
        rounds = parse_rounds(options, 4)
        return cls(players, mode=mode, lives=lives, rounds=rounds, rng=rng, timings=timings)

    # --- interfaz con la sala -------------------------------------------
    @property
    def in_progress(self) -> bool:
        return self.phase not in ("idle", "finished")

    timer_key = None  # el ahorcado no tiene reloj: se juega con calma
    timer_seconds = None

    def start(self) -> None:
        self.start_round()

    def on_timeout(self) -> None:
        pass

    def handle(self, player: str, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "hangman_word":
            self.set_word(player, msg.get("word"), msg.get("hint"))
        elif kind == "hangman_guess":
            self.guess(player, msg.get("letter"))
        elif kind == "hangman_solve":
            self.solve(player, msg.get("word"))
        elif kind == "next_round":
            self.next_round()

    def remove_player(self, player: str) -> None:
        if player in self.players:
            self.players.remove(player)

    # --- quién hace qué ---------------------------------------------------
    @property
    def guessers(self) -> list[str]:
        return [p for p in self.players if p != self.setter]

    @property
    def misses(self) -> int:
        wrong_letters = [c for c in self.guessed if c not in self._letters_in_word()]
        return len(wrong_letters) + len(self.wrong_solves)

    def _letters_in_word(self) -> set[str]:
        return {base_letter(c) for c in self.word if base_letter(c) in LETTERS}

    def _solved(self) -> bool:
        return self._letters_in_word() <= set(self.guessed)

    # --- transiciones ---------------------------------------------------
    def start_round(self) -> None:
        if self.phase not in ("idle", "round_over"):
            raise ValueError("No se puede iniciar ronda ahora")
        if self.round >= self.total_rounds:
            raise ValueError("El juego ya terminó")
        self.round += 1
        self.guessed = []
        self.wrong_solves = []
        self.result = None
        self.hint = ""
        if self.mode == "turns":
            self.setter = self.players[(self.round - 1) % len(self.players)]
            self.word = ""
            self.category = None
            self.phase = "choosing"
        else:
            self.setter = None
            self.category, self.word = self._random_word()
            self.phase = "guessing"

    def _random_word(self) -> tuple[str, str]:
        options = [(cat, w) for cat, words in self.words.items() for w in words if w not in self.used_words]
        if not options:
            self.used_words.clear()
            options = [(cat, w) for cat, words in self.words.items() for w in words]
        category, word = self.rng.choice(options)
        self.used_words.add(word)
        return category, word

    def set_word(self, player: str, raw, hint) -> None:
        if self.phase != "choosing":
            raise ValueError("No es momento de elegir palabra")
        if player != self.setter:
            raise ValueError("Esta vez le toca elegir a tu pareja")
        word = clean_word(raw)
        if len(word) > MAX_WORD:
            raise ValueError(f"Máximo {MAX_WORD} caracteres")
        if not ALLOWED.match(word):
            raise ValueError("Usa solo letras y espacios")
        if len({base_letter(c) for c in word if base_letter(c) in LETTERS}) < 2 or sum(c.isalpha() for c in word) < MIN_LETTERS:
            raise ValueError(f"La palabra necesita al menos {MIN_LETTERS} letras")
        self.word = word
        self.hint = clean_word(hint)[:MAX_HINT]
        self.phase = "guessing"

    def guess(self, player: str, letter) -> None:
        if self.phase != "guessing":
            raise ValueError("No es momento de adivinar")
        if player not in self.guessers:
            raise ValueError("Tú elegiste la palabra: te toca mirar")
        letter = base_letter(str(letter or "").strip()[:1])
        if letter not in LETTERS:
            raise ValueError("Esa no es una letra")
        if letter in self.guessed:
            raise ValueError("Esa letra ya salió")
        self.guessed.append(letter)
        self._check_end(player)

    def solve(self, player: str, raw) -> None:
        """Arriesgar la palabra completa. Si no es, cuesta una vida."""
        if self.phase != "guessing":
            raise ValueError("No es momento de adivinar")
        if player not in self.guessers:
            raise ValueError("Tú elegiste la palabra: te toca mirar")
        attempt = clean_word(raw)
        if not attempt:
            raise ValueError("Escribe la palabra")
        if normalize(attempt).replace(" ", "") == normalize(self.word).replace(" ", ""):
            for c in self._letters_in_word():
                if c not in self.guessed:
                    self.guessed.append(c)
        else:
            self.wrong_solves.append(attempt)
        self._check_end(player)

    def _check_end(self, player: str) -> None:
        if self._solved():
            self._end_round(won=True, by=player)
        elif self.misses >= self.lives:
            self._end_round(won=False, by=player)

    def _end_round(self, won: bool, by: str) -> None:
        if self.mode == "turns":
            winner = by if won else self.setter
            self.scores[winner] = self.scores.get(winner, 0) + 1
        else:
            winner = None
            if won:
                self.saved += 1
        self.result = {"won": won, "by": by, "winner": winner, "livesLeft": self.lives - self.misses}
        self.history.append({
            "round": self.round,
            "word": self.word,
            "setter": self.setter,
            "category": self.category,
            "won": won,
            "winner": winner,
            "misses": self.misses,
        })
        self.phase = "round_over"

    def next_round(self) -> None:
        if self.phase != "round_over":
            raise ValueError("Todavía no hay siguiente ronda")
        if self.round >= self.total_rounds:
            self.phase = "finished"
        else:
            self.start_round()

    # --- estado para los clientes ---------------------------------------
    def snapshot(self, viewer: str | None = None) -> dict:
        reveal_all = self.phase in ("round_over", "finished") or (viewer is not None and viewer == self.setter)
        guessed = set(self.guessed)
        slots = []
        for ch in self.word:
            base = base_letter(ch)
            is_letter = base in LETTERS
            found = is_letter and base in guessed
            slots.append({
                "char": ch if (not is_letter or found or reveal_all) else None,
                "letter": is_letter,
                "found": found,
            })
        in_word = self._letters_in_word()
        return {
            "name": self.name,
            "phase": self.phase,
            "mode": self.mode,
            "round": self.round,
            "totalRounds": self.total_rounds,
            "setter": self.setter,
            "guessers": self.guessers,
            # Mientras adivinan, solo quien eligió la palabra la ve completa.
            "slots": slots if self.phase != "choosing" else [],
            "hint": self.hint,
            "category": self.category,
            "guessed": self.guessed,
            "wrong": [c for c in self.guessed if c not in in_word],
            "wrongSolves": self.wrong_solves,
            "misses": self.misses,
            "lives": self.lives,
            "result": self.result,
            "scores": self.scores,
            "saved": self.saved,
            "history": self.history if self.phase == "finished" else [],
            "options": {"mode": self.mode, "lives": self.lives, "rounds": self.total_rounds},
        }
