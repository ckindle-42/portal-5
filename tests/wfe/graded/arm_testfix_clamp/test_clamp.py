from clamp import clamp


def test_below_lower_bound():
    assert clamp(-3, 0, 10) == 0


def test_at_lower_bound():
    assert clamp(0, 0, 10) == 0


def test_inside_bounds():
    assert clamp(5, 0, 10) == 5


def test_at_upper_bound():
    assert clamp(10, 0, 10) == 10


def test_above_upper_bound():
    assert clamp(14, 0, 10) == 10
