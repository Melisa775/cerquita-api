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
        ("fruta", "uchuva", True),  # de la lista extra
        ("animal", "oso de anteojos", True),
        ("ciudad", "Bogotá", True),
        ("ciudad", "Zipaquirá", True),
        ("ciudad", "Nueva York", True),
        ("ciudad", "Medelin", False),
        ("nombre", "Xyzw", True),  # no se revisa
        ("apellido", "Qwerty", True),
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
        ("fruta", "guayava", "guayaba"),
        ("ciudad", "Barranqilla", "barranquilla"),
        ("ciudad", "Medelin", "medellin"),
        ("cosa", "sapato", "zapato"),
        ("color", "qwerty", None),
    ],
)
def test_suggestions(category, answer, expected):
    assert suggestion(category, answer) == expected
