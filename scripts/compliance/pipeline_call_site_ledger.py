"""The live call-site ledger (TASK_COMPLIANCE_PIPELINE_ALIGNMENT_V1 §P0).

One live call per compliance call site that reaches a model, through the
DEFAULT dialect (the pipeline), each recording from the pipeline's own trace:
the workspace the model tag resolved to, the backend that answered, the model
it served, and the fallback cascade (failed backend attempts before the one
that answered). From config it records what the resolved workspace DECLARES:
think, sampling, predict_limit, context_limit — the values the pipeline
applies to the call regardless of what the caller asked for.

The ledger is measured, not derived: the §0.1 table in the task file came from
resolving tags against config; this script exercises the calls. Call sites
whose transport function returns only the seat's content (the council and
alignment seats, the reading/report closures) do not surface a correlation id;
their rows carry the config prediction and an ``observed_correlation_id`` is
bound afterwards by call order against /v1/trace (see the receipt's
``observed_traces_note``).

Sites and the production shape each row drives:

* ``sweep.map_read``            — one map reading, write=False, seat tag from
                                  scripts/compliance/closeout_family_sweep.py
* ``sweep.reduce_standard``     — the standard-level reduce over the stored
                                  CIP-007 map answers
* ``reader.read``               — the batch/conversational reader's answer
                                  path (the tool loop), store=False
* ``reading.read_and_judge``    — the assessment reading judgment's default
                                  transport closure (production context:
                                  report_fn None → the chat closure, model =
                                  seats[0])
* ``obligation_alignment``      — the alignment seat fn, one row per roster
                                  seat (align_part loops the whole roster)
* ``assessment_report.explain`` — the coverage reporter's transport closure
                                  (production: report_model "" → seats[0])
* ``council._ollama_seat``      — one row per roster seat
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.transport_dialects import _pipeline_api_key
from portal.platform.inference.model_addressing import workspace_id_for_model

OUT_DEFAULT = Path("reports/compliance/pipeline_alignment/p0/call_site_ledger.json")

# The sweep seat the family campaigns pass (closeout_family_sweep.SEAT).
SWEEP_SEAT = "gemma4:26b-a4b-it-q4_K_M-ctx32k"


def _trace(cid: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://localhost:9099/v1/trace/{cid}",
        headers={"Authorization": f"Bearer {_pipeline_api_key()}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return json.load(response)
    except Exception as exc:  # noqa: BLE001 — a missing trace is recorded, not fatal
        return {"error": f"{type(exc).__name__}: {exc}"}


def _cascade(trace: dict[str, Any]) -> dict[str, Any]:
    """The fallback cascade from one turn's spans: every failed attempt, then
    the backend that answered."""
    spans = trace.get("spans") or []
    attempts = [
        {"backend": s.get("backend"), "outcome": s.get("outcome")}
        for s in spans
        if s.get("name") == "backend.attempt"
    ]
    selected = next((s for s in spans if s.get("name") == "backend.selected"), {})
    return {
        "failed_attempts": attempts,
        "selected_backend": selected.get("backend"),
        "selected_model": selected.get("model"),
        "fell_back": bool(attempts),
    }


def _declared(workspace_id: str) -> dict[str, Any]:
    """What the resolved workspace DECLARES in config/portal.yaml — the values
    the pipeline applies to a call addressed to it."""
    from portal.platform.inference.model_addressing import workspaces

    ws = workspaces().get(workspace_id)
    if not ws:
        return {"workspace_id": workspace_id, "found": False}
    keys = (
        "module",
        "model_hint",
        "think",
        "emits_reasoning",
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "repeat_penalty",
        "predict_limit",
        "context_limit",
        "max_concurrent",
    )
    out: dict[str, Any] = {"workspace_id": workspace_id, "found": True}
    for key in keys:
        if key in ws:
            out[key] = ws[key]
    return out


def _build_row(
    site: str, seat: str, fields: dict[str, Any], cid: str, started: float
) -> dict[str, Any]:
    fields["wall_s"] = round(time.time() - started, 2)
    trace = _trace(cid) if cid else {}
    cascade = _cascade(trace) if trace and "error" not in trace else {"trace_error": trace}
    ws_id = fields.get("workspace") or workspace_id_for_model(seat)
    return {
        "site": site,
        "model_arg": seat,
        "config_prediction": workspace_id_for_model(seat),
        "dialect": fields.get("dialect", ""),
        "correlation_id": cid,
        "trace_workspace": trace.get("workspace"),
        "route_backend": fields.get("route_backend") or trace.get("backend"),
        "served_model": fields.get("served_model") or trace.get("model"),
        "cascade": cascade,
        "declared": _declared(ws_id),
        "wall_s": fields.get("wall_s"),
    }


def _recent_cids() -> set[str]:
    request = urllib.request.Request(
        "http://localhost:9099/v1/trace?limit=50",
        headers={"Authorization": f"Bearer {_pipeline_api_key()}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            body = json.load(response)
        rows = body.get("data") if isinstance(body, dict) else body
        return {r.get("correlation_id", "") for r in rows or []}
    except Exception:  # noqa: BLE001 — the diff degrades to "no ids" not a crash
        return set()


def _sites_examined_and_excluded() -> list[dict[str, str]]:
    return [
        {
            "path": "portal/modules/compliance/core/candidate_links.py (vl_rerank) and propose.py",
            "reason": "reaches the VL reranker/embedding service (retrieval stack, "
            "portal/platform/retrieval/embedding.py), not a chat-model seat; no "
            "workspace lane exists or applies",
        },
        {
            "path": "portal/modules/compliance/tools/compliance_mcp.py:496, "
            "core/cip_register.py:205, core/nerc_source_sync.py:142",
            "reason": "web/document fetches (nerc.com, source sync), not model calls",
        },
    ]


def run_single_call_sites(repo: Repository, rows: list[dict[str, Any]]) -> None:
    """map_read, reduce_standard and reader.read — the sites whose transport
    functions hand back enough to bind the trace directly."""
    from portal.modules.compliance.core.sweep import map_read, sweep_order

    ref = sweep_order(repo)[0]

    started = time.time()
    payload = map_read(repo, ref, model=SWEEP_SEAT, write=False)
    fields = {
        k: payload.get(k, "") for k in ("dialect", "workspace", "route_backend", "served_model")
    }
    row = _build_row(
        "sweep.map_read", SWEEP_SEAT, fields, payload.get("correlation_id", ""), started
    )
    row["ref"] = ref
    if "error" in payload:
        row["call_error"] = payload["error"]
    rows.append(row)
    _print_row(row)

    from portal.modules.compliance.core.sweep import reduce_standard, sweep_answers

    started = time.time()
    answers = sweep_answers(repo, "CIP-007-6")
    payload = reduce_standard(repo, "CIP-007-6", answers, model=SWEEP_SEAT)
    row = _build_row("sweep.reduce_standard", SWEEP_SEAT, {"dialect": "pipeline"}, "", started)
    row["n_answers"] = len(answers)
    row["observed_correlation_id"] = _newest_trace_cid(row.get("config_prediction", ""))
    row["note"] = (
        "reduce_standard returns a store receipt, not a ChatResult; the live turn "
        "is bound out-of-band as observed_correlation_id"
    )
    rows.append(row)
    _print_row(row)

    if os.environ.get("LEDGER_SKIP_READER") == "1":
        return

    from portal.modules.compliance.core.reader import read
    from portal.modules.compliance.core.runtime_config import reading_seat

    seat = reading_seat()
    before = _recent_cids()
    started = time.time()
    payload = read(
        repo,
        "State this requirement's Part number and the revision you read. Nothing else.",
        ref,
        model=seat,
        store=False,
        timeout=600,
    )
    new = sorted(_recent_cids() - before)
    row = _build_row("reader.read", seat, {"dialect": "pipeline"}, new[0] if new else "", started)
    row["ref"] = ref
    row["turn_correlation_ids"] = new
    row["reader_failed"] = bool(payload.get("failed"))
    row["reader_stop_reason"] = payload.get("stop_reason", "")
    rows.append(row)
    _print_row(row)


def _newest_trace_cid(workspace_hint: str) -> str:
    request = urllib.request.Request(
        "http://localhost:9099/v1/trace?limit=5",
        headers={"Authorization": f"Bearer {_pipeline_api_key()}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            body = json.load(response)
        rows = body.get("data") if isinstance(body, dict) else body
        for entry in rows or []:
            if workspace_hint in (entry.get("workspace") or ""):
                return str(entry.get("correlation_id", ""))
    except Exception:  # noqa: BLE001 — binding is best-effort, recorded as absent
        return ""
    return ""


def _print_row(row: dict[str, Any]) -> None:
    print(
        f"{row['site']:<34} {row['model_arg'].split(':')[-1][:24]:<26} -> "
        f"{row['route_backend']} / {str(row['served_model'])[:40]}",
        flush=True,
    )


def _record_and_bind(
    rows: list[dict[str, Any]],
    site: str,
    seat: str,
    started: float,
    fields: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one row whose call site does not surface a correlation id; bind
    the live turn out-of-band against the newest trace for the workspace."""
    row = _build_row(site, seat, fields or {"dialect": "pipeline"}, "", started)
    row["observed_correlation_id"] = _newest_trace_cid(row.get("config_prediction", ""))
    row.update(extra or {})
    rows.append(row)
    _print_row(row)


def _run_reading_and_alignment(repo: Repository, rows: list[dict[str, Any]], ref: str) -> None:
    """reading.read_and_judge and the alignment seat fn per roster seat."""
    import json as _json

    from portal.modules.compliance.core.determination import AssessmentContext, AssessmentRequest
    from portal.modules.compliance.core.obligation_alignment import (
        _ALIGNMENT_SYSTEM,
        _default_seat_fn,
    )
    from portal.modules.compliance.core.reading import read_and_judge
    from portal.modules.compliance.core.runtime_config import seat_roster

    roster = seat_roster()
    context = AssessmentContext(repository=repo, seats=roster, seat_fn=None, report_fn=None)
    started = time.time()
    judgment = read_and_judge(AssessmentRequest(requirement_id=ref), context)
    _record_and_bind(
        rows,
        "reading.read_and_judge",
        roster[0]["model"],
        started,
        extra={
            "note": (
                "production context: report_fn/seat_fn None -> the site's chat "
                "closure; model = seats[0]"
            ),
            "judgment_valid": judgment.valid,
        },
    )

    fn = _default_seat_fn()
    packet = _json.dumps(
        {
            "task": "clause_alignment",
            "candidates": [
                {"candidate_id": "C0", "text": "The operator reviews access quarterly."}
            ],
        }
    )
    for seat_entry in roster:
        started = time.time()
        fields: dict[str, Any] = {}
        try:
            fn(seat_entry["model"], _ALIGNMENT_SYSTEM, packet)
        except Exception as exc:  # noqa: BLE001 — a failed seat is a recorded row
            fields["call_error"] = f"{type(exc).__name__}: {exc}"
        _record_and_bind(
            rows, f"obligation_alignment.{seat_entry['id']}", seat_entry["model"], started, fields
        )


def _run_explain(repo: Repository, rows: list[dict[str, Any]], ref: str) -> None:
    """assessment_report.explain — the coverage reporter's transport."""
    from portal.modules.compliance.core.assessment_report import explain
    from portal.modules.compliance.core.determination import AssessmentContext, AssessmentRequest
    from portal.modules.compliance.core.obligation_alignment import AlignmentResult
    from portal.modules.compliance.core.runtime_config import seat_roster

    roster = seat_roster()
    context = AssessmentContext(repository=repo, seats=roster, seat_fn=None, report_fn=None)
    started = time.time()
    explanation = explain(
        AssessmentRequest(requirement_id=ref),
        {},
        AlignmentResult(part_ref=ref, records=[], valid=True),
        {},
        context,
    )
    _record_and_bind(
        rows,
        "assessment_report.explain",
        roster[0]["model"],
        started,
        extra={
            "note": (
                "production: report_model '' -> model = seats[0]; transport is the "
                "site's chat closure (budget 8192, fmt json)"
            ),
            "explanation_valid": explanation.valid,
        },
    )


def _run_council_seats(rows: list[dict[str, Any]], ref: str) -> None:
    """council._ollama_seat, one row per roster seat."""
    import json as _json

    from portal.modules.compliance.core.council import _ollama_seat
    from portal.modules.compliance.core.runtime_config import seat_roster

    seat_packet = _json.dumps(
        {"governing_unit": {"ref": ref}, "candidates": [], "reference_closure": []}
    )
    for seat_entry in seat_roster():
        started = time.time()
        fields: dict[str, Any] = {}
        try:
            _ollama_seat(seat_entry["model"], "You are a test seat.", seat_packet)
        except Exception as exc:  # noqa: BLE001 — a failed seat is a recorded row
            fields["call_error"] = f"{type(exc).__name__}: {exc}"
        _record_and_bind(
            rows, f"council._ollama_seat.{seat_entry['id']}", seat_entry["model"], started, fields
        )


def run_seat_fn_sites(repo: Repository, rows: list[dict[str, Any]]) -> None:
    """The assessment reading/report closures, the alignment seat fn and the
    council seats — each returns content only, so the trace is bound
    out-of-band after the call."""
    from portal.modules.compliance.core.sweep import sweep_order

    ref = sweep_order(repo)[0]
    _run_reading_and_alignment(repo, rows, ref)
    _run_explain(repo, rows, ref)
    _run_council_seats(rows, ref)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args()
    if os.environ.get("COMPLIANCE_TRANSPORT", "pipeline") != "pipeline":
        print("FAIL: COMPLIANCE_TRANSPORT must be unset or 'pipeline' for this ledger")
        return 3

    rows: list[dict[str, Any]] = []
    repo = Repository()
    run_single_call_sites(repo, rows)
    run_seat_fn_sites(repo, rows)
    repo.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_commit": os.popen("git rev-parse HEAD").read().strip(),
        "default_dialect": "pipeline",
        "observed_traces_note": (
            "correlation ids for rows whose call sites do not surface them were bound "
            "by call order and workspace against /v1/trace immediately after each call"
        ),
        "rows": rows,
        "sites_examined_and_excluded": _sites_examined_and_excluded(),
    }
    args.out.write_text(json.dumps(document, indent=2, default=str))
    print(f"\nledger written: {args.out} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
