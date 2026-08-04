"""Executable claims — the missing link between a unit's prose and live reality.

The generation loop guarantees that a Tier-1 doc's `WIKI:GENERATED` block equals
its unit's body. It does not guarantee that the body is *true*. Measured at the
commit this module landed: 567 generated blocks across 25 Tier-1 docs, of which
7 (1.2%) came from a machine-derived `unit-fact-*` unit. The other 560 are
authored prose that the AW gate certifies as "current" by comparing a copy with
its own source — so README could claim 60 benchmark workspaces and 22 MCP
servers against a live 65 and 21 with every gate green.

A claim closes that loop for the facts that are actually checkable. A unit
declares, in frontmatter, where in its body a live quantity appears:

    claims:
    - probe: workspaces.bench
      pattern: "currently {value} workspaces"

There is deliberately no second copy of the number. `{value}` is substituted with
the live probe result and the resulting string must appear in the body — so the
body text is the single place the figure is written, and when code moves the
match fails and names the unit, the probe, and the value the body should carry.
An earlier draft of this module let a claim restate the expected number
(`equals: 65`); that claim compared the probe with itself and passed while the
body still said 60. `equals` survives only for structural invariants the prose
describes qualitatively (`backends.types equals [ollama, omlx]`), where there is
no figure in the text to bind to.
Claims are opt-in per unit — prose about *why* something is designed a certain
way has nothing to assert, and forcing an assertion on it would produce the
mass-stubbing this project has refused elsewhere. Undeclared numeric claims are
reported as visible debt (see `drift.py`), never silently accepted as covered.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]


# ── Probes ────────────────────────────────────────────────────────────────────
# Every probe is pure, offline, and deterministic: it reads committed files only.
# A probe that needs a running service belongs in a live-reality check (BC), not
# here — this gate must hold in CI on a bare clone.


def _load_portal_yaml(root: Path) -> dict:
    import yaml

    return yaml.safe_load((root / "config" / "portal.yaml").read_text(encoding="utf-8")) or {}


def _workspace_names(root: Path) -> list[str]:
    """Workspace *ids*, which are the mapping keys in `config/portal.yaml`.

    The `name` field inside each entry is a display label ("🤖 Portal Auto
    Router"), not an id, so it must never be used here — `workspaces.bench` counts
    the `bench-` id prefix and would silently return 0 if fed display labels.
    An earlier version iterated `workspaces` as though it were a list of dicts;
    that produced the right answer only because iterating a dict yields its keys.
    The shape is asserted rather than guessed so a future restructure fails loudly
    instead of quietly zeroing the bench count.
    """
    workspaces = _load_portal_yaml(root).get("workspaces")
    if isinstance(workspaces, dict):
        return [str(k) for k in workspaces]
    raise TypeError(
        f"config/portal.yaml `workspaces` must be a mapping of id -> spec, "
        f"got {type(workspaces).__name__}"
    )


def _probe_workspaces_total(root: Path) -> int:
    return len(_workspace_names(root))


def _probe_workspaces_bench(root: Path) -> int:
    return sum(1 for n in _workspace_names(root) if n.startswith("bench-"))


def _probe_workspaces_functional(root: Path) -> int:
    return _probe_workspaces_total(root) - _probe_workspaces_bench(root)


def _fleet(root: Path) -> list[dict]:
    return [e for e in (_load_portal_yaml(root).get("mcp_fleet") or []) if isinstance(e, dict)]


def _probe_fleet_entries(root: Path) -> int:
    return len(_fleet(root))


def _probe_fleet_ports(root: Path) -> list[int]:
    return sorted(int(e["port"]) for e in _fleet(root) if e.get("port") is not None)


def _probe_mcpjson_servers(root: Path) -> int:
    data = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    return len(data.get("mcpServers") or {})


def _probe_personas(root: Path) -> int:
    return len(list((root / "config" / "personas").glob("*.yaml")))


def _probe_validate_checks(root: Path) -> int:
    return (root / "scripts" / "validate_system.py").read_text(encoding="utf-8").count("v.run(")


def _probe_canonical_units(root: Path) -> int:
    return len(list((root / "portal_wiki" / "canonical").glob("*.md")))


def _probe_tier1_docs(root: Path) -> int:
    from portal.platform.wiki.render import TIER1_DOCS

    return sum(1 for rel in TIER1_DOCS if (root / rel).exists())


def _probe_generated_blocks(root: Path) -> int:
    from portal.platform.wiki.render import _MARKER_RE, TIER1_DOCS

    total = 0
    for rel in TIER1_DOCS:
        p = root / rel
        if p.exists():
            total += len(_MARKER_RE.findall(p.read_text(encoding="utf-8")))
    return total


def _backend_entries(root: Path) -> list[dict]:
    import yaml

    data = yaml.safe_load((root / "config" / "backends.yaml").read_text(encoding="utf-8")) or {}
    return [e for e in (data.get("backends") or []) if isinstance(e, dict)]


def _probe_backend_groups(root: Path) -> list[str]:
    """Distinct routing groups, not backend ids — `backends` is a list of entries
    and two entries may share a group (ollama-coding and omlx-coding both serve
    `coding`), which is exactly the fact a doc claim wants to assert."""
    return sorted({str(e["group"]) for e in _backend_entries(root) if e.get("group")})


def _probe_backend_ids(root: Path) -> list[str]:
    return sorted(str(e["id"]) for e in _backend_entries(root) if e.get("id"))


def _probe_backend_groups_count(root: Path) -> int:
    return len(_probe_backend_groups(root))


def _probe_backend_types(root: Path) -> list[str]:
    return sorted({str(e["type"]) for e in _backend_entries(root) if e.get("type")})


PROBES: dict[str, Callable[[Path], Any]] = {
    "workspaces.total": _probe_workspaces_total,
    "workspaces.bench": _probe_workspaces_bench,
    "workspaces.functional": _probe_workspaces_functional,
    "mcp.fleet.entries": _probe_fleet_entries,
    "mcp.fleet.ports": _probe_fleet_ports,
    "mcpjson.servers": _probe_mcpjson_servers,
    "personas.count": _probe_personas,
    "validate.checks": _probe_validate_checks,
    "wiki.canonical.units": _probe_canonical_units,
    "wiki.tier1.docs": _probe_tier1_docs,
    "wiki.generated.blocks": _probe_generated_blocks,
    "backends.groups": _probe_backend_groups,
    "backends.groups.count": _probe_backend_groups_count,
    "backends.ids": _probe_backend_ids,
    "backends.types": _probe_backend_types,
}


def probe(name: str, repo_root: Path | None = None) -> Any:
    """Evaluate one probe by name. Raises KeyError for an unknown probe so a
    typo in a unit's frontmatter fails loudly instead of silently passing."""
    root = repo_root or _REPO_ROOT
    return PROBES[name](root)


def probe_all(repo_root: Path | None = None) -> dict[str, Any]:
    """Evaluate every probe. A probe that raises reports its exception text —
    the census must survive one broken reader without losing the rest."""
    root = repo_root or _REPO_ROOT
    out: dict[str, Any] = {}
    for name, fn in PROBES.items():
        try:
            out[name] = fn(root)
        except Exception as exc:  # noqa: BLE001 — census over correctness of one probe
            out[name] = f"<error: {type(exc).__name__}: {exc}>"
    return out


# ── Claim evaluation ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClaimViolation:
    """One unit assertion that no longer matches live state."""

    unit_id: str
    probe: str
    op: str
    claimed: Any
    live: Any

    def __str__(self) -> str:
        if self.op == "pattern":
            return (
                f"{self.unit_id}: body should contain {self.claimed!r} "
                f"(live {self.probe}={self.live!r}) — it does not"
            )
        return (
            f"{self.unit_id}: claims {self.probe} {self.op} {self.claimed!r}, live is {self.live!r}"
        )


def evaluate_claims(units=None, repo_root: Path | None = None) -> list[ClaimViolation]:
    """Check every declared claim on every unit against its live probe.

    Supported operators:
      `pattern`  — a literal template containing `{value}`. The live probe result
                   is substituted and the result must appear in the unit body.
                   This is the operator that catches doc drift, because the body
                   is the only place the figure is recorded.
      `equals`   — probe result must equal the declared value. For structural
                   invariants with no figure in the prose to bind to.
      `contains` — declared value must be a member of a list-valued probe.

    An unknown probe or operator is itself a violation: a claim that cannot be
    evaluated is not a claim that passes.
    """
    root = repo_root or _REPO_ROOT
    if units is None:
        from portal.platform.wiki.store import load_all

        units = load_all()

    cache: dict[str, Any] = {}
    violations: list[ClaimViolation] = []
    for unit in units:
        for claim in getattr(unit, "claims", None) or []:
            if not isinstance(claim, dict):
                violations.append(ClaimViolation(unit.id, "<malformed>", "?", claim, None))
                continue
            name = claim.get("probe", "")
            if name not in PROBES:
                violations.append(
                    ClaimViolation(unit.id, name or "<missing>", "?", claim, "<unknown probe>")
                )
                continue
            if name not in cache:
                try:
                    cache[name] = PROBES[name](root)
                except Exception as exc:  # noqa: BLE001
                    cache[name] = f"<error: {type(exc).__name__}: {exc}>"
            live = cache[name]

            if "pattern" in claim:
                template = str(claim["pattern"])
                if "{value}" not in template:
                    violations.append(
                        ClaimViolation(
                            unit.id, name, "pattern", template, "<template lacks {value}>"
                        )
                    )
                    continue
                expected = template.replace("{value}", str(live))
                if expected not in unit.body:
                    violations.append(ClaimViolation(unit.id, name, "pattern", expected, live))
            elif "equals" in claim:
                claimed = claim["equals"]
                a = list(claimed) if isinstance(claimed, (list, tuple)) else claimed
                b = list(live) if isinstance(live, (list, tuple)) else live
                if a != b:
                    violations.append(ClaimViolation(unit.id, name, "equals", claimed, live))
            elif "contains" in claim:
                claimed = claim["contains"]
                if not isinstance(live, (list, tuple)) or claimed not in live:
                    violations.append(ClaimViolation(unit.id, name, "contains", claimed, live))
            else:
                violations.append(
                    ClaimViolation(unit.id, name, "<no operator>", claim, "<uncheckable>")
                )
    return violations


def claim_count(units=None) -> int:
    """How many claims are declared across the store — the coverage numerator."""
    if units is None:
        from portal.platform.wiki.store import load_all

        units = load_all()
    return sum(len(getattr(u, "claims", None) or []) for u in units)
