from calc import sum_to_n


def test_sum_to_n_includes_n():
    assert sum_to_n(5) == 15
