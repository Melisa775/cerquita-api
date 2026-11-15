"""Build app/data/cities.txt.gz from GeoNames data.

Usage (not needed in production; the file is already generated):
    pip install geonamescache
    python scripts/build_cities.py

Includes:
  - Colombia: every place with more than 500 inhabitants (almost every town).
  - Rest of the world: cities with more than 15,000 inhabitants.
  - Names in other Latin-alphabet languages ("Londres", "Nueva York") for
    cities with more than 100,000 inhabitants. Variants almost identical to
    the official name ("Medelin" for Medellín) are dropped because they are
    usually misspellings, which is exactly what Stop wants to catch.
Names are stored normalized the same way as Stop answers.
"""

import gzip
import json
from difflib import SequenceMatcher
import re
import sys
from pathlib import Path

import geonamescache

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.games.common import normalize  # noqa: E402

DATA = Path(geonamescache.__file__).parent / "data"
LATIN = re.compile(r"^[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ' .\-]+$")


def load(name: str) -> list[dict]:
    return list(json.loads((DATA / name).read_text(encoding="utf-8")).values())


names: set[str] = set()
for city in load("cities500.json"):
    if city["countrycode"] == "CO":
        names.add(normalize(city["name"]))
for city in load("cities15000.json"):
    official = normalize(city["name"])
    names.add(official)
    if city["population"] >= 100_000:
        for alt in city["alternatenames"]:
            alt = normalize(alt) if LATIN.match(alt) else ""
            if alt and SequenceMatcher(None, alt, official).ratio() < 0.85:
                names.add(alt)
names.discard("")

out = ROOT / "app" / "data" / "cities.txt.gz"
out.write_bytes(gzip.compress(("\n".join(sorted(names)) + "\n").encode("utf-8"), 9))
print(f"{len(names)} names -> {out} ({out.stat().st_size // 1024} KB)")
