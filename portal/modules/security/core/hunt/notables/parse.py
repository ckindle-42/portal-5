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
MAX_FIELDS = 48  # effort budget: fields described for one source
MIN_STRUCTURE_SHARE = 0.5  # a structure describes a sample only when most lines share it
MAX_LIST_ITEMS = 20  # effort budget: list entries flattened for one JSON field
MIN_DELIMITED_WIDTH = 3  # a delimiter describes a record only when it yields this many columns
HEADER_MAX_TOKENS = 8  # effort budget: leading tokens searched for the program boundary
MIN_PROGRAM_LINES = 3  # a program needs this many sampled lines to be described
MIN_TEMPLATE_LINES = 3  # a template needs this many lines to be kept
MIN_TEMPLATE_TOKENS = 2  # a message template needs this many tokens
MAX_TEMPLATES_PER_PROGRAM = 12  # effort budget: templates kept for one program
MAX_TEMPLATES_PER_SOURCE = 24  # effort budget: templates kept for one source
MAX_TEMPLATE_SLOTS = 6  # effort budget: variable positions carried from one template
TIME_ORDER_SHARE = 0.9  # a value that moves with event order is time or a sequence
MAX_PARTITIONS = 8  # effort budget: distinct structures one source is split into
MIN_PARTITION_LINES = 4  # a part needs this many sampled events to be described
MIN_PARTITION_DISTANCE = 0.25  # groups must differ by at least this mean Jaccard field distance
_OPENERS = "([{"
_CLOSERS = ")]}"
_KV = re.compile(r"(?<![\w.\-])([A-Za-z_][\w./\-]{0,60})=(\"[^\"]*\"|'[^']*'|[^\s,;]+)")
_COLON_LABEL = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _./\-]{0,60}?):\s+(\S.*?)\s*$")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_.\- ]{0,40}")
_VAR_TOKEN = re.compile(r"^(?:\d{5,}|[IWEF]\d{4}|\d{2}:\d{2}:\d{2}(?:\.\d+)?)$")
_DELIMITERS = ("\t", ",", "|", ";")


@dataclass(frozen=True)
class Parsed:
    """One event's text as fields; `fmt` is the structure it was read with."""

    fmt: str
    fields: Mapping[str, str]


@dataclass(frozen=True)
class Template:
    """One message template: constant tokens, slots (None), and the recurring slots carried."""

    program: str
    tokens: tuple[str | None, ...]
    count: int
    slots: tuple[tuple[int, str], ...] = ()

    @property
    def text(self) -> str:
        return " ".join(token if token is not None else "*" for token in self.tokens)

    def matches(self, message: Sequence[str]) -> bool:
        return len(message) == len(self.tokens) and all(
            expected is None or expected == actual
            for expected, actual in zip(self.tokens, message, strict=True)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "program": self.program,
            "tokens": list(self.tokens),
            "count": self.count,
            "slots": [[position, name] for position, name in self.slots],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> Template:
        tokens = tuple(None if token is None else str(token) for token in raw.get("tokens") or ())
        slots = tuple(
            (int(item[0]), str(item[1]))
            for item in raw.get("slots") or ()
            if isinstance(item, (list, tuple)) and len(item) == 2
        )
        return cls(str(raw.get("program") or ""), tokens, int(raw.get("count") or 0), slots)


@dataclass(frozen=True)
class TemplateModel:
    """The header split and templates learned from one source's own sample."""

    header_tokens: int
    program_position: int
    templates: tuple[Template, ...]
    states: Mapping[str, Any]

    def parse(self, line: str) -> Parsed:
        row = words(line)
        if len(row) <= self.header_tokens:
            return Parsed("text", {})
        program = _program_of(row, self.program_position, self.header_tokens)
        message = row[self.header_tokens :]
        for template in self.templates:
            if template.program and template.program != program:
                continue
            if not template.matches(message):
                continue
            fields: dict[str, str] = {"program": program, "template": template.text}
            for position, name in template.slots:
                value = message[position] if position < len(message) else ""
                if value:
                    fields[name] = value
            return Parsed(
                "template",
                {name: _clip(value, MAX_VALUE_CHARS) for name, value in fields.items() if value},
            )
        return Parsed("text", {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "header_tokens": self.header_tokens,
            "program_position": self.program_position,
            "states": dict(self.states),
            "templates": [template.to_dict() for template in self.templates],
        }

    @classmethod
    def from_dict(cls, raw: Any) -> TemplateModel | None:
        if not isinstance(raw, Mapping):
            return None
        templates = raw.get("templates")
        if not isinstance(templates, list):
            return None
        return cls(
            int(raw.get("header_tokens") or 0),
            int(raw.get("program_position") or 0),
            tuple(Template.from_dict(item) for item in templates if isinstance(item, Mapping)),
            dict(raw.get("states") or {}),
        )


@dataclass(frozen=True)
class Partition:
    """A field whose value selects which other fields an event carries."""

    field: str
    values: tuple[str, ...]


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

    @property
    def variety(self) -> str:
        """constant | identity (values recur) | free (nearly every value is new)."""
        if self.distinct <= 1:
            return "constant"
        return "identity" if self.repeats else "free"


def _clean(cell: str) -> str:
    text = cell.strip()
    if len(text) >= 2 and text[:1] in {'"', "'"} and text[-1:] == text[:1]:
        text = text[1:-1]
    return text


def split_record(line: str, delimiter: str) -> list[str]:
    """Split one record on a delimiter that is outside quotes, brackets and braces."""
    cells: list[str] = []
    current: list[str] = []
    depth = 0
    quote = ""
    for char in line.strip():
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            continue
        if char == '"':
            quote = char
            current.append(char)
            continue
        if char in _OPENERS:
            depth += 1
            current.append(char)
            continue
        if char in _CLOSERS:
            depth = max(0, depth - 1)
            current.append(char)
            continue
        if depth == 0 and char == delimiter:
            cells.append("".join(current))
            current = []
            continue
        current.append(char)
    cells.append("".join(current))
    return cells


def words(line: str) -> list[str]:
    """Whitespace positions: a [bracketed] value stays whole, a quoted phrase is split into words."""
    return [clean for cell in split_record(line.replace('"', " "), " ") if (clean := _clean(cell))]


def _program_stem(token: str) -> str:
    """'sshd[123]:' -> 'sshd'; a bare token is its own stem."""
    stem = token[:-1] if token.endswith(":") else token
    bracket = stem.find("[")
    if bracket > 0:
        stem = stem[:bracket]
    return stem.strip()


def _colon_stem(token: str) -> str:
    return _program_stem(token) if token.endswith(":") else ""


def _program_of(row: Sequence[str], position: int, header_tokens: int) -> str:
    if not header_tokens or position >= len(row):
        return ""
    return _program_stem(row[position])


def _header_shape(rows: Sequence[Sequence[str]]) -> tuple[int, int]:
    """Where the shared header ends: the program token's colon, else the whole line is message."""
    votes: dict[int, int] = {}
    for row in rows:
        for index in range(min(len(row), HEADER_MAX_TOKENS)):
            if _colon_stem(row[index]):
                votes[index] = votes.get(index, 0) + 1
                break
    if votes:
        position = sorted(votes.items(), key=lambda item: (-item[1], item[0]))[0][0]
        if votes[position] / len(rows) >= MIN_STRUCTURE_SHARE:
            return position + 1, position
    return 0, 0


def _mine(program: str, messages: Sequence[Sequence[str]]) -> list[Template]:
    """Length-bucketed positional templates: a position constant across the bucket stays literal."""
    buckets: dict[int, list[Sequence[str]]] = {}
    for message in messages:
        if len(message) >= MIN_TEMPLATE_TOKENS:
            buckets.setdefault(len(message), []).append(message)
    templates: list[Template] = []
    for length, group in sorted(buckets.items()):
        if len(group) < MIN_TEMPLATE_LINES:
            continue
        tokens: list[str | None] = []
        for position in range(length):
            values = {message[position] for message in group}
            sole = next(iter(values)) if len(values) == 1 else None
            tokens.append(None if sole is None or _VAR_TOKEN.match(sole) else sole)
        templates.append(Template(program, tuple(tokens), len(group)))
    return templates


def _slot_fields(template: Template) -> Template:
    """Every variable position becomes a field; the behaviour stage decides which are identities."""
    positions = [index for index, token in enumerate(template.tokens) if token is None][
        :MAX_TEMPLATE_SLOTS
    ]
    slots = tuple((position, f"v{index + 1}") for index, position in enumerate(positions))
    return Template(template.program, template.tokens, template.count, slots)


def learn_templates(lines: Sequence[str]) -> TemplateModel | None:
    """Header plus per-program templates, both learned from how tokens repeat across lines."""
    rows = [words(line) for line in lines]
    if not rows:
        return None
    header_tokens, program_position = _header_shape(rows)
    by_program: dict[str, list[Sequence[str]]] = {}
    for row in rows:
        program = _program_of(row, program_position, header_tokens)
        by_program.setdefault(program, []).append(row[header_tokens:])
    mined: list[Template] = []
    for program, messages in sorted(by_program.items()):
        if len(messages) >= MIN_PROGRAM_LINES:
            mined.extend(_mine(program, messages))
    kept = [template for template in mined if template.count >= MIN_TEMPLATE_LINES]
    if not kept:
        return None
    per_program: dict[str, list[Template]] = {}
    for template in kept:
        per_program.setdefault(template.program, []).append(template)
    selected: list[Template] = []
    for templates in per_program.values():
        templates.sort(key=lambda item: (-item.count, item.text))
        selected.extend(templates[:MAX_TEMPLATES_PER_PROGRAM])
    selected.sort(key=lambda item: (-item.count, item.program, item.text))
    selected = selected[:MAX_TEMPLATES_PER_SOURCE]
    with_slots = [_slot_fields(template) for template in selected]
    states: dict[str, Any] = {"existed": len(kept), "kept": len(with_slots), "lines": len(rows)}
    model = TemplateModel(header_tokens, program_position, tuple(with_slots), states)
    explained = sum(1 for line in lines if model.parse(line).fields)
    states["explained"] = explained
    states["explained_share"] = round(explained / len(rows), 4) if rows else 0.0
    return model


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
                local_attr = _localname(str(attr_name))
                if text:
                    key = f"{tag}[{local_attr}={attr_value}]"
                    fields.setdefault(_clip(key, MAX_KEY_CHARS), _clip(text, MAX_VALUE_CHARS))
                elif attr_value:
                    key = f"{tag}.{local_attr}"
                    fields.setdefault(_clip(key, MAX_KEY_CHARS), _clip(attr_value, MAX_VALUE_CHARS))
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
    # rendered event bodies (e.g. Windows Security) carry "Label: value" detail lines KV misses
    for detail in line.splitlines():
        label = _COLON_LABEL.match(detail)
        if label:
            fields.setdefault(
                _clip(label.group(1), MAX_KEY_CHARS), _clip(label.group(2), MAX_VALUE_CHARS)
            )
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
    cells = [_clean(cell) for cell in first]
    if len(cells) < 2 or not all(_WORD.fullmatch(cell) for cell in cells):
        return None
    seen = {_clean(cell) for row in body for cell in row}
    if any(cell in seen for cell in cells):
        return None
    return cells


def _delimited(lines: Sequence[str]) -> list[Parsed] | None:
    for delimiter in _DELIMITERS:
        rows = [split_record(line, delimiter) for line in lines]
        width = _width(rows)
        if width < MIN_DELIMITED_WIDTH:
            continue
        matched = [(index, row) for index, row in enumerate(rows) if len(row) == width]
        if len(matched) / len(lines) < MIN_STRUCTURE_SHARE:
            continue
        header = _header(matched[0][1], [row for _index, row in matched[1:]])
        names = header or [f"c{index + 1}" for index in range(width)]
        header_index = matched[0][0] if header else -1
        parsed: list[Parsed] = []
        for index, row in enumerate(rows):
            if index == header_index:
                parsed.append(Parsed("header", {}))
                continue
            if len(row) != width:
                parsed.append(Parsed("text", {}))
                continue
            fields = {
                _clip(name, MAX_KEY_CHARS): _clip(_clean(cell), MAX_VALUE_CHARS)
                for name, cell in zip(names, row, strict=True)
            }
            parsed.append(Parsed("delimited", fields))
        return parsed
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


def parse_sample(raws: Sequence[str]) -> tuple[list[Parsed], TemplateModel | None]:
    """Read a sample with the first structure most lines support, else mine log templates.

    The result keeps one item per input line, in input order, so callers can align
    parsed fields with the events they came from.
    """
    lines = [str(raw) for raw in raws]
    if not lines:
        return [], None
    for name, parser in _PARSERS:
        parsed = _apply(name, parser, lines)
        if parsed is not None:
            return parsed, None
    delimited = _delimited(lines)
    if delimited is not None:
        return delimited, None
    model = learn_templates(lines)
    if model is not None:
        return [model.parse(line) for line in lines], model
    return [Parsed("text", {}) for _ in lines], None


def parse_events(raws: Sequence[str]) -> list[Parsed]:
    """Parsed items only; callers that need the learned templates use parse_sample."""
    return parse_sample(raws)[0]


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


def parse_row(
    raw: str,
    fmt: str,
    columns: Sequence[str] = (),
    template: TemplateModel | None = None,
) -> Parsed:
    """Read one event with the structure (or template model) the sample established."""
    if fmt == "template":
        return template.parse(raw) if template is not None else Parsed("text", {})
    if fmt == "delimited" and not columns:
        return Parsed("text", {})
    if fmt != "delimited":
        return parse_with(raw, fmt)
    for delimiter in _DELIMITERS:
        cells = [_clean(cell) for cell in split_record(raw, delimiter)]
        if len(cells) == len(columns):
            fields = {
                _clip(name, MAX_KEY_CHARS): _clip(cell, MAX_VALUE_CHARS)
                for name, cell in zip(columns, cells, strict=True)
            }
            return Parsed("delimited", fields)
    return Parsed("text", {})


def _all_numeric(values: set[str]) -> bool:
    if not values:
        return False
    for raw in values:
        try:
            float(raw.replace(",", ""))
        except ValueError:
            return False
    return True


def _select_fields(order: Sequence[str], distinct: Mapping[str, set[str]]) -> list[str]:
    """Keep sample order when narrow; on wide records prioritize varying non-numeric fields."""
    if len(order) <= MAX_FIELDS:
        return list(order)
    priority = [n for n in order if len(distinct[n]) > 1 and not _all_numeric(distinct[n])]
    rest = [n for n in order if n not in set(priority)]
    return [*priority, *rest][:MAX_FIELDS]


def field_stats(parsed: Sequence[Parsed]) -> list[FieldStat]:
    """Per-field presence, distinct count and first distinct values, prioritizing informative fields."""
    order: list[str] = []
    present: dict[str, int] = {}
    distinct: dict[str, set[str]] = {}
    lines = sum(1 for item in parsed if item.fmt != "header")
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
            lines,
        )
        for name in _select_fields(order, distinct)
    ]


def _group_separation(kept: Mapping[str, Sequence[Parsed]]) -> tuple[int, float]:
    """Count distinct majority field-sets across groups and their mean pairwise Jaccard distance."""
    schemas: list[frozenset[str]] = []
    for items in kept.values():
        counts: dict[str, int] = {}
        for item in items:
            for key in item.fields:
                counts[key] = counts.get(key, 0) + 1
        schemas.append(frozenset(key for key, count in counts.items() if count * 2 >= len(items)))
    distinct_schemas = len(set(schemas))
    if distinct_schemas < 2:
        return distinct_schemas, 0.0
    distances = [
        1.0 - len(left & right) / len(left | right)
        for index, left in enumerate(schemas)
        for right in schemas[index + 1 :]
        if left | right
    ]
    return distinct_schemas, (sum(distances) / len(distances) if distances else 0.0)


def choose_partition(parsed: Sequence[Parsed]) -> Partition | None:
    """The low-variety field whose values separate genuinely distinct per-group field sets."""
    present: dict[str, int] = {}
    distinct: dict[str, set[str]] = {}
    populated = 0
    for item in parsed:
        if not item.fields:
            continue
        populated += 1
        for name, value in item.fields.items():
            present[name] = present.get(name, 0) + 1
            distinct.setdefault(name, set()).add(value)
    best: tuple[int, float, int, str, tuple[str, ...]] | None = None
    for name, values in distinct.items():
        if len(values) < 2 or len(values) > MAX_PARTITIONS or len(values) >= present[name]:
            continue
        if present[name] * 2 < populated or _time_ordered(parsed, name):
            continue
        groups: dict[str, list[Parsed]] = {}
        for item in parsed:
            value = (item.fields.get(name) or "").strip()
            if value:
                groups.setdefault(value, []).append(item)
        kept = {
            value: items for value, items in groups.items() if len(items) >= MIN_PARTITION_LINES
        }
        if len(kept) < 2:
            continue
        schema_count, mean_distance = _group_separation(kept)
        if schema_count < 2 or mean_distance < MIN_PARTITION_DISTANCE:
            continue
        score = (schema_count, round(mean_distance, 4), -len(values), name, tuple(sorted(kept)))
        if best is None or score[:3] > best[:3]:
            best = score
    return Partition(best[3], best[4]) if best is not None else None


def _time_ordered(parsed: Sequence[Parsed], field: str) -> bool:
    """True when a field's non-equal transitions move monotonically with event order."""
    values = [item.fields.get(field) for item in parsed]
    pairs = [
        (left, right) for left, right in zip(values, values[1:], strict=False) if left and right
    ]
    if len(pairs) < MIN_PARTITION_LINES:
        return False
    transitions = [(left, right) for left, right in pairs if left != right]
    if not transitions:
        return False
    ordered = sum(1 for left, right in transitions if _value_leq(str(left), str(right)))
    return ordered / len(transitions) >= TIME_ORDER_SHARE


def _value_leq(left: str, right: str) -> bool:
    try:
        return float(left.replace(",", "")) <= float(right.replace(",", ""))
    except (AttributeError, TypeError, ValueError):
        return left <= right


def partition_groups(
    parsed: Sequence[Parsed], rows: Sequence[Mapping[str, Any]], partition: Partition
) -> dict[str, tuple[list[Mapping[str, Any]], list[Parsed]]]:
    """Rows and parsed items for each partition value that has enough support."""
    found: dict[str, tuple[list[Mapping[str, Any]], list[Parsed]]] = {}
    for row, item in zip(rows, parsed, strict=True):
        value = (item.fields.get(partition.field) or "").strip()
        if value not in partition.values:
            continue
        group_rows, group_parsed = found.setdefault(value, ([], []))
        group_rows.append(row)
        group_parsed.append(item)
    return found


__all__ = [
    "FieldStat",
    "MAX_FIELDS",
    "Partition",
    "Parsed",
    "choose_partition",
    "field_stats",
    "parse_events",
    "parse_row",
    "parse_with",
    "partition_groups",
    "split_record",
    "words",
]
