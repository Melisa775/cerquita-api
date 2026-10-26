"""Los nueve hoyos del mini golf (diseño propio). Campo de 100 × 150.

Coordenadas: x hacia la derecha, y hacia abajo. El primer muro de cada hoyo
es el borde del green (cerrado). Los rectángulos son [x, y, ancho, alto] y
las inclinaciones llevan además la aceleración [ax, ay].
"""


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


COURSES = [
    {
        "name": "Calentamiento",
        "par": 2,
        "tee": [50, 125],
        "hole": [50, 32],
        "walls": [rect(22, 12, 78, 140)],
    },
    {
        "name": "La ele",
        "par": 3,
        "tee": [27, 126],
        "hole": [74, 34],
        "walls": [[[10, 140], [44, 140], [44, 58], [90, 58], [90, 14], [10, 14], [10, 140]]],
    },
    {
        "name": "Pinball",
        "par": 2,
        "tee": [50, 128],
        "hole": [50, 24],
        "walls": [rect(12, 12, 88, 140)],
        "bumpers": [[34, 88, 6], [66, 88, 6], [50, 64, 7], [29, 44, 5], [71, 44, 5]],
    },
    {
        "name": "El río",
        "par": 3,
        "tee": [25, 125],
        "hole": [75, 28],
        "walls": [rect(12, 12, 88, 140)],
        "water": [[12, 68, 32, 16], [56, 68, 32, 16]],
    },
    {
        "name": "Arenal",
        "par": 3,
        "tee": [30, 128],
        "hole": [50, 26],
        "walls": [rect(15, 10, 85, 140), [[15, 90], [58, 90]]],
        "sand": [[27, 34, 15, 10], [58, 34, 15, 10], [38, 46, 24, 9]],
    },
    {
        "name": "La loma",
        "par": 4,
        "tee": [40, 128],
        "hole": [64, 22],
        "walls": [rect(14, 10, 86, 140), [[14, 106], [60, 106]], [[40, 36], [86, 36]]],
        "slopes": [[14, 50, 72, 42, 0, 30]],
    },
    {
        "name": "Portal",
        "par": 2,
        "tee": [30, 126],
        "hole": [50, 28],
        "walls": [rect(12, 10, 88, 140), [[12, 100], [70, 100], [70, 140]]],
        "portals": [[55, 112, 50, 72]],
    },
    {
        "name": "Laberinto",
        "par": 4,
        "tee": [24, 128],
        "hole": [32, 26],
        "walls": [rect(10, 10, 90, 140), [[10, 110], [70, 110]], [[30, 80], [90, 80]], [[10, 50], [70, 50]]],
        "bumpers": [[80, 96, 4], [20, 66, 4]],
    },
    {
        "name": "La isla",
        "par": 3,
        "tee": [50, 128],
        "hole": [50, 30],
        "walls": [rect(10, 10, 90, 140)],
        "water": [[10, 58, 35, 30], [55, 58, 35, 30], [10, 10, 22, 48], [68, 10, 22, 48]],
    },
]
