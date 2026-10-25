from dataclasses import dataclass
import math
import random


@dataclass(frozen=True)
class HSB:
    h: float  # 0–360
    s: float  # 0–100
    b: float  # 0–100

    @classmethod
    def from_dict(cls, data: dict) -> "HSB":
        try:
            h = float(data["h"]) % 360
            s = min(max(float(data["s"]), 0), 100)
            b = min(max(float(data["b"]), 0), 100)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Color inválido") from exc
        return cls(h, s, b)

    def to_dict(self) -> dict:
        return {"h": round(self.h, 1), "s": round(self.s, 1), "b": round(self.b, 1)}


def hsb_to_rgb(c: HSB) -> tuple[float, float, float]:
    s, v = c.s / 100, c.b / 100
    k = lambda n: (n + c.h / 60) % 6  # noqa: E731
    f = lambda n: v - v * s * max(0, min(k(n), 4 - k(n), 1))  # noqa: E731
    return f(5), f(3), f(1)


def _srgb_to_linear(u: float) -> float:
    return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4


def rgb_to_lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (_srgb_to_linear(u) for u in rgb)
    # sRGB -> XYZ (D65)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a: HSB, b: HSB) -> float:
    """Distancia perceptual CIE76 entre dos colores."""
    la, lb = rgb_to_lab(hsb_to_rgb(a)), rgb_to_lab(hsb_to_rgb(b))
    return math.dist(la, lb)


def score(target: HSB, guess: HSB, tolerance: float = 45) -> float:
    """Puntaje de 0 a 10. Idéntico = 10; muy lejos = 0.

    La curva castiga suave los errores pequeños y fuerte los grandes,
    para que acercarse "bastante" se sienta recompensado. Con menos
    tolerancia, el mismo error vale menos puntos (niveles difíciles).
    """
    d = delta_e(target, guess)
    return round(10 * math.exp(-((d / tolerance) ** 1.6)), 2)


def random_color(
    rng: random.Random,
    saturation: tuple[float, float] = (35, 100),
    brightness: tuple[float, float] = (40, 100),
) -> HSB:
    # Por defecto evita grises y casi negros: son casi imposibles de recordar.
    # Los niveles difíciles abren el rango a colores apagados y oscuros.
    return HSB(rng.uniform(0, 360), rng.uniform(*saturation), rng.uniform(*brightness))
