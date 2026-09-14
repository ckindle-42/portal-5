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
import traceback
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

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
    print(f"run_id={run_id}", flush=True)
    last_heartbeat = time.monotonic()
    deadline = time.time() + 6 * 60 * 60
    while time.time() < deadline:
        status = compliance_gaps(operation="status", run_id=run_id, kb_id=kb_id)
        if status.get("status") in ("COMPLETE", "FAILED", "CANCELLED", "INTERRUPTED"):
            break
        if time.monotonic() - last_heartbeat >= 30:
            print(
                f"run_id={run_id} status={status.get('status')} progress={status.get('progress')}",
                flush=True,
            )
            last_heartbeat = time.monotonic()
        time.sleep(2.0)
    else:
        compliance_gaps(operation="cancel", run_id=run_id, kb_id=kb_id)
        raise TimeoutError(f"assessment deadline exceeded; cancellation requested for {run_id}")
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


def _documentary_of(result: dict[str, Any]) -> str:
    if "actual" in result and isinstance(result["actual"], dict):
        return str(result["actual"].get("documentary_coverage", ""))
    return str(result.get("documentary_coverage", result.get("error", "")))


def _live_case_direct(
    manifest: dict[str, Any],
    case: dict[str, Any],
    kb_id: str,
    *,
    scope_text_override: str = "",
    trace_dir: Path | None = None,
) -> dict[str, Any]:
    """Real-corpus diagnostic using the same stage budgets as the async route."""
    from portal.modules.compliance.core.applicability import parse_scope_declaration
    from portal.modules.compliance.core.assessment import assess_part
    from portal.modules.compliance.core.assessment_runs import _guarded_seat
    from portal.modules.compliance.core.assessment_source import build_assessment_request
    from portal.modules.compliance.core.repository import Repository
    from portal.modules.compliance.core.runtime_config import build_assessment_context

    request = build_assessment_request(
        case["requirement_id"],
        kb_id=kb_id,
        effective_on=manifest["effective_on"],
    )
    scope_text = scope_text_override or _scope_text(manifest, case)
    if scope_text:
        request.scope = parse_scope_declaration(scope_text)
    request.scope_basis = "conditional" if scope_text_override else "actual"
    repo = Repository()
    context = build_assessment_context(
        kb_id,
        request.scope,
        manifest["effective_on"],
        request.known_at,
        repo,
        seat_fn=_traced_seat(_guarded_seat(None, "", None), trace_dir),
    )
    result = assess_part(request, context)
    repo.update_run(result.run_id, status="COMPLETE", finished=True)
    return asdict(result)


def _traced_seat(inner: Any, trace_dir: Path | None) -> Any:
    """Write each model attempt before sending it, and persist errors too."""
    import hashlib

    from portal.modules.compliance.core.assessment_report import _REPORT_SYSTEM
    from portal.modules.compliance.core.obligation_alignment import _ALIGNMENT_SYSTEM

    sequence = len(list(trace_dir.glob("model-*.json"))) if trace_dir else 0

    def invoke(model: str, system: str, user: str) -> str:
        nonlocal sequence
        sequence += 1
        stage = (
            "alignment"
            if system == _ALIGNMENT_SYSTEM
            else "report"
            if system == _REPORT_SYSTEM
            else "council"
        )
        path = trace_dir / f"model-{sequence:03}.json" if trace_dir else None
        event: dict[str, Any] = {
            "stage": stage,
            "model": model,
            "status": "STARTED",
            "started_at": datetime.now(UTC).isoformat(),
            "system_sha256": hashlib.sha256(system.encode()).hexdigest(),
            "input_sha256": hashlib.sha256(user.encode()).hexdigest(),
            "system": system,
            "input": user,
        }
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(event, indent=2))
        started = time.monotonic()
        print(f"model_call={sequence} stage={stage} model={model} START", flush=True)
        try:
            raw = inner(model, system, user)
            event.update(status="COMPLETE", response=raw)
            return raw
        except Exception as exc:
            event.update(status="ERROR", error=repr(exc))
            raise
        finally:
            event["elapsed_seconds"] = time.monotonic() - started
            if path:
                path.write_text(json.dumps(event, indent=2))
            print(
                f"model_call={sequence} stage={stage} {event['status']} elapsed={event['elapsed_seconds']:.1f}s",
                flush=True,
            )

    return invoke


def _verify_fixture_load(loaded: dict[str, Any], case: dict[str, Any], kb_id: str) -> None:
    from portal.platform.retrieval import store

    if loaded.get("error") or loaded.get("ingest_error"):
        raise RuntimeError(f"fixture ingestion failed: {loaded}")
    table = store.text_table(kb_id, prefix="compliance_")
    if table is None:
        raise RuntimeError(f"fixture KB unavailable after ingestion: {kb_id}")
    rows = table.to_arrow().to_pylist()
    fixtures = _load_manifest()["controlled_fixtures"]
    expected = {f"{c['label']}.txt": fixtures[c["label"]]["text"] for c in case["candidates"]}
    actual = {r["source_file"]: r["text"] for r in rows}
    if actual != expected or len(rows) != len(expected):
        raise RuntimeError("fixture contents differ from the declared complete candidate set")


@contextmanager
def _controlled_route(case: dict[str, Any], kb_id: str, trace_dir: Path | None = None):
    """Control acquisition evidence/faults, while executing the actual async route.

    Completeness is proved only for this isolated, fully enumerated fixture KB.
    The retrieved candidates must exactly cover that stored population. No
    fixture labels, expected verdicts or gold gap IDs enter model requests.
    """
    from portal.modules.compliance.core import assessment_runs
    from portal.modules.compliance.core.assessment_source import build_corpus_snapshot
    from portal.modules.compliance.core.council import _SEAT_SYSTEM
    from portal.modules.compliance.core.obligation_alignment import _ALIGNMENT_SYSTEM
    from portal.platform.retrieval import store

    build = assessment_runs.build_requests_for
    guarded = assessment_runs._guarded_seat
    captured: list[Any] = []

    def requests(*args: Any, **kwargs: Any) -> list[Any]:
        result = build(*args, **kwargs)
        if kwargs.get("kb_id") != kb_id:
            return result
        table = store.text_table(kb_id, prefix="compliance_")
        population = {r["chunk_id"] for r in table.to_arrow().to_pylist()}
        for request in result:
            candidates = request.candidate_set
            examined = {r.chunk_id for r in candidates.records}
            if examined != population or candidates.unresolved:
                raise RuntimeError("fixture retrieval did not examine the complete declared set")
            receipt = dict(candidates.acquisition_receipt)
            receipt["acquisition_mode"] = "EXPLICIT_SET"
            receipt["boundary_receipt"] = {
                "complete": case["boundary"] == "complete",
                "eligible_sections": sorted(population),
                "examined_sections": sorted(examined),
                "omissions": [],
                "table_version": table.version,
                "acquisition_mode": "EXPLICIT_SET",
                "document_revision_hashes": request.snapshot.document_revision_hashes,
            }
            candidates.acquisition_receipt = receipt
            request.snapshot = build_corpus_snapshot(kb_id, acquisition_receipt=receipt)
            if case["id"] == "22":
                target = next(r for r in candidates.records if r.document_id == "B22.txt")
                target.revision_hash = "0" * 64
                target.source_slice.revision_hash = "0" * 64
            captured.append(request)
        return result

    def seat(repo: Any, run_id: str, inner: Any) -> Any:
        real = guarded(repo, run_id, inner)

        def invoke(model: str, system: str, user: str) -> str:
            if case["id"] == "23" and system == _SEAT_SYSTEM:
                raise TimeoutError("controlled council timeout")
            if case["id"] == "24" and system == _ALIGNMENT_SYSTEM:
                return "not a json object"
            return real(model, system, user)

        return _traced_seat(invoke, trace_dir)

    with (
        patch.object(assessment_runs, "build_requests_for", requests),
        patch.object(assessment_runs, "_guarded_seat", seat),
    ):
        yield captured


def _proposal_result(
    manifest: dict[str, Any], case: dict[str, Any], request: Any
) -> dict[str, Any]:
    import hashlib

    from portal.modules.compliance.core.assessment_runs import _guarded_seat
    from portal.modules.compliance.core.determination import ScenarioEdit, ScenarioOverlay
    from portal.modules.compliance.core.operations import propose
    from portal.modules.compliance.core.repository import Repository
    from portal.modules.compliance.core.runtime_config import build_assessment_context

    virtual = case["virtual"]
    target = next(
        r for r in request.candidate_set.records if r.document_id == f"{virtual['target']}.txt"
    )
    edit = ScenarioEdit(
        operation="REPLACE",
        target_document=target.document_id,
        chunk_id=target.chunk_id,
        char_start=0,
        char_end=len(target.text),
        expected_old_hash=hashlib.sha256(target.text.encode()).hexdigest(),
        new_text=virtual["replacement_text"],
    )
    overlay = ScenarioOverlay(base_snapshot_fingerprint=request.snapshot.fingerprint, edits=[edit])
    context = build_assessment_context(
        request.kb_id,
        request.scope,
        manifest["effective_on"],
        request.known_at,
        Repository(),
        seat_fn=_guarded_seat(None, "", None),
    )
    package = propose(
        case["requirement_id"],
        ["evaluation cadence"],
        virtual["replacement_text"],
        overlay=overlay,
        context=context,
        request=request,
    )
    return asdict(package)


def _live_checks(case: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    """Never count the expected word alone as acceptance of a broken run."""
    expected = case["expected"]
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: Any = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    check("execution", not result.get("error"), result.get("error", ""))
    if result.get("error"):
        return checks
    if case["id"] == "01":
        actual, conditional = result.get("actual", {}), result.get("conditional", {})
        check(
            "actual_scope",
            actual.get("coverage") == "UNRESOLVED" and not actual.get("substantively_resolved"),
        )
        check(
            "conditional_documentary",
            conditional.get("documentary_coverage") == "FULL",
            conditional.get("missing_fact"),
        )
        check(
            "conditional_evidence", bool(conditional.get("covered")) and not conditional.get("gaps")
        )
        # The actual corpus has real document names, not controlled A22/B22 IDs.
        check(
            "scope_disclosed", bool(actual.get("missing_fact", {}).get("missing_scope_declaration"))
        )
        return checks
    for name in ("documentary_coverage", "coverage", "substantively_resolved"):
        check(
            name,
            result.get(name) == expected[name],
            {"got": result.get(name), "expected": expected[name]},
        )
    check(
        "acquisition",
        not result.get("retrieval_errors")
        and not result.get("receipt", {}).get("retrieval_errors"),
        result.get("missing_fact"),
    )
    if expected.get("expected_code"):
        check(
            "code",
            result.get("unresolved_code") == expected["expected_code"],
            result.get("unresolved_code"),
        )
    kinds = [g["kind"] for g in result.get("gaps", [])]
    check("gap_kinds", kinds == expected.get("gap_kinds", []), kinds)
    _check_live_gap_identities(case, result, check)
    _check_live_sources(expected, result, check)
    receipt = result.get("receipt", {})
    if case["id"] in ("25", "26"):
        proposal = result.get("proposal", {})
        check(
            "proposal_status",
            proposal.get("status") == expected["proposal_status"],
            proposal.get("status"),
        )
        check(
            "virtual_coverage",
            (proposal.get("rejudged") or {}).get("documentary_coverage")
            == expected["virtual_coverage"],
        )
        if case["id"] == "26":
            check("closes_fields", proposal.get("closes_fields") == [])
    check("run_identity", bool(result.get("run_id")) and bool(result.get("assessment_id")))
    if case["id"] not in ("21", "22"):
        check("model_evidence", bool(receipt.get("alignment", {}).get("raw")))
    return checks


def _check_live_gap_identities(case: dict[str, Any], result: dict[str, Any], check: Any) -> None:
    """Resolve fixture handles to actual IDs by exact kind and source identities."""
    gaps = result.get("gaps", [])
    ids = [g.get("gap_id", "") for g in gaps]
    expected_ids = case["expected"].get("gap_ids", [])
    sources = {s["slice_id"]: s for s in result.get("selected_source_slices", [])}
    identities: dict[str, str] = {}
    # Cases 16/21/23/24 carry `"report": null`: .get()'s default never applies.
    for gold in (case.get("report") or {}).get("gaps", []):
        if gold["gap_id"] not in expected_ids:
            continue
        matches = []
        for gap in gaps:
            counter = {
                sources.get(sid, {})
                .get("document_id", "")
                .removeprefix("fixture:")
                .removesuffix(".txt")
                for sid in gap.get("internal_counterevidence_slice_ids", [])
            }
            governing = {
                sources.get(sid, {}).get("ref", "") for sid in gap.get("governing_slice_ids", [])
            }
            if (
                gap.get("kind") == gold["kind"]
                and counter == set(gold.get("counter", []))
                and case["requirement_id"] in governing
                and gap.get("missing_commitment", "").strip()
                and (gap.get("kind") != "OMISSION" or gap.get("boundary_proof_id"))
            ):
                matches.append(gap.get("gap_id", ""))
        if len(matches) == 1:
            identities[gold["gap_id"]] = matches[0]
    ok = (
        len(ids) == len(expected_ids)
        and all(ids)
        and len(set(ids)) == len(ids)
        and set(identities) == set(expected_ids)
        and len(set(identities.values())) == len(expected_ids)
    )
    check(
        "gap_ids",
        ok,
        {"actual_ids": ids, "fixture_identity_map": identities, "expected": expected_ids},
    )


def _check_live_sources(expected: dict[str, Any], result: dict[str, Any], check: Any) -> None:
    receipt = result.get("receipt", {})
    packet = receipt.get("council_packet", {})
    core = {c.get("document_id", "") for c in packet.get("candidates", [])}
    core |= {c.get("commitment_id", "") for c in packet.get("candidates", [])}
    used_ids = {sid for c in result.get("covered", []) for sid in c.get("internal_slice_ids", [])}
    used_ids |= {
        sid
        for g in result.get("gaps", [])
        for sid in g.get("internal_counterevidence_slice_ids", [])
    }
    used_docs = {
        s.get("document_id", "")
        for s in result.get("selected_source_slices", [])
        if s.get("slice_id") in used_ids
    }

    def has_label(label: str, values: set[str]) -> bool:
        return any(
            v == f"{label}.txt" or v.startswith(f"{label}.txt ") or v == f"fixture:{label}"
            for v in values
        )

    for label in expected.get("required_citations", []):
        check(f"required:{label}", has_label(label, used_docs), sorted(used_docs))
    for label in expected.get("forbidden_citations", []):
        check(
            f"forbidden:{label}", not has_label(label, used_docs | core), sorted(used_docs | core)
        )
    links = {r["link_id"]: r for r in receipt.get("alignment", {}).get("records", [])}
    outcomes = packet.get("binding_outcomes", [])
    for item in expected.get("arithmetic", []):
        matches = [
            o
            for o in outcomes
            if has_label(
                item["candidate"], {links.get(o.get("link_id"), {}).get("document_id", "")}
            )
        ]
        check(
            f"arithmetic:{item['candidate']}",
            any(o.get("result") == item["result"] for o in matches),
            matches,
        )


def _execute_live_case(
    manifest: dict[str, Any],
    case: dict[str, Any],
    case_kb: str,
    setup_error: str,
    trace_dir: Path | None = None,
) -> dict[str, Any]:
    cid = case["id"]
    try:
        if setup_error:
            return {"error": setup_error, "stage": "fixture_setup"}
        if cid == "01":
            actual = _live_case_direct(
                manifest, case, case_kb, trace_dir=trace_dir / "actual" if trace_dir else None
            )
            conditional = _live_case_direct(
                manifest,
                case,
                case_kb,
                scope_text_override=manifest["scope"]["applicable_text"],
                trace_dir=trace_dir / "conditional" if trace_dir else None,
            )
            return {"actual": actual, "conditional": conditional}
        with _controlled_route(case, case_kb, trace_dir) as requests:
            if cid == "21":
                from portal.modules.compliance.core import assessment_runs

                with patch.object(
                    assessment_runs,
                    "resolve_governing_bundle",
                    side_effect=ValueError("controlled missing governing anchor"),
                ):
                    result = _live_case_via_gaps(manifest, case, case_kb)
            else:
                result = _live_case_via_gaps(manifest, case, case_kb)
            if cid in ("25", "26") and requests:
                result["proposal"] = _proposal_result(manifest, case, requests[0])
            return result
    except Exception as exc:
        return {"error": repr(exc)}


def _run_manifest() -> dict[str, Any]:
    import hashlib
    import subprocess
    import urllib.request

    from portal.modules.compliance.core.runtime_config import seat_roster

    patterns = (
        "portal/modules/compliance/core/*.py",
        "portal/modules/compliance/tools/*.py",
        "portal/platform/retrieval/*.py",
        "config/compliance/council.yaml",
        "portal/modules/compliance/data/nerc_cip_register.json",
        "portal/modules/compliance/data/cip_pdfs/*.pdf",
        "tests/data/compliance_reading_acceptance.json",
        "scripts/verify_compliance_reading_acceptance.py",
    )
    files = sorted({p for pattern in patterns for p in REPO_ROOT.glob(pattern)})
    hashes = {
        str(p.relative_to(REPO_ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
    }
    roster = seat_roster()
    with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=15) as response:
        models = json.load(response).get("models", [])
    configured = {seat["model"] for seat in roster}
    digests = {m["name"]: m["digest"] for m in models if m["name"] in configured}
    if set(digests) != configured:
        raise RuntimeError(
            f"configured model digests unavailable: {sorted(configured - digests.keys())}"
        )
    return {
        "started_at": datetime.now(UTC).isoformat(),
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip(),
        "source_sha256": hashes,
        "roster": roster,
        "model_digests": digests,
    }


def _guarded_live_checks(
    case: dict[str, Any], result: dict[str, Any], case_dir: Path, index: int
) -> list[dict[str, Any]]:
    """Record a checker crash as a failed check instead of ending the suite: it
    used to abort the whole multi-hour run at that case, discarding every case
    after it. Never a pass, never a skip."""
    try:
        return _live_checks(case, result)
    except Exception as exc:  # noqa: BLE001 - a checker defect must not end the run
        trace = traceback.format_exc()
        (case_dir / f"checker_error-{index}.txt").write_text(trace)
        print(f"case {case['id']} run {index}: CHECKER ERROR {exc!r}", flush=True)
        return [{"name": "checker_error", "ok": False, "detail": repr(exc)}]


def _run_record(
    cid: str, index: int, result: dict[str, Any], failed: list[str], trace_dir: Path
) -> dict[str, Any]:
    """Per-run closeout evidence the brief's final handoff must report: run id,
    elapsed and actual model-call count, aggregated here rather than recovered
    by hand from each case directory afterwards."""
    run_ids = [str(result.get("run_id", ""))] if result.get("run_id") else []
    for key in ("actual", "conditional"):
        nested = result.get(key)
        if isinstance(nested, dict) and nested.get("run_id"):
            run_ids.append(str(nested["run_id"]))
    return {
        "case": cid,
        "run": index,
        "status": "FAIL" if failed else "PASS",
        "documentary": _documentary_of(result),
        "run_id": run_ids[0] if len(run_ids) == 1 else "",
        "run_ids": run_ids,
        "assessment_id": str(result.get("assessment_id", "")),
        "unresolved_code": str(result.get("unresolved_code", "")),
        "elapsed_seconds": float(result.get("elapsed_seconds", 0.0)),
        "model_calls": len(sorted(trace_dir.rglob("model-*.json"))) if trace_dir.exists() else 0,
        "failed": failed,
    }


def _write_summary(
    receipt_dir: Path,
    args: argparse.Namespace,
    summaries: list[tuple[str, str, str]],
    records: list[dict[str, Any]],
    *,
    complete: bool,
) -> None:
    (receipt_dir / "summary.json").write_text(
        json.dumps(
            {
                "kb_id": args.kb_id,
                "runs": args.runs,
                "rows": summaries,
                "records": records,
                "per_case_kb": True,
                "complete": complete,
            },
            indent=2,
        )
    )


def run_live(args: argparse.Namespace) -> int:
    manifest = _load_manifest()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    receipt_dir = PRIVATE_DIR / timestamp
    receipt_dir.mkdir(parents=True, exist_ok=False)
    only = set(args.cases.split(",")) if args.cases else None
    cases = {c["id"]: c for c in manifest["cases"]}
    if only and not only.issubset(cases):
        raise ValueError(f"unknown case ids: {sorted(only - cases.keys())}")
    summaries: list[tuple[str, str, str]] = []
    records: list[dict[str, Any]] = []
    print(f"receipts: {receipt_dir}", flush=True)
    (receipt_dir / "manifest.json").write_text(json.dumps(_run_manifest(), indent=2))
    for cid, case in cases.items():
        if only and cid not in only:
            continue
        case_dir = receipt_dir / f"case-{cid}"
        case_dir.mkdir()
        case_kb = "operator_corpus" if cid == "01" else f"{args.kb_id}-c{cid}"
        setup_error = ""
        if cid != "01" and case.get("candidates"):
            try:
                loaded = _materialize_case_fixtures(manifest, case, case_kb)
                (case_dir / "fixture_load.json").write_text(
                    json.dumps(loaded, indent=2, default=str)
                )
                _verify_fixture_load(loaded, case, case_kb)
            except Exception as exc:
                setup_error = repr(exc)
                (case_dir / "fixture_load_error.txt").write_text(setup_error)
        for index in range(max(1, args.runs)):
            started = time.monotonic()
            print(f"case {cid} run {index}: START", flush=True)
            result = _execute_live_case(
                manifest, case, case_kb, setup_error, case_dir / f"trace-{index}"
            )
            result["elapsed_seconds"] = time.monotonic() - started
            checks = _guarded_live_checks(case, result, case_dir, index)
            (case_dir / f"run-{index}.json").write_text(json.dumps(result, indent=2, default=str))
            (case_dir / f"checks-{index}.json").write_text(
                json.dumps(checks, indent=2, default=str)
            )
            failed = [c["name"] for c in checks if not c["ok"]]
            status = "FAIL" if failed else "PASS"
            record = _run_record(cid, index, result, failed, case_dir / f"trace-{index}")
            records.append(record)
            detail = (
                f"run={index} got={record['documentary']} run_id={record['run_id'] or '-'} "
                f"calls={record['model_calls']} elapsed={record['elapsed_seconds']:.1f}s "
                f"failed={','.join(failed)}"
            )
            summaries.append((cid, status, detail))
            _write_summary(receipt_dir, args, summaries, records, complete=False)
            print(f"case {cid} run {index}: {status} {detail}", flush=True)
    _write_summary(receipt_dir, args, summaries, records, complete=True)
    _print_table(summaries)
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
