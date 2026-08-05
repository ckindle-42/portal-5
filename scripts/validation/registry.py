"""Ordered check registry for validate_system.py.
Slug is identity, label is display. Assert slug AND label uniqueness at import.

Ordering is explicit (``order=``) rather than insertion-ordered because the
canonical check sequence interleaves the family modules (config's C/D sit
inside inference's A–H; wiki's AJ/AW/BR–BT interleave security_bench, blue,
and telemetry), so import order alone cannot reproduce the golden sequence.
Checks without an explicit order sort after all ordered checks, preserving
insertion order among themselves.

register() works both as a plain call ``register(slug, label, fn)`` and as a
parameterized decorator ``@register(slug, label, order=N)``.
"""

from __future__ import annotations

from collections.abc import Callable

_CHECKS: list[tuple[str, str, Callable]] = []
_ORDER: dict[str, int] = {}


def register(
    slug: str, label: str, fn: Callable | None = None, *, order: int | None = None
) -> Callable:
    assert slug not in {s for s, _, _ in _CHECKS}, f"duplicate slug {slug}"
    assert label not in {lb for _, lb, _ in _CHECKS}, f"duplicate label {label}"

    def _decorate(func: Callable) -> Callable:
        _CHECKS.append((slug, label, func))
        if order is not None:
            _ORDER[slug] = order
        return func

    if fn is not None:
        return _decorate(fn)
    return _decorate


def all_checks() -> list[tuple[str, str, Callable]]:
    if _ORDER:
        return sorted(_CHECKS, key=lambda c: _ORDER.get(c[0], len(_CHECKS)))
    return list(_CHECKS)
