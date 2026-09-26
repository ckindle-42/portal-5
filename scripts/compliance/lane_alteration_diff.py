"""The lane-alteration diff (TASK_COMPLIANCE_PIPELINE_ALIGNMENT_V1 §P1).

The objective: a change to any NON-compliance lane cannot change a compliance
result. The check is mechanical — resolve every compliance call site's model
argument against the live config, then resolve the SAME arguments against a
config where every non-compliance workspace's model_hint is altered, and diff.
A moved resolution is a seat living in a borrowed lane.

Uses the real resolver (portal.platform.inference.model_addressing), pointed at
an altered temp copy of config/portal.yaml. Nothing on disk is modified.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import yaml

from portal.modules.compliance.core.repository import Repository

OUT_DEFAULT = Path("reports/compliance/pipeline_alignment/p1/owned_workspaces.json")
PORTAL_YAML = Path("config/portal.yaml")


def _resolve_map(portal_file: Path, model_args: list[str]) -> dict[str, str]:
    """Resolve each argument with the REAL resolver, pointed at portal_file."""
    import portal.platform.inference.model_addressing as ma

    original = ma._PORTAL_YAML
    ma._PORTAL_YAML = portal_file
    ma._BY_HINT.clear()
    ma._BY_WORKSPACE.clear()
    ma._BY_ALIAS.clear()
    try:
        return {arg: ma.workspace_id_for_model(arg) for arg in model_args}
    finally:
        ma._PORTAL_YAML = original
        ma._BY_HINT.clear()
        ma._BY_WORKSPACE.clear()
        ma._BY_ALIAS.clear()


def _alter_non_compliance(doc: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Every non-compliance workspace's model_hint is rewritten to a sentinel."""
    altered: list[str] = []
    for ws_id, cfg in (doc.get("workspaces") or {}).items():
        if not isinstance(cfg, dict):
            continue
        if cfg.get("module") == "compliance":
            continue
        hint = cfg.get("model_hint")
        if hint:
            cfg["model_hint"] = f"altered::{ws_id}"
            altered.append(ws_id)
    return doc, altered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args()

    from portal.modules.compliance.core.runtime_config import seat_roster

    repo = Repository()
    from portal.modules.compliance.core.runtime_config import reading_seat

    reading = reading_seat()
    repo.close()

    roster = seat_roster()
    # One argument per compliance call site: the reading/sweep seat tag, and
    # each council seat's declared workspace (falling back to its tag).
    model_args: list[tuple[str, str]] = [
        ("sweep.map_read / sweep.reduce_standard / reader.read", reading),
    ]
    for seat in roster:
        label = f"council.{seat['id']} ({'workspace' if seat.get('workspace') else 'tag'})"
        model_args.append((label, str(seat.get("workspace") or seat["model"])))

    doc = yaml.safe_load(PORTAL_YAML.read_text())
    baseline = _resolve_map(PORTAL_YAML, [arg for _, arg in model_args])

    doc, altered = _alter_non_compliance(doc)
    altered_file = Path("/tmp/portal.altered.yaml")
    altered_file.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False))
    after = _resolve_map(altered_file, [arg for _, arg in model_args])

    # Every compliance call must land in a workspace compliance owns.
    workspaces = yaml.safe_load(PORTAL_YAML.read_text()).get("workspaces") or {}
    rows = []
    for label, arg in model_args:
        before_ws, after_ws = baseline[arg], after[arg]
        owned = (workspaces.get(after_ws) or {}).get("module") == "compliance"
        rows.append(
            {
                "call_site": label,
                "model_arg": arg,
                "baseline_workspace": before_ws,
                "altered_config_workspace": after_ws,
                "moved": before_ws != after_ws,
                "compliance_owned": owned,
            }
        )
        print(
            f"{label:<52} {before_ws:<28} altered->{after_ws:<28} "
            f"moved={before_ws != after_ws} owned={owned}"
        )

    # The council seats' tags must NOT resolve to their old borrowed lanes
    # when addressed by tag directly either — the hint now lives in a
    # compliance workspace, and if a non-compliance workspace shares it, the
    # workspace-addressed call sites are immune but the raw-tag resolution is
    # recorded so the operator sees both.
    tag_rows = []
    for seat in roster:
        tag = seat["model"]
        tag_rows.append(
            {
                "seat": seat["id"],
                "tag": tag,
                "baseline_workspace": baseline.get(tag, workspace_of(tag, doc)),
                "note": "resolved from the tag itself; call sites address the workspace id",
            }
        )

    document = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": (
            "resolve every compliance call-site argument with the real resolver "
            "against the live config, then against a copy with every non-compliance "
            "workspace's model_hint rewritten to a sentinel; diff"
        ),
        "n_altered_workspaces": len(altered),
        "rows": rows,
        "tag_resolution_snapshot": tag_rows,
        "objective_met": all(not r["moved"] and r["compliance_owned"] for r in rows),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, default=str))
    verdict = "MET" if document["objective_met"] else "NOT MET"
    print(
        f"\nlane-alteration objective {verdict}: {len(rows)} call sites, "
        f"{len(altered)} non-compliance workspaces altered"
    )
    print(f"written: {args.out}")
    return 0 if document["objective_met"] else 1


def workspace_of(tag: str, doc: dict[str, Any]) -> str:
    for ws_id, cfg in (doc.get("workspaces") or {}).items():
        if isinstance(cfg, dict) and cfg.get("model_hint") == tag:
            return ws_id
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
