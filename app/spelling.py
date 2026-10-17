"""Revisión de ortografía para el Stop.

Ciudad se compara con una lista de ciudades (GeoNames). Fruta, color, animal
y cosa se revisan palabra por palabra contra el diccionario general más una
lista de palabras extra (frutas colombianas, préstamos del inglés, etc.).
Nombre y apellido no se revisan.

Si algo no pasa, se sugiere la palabra más parecida. Para eso se comparan
"claves fonéticas": en español "girafa" y "jirafa", o "guayava" y "guayaba",
suenan igual, así que la sugerencia correcta es la que suena igual aunque
otra palabra se escriba más parecido.
"""

import gzip
import re
from bisect import bisect_left
from difflib import SequenceMatcher, get_close_matches
from functools import cache
from pathlib import Path

from app.dictionary import spanish
from app.games.common import normalize

DATA = Path(__file__).parent / "data"
CHECKED = {"ciudad", "fruta", "color", "animal", "cosa"}
MIN_CHECKED_WORD = 3  # "de", "la", "el" no se revisan


@cache
def cities() -> frozenset[str]:
    with gzip.open(DATA / "ciudades.txt.gz", "rt", encoding="utf-8") as f:
        return frozenset(line.strip() for line in f if line.strip())


@cache
def extra_words() -> frozenset[str]:
    lines = (DATA / "stop_extra.txt").read_text(encoding="utf-8").splitlines()
    return frozenset(normalize(line) for line in lines if line.strip() and not line.startswith("#"))


def phonetic(word: str) -> str:
    """Clave que iguala letras que suenan igual: b/v, s/z/c, j/g, y/ll, h muda."""
    w = word.replace("ch", "#").replace("h", "").replace("qu", "k")
    w = re.sub(r"c(?=[ei])", "s", w).replace("c", "k")
    w = re.sub(r"g(?=[ei])", "j", w)
    w = w.replace("v", "b").replace("z", "s").replace("w", "u").replace("ll", "y")
    w = re.sub(r"y$", "i", w)
    w = re.sub(r"(.)\1+", r"\1", w)  # letras repetidas: "perrro" -> "pero"
    return w.replace("#", "ch")


def _levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# Letras con las que puede empezar una palabra según cómo empieza su clave
_SAME_SOUND = {"b": "bv", "s": "szc", "k": "ckq", "j": "jg", "y": "yl", "i": "iy", "u": "uw"}


@cache
def _sorted(source: str) -> list[str]:
    if source == "ciudad":
        return sorted(cities())
    return sorted({*spanish().words, *extra_words()})


@cache
def _bucket(source: str, initial: str, length: int) -> dict[str, list[str]]:
    """Palabras de largo parecido cuya clave fonética empieza por `initial`."""
    words = _sorted(source)
    out: dict[str, list[str]] = {}
    for first in set(_SAME_SOUND.get(initial, initial) + "h"):
        start = bisect_left(words, first)
        end = bisect_left(words, first + "\uffff")
        for w in words[start:end]:
            if abs(len(w) - length) <= 2:
                key = phonetic(w)
                if key.startswith(initial):
                    out.setdefault(key, []).append(w)
    return out


def _closest(word: str, source: str) -> str | None:
    key = phonetic(word)
    bucket = _bucket(source, key[:1], len(word))
    near = get_close_matches(key, list(bucket), n=10, cutoff=0.7)
    candidates = [w for k in near for w in bucket[k]]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda c: (
            _levenshtein(key, phonetic(c)),  # primero, la que suena más parecido
            -SequenceMatcher(None, word, c).ratio(),  # luego, la que se escribe más parecido
            len(c),
        ),
    )


def _word_ok(word: str) -> bool:
    return len(word) < MIN_CHECKED_WORD or word in spanish() or word in extra_words()


def spelled_ok(category: str, answer: str) -> bool:
    text = normalize(answer)
    if category not in CHECKED or not text:
        return True
    if category == "ciudad":
        return text in cities()
    return text in extra_words() or all(_word_ok(w) for w in text.split())


@cache
def suggestion(category: str, answer: str) -> str | None:
    """La corrección más probable, o None si no hay ninguna parecida."""
    text = normalize(answer)
    if not text or spelled_ok(category, answer):
        return None
    if category == "ciudad":
        return _closest(text, "ciudad")
    fixed = []
    for word in text.split():
        if _word_ok(word):
            fixed.append(word)
            continue
        found = _closest(word, "palabras")
        if not found:
            return None
        fixed.append(found)
    return " ".join(fixed)
