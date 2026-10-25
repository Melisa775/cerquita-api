import gzip
from bisect import bisect_left
from functools import cache
from pathlib import Path
from typing import Iterable

DATA = Path(__file__).parent / "data" / "palabras.txt.gz"


class Dictionary:
    def __init__(self, words: Iterable[str]):
        self.words = sorted(set(words))
        self._set = set(self.words)

    def __contains__(self, word: str) -> bool:
        return word in self._set

    def __len__(self) -> int:
        return len(self.words)

    def has_prefix(self, prefix: str) -> bool:
        """¿Alguna palabra empieza así? Búsqueda binaria sobre la lista ordenada."""
        i = bisect_left(self.words, prefix)
        return i < len(self.words) and self.words[i].startswith(prefix)


@cache
def spanish() -> Dictionary:
    with gzip.open(DATA, "rt", encoding="utf-8") as f:
        return Dictionary(line.strip() for line in f if line.strip())
