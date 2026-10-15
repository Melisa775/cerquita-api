import random

import pytest

from app.colors import HSB, delta_e, hsb_to_rgb, random_color, score


def test_hsb_to_rgb_primaries():
    assert hsb_to_rgb(HSB(0, 100, 100)) == pytest.approx((1, 0, 0))
    assert hsb_to_rgb(HSB(120, 100, 100)) == pytest.approx((0, 1, 0))
    assert hsb_to_rgb(HSB(240, 100, 100)) == pytest.approx((0, 0, 1))
    assert hsb_to_rgb(HSB(0, 0, 0)) == pytest.approx((0, 0, 0))


def test_identical_color_scores_ten():
    c = HSB(200, 60, 80)
    assert delta_e(c, c) == 0
    assert score(c, c) == 10


def test_closer_guess_scores_higher():
    target = HSB(30, 80, 90)
    close = HSB(35, 75, 88)
    far = HSB(210, 80, 90)
    assert score(target, close) > score(target, far)
    assert score(target, close) > 7
    assert score(target, far) < 2


def test_score_is_bounded():
    rng = random.Random(1)
    for _ in range(200):
        s = score(random_color(rng), random_color(rng))
        assert 0 <= s <= 10


def test_from_dict_clamps_and_wraps():
    c = HSB.from_dict({"h": 370, "s": 120, "b": -5})
    assert c == HSB(10, 100, 0)


@pytest.mark.parametrize("bad", [{}, {"h": "x", "s": 1, "b": 1}, {"h": None, "s": 1, "b": 1}])
def test_from_dict_rejects_invalid(bad):
    with pytest.raises(ValueError):
        HSB.from_dict(bad)
