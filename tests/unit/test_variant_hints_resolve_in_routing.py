"""Every workspace variant's model_hint must resolve inside its routed groups.

A variant inherits its base workspace's ``workspace_routing`` groups, so a
variant hint that only lives in another group is served only by the tier-3
"remaining healthy backends" net (or not at all on the engine the roster
targets). ``auto-general-uncensored::creative`` regressed that way when the
auto-creative fold (adafe9c35) moved the hint onto ollama-general but left the
oMLX conversion reachable only from the security/creative groups.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts import speed_gate

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"


def _load(name: str) -> dict:
    return yaml.safe_load((CONFIG / name).read_text(encoding="utf-8")) or {}


def _catalog(backends: dict) -> dict[str, tuple[set[str], dict[str, str]]]:
    """group -> (model ids, aliases) across every backend type."""
    catalog: dict[str, tuple[set[str], dict[str, str]]] = {}
    for backend in backends.get("backends") or []:
        group = str(backend.get("group") or "")
        ids, aliases = catalog.setdefault(group, (set(), {}))
        ids.update(
            str(m.get("id") if isinstance(m, dict) else m) for m in backend.get("models") or []
        )
        aliases.update({str(k): str(v) for k, v in (backend.get("aliases") or {}).items()})
    return catalog


def _resolves(hint: str, groups: list[str], catalog: dict) -> str | None:
    ids: set[str] = set()
    aliases: dict[str, str] = {}
    for group in groups:
        group_ids, group_aliases = catalog.get(group, (set(), {}))
        ids |= group_ids
        aliases.update(group_aliases)
    if hint in aliases:
        return aliases[hint]
    return hint if hint in ids else None


def _seats(backends: dict, portal: dict, bench: dict) -> list[tuple[str, list[str], str]]:
    workspaces = {**(portal.get("workspaces") or {}), **(bench.get("workspaces") or {})}
    routing = backends.get("workspace_routing") or {}
    seats = []
    for workspace_id, workspace in workspaces.items():
        if not isinstance(workspace, dict):
            continue
        groups = routing.get(workspace_id) or []
        declared = {"": {}, **(workspace.get("variants") or {})}
        for variant, overrides in declared.items():
            hint = str({**workspace, **(overrides or {})}.get("model_hint") or "").strip()
            if hint:
                seat = f"{workspace_id}::{variant}" if variant else workspace_id
                seats.append((seat, groups, hint))
    return seats


def test_every_workspace_variant_hint_resolves_in_its_routed_groups() -> None:
    backends = _load("backends.yaml")
    catalog = _catalog(backends)
    offenders = [
        f"{seat} (groups={groups}) -> {hint!r}"
        for seat, groups, hint in _seats(
            backends, _load("portal.yaml"), _load("bench_workspaces.yaml")
        )
        if _resolves(hint, groups, catalog) is None
    ]
    assert not offenders, "variant hints outside their routed groups:\n  " + "\n  ".join(offenders)


def test_creative_variant_resolves_on_its_group_omlx_shadow() -> None:
    """The folded creative lane is benchable on oMLX through the general group."""
    backends, portal = speed_gate.load_config(CONFIG)
    seats = speed_gate.resolve_seats(portal, backends)
    assert (
        seats.get("auto-general-uncensored::creative") == "Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit"
    )
