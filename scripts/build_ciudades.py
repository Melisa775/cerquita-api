"""Genera app/data/ciudades.txt.gz a partir de los datos de GeoNames.

Uso (no hace falta en producción; el archivo ya está generado):
    pip install geonamescache
    python scripts/build_ciudades.py

Incluye:
  - Colombia: todos los lugares con más de 500 habitantes (casi todos los municipios).
  - Resto del mundo: ciudades de más de 15.000 habitantes.
  - Nombres en otros idiomas en alfabeto latino ("Londres", "Nueva York") para
    ciudades de más de 100.000 habitantes. Se descartan las variantes casi
    iguales al nombre oficial ("Medelin" para Medellín) porque suelen ser
    errores de ortografía, que es justo lo que el Stop quiere detectar.
Los nombres se guardan normalizados igual que las respuestas del Stop.
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

out = ROOT / "app" / "data" / "ciudades.txt.gz"
out.write_bytes(gzip.compress(("\n".join(sorted(names)) + "\n").encode("utf-8"), 9))
print(f"{len(names)} nombres -> {out} ({out.stat().st_size // 1024} KB)")
