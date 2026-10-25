
#Utilidades compartidas por los juegos.

import re
import unicodedata

DEFAULT_ROUNDS = 5


def parse_rounds(options: dict, default: int = DEFAULT_ROUNDS) -> int:
    try:
        rounds = int(options.get("rounds", default))
    except (TypeError, ValueError) as exc:
        raise ValueError("Elige entre 1 y 10 rondas") from exc
    if not 1 <= rounds <= 10:
        raise ValueError("Elige entre 1 y 10 rondas")
    return rounds


def normalize(text: str) -> str:
   
    text = text.strip().lower().replace("ñ", "\0")
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = text.replace("\0", "ñ")
    text = re.sub(r"[^a-z0-9ñ ]+", "", text)
    return re.sub(r"\s+", " ", text).strip()
