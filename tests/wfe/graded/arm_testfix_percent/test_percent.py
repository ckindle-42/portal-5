import pytest
from percent import percent


def test_quarter():
    assert percent(1, 4) == 25


def test_half():
    assert percent(1, 2) == 50


def test_zero_part():
    assert percent(0, 7) == 0


def test_negative_part():
    assert percent(-1, 4) == -25


def test_zero_whole_is_rejected():
    with pytest.raises(ValueError):
        percent(1, 0)
