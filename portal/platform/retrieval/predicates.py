"""The one filter seam's clause builder (SUBSTRATE_PROPERTIES_V1 P2).

Two consumers needed the same thing and each built it inline: the Bully went
around ``pipeline.search`` with its own ``key = 'value'`` builder, and the
compliance module had no way at all to push a clock predicate below ranking.
This module is the shared seam's language: callers describe what they mean —
``{"family": "steal"}``, ``("effective_from", "<=", "2026-09-16")``, an
``IN`` list, an OR-group of clock bounds — and ONE place turns that into the
SQL-ish string a LanceDB ``.where()`` accepts.

**Injection is the reason this lives in one place.** Predicate values are tool
arguments an operator — or a model in a tool loop — supplies. A raw caller
string never reaches a clause: every string is single-quoted with embedded
quotes doubled, so ``CIP-007-6' OR 1=1 --`` arrives as one literal value and
matches nothing, instead of being a tautology. Column names come from code,
never from a caller, and are validated anyway.
"""

from __future__ import annotations

import re
from typing import Any

#: a column (or any identifier) that may appear in a clause. Columns are
#: code-authored, but the check is cheap and absolute: an identifier outside
#: this shape never reaches a clause string.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

_OPS = ("=", "!=", "<", "<=", ">", ">=", "LIKE")


def quote(value: str) -> str:
    """A string as a safe single-quoted literal — embedded quotes doubled."""
    return "'" + str(value).replace("'", "''") + "'"


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return quote(value)
    raise ValueError(
        f"unsupported predicate value {value!r} ({type(value).__name__}) — a clause "
        "never interpolates a value it cannot quote"
    )


def _column(name: Any) -> str:
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"unsupported predicate column {name!r}")
    return name


def _clause(column: str, op: str, value: Any) -> str:
    if op not in _OPS:
        raise ValueError(f"unsupported predicate operator {op!r}")
    return f"{_column(column)} {op} {_literal(value)}"


def _in_clause(column: str, values: list[Any] | tuple[Any, ...]) -> str:
    if not values:
        # an empty IN can never match; saying so beats emitting broken SQL
        return "0"
    return f"{_column(column)} IN ({', '.join(_literal(v) for v in values)})"


def _entry(entry: Any) -> str:
    """One conjunction term: a 3-tuple, an IN spec, or a nested OR-group."""
    if isinstance(entry, (list, tuple)) and len(entry) == 3 and entry[0] == "in":
        _, column, values = entry
        return _in_clause(column, values)
    if isinstance(entry, (list, tuple)) and entry and isinstance(entry[0], (list, tuple)):
        # a nested group: its members are OR-joined, parenthesised
        return "(" + " OR ".join(_entry(e) for e in entry) + ")"
    if isinstance(entry, (list, tuple)) and len(entry) == 3:
        return _clause(str(entry[0]), str(entry[1]), entry[2])
    raise ValueError(f"unsupported predicate entry {entry!r}")


def build(spec: dict[str, Any] | list[Any] | None) -> str:
    """The ``.where()`` clause for ``spec``, or ``""`` when nothing is asked.

    * ``None`` / ``{}`` / ``[]`` → ``""`` (no filter — every existing caller).
    * ``{"col": value}`` → AND of equalities (the Bully's former inline shape).
    * ``[(col, op, value), …]`` → AND of comparisons; ops
      ``=  !=  <  <=  >  >=  LIKE`` (the value is quoted either way — a ``%``
      inside a caller string is data unless the caller of ``build`` put it there
      deliberately).
    * ``("in", col, [v…])`` → an ``IN`` list.
    * a nested list of entries → a parenthesised OR-group (the clock bounds:
      ``(effective_from = '' OR effective_from <= '2026-09-16')``).

    Groups AND-join at the top level; entries inside a group OR-join.
    """
    if not spec:
        return ""
    if isinstance(spec, dict):
        entries: list[Any] = [(k, "=", v) for k, v in spec.items()]
    elif isinstance(spec, list):
        entries = list(spec)
    else:
        raise ValueError(f"unsupported predicate spec {type(spec).__name__}")
    return " AND ".join(_entry(e) for e in entries)
