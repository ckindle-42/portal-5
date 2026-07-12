"""The capability index — unifies the scattered security library into one
queryable index (Phase 2).

A Capability is one thing the system can *do*: a technique bound to the
tools that perform it, the observation predicate that makes it
applicable, the oracle that verifies it, and (if applicable) source
provenance. Built additively from real sources — nothing invented.

query(observations) is THE retrieval call: "given what I've seen, here
is the range of things worth trying" — grounded in the library, ranked
by applicability x journal-prior x tool-availability x phase-fit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from portal.modules.security.core import scoring
from portal.modules.security.core.capability.tool_inventory import (
    load_tool_catalog,
    tools_for_service,
)
from portal.modules.security.core.oracles import ORACLES

_REPO_ROOT = Path(__file__).resolve().parents[5]

# service key -> domain, for capabilities derived from _LAB_SERVICE_PROBES.
_SERVICE_DOMAIN: dict[str, str] = {
    "smb": "ad",
    "winrm": "ad",
    "ldap": "ad",
    "kerberos": "ad",
    "http": "web",
    "https": "web",
    "ssh": "linux",
    "ftp": "linux",
    "mysql": "web",
    "redis": "web",
}

_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ad": ("ad-", "kerberos", "smb", "ldap", "dc", "adcs", "golden", "dacl"),
    "web": ("web", "http", "sql", "ssrf", "xss", "rce", "gitlab", "vulhub"),
    "cloud": ("cloud", "k8s", "kube", "aws", "s3", "iam"),
    "re": ("firmware", "binwalk", "binary", "reverse"),
    "windows": ("windows", "winrm", "psexec", "wmiexec"),
    "linux": ("linux", "privesc", "container", "ssh"),
}


@dataclass
class Capability:
    """One indexed capability. Every `tools` entry resolves to a real
    tool_catalog name; `oracle` (when set) resolves to a registered
    ORACLES key — this is the legibility contract, enforced by
    test_capability_index.py."""

    id: str
    phase: str
    domain: str
    applies_when: dict[str, Any]
    tools: list[str]
    technique: str
    oracle: str | None
    mitre: list[str] = field(default_factory=list)
    source: str = "unknown"


def _infer_domain(text: str) -> str:
    lowered = text.lower()
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return domain
    return "web"


def _from_service_probes() -> list[Capability]:
    """_LAB_SERVICE_PROBES: service -> (port, probe_cmd, success_keywords)."""
    from portal.modules.security.core._data import _LAB_SERVICE_PROBES

    caps = []
    for service, (port, cmd, _keywords) in _LAB_SERVICE_PROBES.items():
        tools = [t["name"] for t in tools_for_service(service)]
        caps.append(
            Capability(
                id=f"{service}_probe",
                phase="recon",
                domain=_SERVICE_DOMAIN.get(service, _infer_domain(service)),
                applies_when={"field": "open_ports", "contains": port},
                tools=tools,
                technique=cmd,
                oracle=None,
                mitre=[],
                source="service_probe",
            )
        )
    return caps


def _from_challenge_classes() -> list[Capability]:
    cc = yaml.safe_load((_REPO_ROOT / "config" / "challenge_classes.yaml").read_text())
    caps = []
    for entry in cc.get("classes", []):
        oracle = (entry.get("ground_truth") or {}).get("oracle")
        if oracle is not None and oracle not in ORACLES:
            oracle = None  # never reference an unregistered oracle
        technique_desc = entry.get("id", "")
        vulhub = entry.get("vulhub")
        if vulhub:
            technique_desc += f" (vulhub: {vulhub[0] if isinstance(vulhub, list) else vulhub})"
        caps.append(
            Capability(
                id=entry["id"],
                phase="exploit",
                domain=_infer_domain(entry.get("id", "")),
                applies_when={},
                tools=[],
                technique=technique_desc,
                oracle=oracle,
                mitre=[],
                source="challenge_class",
            )
        )
    return caps


def _from_lab_targets() -> list[Capability]:
    lt = yaml.safe_load((_REPO_ROOT / "config" / "lab_targets.yaml").read_text())
    caps = []
    for entry in lt.get("targets", []):
        oracle = (entry.get("ground_truth") or {}).get("oracle")
        if oracle is not None and oracle not in ORACLES:
            oracle = None
        applies_when: dict[str, Any] = {}
        port = entry.get("port")
        if port:
            applies_when = {"field": "open_ports", "contains": port}
        technique = entry.get("technique", "") or entry.get("id", "")
        cve = entry.get("cve")
        if cve:
            technique = f"{technique} ({cve})"
        caps.append(
            Capability(
                id=entry["id"],
                phase="exploit",
                domain=_infer_domain(f"{entry.get('id', '')} {technique}"),
                applies_when=applies_when,
                tools=[],
                technique=technique,
                oracle=oracle,
                mitre=[],
                source="lab_target",
            )
        )
    return caps


@lru_cache(maxsize=1)
def build_index() -> list[Capability]:
    """Ingest and normalize every source into one capability list.
    Cached — the underlying sources are static config/data, not runtime
    state. Additive/normalizing only: every capability traces to a real
    source (`source` field) and never references a tool or oracle that
    doesn't actually exist in the catalog/registry.
    """
    caps: list[Capability] = []
    caps.extend(_from_service_probes())
    caps.extend(_from_challenge_classes())
    caps.extend(_from_lab_targets())

    # Validate the legibility contract here too (belt-and-suspenders with
    # the unit test) — an orphan reference is a build-time bug, not a
    # runtime surprise.
    catalog_names = {t["name"] for t in load_tool_catalog()}
    for cap in caps:
        for tool in cap.tools:
            if tool not in catalog_names:
                raise ValueError(f"Capability {cap.id!r} references unknown tool {tool!r}")
        if cap.oracle is not None and cap.oracle not in ORACLES:
            raise ValueError(f"Capability {cap.id!r} references unknown oracle {cap.oracle!r}")
    return caps


def _journal_prior_score(cap: Capability) -> float:
    """Has this capability's technique landed before? Reuses
    field_journal.recall's relevance retrieval — a nonzero prior count
    outranks an equally-applicable capability with no history."""
    try:
        from portal.modules.security.core import field_journal

        hits = field_journal.recall(cap.domain, keywords=[cap.id], limit=5)
        return min(len(hits), 5) / 5.0
    except Exception:
        return 0.0


def _tool_availability_score(cap: Capability, tool_presence: dict[str, bool | None]) -> float:
    if not cap.tools:
        return 0.5  # neutral — no tool dependency to penalize or reward
    known = [tool_presence.get(t) for t in cap.tools]
    if not known or all(v is None for v in known):
        return 0.5  # declared-only catalog, presence unverified
    present = sum(1 for v in known if v)
    return present / len(known)


def query(
    observations: dict[str, Any],
    *,
    phase: str | None = None,
    domain: str | None = None,
    goal: str | None = None,
    limit: int = 12,
) -> list[Capability]:
    """THE retrieval call the decide step uses. Returns capabilities whose
    `applies_when` matches `observations`, optionally filtered by
    phase/domain, ranked by applicability x journal-prior x
    tool-availability x phase-fit.

    `goal` is currently a free-text filter over `technique`/`id` (a
    simple substring match) — Stage 2 (goal-driven decide) is the
    consumer that will make real use of it; kept minimal here since this
    task is read-only indexing, not the reasoning layer itself.
    """
    from portal.modules.security.core.capability.tool_inventory import verify_tools_present

    candidates = build_index()
    if phase is not None:
        candidates = [c for c in candidates if c.phase == phase]
    if domain is not None:
        candidates = [c for c in candidates if c.domain == domain]
    if goal:
        goal_lower = goal.lower()
        candidates = [
            c for c in candidates if goal_lower in c.id.lower() or goal_lower in c.technique.lower()
        ]

    applicable = [
        c
        for c in candidates
        if not c.applies_when or scoring.evaluate_condition(c.applies_when, observations)
    ]

    tool_presence = verify_tools_present(dry_run=True)  # never hits the lab from query()
    scored = []
    for cap in applicable:
        applicability = 1.0  # already filtered to applicable-only above
        journal = _journal_prior_score(cap)
        tool_avail = _tool_availability_score(cap, tool_presence)
        phase_fit = 1.0 if phase is not None and cap.phase == phase else 0.5
        composite = applicability * (0.4 + 0.3 * journal + 0.2 * tool_avail + 0.1 * phase_fit)
        scored.append((composite, cap))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [cap for _, cap in scored[:limit]]
