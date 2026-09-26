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
# Third seat updated 2026-09-26: config/compliance/council.yaml is authoritative
# and this must mirror it — see that file's "Superseded seats" note for why
# mistral was replaced by deepseek_r1 (provisional, PROMOTE_POLICY: confirm).
_DEFAULT_SEATS: list[dict[str, str]] = [
    {
        "id": "qwen38",
        "label": "Qwen3.8 27B (unsloth Q4_K_M, 32k)",
        "model": "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k",
    },
    {"id": "granite41", "label": "IBM Granite 4.1 30B (16k)", "model": "granite4.1:30b-ctx16k"},
    {
        "id": "deepseek_r1",
        "label": "DeepSeek-R1-0528-Qwen3-8B (unsloth Q4_K_XL, 64k)",
        "model": "hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k",
    },
]

_DEFAULT_QUORUM = 0.66
_PORTAL_CONFIG = _CONFIG.parent / "portal.yaml"


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
        out: list[dict[str, str]] = []
        for s in seats:
            entry = {
                "id": str(s["id"]),
                "label": str(s.get("label", s["id"])),
                "model": str(s["model"]),
            }
            # The compliance-owned workspace the seat is addressed through
            # (PIPELINE_ALIGNMENT_V1 §P1). Optional so older rosters load;
            # the call sites fall back to the tag when absent.
            if s.get("workspace"):
                entry["workspace"] = str(s["workspace"])
            out.append(entry)
        return out
    return list(_DEFAULT_SEATS)


def council_quorum() -> float:
    """The configured categorical-agreement quorum, defaulting to 0.66."""
    q = _read_council_config().get("quorum")
    if isinstance(q, (int, float)) and not isinstance(q, bool):
        return float(q)
    return _DEFAULT_QUORUM


def reading_seat() -> str:
    """Resolve the single workspace-bound seat that has measured tool support.

    The workspace binding is authoritative.  A model is not eligible merely
    because a name appears in a council roster: it must have an explicit
    ``supports_tools: true`` registry record produced by a direct preflight.
    """
    import os

    configured = os.environ.get("COMPLIANCE_READING_MODEL", "")
    if not configured and _PORTAL_CONFIG.exists():
        try:
            import yaml

            portal = yaml.safe_load(_PORTAL_CONFIG.read_text()) or {}
            workspaces = portal.get("workspaces") or {}
            binding = (
                workspaces.get("compliance-reading") or workspaces.get("auto-compliance") or {}
            )
            configured = str(binding.get("model_hint", ""))
        except Exception:  # noqa: BLE001 - a malformed binding is reported below
            configured = ""
    if not configured:
        raise RuntimeError("compliance-reading has no workspace-bound reading seat")

    backends = Path(__file__).resolve().parents[4] / "config" / "backends.yaml"
    measured = False
    if backends.exists():
        try:
            import yaml

            data = yaml.safe_load(backends.read_text()) or {}
            for group in data.get("backends", []) or []:
                for candidate in group.get("models", []) or []:
                    if (
                        str(candidate.get("id", "")) == configured
                        and candidate.get("supports_tools") is True
                    ):
                        measured = True
                        break
                if measured:
                    break
        except Exception:  # noqa: BLE001 - refuse closed on malformed registry
            measured = False
    if not measured:
        raise RuntimeError(
            f"reading seat {configured!r} has no measured CAN_DRIVE_A_LOOP registry verdict"
        )
    return configured


def build_assessment_context(
    kb_id: str,
    scope: AssetScope | None,
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
