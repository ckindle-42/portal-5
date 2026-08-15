"""bully.evidence -- evidence manifests, content-hash verification, the
Episode adapter, and flagged shadow ingestion (P1.3).

The truth-plane `episode.py::Episode` (unchanged) is the sole Red->bully
contract (I-2). This module never redefines Episode; it only adapts one
into the shapes SUB/ORG persist. Capture bytes are never duplicated here --
`siem/capture_store.py::save_evidence` stays the actual byte store; this
module records manifests/hashes that point at it (content-hash
verification on dereference, never a second copy of the bytes).
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..telemetry import (
    GRADEABLE_EVIDENCE_ORIGINS,
    OBSERVED_EVIDENCE_ORIGINS,
    evidence_trust_tier,
)

SHADOW_FLAGS = ("off", "shadow", "authoritative")


class EvidenceIntegrityError(RuntimeError):
    """Raised when a dereferenced evidence item's bytes don't match its manifest hash."""


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class EvidenceItemRef:
    evidence_id: str
    type: str
    uri: str
    content_hash: str
    origin: str = ""  # telemetry.py origin tag, e.g. observed_packet | synthetic_fixture
    trust_tier: str = ""
    source_actor: str = ""
    synthetic: bool = False
    verification_status: str = "declared"  # declared|verified|invalid|quarantined|expired


@dataclass(frozen=True)
class EvidenceManifest:
    manifest_id: str
    episode_id: str
    required_types: tuple[str, ...]
    items: tuple[EvidenceItemRef, ...] = field(default_factory=tuple)
    created_at: float = field(default_factory=time.time)

    @property
    def present_types(self) -> set[str]:
        return {i.type for i in self.items}

    @property
    def completeness(self) -> float:
        if not self.required_types:
            return 1.0
        present = self.present_types & set(self.required_types)
        return len(present) / len(self.required_types)

    @property
    def missing_reasons(self) -> list[str]:
        missing = set(self.required_types) - self.present_types
        return [f"missing required evidence type: {t}" for t in sorted(missing)]


def build_manifest(
    *, episode_id: str, required_types: list[str], items: list[EvidenceItemRef]
) -> EvidenceManifest:
    return EvidenceManifest(
        manifest_id=f"em-{uuid.uuid4().hex[:12]}",
        episode_id=episode_id,
        required_types=tuple(required_types),
        items=tuple(items),
    )


def verify_item(item: EvidenceItemRef, actual_bytes: bytes) -> EvidenceItemRef:
    """Dereference-and-validate: hash the actual bytes and compare (C2).

    Returns a new EvidenceItemRef with `verification_status` updated --
    never mutates in place (immutable dataclass; frozen=True).
    """
    from dataclasses import replace

    actual_hash = content_hash(actual_bytes)
    if actual_hash != item.content_hash:
        return replace(item, verification_status="invalid")
    return replace(item, verification_status="verified")


def has_gradeable_origin(items: list[EvidenceItemRef]) -> bool:
    """G0 precondition: at least one live or imported observed item."""
    return any(i.origin in GRADEABLE_EVIDENCE_ORIGINS for i in items)


def has_observed_origin(items: list[EvidenceItemRef]) -> bool:
    """Production-credit precondition: at least one live-sensor item.

    `source_actor` here is used to carry the origin tag
    (`telemetry.OBSERVED_EVIDENCE_ORIGINS` member) the same way
    `telemetry.py` names it -- synthetic/counterfactual origins never
    satisfy this, by construction of the frozenset membership check.
    """
    return any(i.origin in OBSERVED_EVIDENCE_ORIGINS for i in items)


def can_mint_known_covered(items: list[EvidenceItemRef]) -> bool:
    """Imported telemetry can be graded but cannot alone mint coverage credit."""
    return has_observed_origin(items)


def synthetic_never_passes_g0(items: list[EvidenceItemRef]) -> bool:
    """C2: 'synthetic never passes G0.' True means the manifest is G0-eligible."""
    if any(i.synthetic for i in items) and not has_gradeable_origin(items):
        return False
    return has_gradeable_origin(items)


def with_inferred_trust(item: EvidenceItemRef) -> EvidenceItemRef:
    """Return an item carrying the canonical tier for its origin claim."""
    if item.trust_tier:
        return item
    from dataclasses import replace

    return replace(item, trust_tier=evidence_trust_tier(item.origin))


# ── Episode adapter (I-2) ────────────────────────────────────────────────────


def adapt_episode(episode: Any) -> dict:
    """Project the truth-plane Episode into the summary SUB/ORG persist.

    `episode` is `episode.py::Episode` (unchanged) -- duck-typed here on
    purpose so this module never has to import episode.py's dataclass
    definition and risk drifting a second copy of its shape; it reads the
    same fields `derive_verdict`/`to_dict` already expose.
    """
    return {
        "episode_id": episode.episode_id,
        "scenario": episode.scenario,
        "target_host": episode.target_host,
        "red_status": episode.red_status,
        "telemetry_status": episode.telemetry_status,
        "detection_status": episode.detection_status,
        "response_status": episode.response_status,
        "used_synthetic": episode.used_synthetic,
        "evidence_refs": list(episode.evidence_refs),
        "verdict": episode.verdict(),
    }


def episode_verdict_is_blocked(episode: Any) -> bool:
    """LOOP blocks unscoreable infrastructure/unavailable truth planes."""
    return episode.verdict() in {"INDETERMINATE", "UNAVAILABLE"}


# ── Shadow ingestion (I-22) ──────────────────────────────────────────────────


def shadow_ingest(episode: Any, *, flag: str) -> dict | None:
    """Feature-flagged shadow observation to the bully Episode adapter.

    With `flag == "off"` this is a pure no-op returning None -- the existing
    purple caller's legacy results are byte-stable (I-22 / the P1.3
    byte-stability test asserts exactly this: calling this function must
    never touch any legacy state, only optionally compute and return an
    adapter view for shadow comparison).
    """
    if flag not in SHADOW_FLAGS:
        raise ValueError(f"unknown shadow flag: {flag!r}; must be one of {SHADOW_FLAGS}")
    if flag == "off":
        return None
    return adapt_episode(episode)
