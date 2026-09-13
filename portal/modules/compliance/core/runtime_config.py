"""Live-analysis runtime configuration (TASK_COMPLIANCE_REASONING_V6 P7).

The council seat roster and the operator-corpus organization graph, resolved
from config with documented fallbacks so the assessment service can run LIVE
rather than read a materialized row.

Seat roster: ``config/compliance/council.yaml`` ``seats:`` when present,
otherwise the three diverse defaults below (finalised by the D0-M seat
qualification — see the run report). Organization commitments: the built
``org_graph.json`` under the operator's private run directory, or an explicit
MISSING/EMPTY status (which makes every actor-CU return ABSENT with a complete
reading, the honest answer when no corpus is ingested).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.determination import AssessmentContext, CorpusSnapshot

_CONFIG = Path(__file__).resolve().parents[4] / "config" / "compliance"
_DEFAULT_ORG_GRAPH = (
    Path(__file__).resolve().parents[4]
    / "coding_task"
    / "v9_compliance"
    / "private"
    / "org_graph.json"
)

# D0-M-qualified default roster — the fallback when config/compliance/council.yaml
# is absent. Selected from the 12-seat judgment-probe sweep (2026-09-06): three
# families, F2 {0.952, 0.843, 0.802} on violation detection, all vca >= 0.87.
_DEFAULT_SEATS: list[dict[str, str]] = [
    {
        "id": "qwen38",
        "label": "Qwen3.8 27B (unsloth Q4_K_M, 32k)",
        "model": "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k",
    },
    {"id": "granite41", "label": "IBM Granite 4.1 30B (16k)", "model": "granite4.1:30b-ctx16k"},
    {
        "id": "mistral",
        "label": "Mistral Small 3.2 24B (Q4_K_M)",
        "model": "mistral-small3.2:24b-instruct-2506-q4_K_M",
    },
]

_DEFAULT_QUORUM = 0.66


def _read_council_config() -> dict[str, Any]:
    cfg = _CONFIG / "council.yaml"
    if not cfg.exists():
        return {}
    try:
        import yaml

        data = yaml.safe_load(cfg.read_text()) or {}
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - a malformed config falls back to the default
        return {}


def seat_roster() -> list[dict[str, str]]:
    data = _read_council_config()
    seats = data.get("seats")
    if isinstance(seats, list) and seats:
        return [
            {
                "id": str(s["id"]),
                "label": str(s.get("label", s["id"])),
                "model": str(s["model"]),
            }
            for s in seats
        ]
    return list(_DEFAULT_SEATS)


def council_quorum() -> float:
    """The configured categorical-agreement quorum, defaulting to 0.66."""
    q = _read_council_config().get("quorum")
    if isinstance(q, (int, float)) and not isinstance(q, bool):
        return float(q)
    return _DEFAULT_QUORUM


def build_assessment_context(
    kb_id: str,
    scope: AssetScope,
    effective_on: str,
    known_at: str,
    repository: Any,
    *,
    policy_graph: Any = None,
    seat_fn: Any = None,
    arbiter_fn: Any = None,
) -> AssessmentContext:
    """Build the injected runtime context for one assessment run.

    Seats and quorum come from the reviewed council config; the source resolver
    is the register-backed bundle resolver. ``scope``/``effective_on``/
    ``known_at`` are accepted for caller symmetry — they are request data and
    live on ``AssessmentRequest``, not on the non-serializable context.
    """
    from portal.modules.compliance.core.assessment_source import resolve_governing_bundle

    return AssessmentContext(
        repository=repository,
        seats=seat_roster(),
        quorum=council_quorum(),
        seat_fn=seat_fn,
        report_fn=None,
        report_model="",
        policy_graph=policy_graph,
        source_resolver=resolve_governing_bundle,
        arbiter_fn=arbiter_fn,
        kb_id=kb_id,
    )


def snapshot_for(
    kb_id: str, *, acquisition_receipt: dict[str, Any] | None = None
) -> CorpusSnapshot:
    """Typed convenience loader for the pinned corpus snapshot."""
    from portal.modules.compliance.core.assessment_source import build_corpus_snapshot

    return build_corpus_snapshot(kb_id, acquisition_receipt=acquisition_receipt)


def load_org_commitments_result(org_graph_path: str | Path | None = None) -> dict[str, Any]:
    """Load the built organization graph with an explicit MISSING/EMPTY/LOADED
    status and retained source/revision provenance."""
    path = Path(org_graph_path) if org_graph_path else _DEFAULT_ORG_GRAPH
    if not path.exists():
        return {"status": "MISSING", "source": str(path), "revision": "", "commitments": []}
    raw = path.read_bytes()
    revision = hashlib.sha256(raw).hexdigest()
    d = json.loads(raw.decode("utf-8"))
    docs = {x["logical_id"]: x for x in d.get("documents", [])}
    out: list[dict[str, Any]] = []
    for n in d.get("nodes", []):
        if n.get("node_type") not in ("commitment", "activity"):
            continue
        doc = docs.get(n.get("document_id"), {})
        fields = n.get("fields", {})
        out.append(
            {
                "commitment_id": n["id"],
                "document_id": n["document_id"],
                "standard_folder": doc.get("standard_folder", ""),
                "actor": ", ".join(fields.get("roles", [])) or "Responsible Entity",
                "text": n.get("text", ""),
                "relation": fields.get("relation", "IMPLEMENTS"),
                "source": str(path),
                "revision": revision,
                "document_revision_id": doc.get("revision_id", ""),
                "document_source_path": doc.get("source_path", ""),
                "document_class": doc.get("document_class", ""),
                "effective_date": doc.get("effective_date", ""),
            }
        )
    return {
        "status": "LOADED" if out else "EMPTY",
        "source": str(path),
        "revision": revision,
        "commitments": out,
    }


def load_org_commitments(org_graph_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Compatibility loader: the commitment list only. Use
    ``load_org_commitments_result`` to distinguish MISSING from EMPTY and to
    read the source/revision provenance."""
    commitments: list[dict[str, Any]] = load_org_commitments_result(org_graph_path)["commitments"]
    return commitments
