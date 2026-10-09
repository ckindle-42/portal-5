"""review.content -- what a unit's records *do*, as normalized terms, for any schema.

``bully.behavior_values`` keeps only the values of ~60 hand-listed field names (Image,
CommandLine, TargetObject ...): a definition table. A source whose fields are named
differently contributes nothing, which is exactly the "hundreds of source types" the product
exists for. Here the content fields are chosen by *inferred role* (``field_roles``: ACTION and
PAYLOAD fields), and values are masked with the same environment-identity masking
``behavior_values.normalize`` applies (users, hosts, GUIDs, SIDs, hashes, IPs, long numbers).

Terms are values only -- no field names. Field names are schema; two sources of the same
behavior share values (``whoami``, ``certutil -urlcache``), not column names, and the lab's own
measurement (B1.1) found the values channel is what carries cross-source similarity.

Rarest first: a window is mostly recurring background; the actions that distinguish one
behavior from another tend to occur once or twice (the ordering ``behavior_values`` uses).

Observation plane: no label identifiers (see ``wall``).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from ..bully.behavior_values import normalize

CONTENT_ROLES: frozenset[str] = frozenset({"ACTION", "PAYLOAD"})

#: Card-size bounds (not decision constants): how many terms a unit card carries and how many
#: any one field may contribute so a burst of one background field cannot crowd out the rest.
#: The measurement plane may A/B them; the stamp records the values used.
DEFAULT_LIMIT = 24
DEFAULT_PER_FIELD_CAP = 4


def flatten_values(record: Mapping[str, Any], prefix: str = "") -> dict[str, list[str]]:
    """Dotted-path leaves of ``record`` as lists of strings (scalar lists keep every item)."""
    out: dict[str, list[str]] = {}
    for key, value in record.items():
        path = f"{prefix}{key}"
        if isinstance(value, Mapping):
            out.update(flatten_values(value, prefix=f"{path}."))
        elif isinstance(value, (list, tuple)):
            scalars = [str(v) for v in value if not isinstance(v, (Mapping, list, tuple))]
            if scalars:
                out[path] = scalars
        elif value is not None:
            out[path] = [str(value)]
    return out


def content_terms(
    records: Iterable[Mapping[str, Any]],
    roles: Mapping[str, str],
    *,
    limit: int = DEFAULT_LIMIT,
    per_field_cap: int = DEFAULT_PER_FIELD_CAP,
) -> list[str]:
    """Distinct masked values of the ACTION/PAYLOAD fields of ``records``, rarest first.

    ``roles`` maps a dotted field path to its inferred role (``FieldRoleMap.profiles``)."""
    counts: Counter[tuple[str, str]] = Counter()
    first: dict[tuple[str, str], int] = {}
    for record in records:
        for path, values in flatten_values(record).items():
            if roles.get(path) not in CONTENT_ROLES:
                continue
            for value in values:
                term = normalize("value", value)
                if len(term) < 2:
                    continue
                key = (path, term)
                counts[key] += 1
                first.setdefault(key, len(first))
    out: list[str] = []
    seen: set[str] = set()
    per_field: Counter[str] = Counter()
    for key in sorted(counts, key=lambda k: (counts[k], first[k])):
        path, term = key
        if term in seen or per_field[path] >= per_field_cap:
            continue
        seen.add(term)
        per_field[path] += 1
        out.append(term)
        if len(out) >= limit:
            break
    return out
