"""Version 2 bounded incumbent R1 experiment on dev and frozen holdout.

Model responses, reasoning traces, and backend request bodies are written only
to the ignored private receipt directory. Public phase receipts contain IDs,
route metadata, scores, and error classes, never prompt or response bodies.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Any

from portal.modules.compliance.core.council import _MODEL_TEMPERATURE, _SEAT_BUDGET, _SEAT_SYSTEM
from portal.modules.compliance.core.reading_transport import (
    DEFAULT_EFFORT,
    DEFAULT_NUM_CTX,
    DEFAULT_TEMPERATURE,
    chat,
)
from portal.modules.compliance.core.transport_dialects import _pipeline_api_key, resolve_dialect
from portal.platform.inference.model_addressing import workspace_model_hint
from portal.platform.inference.router.workspaces import WORKSPACES
from tests.benchmarks.bench_judgment_probe_v6 import (
    aggregate as aggregate_v1,
)
from tests.benchmarks.bench_judgment_probe_v6 import (
    parse_output as parse_output_v1,
)
from tests.benchmarks.bench_judgment_probe_v6 import (
    score_case as score_case_v1,
)
from tests.benchmarks.bench_judgment_probe_v6 import (
    std_nums as std_nums_v1,
)
from tests.benchmarks.compliance_judgment_contract_v2 import (
    aggregate_v2,
    packet_v2,
    score_case_v2,
)

ROOT = Path(__file__).resolve().parents[2]
RUN_ID = "20260927T095336Z"
PUBLIC_RUN = ROOT / "reports/compliance/stream_and_council_repair" / RUN_ID
PRIVATE_RUN = (
    ROOT
    / "portal/modules/compliance/data/private/stream_and_council_repair"
    / RUN_ID
    / "council_experiment_v2"
)
R1_TEMPLATE_DIR = Path(
    "/Volumes/data01/omlx-models/DeepSeek-R1-0528-Qwen3-8B-4bit"
)
R1_CHAT_TEMPLATE = R1_TEMPLATE_DIR / "chat_template.jinja"
R1_TOKENIZER_CONFIG = R1_TEMPLATE_DIR / "tokenizer_config.json"
DEV_CASES = ROOT / "tests/compliance_probe/judgment_probe_v6.jsonl"
HOLDOUT_CASES = ROOT / "tests/compliance_probe/judgment_probe_holdout_v1.jsonl"
WORKSPACE = "compliance-council-deepseek-r1"
PIPELINE_URL = os.environ.get("PIPELINE_BASE", "http://localhost:9099").rstrip("/")
TIMEOUT_S = 900
WORKSPACE_POLICY = WORKSPACES.get(WORKSPACE, {})

PROMPT_EXPLICIT_CONTRACT = (
    _SEAT_SYSTEM
    + "\n\nCONTRACT DETAIL:\n"
    + "- Treat acquisition_completeness as authoritative. If it is PARTIAL or "
    + "UNKNOWN and the conclusion depends on omitted material, return INSUFFICIENT.\n"
    + "- ABSENT requires acquisition_completeness COMPLETE and an explicit complete "
    + "inventory showing no candidate.\n"
    + "- Cite exact IDs from source_refs verbatim; do not substitute a parent reference."
)

ARMS = ("production", "user_role", "explicit_contract")
DEV_ORDER = (
    ("production", 1),
    ("user_role", 1),
    ("explicit_contract", 1),
    ("explicit_contract", 2),
    ("user_role", 2),
    ("production", 2),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _applicability(case: dict[str, Any]) -> str:
    declared = case.get("applicability")
    if isinstance(declared, str) and declared.upper() in {"APPLIES", "UNKNOWN", "CONFLICTED"}:
        return declared.upper()
    text = " ".join(
        [str(case.get("governing_text", "")), *[str(p) for p in case.get("premises", [])]]
    ).lower()
    if "if any" in text and "does not state whether" in text:
        return "UNKNOWN"
    return "APPLIES"


def production_packet(case: dict[str, Any]) -> dict[str, Any]:
    """Preserve v6 evidence in a product-shaped, explicitly referenced packet."""
    versioned = packet_v2(case)
    refs = versioned["source_refs"]
    complete = bool(case.get("packet_complete"))
    candidate = case.get("candidate_text")
    packet = {
        "governing_unit": versioned["governing_unit"],
        "premises": versioned["premises"],
        "candidate_implementation": candidate,
        "candidates": [] if candidate is None else [{"text": candidate}],
        "packet_complete": complete,
        "acquisition_completeness": "COMPLETE" if complete else "PARTIAL",
        "applicability": {"state": _applicability(case)},
        "reference_closure": [ref for ref in refs if ref != case["governing_ref"]],
        "source_refs": refs,
    }
    return packet


def messages_for_arm(case: dict[str, Any], arm: str) -> list[dict[str, str]]:
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    system = PROMPT_EXPLICIT_CONTRACT if arm == "explicit_contract" else _SEAT_SYSTEM
    packet_text = json.dumps(production_packet(case), ensure_ascii=False, indent=2)
    first_role = "user" if arm == "user_role" else "system"
    return [
        {"role": first_role, "content": system},
        {"role": "user", "content": packet_text},
    ]


def frozen_manifest() -> dict[str, Any]:
    dialect = resolve_dialect()
    if dialect.name != "pipeline":
        raise RuntimeError(f"expected production pipeline transport, got {dialect.name}")
    dev = load_cases(DEV_CASES)
    holdout = load_cases(HOLDOUT_CASES)
    tag = workspace_model_hint(WORKSPACE) or WORKSPACE
    return {
        "experiment": "compliance_r1_incumbent_v2",
        "frozen_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "status": "FROZEN_BEFORE_NEW_R1_INFERENCE",
        "model_address": WORKSPACE,
        "model_tag": tag,
        "expected_route": {
            "workspace": WORKSPACE,
            "backend": "omlx-reasoning",
            "served_model": "DeepSeek-R1-0528-Qwen3-8B-4bit",
        },
        "served_template_identity": {
            "directory": str(R1_TEMPLATE_DIR),
            "chat_template_sha256": sha256_bytes(R1_CHAT_TEMPLATE.read_bytes())
            if R1_CHAT_TEMPLATE.is_file()
            else None,
            "tokenizer_config_sha256": sha256_bytes(R1_TOKENIZER_CONFIG.read_bytes())
            if R1_TOKENIZER_CONFIG.is_file()
            else None,
        },
        "applied_policy_expected_from_workspace": {
            "temperature": _MODEL_TEMPERATURE.get(
                tag, WORKSPACE_POLICY.get("temperature", DEFAULT_TEMPERATURE)
            ),
            "top_p": WORKSPACE_POLICY.get("top_p"),
            "top_k": WORKSPACE_POLICY.get("top_k"),
            "min_p": WORKSPACE_POLICY.get("min_p"),
            "workspace_context_limit": WORKSPACE_POLICY.get("context_limit"),
            "caller_num_ctx_default": DEFAULT_NUM_CTX,
            "backend_request_num_ctx": None,
            "context_enforcement": "workspace policy 65536 via derived ctx64k served model tag; pipeline OpenAI request omits num_ctx",
            "workspace_declared_output_limit": WORKSPACE_POLICY.get("predict_limit"),
            "production_caller_answer_budget": _SEAT_BUDGET,
            "production_caller_think_argument": DEFAULT_EFFORT,
            "production_caller_reasoning_allowance_applied": 0,
            "requested_total_predict_tokens": _SEAT_BUDGET,
            "expected_applied_output_limit": _SEAT_BUDGET,
            "workspace_think_policy": WORKSPACE_POLICY.get("think"),
            "enable_thinking": WORKSPACE_POLICY.get("think"),
            "presence_penalty": WORKSPACE_POLICY.get("presence_penalty"),
            "repeat_penalty": WORKSPACE_POLICY.get("repeat_penalty"),
            "seed": WORKSPACE_POLICY.get("seed"),
            "concurrency": 1,
        },
        "transport_contract": {
            "dialect": dialect.name,
            "response_format": "json_object",
            "tools": "none; portal_no_tools true",
            "timeout_seconds_per_call": TIMEOUT_S,
            "retries": "none in this driver; one production bounded native retry is unreachable for pipeline; every exception is a retained failed cell",
            "raw_and_reasoning_receipts": str(PRIVATE_RUN),
            "preflight_correction": (
                "V1 incorrectly added DEFAULT_REASONING_ALLOWANCE although the production caller "
                "uses DEFAULT_EFFORT=False and does not pass think=True. The workspace then "
                "enables template thinking, while applied output_limit remains the caller's "
                "8192. V1's four completed cells are retained separately and excluded."
            ),
        },
        "arms": {
            "production": {
                "change": "none; current _SEAT_SYSTEM in system role",
                "prompt_sha256": sha256_bytes(_SEAT_SYSTEM.encode()),
            },
            "user_role": {
                "change": "same two message bodies and order; first message role changes from system to user",
                "prompt_sha256": sha256_bytes(_SEAT_SYSTEM.encode()),
            },
            "explicit_contract": {
                "change": "production system role plus explicit acquisition completeness, complete-absence, and exact source_refs citation rules",
                "prompt_sha256": sha256_bytes(PROMPT_EXPLICIT_CONTRACT.encode()),
            },
        },
        "repetitions": 2,
        "development": {
            "path": str(DEV_CASES.relative_to(ROOT)),
            "sha256": sha256_bytes(DEV_CASES.read_bytes()),
            "n": len(dev),
            "case_ids": [case["id"] for case in dev],
            "exposed_cases": True,
        },
        "frozen_holdout": {
            "path": str(HOLDOUT_CASES.relative_to(ROOT)),
            "sha256": sha256_bytes(HOLDOUT_CASES.read_bytes()),
            "n": len(holdout),
            "case_ids": [case["id"] for case in holdout],
            "gold_labels_and_rationales_private_to_scorer": True,
        },
        "scorer": {
            "version": "compliance_judgment_contract_v2",
            "path": "tests/benchmarks/compliance_judgment_contract_v2.py",
            "sha256": sha256_bytes(
                (ROOT / "tests/benchmarks/compliance_judgment_contract_v2.py").read_bytes()
            ),
            "acceptance_bars": {
                "violation_class_accuracy_min": 0.87,
                "abstain_recall": 1.0,
                "schema_valid_rate": 1.0,
            },
        },
        "legacy_scorer": {
            "version": "judgment_probe_v6 unchanged",
            "path": "tests/benchmarks/bench_judgment_probe_v6.py",
            "sha256": sha256_bytes(
                (ROOT / "tests/benchmarks/bench_judgment_probe_v6.py").read_bytes()
            ),
            "purpose": "side-by-side descriptive scoring only; V2 strict final-object scoring controls gates",
        },
        "design": {
            "development_order_per_case": [f"{arm}:rep{rep}" for arm, rep in DEV_ORDER],
            "holdout": "selected arm only, two repetitions, no prompt or scorer edits after selection",
            "score_final_answer_only": True,
            "no_json_salvage_from_reasoning_or_prose": True,
            "no_model_swap_or_promotion": True,
            "v1_preflight_cells_excluded": {
                "count": 4,
                "receipt": "portal/modules/compliance/data/private/stream_and_council_repair/20260927T095336Z/council_experiment/dev_campaign.jsonl",
                "public_summary": "reports/compliance/stream_and_council_repair/20260927T095336Z/phase-results/P3B-v1-preflight-invalid.json",
                "reason": "The v1 manifest predicted 12288 tokens; live trace showed 8192 applied. They are preserved, not retried or included in v2 scores.",
            },
        },
        "source_hashes": {
            "production_prompt_source": "portal/modules/compliance/core/council.py",
            "production_council_source": sha256_bytes(
                (ROOT / "portal/modules/compliance/core/council.py").read_bytes()
            ),
            "workspace_policy": sha256_bytes((ROOT / "config/portal.yaml").read_bytes()),
            "backend_routes": sha256_bytes((ROOT / "config/backends.yaml").read_bytes()),
            "council_seat_policy": sha256_bytes(
                (ROOT / "config/compliance/council.yaml").read_bytes()
            ),
            "reading_transport": sha256_bytes(
                (ROOT / "portal/modules/compliance/core/reading_transport.py").read_bytes()
            ),
            "pipeline_dialect": sha256_bytes(
                (ROOT / "portal/modules/compliance/core/transport_dialects.py").read_bytes()
            ),
            "experiment_driver": sha256_bytes(Path(__file__).read_bytes()),
        },
        "web_model_guidance": [
            "https://github.com/deepseek-ai/DeepSeek-R1/blob/main/README.md",
            "https://huggingface.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF/blob/main/README.md",
        ],
        "secrets_recorded": False,
    }


def write_manifest() -> None:
    manifest = frozen_manifest()
    target = PUBLIC_RUN / "experiment_manifest_v2.json"
    if target.exists():
        existing = json.loads(target.read_text())
        comparison = {k: v for k, v in existing.items() if k != "frozen_at_utc"}
        current = {k: v for k, v in manifest.items() if k != "frozen_at_utc"}
        if comparison != current:
            raise RuntimeError("version 2 experiment manifest already exists with different frozen inputs")
        print(f"frozen manifest already matches: {target}")
        return
    PUBLIC_RUN.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2) + "\n")
    target.chmod(0o644)
    print(f"frozen manifest: {target}")


def fetch_trace(correlation_id: str) -> dict[str, Any] | None:
    if not correlation_id:
        return None
    request = urllib.request.Request(
        f"{PIPELINE_URL}/v1/trace/{correlation_id}",
        headers={"Authorization": f"Bearer {_pipeline_api_key()}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            return json.load(response)
    except Exception:
        return None


def private_jsonl_path(suite: str) -> Path:
    return PRIVATE_RUN / f"{suite}_campaign.jsonl"


def _read_completed(path: Path) -> set[tuple[str, str, int]]:
    completed: set[tuple[str, str, int]] = set()
    if not path.exists():
        return completed
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        completed.add((str(row["case_id"]), str(row["arm"]), int(row["rep"])))
    return completed


def _append_private(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)


def _run_cell(case: dict[str, Any], arm: str, rep: int) -> dict[str, Any]:
    packet = production_packet(case)
    messages = messages_for_arm(case, arm)
    tag = workspace_model_hint(WORKSPACE) or WORKSPACE
    started = time.monotonic()
    try:
        result = chat(
            WORKSPACE,
            messages=messages,
            budget=_SEAT_BUDGET,
            fmt="json",
            temperature=_MODEL_TEMPERATURE.get(tag, DEFAULT_TEMPERATURE),
            timeout=TIMEOUT_S,
        )
        elapsed = time.monotonic() - started
        trace = fetch_trace(result.get("correlation_id", ""))
        final_text = result.content
        score = score_case_v2(case, final_text)
        return {
            "case_id": case["id"],
            "arm": arm,
            "rep": rep,
            "request": {"model": WORKSPACE, "messages": messages, "packet": packet},
            "response": {
                "content": final_text,
                "reasoning_content": result.thinking,
                "raw_message": result.raw_message,
            },
            "result": {
                "score_v2": score,
                "route_workspace": result.get("workspace", ""),
                "route_backend": result.get("route_backend", ""),
                "served_model": result.get("served_model", ""),
                "correlation_id": result.get("correlation_id", ""),
                "options_applied": result.get("applied_options"),
                "reasoned": result.reasoned,
                "thinking_chars": len(result.thinking),
                "num_ctx_requested": result.get("num_ctx"),
                "num_ctx_applied": result.get("num_ctx_applied"),
                "seat_ceiling": result.get("seat_ceiling"),
                "finish_reason": result.get("finish_reason"),
                "stop_reason": result.get("stop_reason"),
                "eval_tokens": result.get("eval_count"),
                "prompt_tokens": result.get("prompt_eval_count"),
                "usage": result.get("usage"),
                "elapsed_seconds": round(elapsed, 2),
                "trace": trace,
                "backend_request_captured": bool(
                    trace and (trace.get("bodies") or {}).get("backend_request")
                ),
            },
        }
    except Exception as exc:  # one cell is retained as an error, never retried
        return {
            "case_id": case["id"],
            "arm": arm,
            "rep": rep,
            "request": {"model": WORKSPACE, "messages": messages, "packet": packet},
            "response": {"content": "", "reasoning_content": "", "raw_message": {}},
            "result": {
                "score_v2": score_case_v2(case, ""),
                "exception_type": type(exc).__name__,
                "exception": str(exc),
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "trace": None,
                "backend_request_captured": False,
            },
        }


def _public_cell(row: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    result = row["result"]
    score = result["score_v2"]
    legacy = result.get("score_v1") or {}
    return {
        "case_id": row["case_id"],
        "category": case.get("category"),
        "gold_label": case["gold_label"],
        "arm": row["arm"],
        "rep": row["rep"],
        "pred": score.get("pred"),
        "schema_ok": score.get("schema_ok"),
        "schema_error": score.get("schema_error", ""),
        "correct": score.get("correct"),
        "violation_class_correct": (
            score.get("correct")
            if case["gold_label"] in {"SUPPORTED", "ABSTAIN", "INSUFFICIENT"}
            else score.get("pred") in {"PARTIAL", "CONTRADICTED", "ABSENT"}
        ),
        "literal_false_supported": score.get("literal_false_supported"),
        "conservative_unresolved_penalty": score.get("conservative_unresolved_penalty"),
        "missed_abstain": score.get("missed_abstain"),
        "citation_ok": score.get("citation_ok"),
        "off_packet_citations": score.get("off_packet_citations", []),
        "exception_type": result.get("exception_type", ""),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "route_workspace": result.get("route_workspace", ""),
        "route_backend": result.get("route_backend", ""),
        "served_model": result.get("served_model", ""),
        "correlation_id": result.get("correlation_id", ""),
        "finish_reason": result.get("finish_reason"),
        "stop_reason": result.get("stop_reason"),
        "eval_tokens": result.get("eval_tokens"),
        "prompt_tokens": result.get("prompt_tokens"),
        "reasoning_chars": result.get("thinking_chars", 0),
        "num_ctx_requested": result.get("num_ctx_requested"),
        "num_ctx_applied": result.get("num_ctx_applied"),
        "seat_ceiling": result.get("seat_ceiling"),
        "backend_request_captured": result.get("backend_request_captured", False),
        "options_applied": result.get("options_applied"),
        "legacy_v1_schema_ok": legacy.get("schema_ok"),
        "legacy_v1_pred": legacy.get("pred"),
        "legacy_v1_correct": legacy.get("correct"),
        "legacy_v1_citation_ok": legacy.get("citation_ok"),
    }


def _write_public_summaries(suite: str, cases: list[dict[str, Any]], private_path: Path) -> None:
    raw_rows = [json.loads(line) for line in private_path.read_text().splitlines() if line.strip()]
    case_by_id = {case["id"]: case for case in cases}
    cells = [_public_cell(row, case_by_id[row["case_id"]]) for row in raw_rows]
    for arm in ARMS if suite == "dev" else ARMS:
        for rep in (1, 2):
            selected = [cell for cell in cells if cell["arm"] == arm and cell["rep"] == rep]
            if not selected:
                continue
            selected.sort(
                key=lambda cell: next(
                    i for i, case in enumerate(cases) if case["id"] == cell["case_id"]
                )
            )
            selected_cases = [case_by_id[cell["case_id"]] for cell in selected]
            score_rows = [
                score_case_v2(
                    case,
                    next(
                        row["response"]["content"]
                        for row in raw_rows
                        if row["case_id"] == cell["case_id"]
                        and row["arm"] == arm
                        and row["rep"] == rep
                    ),
                )
                for case, cell in zip(selected_cases, selected, strict=True)
            ]
            legacy_rows = [
                score_case_v1(
                    case,
                    parse_output_v1(
                        next(
                            row["response"]["content"]
                            for row in raw_rows
                            if row["case_id"] == cell["case_id"]
                            and row["arm"] == arm
                            and row["rep"] == rep
                        )
                    ),
                    std_nums_v1(
                        " ".join(
                            [
                                case["governing_ref"],
                                case["governing_text"],
                                *case.get("premises", []),
                            ]
                        )
                    ),
                )
                for case, cell in zip(selected_cases, selected, strict=True)
            ]
            summary = {
                "phase": "P3B_DEVELOPMENT" if suite == "dev" else "P3B_FROZEN_HOLDOUT",
                "suite": suite,
                "arm": arm,
                "repetition": rep,
                "complete": len(selected) == len(cases),
                "case_count": len(selected),
                "expected_case_count": len(cases),
                "aggregate_v2": aggregate_v2(selected_cases, score_rows),
                "legacy_v1_aggregate_same_final_fields": aggregate_v1(legacy_rows, selected_cases),
                "case_results": selected,
                "latency_seconds": {
                    "mean": round(statistics.mean(c["elapsed_seconds"] or 0 for c in selected), 2),
                    "median": round(
                        statistics.median(c["elapsed_seconds"] or 0 for c in selected), 2
                    ),
                    "max": round(max(c["elapsed_seconds"] or 0 for c in selected), 2),
                },
                "private_receipt": str(private_path),
            }
            suffix = f"dev-{arm}-rep{rep}" if suite == "dev" else f"holdout-{arm}-rep{rep}"
            target = PUBLIC_RUN / "phase-results" / f"P3B-{suffix}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(summary, indent=2) + "\n")


def run_campaign(suite: str, selected_holdout_arm: str | None = None) -> None:
    if suite == "dev":
        cases = load_cases(DEV_CASES)
        schedule = DEV_ORDER
    elif suite == "holdout":
        cases = load_cases(HOLDOUT_CASES)
        if selected_holdout_arm not in ARMS:
            raise ValueError("holdout requires the selected arm from the development review")
        schedule = ((selected_holdout_arm, 1), (selected_holdout_arm, 2))
    else:
        raise ValueError(f"unsupported suite {suite!r}")

    manifest_path = PUBLIC_RUN / "experiment_manifest_v2.json"
    if not manifest_path.exists():
        raise RuntimeError("freeze experiment_manifest_v2.json before any R1 inference")
    manifest = json.loads(manifest_path.read_text())
    frozen_input = manifest["frozen_holdout" if suite == "holdout" else "development"]
    source_path = HOLDOUT_CASES if suite == "holdout" else DEV_CASES
    if sha256_bytes(source_path.read_bytes()) != frozen_input["sha256"]:
        raise RuntimeError(f"{suite} source changed after freeze")
    if sha256_bytes(Path(__file__).read_bytes()) != manifest["source_hashes"]["experiment_driver"]:
        raise RuntimeError("experiment driver changed after freeze")
    if (
        sha256_bytes((ROOT / "tests/benchmarks/compliance_judgment_contract_v2.py").read_bytes())
        != manifest["scorer"]["sha256"]
    ):
        raise RuntimeError("V2 scorer changed after freeze")
    if (
        sha256_bytes((ROOT / "tests/benchmarks/bench_judgment_probe_v6.py").read_bytes())
        != manifest["legacy_scorer"]["sha256"]
    ):
        raise RuntimeError("legacy scorer changed after freeze")

    private_path = private_jsonl_path(suite)
    completed = _read_completed(private_path)
    done = len(completed)
    total = len(cases) * len(schedule)
    for case_index, case in enumerate(cases, start=1):
        for arm, rep in schedule:
            key = (case["id"], arm, rep)
            if key in completed:
                continue
            row = _run_cell(case, arm, rep)
            legacy_parsed = parse_output_v1(row["response"].get("content", ""))
            row["result"]["score_v1"] = score_case_v1(
                case,
                legacy_parsed,
                std_nums_v1(
                    " ".join(
                        [
                            case["governing_ref"],
                            case["governing_text"],
                            *case.get("premises", []),
                        ]
                    )
                ),
            )
            _append_private(private_path, row)
            completed.add(key)
            done += 1
            result = row["result"]
            score = result["score_v2"]
            route = f"{result.get('route_backend') or '?'}:{result.get('served_model') or '?'}"
            print(
                f"{suite} {done}/{total} case={case_index}/{len(cases)} "
                f"id={case['id']} arm={arm} rep={rep} "
                f"schema={'ok' if score.get('schema_ok') else 'bad'} "
                f"pred={score.get('pred') or 'ERR'} route={route} "
                f"sec={result.get('elapsed_seconds')} "
                f"trace_body={result.get('backend_request_captured', False)}",
                flush=True,
            )
    _write_public_summaries(suite, cases, private_path)
    print(f"{suite} campaign completed; private receipt={private_path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-manifest", action="store_true")
    parser.add_argument("--suite", choices=("dev", "holdout"))
    parser.add_argument("--holdout-arm", choices=ARMS)
    args = parser.parse_args()
    if args.freeze_manifest:
        write_manifest()
        return
    if not args.suite:
        raise SystemExit("choose --freeze-manifest or --suite")
    run_campaign(args.suite, args.holdout_arm)


if __name__ == "__main__":
    main()
