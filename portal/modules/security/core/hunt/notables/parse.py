"""Event structure discovery: the event's own text decides its fields, never a source table."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree

MAX_VALUE_CHARS = 400  # effort budget: characters kept from one field value
MAX_KEY_CHARS = 120  # effort budget: characters kept from one generated field name
EXAMPLE_CHARS = 80  # effort budget: characters kept from one value shown to the model
EXAMPLES_PER_FIELD = 3  # effort budget: distinct values shown to the model per field
MAX_FIELDS = 24  # effort budget: fields described for one source
MIN_STRUCTURE_SHARE = 0.5  # a structure describes a sample only when most lines share it
MAX_LIST_ITEMS = 20  # effort budget: list entries flattened for one JSON field
_KV = re.compile(r"(?<![\w.\-])([A-Za-z_][\w./\-]{0,60})=(\"[^\"]*\"|'[^']*'|[^\s,;]+)")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_.\- ]{0,40}")
_DELIMITERS = ("\t", ",", "|", ";")


@dataclass(frozen=True)
class Parsed:
    """One event's text as fields; `fmt` is the structure it was read with."""

    fmt: str
    fields: Mapping[str, str]


@dataclass(frozen=True)
class FieldStat:
    """What one sample says about one field: presence, variety, and a few values."""

    name: str
    present: int
    distinct: int
    examples: tuple[str, ...]
    lines: int

    @property
    def repeats(self) -> bool:
        """True when some value is observed at least twice in the sample."""
        return self.distinct < self.present


def _clip(value: str, limit: int) -> str:
    text = value.strip().replace("\r", " ").replace("\n", " ")
    return text[:limit]


def _flatten(value: Any, prefix: str, out: dict[str, str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            _flatten(item, name, out)
        return
    if isinstance(value, list):
        scalars = [item for item in value if not isinstance(item, (Mapping, list))]
        if len(scalars) == len(value):
            out[_clip(prefix, MAX_KEY_CHARS)] = _clip(
                ",".join(str(item) for item in value), MAX_VALUE_CHARS
            )
            return
        for index, item in enumerate(value[:MAX_LIST_ITEMS]):
            _flatten(item, f"{prefix}[{index}]", out)
        return
    out[_clip(prefix, MAX_KEY_CHARS)] = _clip(str(value), MAX_VALUE_CHARS)


def parse_json(line: str) -> dict[str, str]:
    try:
        value = json.loads(line)
    except (ValueError, TypeError):
        return {}
    fields: dict[str, str] = {}
    _flatten(value, "", fields)
    return {name: item for name, item in fields.items() if name}


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_xml(line: str) -> dict[str, str]:
    try:
        root = ElementTree.fromstring(line)
    except ElementTree.ParseError:
        return {}
    fields: dict[str, str] = {}
    for element in root.iter():
        text = (element.text or "").strip()
        tag = _localname(str(element.tag))
        if not tag:
            continue
        if element.attrib:
            for attr_name, attr_value in sorted(element.attrib.items()):
                key = f"{tag}[{_localname(str(attr_name))}={attr_value}]"
                fields.setdefault(_clip(key, MAX_KEY_CHARS), _clip(text, MAX_VALUE_CHARS))
        elif text:
            fields.setdefault(_clip(tag, MAX_KEY_CHARS), _clip(text, MAX_VALUE_CHARS))
    return fields


def parse_kv(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in _KV.finditer(line):
        key = match.group(1)
        value = match.group(2)
        if value[:1] in {'"', "'"} and value[-1:] == value[:1]:
            value = value[1:-1]
        fields.setdefault(_clip(key, MAX_KEY_CHARS), _clip(value, MAX_VALUE_CHARS))
    return fields if len(fields) >= 2 else {}


def _width(rows: Sequence[list[str]]) -> int:
    counts: dict[int, int] = {}
    for row in rows:
        if len(row) > 1:
            counts[len(row)] = counts.get(len(row), 0) + 1
    if not counts:
        return 0
    return max(counts, key=lambda width: (counts[width], width))


def _header(first: Sequence[str], body: Sequence[Sequence[str]]) -> list[str] | None:
    """A first row of label-like cells that never recurs as data names the columns."""
    if len(first) < 2 or not all(_WORD.fullmatch(cell.strip()) for cell in first):
        return None
    seen = {cell.strip() for row in body for cell in row}
    if any(cell.strip() in seen for cell in first):
        return None
    return [cell.strip() for cell in first]


def _delimited(lines: Sequence[str]) -> list[Parsed] | None:
    for delimiter in _DELIMITERS:
        rows = [line.split(delimiter) for line in lines]
        width = _width(rows)
        if width < 2:
            continue
        matched = [row for row in rows if len(row) == width]
        if len(matched) / len(lines) < MIN_STRUCTURE_SHARE:
            continue
        header = _header(matched[0], matched[1:])
        names = header or [f"c{index + 1}" for index in range(width)]
        body = matched[1:] if header else matched
        parsed: list[Parsed] = []
        for row in body:
            if len(row) == width:
                fields = {
                    _clip(name, MAX_KEY_CHARS): _clip(cell, MAX_VALUE_CHARS)
                    for name, cell in zip(names, row, strict=True)
                }
                parsed.append(Parsed("delimited", fields))
            else:
                parsed.append(Parsed("text", {}))
        return parsed or None
    return None


Parser = Callable[[str], dict[str, str]]
_PARSERS: tuple[tuple[str, Parser], ...] = (
    ("json", parse_json),
    ("xml", parse_xml),
    ("kv", parse_kv),
)


def _apply(name: str, parser: Parser, lines: Sequence[str]) -> list[Parsed] | None:
    parsed = [Parsed(name if (fields := parser(line)) else "text", fields) for line in lines]
    hits = sum(1 for item in parsed if item.fields)
    if hits / len(lines) < MIN_STRUCTURE_SHARE:
        return None
    return parsed


def parse_events(raws: Sequence[str]) -> list[Parsed]:
    """Read a sample with the first structure most of its lines support, else free text."""
    lines = [str(raw) for raw in raws if str(raw).strip()]
    if not lines:
        return []
    for name, parser in _PARSERS:
        parsed = _apply(name, parser, lines)
        if parsed is not None:
            return parsed
    delimited = _delimited(lines)
    if delimited is not None:
        return delimited
    return [Parsed("text", {}) for _ in lines]


def parse_with(raw: str, fmt: str) -> Parsed:
    """Read one event with the structure its source was sampled with."""
    parsers: dict[str, Parser] = dict(_PARSERS)
    if fmt == "delimited":
        parsed = _delimited([raw])
        if parsed:
            return parsed[0]
        return Parsed("text", {})
    parser = parsers.get(fmt)
    fields = parser(raw) if parser is not None else {}
    return Parsed(fmt if fields else "text", fields)


def parse_row(raw: str, fmt: str, columns: Sequence[str] = ()) -> Parsed:
    """Read one event into the column names the sample established."""
    if fmt != "delimited":
        return parse_with(raw, fmt)
    if not columns:
        return Parsed("text", {})
    for delimiter in _DELIMITERS:
        cells = raw.split(delimiter)
        if len(cells) == len(columns):
            fields = {
                _clip(name, MAX_KEY_CHARS): _clip(cell, MAX_VALUE_CHARS)
                for name, cell in zip(columns, cells, strict=True)
            }
            return Parsed("delimited", fields)
    return Parsed("text", {})


def field_stats(parsed: Sequence[Parsed]) -> list[FieldStat]:
    """Per-field presence, distinct count and first distinct values, in sample order."""
    order: list[str] = []
    present: dict[str, int] = {}
    distinct: dict[str, set[str]] = {}
    for item in parsed:
        for name, value in item.fields.items():
            if name not in present:
                order.append(name)
                present[name] = 0
                distinct[name] = set()
            present[name] += 1
            distinct[name].add(value)
    return [
        FieldStat(
            name,
            present[name],
            len(distinct[name]),
            tuple(value[:EXAMPLE_CHARS] for value in sorted(distinct[name])[:EXAMPLES_PER_FIELD]),
            len(parsed),
        )
        for name in order[:MAX_FIELDS]
    ]
