import pytest

from app.spelling import phonetic, spelled_ok, suggestion


def test_phonetic_key_matches_sound_alike_spellings():
    assert phonetic("jirafa") == phonetic("girafa")
    assert phonetic("guayaba") == phonetic("guayava")
    assert phonetic("zapato") == phonetic("sapato")
    assert phonetic("llave") == phonetic("yave")
    assert phonetic("helado") == phonetic("elado")
    assert phonetic("perro") == phonetic("perrro")
    assert phonetic("chocolate") == "choko" + "late"


@pytest.mark.parametrize(
    ("category", "answer", "ok"),
    [
        ("color", "Verde limón", True),
        ("color", "asul", False),
        ("fruit", "uchuva", True),  # from the extra list
        ("animal", "oso de anteojos", True),
        ("city", "Bogotá", True),
        ("city", "Zipaquirá", True),
        ("city", "Nueva York", True),
        ("city", "Medelin", False),
        ("name", "Xyzw", True),  # not checked
        ("surname", "Qwerty", True),
    ],
)
def test_spelled_ok(category, answer, ok):
    assert spelled_ok(category, answer) is ok


@pytest.mark.parametrize(
    ("category", "answer", "expected"),
    [
        ("color", "Amarilo", "amarillo"),
        ("color", "asul", "azul"),
        ("animal", "girafa", "jirafa"),
        ("animal", "perrro", "perro"),
        ("fruit", "guayava", "guayaba"),
        ("city", "Barranqilla", "barranquilla"),
        ("city", "Medelin", "medellin"),
        ("thing", "sapato", "zapato"),
        ("color", "qwerty", None),
    ],
)
def test_suggestions(category, answer, expected):
    assert suggestion(category, answer) == expected
