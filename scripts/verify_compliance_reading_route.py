#!/usr/bin/env python3
"""Deployed-route qualification for the compliance reading architecture.

The 26-case verifier exercises the registered async handler in-process against
isolated Parts. This covers what that cannot (brief §7.1 / resume §5D): a scoped
``CIP-007-6 R2`` request over the deployed MCP HTTP surface, with explicit scope,
conditional-scope disclosure and a non-today effective date, carried through
start → status → result to four persisted Part assessment IDs. It asserts the
envelope replays the original request context, that start returns identity only,
and that a repeated status/result pair does no further model work (A08). A check
that cannot be evaluated is a failure, never a skip.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "tests" / "data" / "compliance_reading_acceptance.json"
DEFAULT_BASE_URL = "http://localhost:8937"


def _manifest() -> dict[str, Any]:
    loaded: Any = json.loads(MANIFEST_PATH.read_text())
    return dict(loaded)


def _invoke(client: httpx.Client, base_url: str, **arguments: Any) -> tuple[dict[str, Any], float]:
    started = time.monotonic()
    response = client.post(
        f"{base_url}/tools/compliance_gaps",
        json={"arguments": arguments},
    )
    elapsed = time.monotonic() - started
    response.raise_for_status()
    body: Any = response.json()
    if not isinstance(body, dict):
        raise TypeError(f"compliance_gaps returned {type(body).__name__}, not an object")
    return dict(body), elapsed


class _Checks:
    """Ordered check log; an unevaluable check is a failure, never a skip."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, name: str, ok: bool, detail: Any = "") -> bool:
        self.rows.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)
        return bool(ok)

    def failed(self) -> list[str]:
        return [r["name"] for r in self.rows if not r["ok"]]


def _check_start(payload: dict[str, Any], expected_parts: list[str], checks: _Checks) -> str:
    run_id = str(payload.get("run_id", ""))
    checks.add("start_run_id", bool(run_id), run_id)
    checks.add("start_has_no_coverage_rows", not payload.get("rows"), payload.get("rows", []))
    checks.add(
        "start_requirements",
        sorted(payload.get("requirements", [])) == expected_parts,
        payload.get("requirements", []),
    )
    return run_id


def _await_completion(
    client: httpx.Client, args: argparse.Namespace, run_id: str
) -> dict[str, Any]:
    deadline = time.monotonic() + args.deadline
    status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        status, _ = _invoke(
            client, args.base_url, operation="status", run_id=run_id, kb_id=args.kb_id
        )
        state = str(status.get("status", ""))
        print(f"run_id={run_id} status={state} progress={status.get('progress')}", flush=True)
        if state in ("COMPLETE", "FAILED", "CANCELLED", "INTERRUPTED"):
            break
        time.sleep(args.poll_interval)
    return status


def _check_result(
    result: dict[str, Any],
    *,
    run_id: str,
    expected_parts: list[str],
    engine: str,
    effective_on: str,
    checks: _Checks,
) -> list[str]:
    rows = result.get("rows", [])
    assessed = sorted(str(r.get("requirement_id", "")) for r in rows)
    ids = [str(r.get("assessment_id", "")) for r in rows]
    checks.add("result_all_parts", assessed == expected_parts, assessed)
    checks.add(
        "result_assessment_ids",
        len(ids) == len(expected_parts) and len(set(ids)) == len(ids),
        ids,
    )
    checks.add(
        "result_shared_run_id",
        {str(r.get("run_id", "")) for r in rows} == {run_id},
        sorted({str(r.get("run_id", "")) for r in rows}),
    )
    checks.add("result_engine", str(result.get("engine")) == engine, result.get("engine"))
    # Must replay the ORIGINAL request context, not this call's wrong kb/date.
    checks.add(
        "result_original_effective_on",
        str(result.get("effective_on")) == effective_on,
        {"got": result.get("effective_on"), "expected": effective_on},
    )
    today = datetime.now(UTC).date().isoformat()
    checks.add(
        "result_effective_on_is_not_today",
        str(result.get("effective_on")) != today or effective_on == today,
        {"got": result.get("effective_on"), "today": today},
    )
    scope_out = result.get("scope", {})
    checks.add("result_scope_disclosed", isinstance(scope_out, dict) and bool(scope_out), scope_out)
    checks.add(
        "result_conditional_scope_disclosed",
        bool(scope_out.get("impact_present")) or bool(scope_out.get("associated_present")),
        scope_out,
    )
    return ids


def _check_replay(
    client: httpx.Client,
    args: argparse.Namespace,
    *,
    run_id: str,
    ids: list[str],
    status: dict[str, Any],
    checks: _Checks,
    receipt_dir: Path,
) -> None:
    repeat_status, status_elapsed = _invoke(
        client, args.base_url, operation="status", run_id=run_id, kb_id=args.kb_id
    )
    repeat_result, result_elapsed = _invoke(
        client, args.base_url, operation="result", run_id=run_id, kb_id=args.replay_kb_id
    )
    (receipt_dir / "repeat_status.json").write_text(json.dumps(repeat_status, indent=2))
    (receipt_dir / "repeat_result.json").write_text(json.dumps(repeat_result, indent=2))
    repeat_ids = [str(r.get("assessment_id", "")) for r in repeat_result.get("rows", [])]
    checks.add("repeat_identical_ids", repeat_ids == ids, repeat_ids)
    checks.add(
        "repeat_identical_finished_at",
        repeat_status.get("finished_at") == status.get("finished_at"),
        {"first": status.get("finished_at"), "repeat": repeat_status.get("finished_at")},
    )
    checks.add(
        "repeat_no_model_work",
        max(status_elapsed, result_elapsed) < args.replay_budget,
        {"status_s": round(status_elapsed, 3), "result_s": round(result_elapsed, 3)},
    )


def _finish(
    receipt_dir: Path,
    args: argparse.Namespace,
    checks: _Checks,
    run_id: str,
    ids: list[str],
    effective_on: str,
    scope_text: str,
) -> int:
    (receipt_dir / "checks.json").write_text(json.dumps(checks.rows, indent=2))
    summary = {
        "run_id": run_id,
        "base_url": args.base_url,
        "requirement": args.requirement,
        "kb_id": args.kb_id,
        "effective_on": effective_on,
        "scope_text": scope_text,
        "conditional_scope": True,
        "assessment_ids": ids,
        "failed": checks.failed(),
        "complete": True,
    }
    (receipt_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)
    return 1 if checks.failed() else 0


def _run(args: argparse.Namespace) -> int:
    manifest = _manifest()
    expected_parts = sorted(manifest["governing_parts"])
    effective_on = args.effective_on or str(manifest["effective_on"])
    scope_text = args.scope or str(manifest["scope"]["conditional_text"])
    receipt_dir = Path(args.out) / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    receipt_dir.mkdir(parents=True, exist_ok=False)
    print(f"receipts: {receipt_dir}", flush=True)

    checks = _Checks()
    request_args: dict[str, Any] = {
        "standard": args.standard,
        "requirement": args.requirement,
        "kb_id": args.kb_id,
        "effective_on": effective_on,
        "scope": scope_text,
        "conditional_scope": True,
        "operation": "start",
    }
    (receipt_dir / "request.json").write_text(json.dumps(request_args, indent=2))
    run_id: str = ""
    ids: list[str] = []

    def finish() -> int:
        return _finish(receipt_dir, args, checks, run_id, ids, effective_on, scope_text)

    with httpx.Client(timeout=args.http_timeout) as client:
        health = client.get(f"{args.base_url}/health")
        if not checks.add("health", health.status_code == 200, health.text.strip()):
            return finish()

        started_payload, _ = _invoke(client, args.base_url, **request_args)
        (receipt_dir / "start.json").write_text(json.dumps(started_payload, indent=2))
        run_id = _check_start(started_payload, expected_parts, checks)
        if not run_id:
            return finish()

        status = _await_completion(client, args, run_id)
        (receipt_dir / "status.json").write_text(json.dumps(status, indent=2))
        if not checks.add(
            "status_complete", str(status.get("status")) == "COMPLETE", status.get("status")
        ):
            return finish()

        result, _ = _invoke(
            client,
            args.base_url,
            operation="result",
            run_id=run_id,
            kb_id=args.replay_kb_id,
            effective_on="",
            verbose=False,
        )
        (receipt_dir / "result.json").write_text(json.dumps(result, indent=2))
        ids = _check_result(
            result,
            run_id=run_id,
            expected_parts=expected_parts,
            engine=str(manifest["engine"]),
            effective_on=effective_on,
            checks=checks,
        )
        _check_replay(
            client,
            args,
            run_id=run_id,
            ids=ids,
            status=status,
            checks=checks,
            receipt_dir=receipt_dir,
        )

    return finish()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--standard", default="CIP-007-6")
    parser.add_argument("--requirement", default="CIP-007-6 R2")
    parser.add_argument("--kb-id", default="operator_corpus")
    parser.add_argument("--effective-on", default="")
    parser.add_argument("--scope", default="")
    parser.add_argument("--deadline", type=float, default=10800.0)
    parser.add_argument("--poll-interval", type=float, default=15.0)
    parser.add_argument("--http-timeout", type=float, default=300.0)
    parser.add_argument("--replay-budget", type=float, default=15.0)
    parser.add_argument(
        "--replay-kb-id",
        default="deliberately-different-kb",
        help="wrong KB sent on result calls; the envelope must replay the original",
    )
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "coding_task" / "v9_compliance" / "private" / "reading_route"),
    )
    return _run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
