"""Workstream G — the reading-architecture acceptance suite (IMPLEMENTATION_BRIEF §7).

Hermetic: no network, no real Ollama. Each of the 26 seed cases builds a
synthetic ``GoverningBundle``/``CandidateSet``/``CorpusSnapshot`` from the
controlled fixture texts in ``tests/data/compliance_reading_acceptance.json``
and injects a deterministic three-stage transport that answers the alignment,
council and report system prompts with the JSON the case's EXPECTED semantics
imply. That proves routing, contracts, arithmetic, projection, persistence and
serialization — not semantic capability.

Known production gaps (the spec expects a code the landed path cannot yet
emit) are carried as ``blocked`` checks named in ``KNOWN_GAPS`` rather than
silently weakened; ``scripts/verify_compliance_reading_acceptance.py`` prints
them in its table.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from portal.modules.compliance.core.assessment_source import (
    resolve_governing_bundle,
)
from portal.modules.compliance.core.determination import (
    SourceSlice,
)

ROOT = Path(__file__).resolve().parents[2]

MANIFEST_PATH = ROOT / "tests/data/compliance_reading_acceptance.json"

MANIFEST: dict[str, Any] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

CASES: dict[str, dict[str, Any]] = {c["id"]: c for c in MANIFEST["cases"]}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_a11_dependent_annotation_invalidation() -> None:
    from portal.modules.compliance.core.gate import _governing_cu

    complete = resolve_governing_bundle(CASES["20"]["requirement_id"])
    truncated = resolve_governing_bundle(CASES["20"]["requirement_id"])
    truncated.part_text = "or delegate."
    truncated.source_slices = [
        SourceSlice(
            slice_id=s.slice_id,
            ref=s.ref,
            document_id=s.document_id,
            revision_hash=_sha("or delegate."),
            chunk_id=s.chunk_id,
            text="or delegate.",
            role=s.role,
        )
        for s in truncated.source_slices[:1]
    ]
    from portal.modules.compliance.core.assessment_source import _bundle_fingerprint

    truncated.fingerprint = _bundle_fingerprint(truncated.source_slices)
    assert complete.fingerprint != truncated.fingerprint
    cu = _governing_cu(complete, complete.ref, "Responsible Entity", None)
    assert "Part 2.3" in cu["constraint"]["text"]
    assert cu["constraint"]["text"] != "or delegate."
    assert "CIP Senior Manager" in cu["constraint"]["text"]
