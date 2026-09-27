"""Run one isolated assess_part cross-check with a live R1 council seat.

The other assessment stages and two council seats use the deterministic
acceptance fixture. The DeepSeek seat still enters through assess_part,
run_council, and _ollama_seat; this harness appends the selected P3B contract
instructions at that per-run transport seam. Raw request, answer, reasoning,
and pipeline trace are written only to the ignored private run directory.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path.cwd().resolve()
if not (ROOT / "pyproject.toml").is_file():
    raise RuntimeError("run this helper from the portal-5 repository root")

PUBLIC_RUN = ROOT / "reports/compliance/stream_and_council_repair/20260927T095336Z"
PRIVATE_RUN = (
    ROOT / "portal/modules/compliance/data/private/stream_and_council_repair/20260927T095336Z/p3c"
)
PRIVATE_RUN.mkdir(parents=True, exist_ok=True, mode=0o700)
PRIVATE_RUN.chmod(0o700)
os.umask(0o077)

from portal.modules.compliance.core import council, reading_transport  # noqa: E402
from portal.modules.compliance.core.assessment import assess_part  # noqa: E402
from portal.modules.compliance.core.determination import AssessmentContext  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402
from portal.modules.compliance.core.runtime_config import council_quorum, seat_roster  # noqa: E402
from tests.benchmarks.compliance_judgment_r1_experiment_v2 import (  # noqa: E402
    _SEAT_SYSTEM,
    WORKSPACE,
    fetch_trace,
)
from tests.unit.test_compliance_reading_acceptance import (  # noqa: E402
    CASES,
    KB_ID,
    FakeTransport,
    build_request,
)

CONTRACT_DETAIL = (
    "\n\nCONTRACT DETAIL:\n"
    "- Treat acquisition_completeness as authoritative. If it is PARTIAL or "
    "UNKNOWN and the conclusion depends on omitted material, return INSUFFICIENT.\n"
    "- ABSENT requires acquisition_completeness COMPLETE and an explicit complete "
    "inventory showing no candidate.\n"
    "- Cite exact IDs from source_refs verbatim; do not substitute a parent reference."
)


def _trace_for(correlation_id: str) -> dict[str, Any] | None:
    if not correlation_id:
        return None
    return fetch_trace(correlation_id)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    case = copy.deepcopy(CASES["02"])
    seats = seat_roster()
    live_seat = next(seat for seat in seats if seat.get("workspace") == WORKSPACE)
    live_address = str(live_seat["workspace"])
    case["council_votes"] = {
        str(seat.get("workspace") or seat["model"]): "SUPPORTED"
        for seat in seats
        if seat["id"] != live_seat["id"]
    }

    case_receipt = PRIVATE_RUN / "assess_part_case02_private.json"
    trace_receipt = PRIVATE_RUN / "assess_part_case02_pipeline_trace.json"
    db_path = PRIVATE_RUN / "assess_part_case02.sqlite3"
    if db_path.exists():
        raise RuntimeError(f"refusing to reuse existing isolated database: {db_path}")

    fake = FakeTransport(case)
    live_calls: list[dict[str, Any]] = []
    original_chat = reading_transport.chat

    def record_chat(*args: Any, **kwargs: Any) -> Any:
        response = original_chat(*args, **kwargs)
        live_calls.append(
            {
                "model": response.get("model"),
                "content": response.get("content", ""),
                "thinking": response.get("thinking", ""),
                "raw_message": response.get("raw_message", {}),
                "correlation_id": response.get("correlation_id", ""),
                "workspace": response.get("workspace", ""),
                "route_backend": response.get("route_backend", ""),
                "served_model": response.get("served_model", ""),
                "applied_options": response.get("applied_options"),
                "reasoned": response.get("reasoned"),
                "thinking_chars": len(response.get("thinking", "")),
                "eval_tokens": response.get("eval_count"),
                "prompt_tokens": response.get("prompt_eval_count"),
                "finish_reason": response.get("finish_reason"),
                "stop_reason": response.get("stop_reason"),
                "elapsed_seconds": response.get("elapsed"),
                "num_ctx_requested": response.get("num_ctx"),
                "num_ctx_applied": response.get("num_ctx_applied"),
            }
        )
        return response

    class P3CTransport:
        def __call__(self, model: str, system: str, user: str) -> str:
            if system == _SEAT_SYSTEM and model == live_address:
                council._LAST_TRACE.clear()
                return council._ollama_seat(model, system + CONTRACT_DETAIL, user)
            return fake(model, system, user)

    context = AssessmentContext(
        repository=Repository(db_path),
        seats=seats,
        quorum=council_quorum(),
        seat_fn=P3CTransport(),
        kb_id=KB_ID,
    )
    try:
        reading_transport.chat = record_chat
        result = assess_part(build_request(case), context)
    finally:
        reading_transport.chat = original_chat
        context.repository.close()

    private = {
        "case_id": case["id"],
        "assessment_result": asdict(result),
        "assessment_receipt": result.receipt,
        "fake_transport_calls": fake.calls,
        "live_chat_calls": live_calls,
    }
    case_receipt.write_text(json.dumps(private, ensure_ascii=False, indent=2, default=str) + "\n")
    case_receipt.chmod(0o600)

    live = live_calls[-1] if live_calls else {}
    raw_trace = _trace_for(str(live.get("correlation_id", "")))
    if raw_trace is not None:
        trace_receipt.write_text(json.dumps(raw_trace, ensure_ascii=False, indent=2) + "\n")
        trace_receipt.chmod(0o600)
    trace_bodies = (raw_trace or {}).get("bodies") or {}
    backend_messages = trace_bodies.get("messages") or []
    backend_systems = [m for m in backend_messages if m.get("role") == "system"]
    backend_system = str(backend_systems[0].get("content", "")) if backend_systems else ""
    council_result = result.council_result or {}
    opinions = council_result.get("opinions", [])
    safe_opinions = [
        {
            "seat_id": opinion.get("seat_id"),
            "model": opinion.get("model"),
            "valid": opinion.get("valid"),
            "determination": opinion.get("determination"),
            "finding_type": opinion.get("finding_type"),
            "citation_count": len(opinion.get("cited_refs") or []),
            "cited_refs": opinion.get("cited_refs") or [],
            "dropped": opinion.get("dropped") or "",
        }
        for opinion in opinions
    ]

    public = {
        "phase": "P3C_LIVE_ASSESS_PART_CROSS_CHECK",
        "status": "LIVE_R1_SEAT_EXERCISED" if live_calls else "LIVE_R1_CALL_MISSING",
        "assessment_case_id": case["id"],
        "assessment_id": result.assessment_id,
        "run_id": result.run_id,
        "engine_version": result.engine_version,
        "quorum": council_result.get("quorum_required"),
        "roster_size": council_result.get("roster"),
        "council_determination": council_result.get("determination"),
        "vote_counts": council_result.get("votes"),
        "dissent_seats": council_result.get("dissent"),
        "citations": council_result.get("citations"),
        "seats": safe_opinions,
        "coverage": result.coverage,
        "documentary_coverage": result.documentary_coverage,
        "substantively_resolved": result.substantively_resolved,
        "unresolved_code": result.unresolved_code,
        "live_model_address": live.get("model"),
        "live_route": {
            "workspace": live.get("workspace"),
            "backend": live.get("route_backend"),
            "served_model": live.get("served_model"),
            "correlation_id": live.get("correlation_id"),
        },
        "applied_options": live.get("applied_options"),
        "resource_use": {
            "reasoned": live.get("reasoned"),
            "reasoning_chars": live.get("thinking_chars"),
            "eval_tokens": live.get("eval_tokens"),
            "prompt_tokens": live.get("prompt_tokens"),
            "elapsed_seconds": live.get("elapsed_seconds"),
            "finish_reason": live.get("finish_reason"),
            "stop_reason": live.get("stop_reason"),
            "num_ctx_requested": live.get("num_ctx_requested"),
            "num_ctx_applied": live.get("num_ctx_applied"),
        },
        "prompt_evidence": {
            "selected_arm": "explicit_contract",
            "system_sha256": _sha(_SEAT_SYSTEM + CONTRACT_DETAIL),
            "captured_at_backend": bool(backend_system),
            "backend_system_sha256": _sha(backend_system) if backend_system else None,
            "completeness_instruction_present": "Treat acquisition_completeness as authoritative"
            in backend_system,
            "complete_absence_instruction_present": "ABSENT requires acquisition_completeness COMPLETE"
            in backend_system,
            "exact_reference_instruction_present": "Cite exact IDs from source_refs verbatim"
            in backend_system,
        },
        "trace": {
            "outcome": (raw_trace or {}).get("outcome"),
            "backend_request_captured": bool(trace_bodies.get("backend_request")),
            "backend_messages_captured": bool(backend_messages),
            "private_trace": str(trace_receipt.resolve()) if raw_trace else None,
            "private_assessment_receipt": str(case_receipt.resolve()),
            "private_database": str(db_path.resolve()),
        },
        "scope_note": "One live DeepSeek council seat in the real assess_part cross-check; reader, alignment, and two peer seats are controlled acceptance transports. Deterministic council failure-shape tests are reported separately.",
    }
    public_path = PUBLIC_RUN / "phase-results/P3C-live-assess-part.json"
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(json.dumps(public, indent=2) + "\n")
    public_path.chmod(0o644)
    print(json.dumps(public, indent=2))


if __name__ == "__main__":
    main()
