def _validate_n(n):
    if not isinstance(n, int):
        raise TypeError("n must be an integer")
    if n < 0:
        raise ValueError("n must be non-negative")
    return n


def sum_to_n(n):
    "Return the sum of the positive integers through n."
    n = _validate_n(n)
    if n == 0:
        return 0
    total = 0
    for value in range(1, n):
        total += value
    return total
