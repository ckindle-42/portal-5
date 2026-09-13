#!/usr/bin/env python
"""Workstream G acceptance runner: fast hermetic table, or every controlled
fixture through the actual configured models (brief §7/§7.1).

    uv run python scripts/verify_compliance_reading_acceptance.py
    uv run python scripts/verify_compliance_reading_acceptance.py --cases 02,10
    uv run python scripts/verify_compliance_reading_acceptance.py --live --runs 3
    uv run python scripts/verify_compliance_reading_acceptance.py --live --kb-id compliance_acceptance

Fast mode (default) runs the hermetic layer in
``tests/unit/test_compliance_reading_acceptance.py`` and prints a case-by-case
table with the exact failed assertion. ``BLOCKED`` marks a spec expectation the
landed path cannot yet emit (the reason names the owner module).

Live mode ingests the controlled fixtures into an isolated ``compliance_*`` KB
via the existing ingest API, then runs the real configured models through
``assess_part``/``compliance_gaps`` with no stubs. Per-run results, fingerprints
and the captured model-call trace are retained under
``coding_task/v9_compliance/private/reading_acceptance/<timestamp>/``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PRIVATE_DIR = REPO_ROOT / "coding_task" / "v9_compliance" / "private" / "reading_acceptance"

# ── fast mode ───────────────────────────────────────────────────────────────


def _fast_rows(only: set[str] | None) -> list[tuple[str, str, str]]:
    from tests.unit import test_compliance_reading_acceptance as acc

    rows: list[tuple[str, str, str]] = []
    for cid, case in acc.CASES.items():
        if only and cid not in only:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            repo = acc.Repository(Path(tmp) / f"{cid}.db")
            try:
                outcome = acc.run_case(case, repo)
                checks = acc.evaluate_checks(case, outcome)
            except Exception as exc:  # noqa: BLE001 - a runner crash is a failed case
                rows.append((cid, "FAIL", f"runner error: {exc!r}"))
                continue
        hard = [c for c in checks if not c.blocked]
        blocked = [c for c in checks if c.blocked]
        failures = [c for c in hard if not c.ok]
        if failures:
            rows.append((cid, "FAIL", "; ".join(f"{c.name}: {c.detail}" for c in failures)))
        elif blocked:
            rows.append((cid, "BLOCKED", "; ".join(f"{c.name}: {c.blocked}" for c in blocked)))
        else:
            rows.append((cid, "PASS", f"{len(hard)} checks"))
    return rows


def _print_table(rows: list[tuple[str, str, str]]) -> None:
    width = max((len(r[0]) for r in rows), default=2)
    status_width = max((len(r[1]) for r in rows), default=6)
    print(f"{'CASE':<{width}}  {'STATUS':<{status_width}}  DETAIL")
    print("-" * (width + status_width + 40))
    for cid, status, detail in rows:
        print(f"{cid:<{width}}  {status:<{status_width}}  {detail}")
    counts: dict[str, int] = {}
    for _, status, _ in rows:
        counts[status] = counts.get(status, 0) + 1
    print("-" * (width + status_width + 40))
    print("  ".join(f"{k}={v}" for k, v in sorted(counts.items())))


# ── live mode ───────────────────────────────────────────────────────────────


def _load_manifest() -> dict[str, Any]:
    path = REPO_ROOT / "tests/data/compliance_reading_acceptance.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _materialize_fixtures(manifest: dict[str, Any], kb_id: str) -> dict[str, Any]:
    """Write controlled fixtures to a temp folder and ingest them into an
    isolated ``compliance_*`` KB. Never touches the operator corpus."""
    from portal.modules.compliance.core.ingest import ingest_folder

    with tempfile.TemporaryDirectory(prefix="reading-acceptance-") as tmp:
        src = Path(tmp)
        for label, fixture in manifest["controlled_fixtures"].items():
            name = f"{label}.txt"
            src.joinpath(name).write_text(fixture["text"], encoding="utf-8")
        return asyncio.run(ingest_folder(str(src), kb_id=kb_id, rebuild=True))


def _materialize_case_fixtures(
    manifest: dict[str, Any], case: dict[str, Any], kb_id: str
) -> dict[str, Any]:
    """Ingest ONLY this case's declared candidate documents into an isolated KB.

    One shared KB lets retrieval return every fixture, so a case's controlled
    candidate set is polluted by decoys from other cases. Per-case isolation
    makes the routed ``compliance_gaps`` call see exactly the case's candidates.
    """
    from portal.modules.compliance.core.ingest import ingest_folder

    labels = [c.get("label") for c in case.get("candidates", []) if c.get("label")]
    fixtures = manifest["controlled_fixtures"]
    with tempfile.TemporaryDirectory(prefix=f"reading-acceptance-{case['id']}-") as tmp:
        src = Path(tmp)
        for label in labels:
            fixture = fixtures.get(label)
            if fixture is None:
                continue
            src.joinpath(f"{label}.txt").write_text(fixture["text"], encoding="utf-8")
        return asyncio.run(ingest_folder(str(src), kb_id=kb_id, rebuild=True))


def _scope_text(manifest: dict[str, Any], case: dict[str, Any]) -> str:
    if case["scope"] == "derived":
        return ""
    return manifest["scope"]["applicable_text"]


def _live_case_via_gaps(
    manifest: dict[str, Any], case: dict[str, Any], kb_id: str
) -> dict[str, Any]:
    """Run the routed ``compliance_gaps`` async path for one controlled Part.

    The async worker injects the configured seat transport (unlike the legacy
    sync path), so this is the real routed assessment: start, poll status, fetch
    the persisted result. No speculative rows while pending.
    """
    from portal.modules.compliance.tools.compliance_mcp import compliance_gaps

    # Scope the routed call to THIS case's Part: a full "R2" call assesses all
    # four Parts (each minutes of model time) when only one is under test.
    started = compliance_gaps(
        standard=case["requirement_id"].split(" ")[0],
        requirement=case["requirement_id"],
        kb_id=kb_id,
        scope=_scope_text(manifest, case),
        conditional_scope=case["scope"] == "derived",
        effective_on=manifest["effective_on"],
        operation="start",
        generate_drafts=False,
    )
    run_id = started.get("run_id", "")
    if not run_id:
        return {"error": "compliance_gaps start returned no run_id", "started": started}
    deadline = time.time() + 6 * 60 * 60
    while time.time() < deadline:
        status = compliance_gaps(operation="status", run_id=run_id, kb_id=kb_id)
        if status.get("status") in ("COMPLETE", "FAILED", "CANCELLED", "INTERRUPTED"):
            break
        time.sleep(2.0)
    payload = compliance_gaps(
        operation="result",
        run_id=run_id,
        kb_id=kb_id,
        verbose=True,
        generate_drafts=False,
    )
    for row in payload.get("rows", []):
        if row.get("requirement_id") == case["requirement_id"]:
            return row
    return {"error": "part not returned by compliance_gaps", "payload": payload}


def _install_seat_wrapper(mode: str) -> Any:
    """Install a controlled failure on the real seat transport; returns a
    restore callable. ``timeout`` fails every seat call, ``invalid_alignment``
    makes the alignment reader return non-JSON."""
    from portal.modules.compliance.core import council, obligation_alignment

    real_seat = council._ollama_seat
    real_default = obligation_alignment._default_seat_fn

    def wrapped(model: str, system: str, user: str) -> str:
        if system == obligation_alignment._ALIGNMENT_SYSTEM:
            if mode == "invalid_alignment":
                return "not a json object"
            if mode == "timeout":
                raise TimeoutError("controlled seat timeout")
        if system == council._SEAT_SYSTEM and mode == "timeout":
            raise TimeoutError("controlled seat timeout")
        return real_seat(model, system, user)

    council._ollama_seat = wrapped  # type: ignore[assignment]
    obligation_alignment._default_seat_fn = lambda: wrapped  # type: ignore[assignment]

    def restore() -> None:
        council._ollama_seat = real_seat  # type: ignore[assignment]
        obligation_alignment._default_seat_fn = real_default  # type: ignore[assignment]

    return restore


def _documentary_of(result: dict[str, Any]) -> str:
    if "actual" in result and isinstance(result["actual"], dict):
        return str(result["actual"].get("documentary_coverage", ""))
    return str(result.get("documentary_coverage", result.get("error", "")))


def _live_case_direct(
    manifest: dict[str, Any],
    case: dict[str, Any],
    kb_id: str,
    *,
    failure_mode: str = "",
    scope_text_override: str = "",
) -> dict[str, Any]:
    """Build the request from the isolated KB and run the shared service.

    ``failure_mode`` injects a controlled failure on the real route: ``timeout``
    makes the configured seat fail, ``invalid_alignment`` makes the alignment
    reader return non-JSON, and ``hash`` corrupts the B22 candidate slice hash.
    """
    from portal.modules.compliance.core.applicability import parse_scope_declaration
    from portal.modules.compliance.core.assessment import assess_part
    from portal.modules.compliance.core.assessment_source import build_assessment_request
    from portal.modules.compliance.core.council import _ollama_seat
    from portal.modules.compliance.core.determination import AssessmentContext
    from portal.modules.compliance.core.runtime_config import seat_roster

    restore = None
    seat_fn: Any = _ollama_seat
    if failure_mode in ("timeout", "invalid_alignment"):
        restore = _install_seat_wrapper(failure_mode)
        from portal.modules.compliance.core import council as _council

        seat_fn = _council._ollama_seat

    try:
        request = build_assessment_request(
            case["requirement_id"],
            kb_id=kb_id,
            effective_on=manifest["effective_on"],
        )
        if failure_mode == "hash":
            for record in request.candidate_set.records:
                if record.candidate_id == "B22" or "35 calendar days" in record.text:
                    record.revision_hash = "0" * 64
                    if record.source_slice is not None:
                        record.source_slice.revision_hash = "0" * 64
        scope_text = scope_text_override or _scope_text(manifest, case)
        request.scope = parse_scope_declaration(scope_text) if scope_text else request.scope
        request.scope_basis = "conditional" if case["scope"] == "derived" else "actual"
        context = AssessmentContext(seats=seat_roster(), quorum=0.66, kb_id=kb_id, seat_fn=seat_fn)
        result = assess_part(request, context)
        return asdict(result)
    finally:
        if restore is not None:
            restore()


def run_live(args: argparse.Namespace) -> int:
    manifest = _load_manifest()
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    receipt_dir = PRIVATE_DIR / timestamp
    receipt_dir.mkdir(parents=True, exist_ok=True)

    only = set(args.cases.split(",")) if args.cases else None
    from tests.unit import test_compliance_reading_acceptance as acc

    summaries: list[tuple[str, str, str]] = []
    for cid, case in acc.CASES.items():
        if only and cid not in only:
            continue
        case_dir = receipt_dir / f"case-{cid}"
        case_dir.mkdir(exist_ok=True)
        # Isolate the case's own candidates so the routed call cannot see other
        # cases' decoys. Case 01 runs against the pinned operator corpus.
        case_kb = args.kb_id
        if cid != "01" and case.get("candidates"):
            case_kb = f"{args.kb_id}-c{cid}"
            try:
                loaded = _materialize_case_fixtures(manifest, case, case_kb)
                (case_dir / "fixture_load.json").write_text(
                    json.dumps(loaded, indent=2, default=str), encoding="utf-8"
                )
            except Exception as exc:  # noqa: BLE001 - retained on the case
                (case_dir / "fixture_load_error.txt").write_text(repr(exc), encoding="utf-8")
        expected = case["expected"]
        for run_index in range(max(1, args.runs)):
            try:
                if cid == "01":
                    # actual derived scope (UNKNOWN) and the explicit conditional
                    # diagnostic are reported separately.
                    actual = _live_case_direct(manifest, case, "operator_corpus")
                    conditional = _live_case_direct(
                        manifest,
                        case,
                        "operator_corpus",
                        scope_text_override=manifest["scope"]["applicable_text"],
                    )
                    result = {"actual": actual, "conditional": conditional}
                elif cid == "21":
                    from portal.modules.compliance.core import assessment_runs

                    with tempfile.TemporaryDirectory() as tmp:
                        repo = acc.Repository(Path(tmp) / "live21.db")
                        bad_ref = f"{case['requirement_id']} (unresolvable)"
                        run_id = repo.create_run(
                            {"requirements": [bad_ref], "kb_id": case_kb},
                            status="RUNNING",
                        )
                        results = assessment_runs.assess_requirements_now(
                            [bad_ref],
                            kb_id=case_kb,
                            scope=acc.build_scope(case),
                            effective_on=manifest["effective_on"],
                            repository=repo,
                            run_id=run_id,
                        )
                        result = asdict(results[0])
                elif cid in ("22", "23", "24"):
                    mode = {"22": "hash", "23": "timeout", "24": "invalid_alignment"}[cid]
                    result = _live_case_direct(manifest, case, case_kb, failure_mode=mode)
                else:
                    result = _live_case_via_gaps(manifest, case, case_kb)
            except Exception as exc:  # noqa: BLE001 - an errored live case is retained
                result = {"error": repr(exc)}
            (case_dir / f"run-{run_index}.json").write_text(
                json.dumps(result, indent=2, default=str), encoding="utf-8"
            )
            got = _documentary_of(result)
            ok = got == expected["documentary_coverage"]
            summaries.append((cid, "PASS" if ok else "FAIL", f"got={got}"))
        print(f"case {cid}: retained {receipt_dir / f'case-{cid}'}")

    (receipt_dir / "summary.json").write_text(
        json.dumps(
            {"kb_id": args.kb_id, "runs": args.runs, "rows": summaries, "per_case_kb": True},
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print()
    _print_table(summaries)
    print(f"\nreceipts: {receipt_dir}")
    return 0 if all(status == "PASS" for _, status, _ in summaries) else 1


# ── entry point ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="run the real configured models")
    parser.add_argument("--cases", default="", help="comma-separated case ids (e.g. 02,10)")
    parser.add_argument("--kb-id", default="compliance_acceptance", help="isolated test KB id")
    parser.add_argument("--runs", type=int, default=1, help="live repeats per case")
    args = parser.parse_args(argv)

    if args.live:
        return run_live(args)

    only = set(args.cases.split(",")) if args.cases else None
    started = time.time()
    rows = _fast_rows(only)
    _print_table(rows)
    print(f"\nfast layer completed in {time.time() - started:.2f}s")
    global_failed = any(status == "FAIL" for _, status, _ in rows)
    return 1 if global_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
