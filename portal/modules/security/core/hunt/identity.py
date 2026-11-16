from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


def host_identity(host: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in host.casefold())


@dataclass(frozen=True)
class HostAliases:
    display_by_identity: Mapping[str, str]
    spellings_by_identity: Mapping[str, tuple[str, ...]]
    name_count: int
    machine_count: int
    merge: bool = True

    def display(self, host: str) -> str:
        if not self.merge:
            return host
        return self.display_by_identity.get(host_identity(host), host)

    def spellings(self, host: str) -> tuple[str, ...]:
        if not self.merge:
            return (host,)
        return self.spellings_by_identity.get(host_identity(host), (host,))


def build_host_aliases(rows: Iterable[Mapping[str, Any]]) -> HostAliases:
    counts: dict[str, int] = {}
    identities: dict[str, str] = {}
    for row in rows:
        host = str(row["host"])
        identities[host] = host_identity(host)
        counts[host] = counts.get(host, 0) + int(float(row["count"]))
    spellings: dict[str, list[str]] = {}
    for host, identity in identities.items():
        spellings.setdefault(identity, []).append(host)
    ordered = {key: tuple(sorted(names)) for key, names in spellings.items()}
    display = {
        identity: min(names, key=lambda host: (-counts[host], host))
        for identity, names in ordered.items()
    }
    return HostAliases(display, ordered, len(identities), len(ordered))


def identity_only(names: Iterable[str]) -> HostAliases:
    found = set(names)
    return HostAliases(
        {},
        {},
        len(found),
        len({host_identity(host) for host in found}),
        merge=False,
    )


def fold_host_rows(rows: Iterable[dict[str, Any]], aliases: HostAliases) -> list[dict[str, Any]]:
    return [{**row, "host": aliases.display(str(row["host"]))} for row in rows]


def host_filter(host: str, aliases: Sequence[str] | None, quote: Callable[[str], str]) -> str:
    names = sorted(set(aliases or (host,)))
    predicates = [f"host={quote(name)}" for name in names]
    if len(predicates) == 1:
        return predicates[0]
    return f"({' OR '.join(predicates)})"
