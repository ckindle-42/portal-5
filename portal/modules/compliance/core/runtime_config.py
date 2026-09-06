"""Live-analysis runtime configuration (TASK_COMPLIANCE_REASONING_V6 P7).

The council seat roster and the operator-corpus organization graph, resolved
from config with documented fallbacks so ``compliance_analyze`` can assess
LIVE rather than read a materialized row.

Seat roster: ``config/compliance/council.yaml`` ``seats:`` when present,
otherwise the three diverse defaults below (finalised by the D0-M seat
qualification — see the run report). Organization commitments: the built
``org_graph.json`` under the operator's private run directory, or an empty
list (which makes every actor-CU return ABSENT with a complete reading, the
honest answer when no corpus is ingested).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CONFIG = Path(__file__).resolve().parents[4] / "config" / "compliance"
_DEFAULT_ORG_GRAPH = (
    Path(__file__).resolve().parents[4]
    / "coding_task"
    / "v9_compliance"
    / "private"
    / "org_graph.json"
)

# D0-M-qualified default roster — three families, sized to co-reside on 64 GB
# with the Docker stack. Overridden by config/compliance/council.yaml.
_DEFAULT_SEATS: list[dict[str, str]] = [
    {"id": "granite", "label": "IBM Granite 4.2 30B", "model": "granite4.2:30b-q4_K_M"},
    {
        "id": "qwen",
        "label": "Qwen3.8 27B",
        "model": "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k",
    },
    {
        "id": "glm",
        "label": "GLM-4.7-Flash-REAP 23B",
        "model": "hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k",
    },
]


def seat_roster() -> list[dict[str, str]]:
    cfg = _CONFIG / "council.yaml"
    if cfg.exists():
        try:
            import yaml

            data = yaml.safe_load(cfg.read_text()) or {}
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
        except Exception:  # noqa: BLE001 - a malformed config falls back to the default
            pass
    return list(_DEFAULT_SEATS)


def load_org_commitments(org_graph_path: str | Path | None = None) -> list[dict[str, Any]]:
    path = Path(org_graph_path) if org_graph_path else _DEFAULT_ORG_GRAPH
    if not path.exists():
        return []
    d = json.loads(path.read_text(encoding="utf-8"))
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
            }
        )
    return out
