#!/usr/bin/env python3
"""Derived state of the Bully/Crogl review program -- never hand-written.

Root cause this exists for (lesson 19, and the stale brief this very program was started from):
state was recorded as prose snapshots, and prose goes stale in days. Here the state document is
RENDERED from three kinds of evidence, and ``--check`` fails when the committed document is not
what the evidence renders to:

* claims   -- the defect census (each claim is a probe that re-runs against the code);
* numbers  -- stamped evaluation reports (only ``real:`` corpora count as evidence);
* decisions -- pre-registered decision records, validated (``review_eval.decisions``).

    uv run python scripts/bully_review_state.py --write   # regenerate docs/BULLY_REVIEW_STATE.md
    uv run python scripts/bully_review_state.py --check   # exit 1 if stale or a record is invalid
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from portal.modules.security.core.review_eval import (  # noqa: E402
    claims as claims_mod,
)
from portal.modules.security.core.review_eval import (
    decisions as decisions_mod,
)
from portal.modules.security.core.review_eval import (
    report as report_mod,
)
from portal.modules.security.core.review_eval import (
    selftest as selftest_mod,
)
from portal.modules.security.core.review_eval import (
    stamp as stamp_mod,
)

OUT = "docs/BULLY_REVIEW_STATE.md"


def _claims(census: Mapping[str, Any] | None) -> list[str]:
    lines = ["## Claims (each is a probe: `scripts/bully_review_defect_census.py`)", ""]
    if not census:
        return [*lines, "No census has been run."]
    lines += ["| id | status | evidence |", "|---|---|---|"]
    for f in sorted(census.get("findings", []), key=lambda f: f["id"]):
        lines.append(
            f"| {f['id']} | {f['status']} | {str(f['evidence']).replace('|', '/')[:120]} |"
        )
    summary = (census.get("census") or {}).get("summary") or {}
    if summary:
        lines += ["", "Reachability of the engine package (static import closure):", ""]
        lines += ["| class | modules | lines |", "|---|---|---|"]
        lines += [f"| {k} | {v['modules']} | {v['lines']} |" for k, v in summary.items()]
    return lines


def _decisions(items: Sequence[tuple[decisions_mod.Decision, list[str]]]) -> list[str]:
    lines = ["## Decisions", ""]
    if not items:
        return [*lines, "No decision records."]
    lines += ["| id | stage | status | report | problems |", "|---|---|---|---|---|"]
    for d, problems in sorted(items, key=lambda x: x[0].id):
        lines.append(
            f"| {d.id} | {d.stage} | {d.status} | {d.report or '-'} | {'; '.join(problems) or 'none'} |"
        )
    return lines


def _measured(reports: Sequence[Mapping[str, Any]]) -> list[str]:
    real = [r for r in reports if str(r["stamp"]["corpus_snapshot"]).startswith("real:")]
    lines = ["## Measured (stamped, real corpora only)", ""]

    def ledger_for(doc: Mapping[str, Any]) -> Mapping[str, Any]:
        extra = doc.get("extra")
        if not isinstance(extra, Mapping):
            return {}
        ledger = extra.get("ledger")
        return ledger if isinstance(ledger, Mapping) else {}

    binding_reported = any("binding" in ledger_for(doc) for doc in real)
    if not real:
        lines.append("No real-data report exists yet.")
    for r in sorted(real, key=lambda r: (str(r["extra"].get("arm", "")), r["stamp_digest"])):
        st = r["stamp"]
        lines += [
            f"### arm `{r['extra'].get('arm', '?')}` stamp `{r['stamp_digest']}`",
            "",
            f"commit `{st['commit'][:12]}`, embedder `{st['embedder_id']}`, corpus `{st['corpus_snapshot']}`",
            "",
            "| metric | value | n | reads as failure when |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {m['name']} | {m['value']:.6g} | {m['n']} | {m['can_fail']} |" for m in r["metrics"]
        ]
        binding = (r["extra"].get("ledger") or {}).get("binding")
        if binding is not None:
            lines += ["", f"binding stage: `{binding or 'none (nothing lost)'}`"]
        lines.append("")
    if not binding_reported and any(
        ledger_for(doc).get("status") == "not_measured" for doc in real
    ):
        lines += [
            "binding stage: `unmeasured` (all pre-registered paired slices were excluded before product execution)",
            "",
        ]
    if len(real) != len(reports):
        lines += [f"Proxy runs (not evidence for any claim): {len(reports) - len(real)}", ""]
    return lines


def _ownership(ownership: Mapping[str, Any] | None) -> list[str]:
    lines = ["## Ownership (one owner per capability)", ""]
    if not ownership:
        return [*lines, "No ownership map."]
    lines += ["| capability | owner |", "|---|---|"]
    return lines + [
        f"| {k} | {v} |" for k, v in sorted((ownership.get("capabilities") or {}).items())
    ]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _validate_t6_proof(document: Mapping[str, Any]) -> list[str]:  # noqa: C901, PLR0912, PLR0915 -- report validation boundary.
    """Revalidate the T6 report and recompute its claims from the persisted aggregate rows."""
    problems: list[str] = []
    stamp_doc = document.get("stamp")
    extra = document.get("extra")
    selftest_doc = document.get("selftest")
    if not all(isinstance(value, Mapping) for value in (stamp_doc, extra, selftest_doc)):
        return ["report is missing stamp, selftest, or extra mappings"]
    assert isinstance(stamp_doc, Mapping)
    assert isinstance(extra, Mapping)
    assert isinstance(selftest_doc, Mapping)
    try:
        corpus_snapshot = str(stamp_doc["corpus_snapshot"])
        if not corpus_snapshot.startswith("real:"):
            problems.append("report stamp corpus_snapshot is not real:")
        run_stamp = stamp_mod.Stamp(
            harness_version=str(stamp_doc["harness_version"]),
            commit=str(stamp_doc["commit"]),
            dirty=bool(stamp_doc["dirty"]),
            embedder_id=str(stamp_doc["embedder_id"]),
            model_digests=tuple(
                (str(item[0]), str(item[1])) for item in stamp_doc["model_digests"]
            ),
            config_hash=str(stamp_doc["config_hash"]),
            corpus_snapshot=corpus_snapshot,
            policy=str(stamp_doc["policy"]),
        )
        stamp_digest = str(document["stamp_digest"])
        if run_stamp.digest != stamp_digest:
            problems.append("report stamp digest does not match its stamp fields")

        proof_rows = extra.get("proof_rows")
        if not isinstance(proof_rows, list) or not all(
            isinstance(row, Mapping) for row in proof_rows
        ):
            return [*problems, "report extra.proof_rows is missing or malformed"]
        if report_mod.rows_digest(proof_rows) != document.get("rows_digest"):
            problems.append("report proof rows do not match rows_digest")
        if len(proof_rows) != document.get("rows"):
            problems.append("report row count does not match proof_rows")

        checks = selftest_doc.get("checks")
        if not isinstance(checks, Mapping) or not checks:
            return [*problems, "report known-answer self-test checks are missing"]
        checks_passed = all(
            isinstance(check, Mapping) and check.get("passed") is True for check in checks.values()
        )
        passed = selftest_doc.get("passed") is True and checks_passed
        if not passed:
            problems.append("report known-answer self-test is not fully passing")
        test_result = selftest_mod.SelfTestResult(
            passed=passed,
            stamp_digest=str(stamp_digest),
            checks={
                str(key): dict(value) for key, value in checks.items() if isinstance(value, Mapping)
            },
        )

        metrics_doc = document.get("metrics")
        if not isinstance(metrics_doc, list) or not all(
            isinstance(metric, Mapping) for metric in metrics_doc
        ):
            return [*problems, "report metrics are missing or malformed"]
        metrics = [
            report_mod.MetricRow(
                name=str(metric["name"]),
                value=float(metric["value"]),
                n=int(metric["n"]),
                denominator=int(metric["denominator"]),
                can_fail=str(metric["can_fail"]),
            )
            for metric in metrics_doc
        ]
        meta_rows = [row for row in proof_rows if row.get("claim") == "META"]
        if len(meta_rows) != 1:
            return [*problems, "report must contain exactly one aggregate META row"]
        recompute: dict[str, report_mod.Recompute] = {
            "claim_proven_fraction": lambda rows: (
                float(next(row for row in rows if row.get("claim") == "META")["claim_proven_count"])
                / 4.0
            ),
            "processed_corpus_fraction": lambda rows: float(
                next(row for row in rows if row.get("claim") == "META")["processed_fraction"]
            ),
            "drill_pass_fraction": lambda rows: (
                float(next(row for row in rows if row.get("claim") == "META")["drill_pass_count"])
                / 3.0
            ),
        }
        problems.extend(
            report_mod.validate_report(
                stamp=run_stamp,
                selftest=test_result,
                metrics=metrics,
                rows=proof_rows,
                recompute=recompute,
            )
        )

        claims_doc = extra.get("claims")
        capture = extra.get("capture_admission")
        if not isinstance(claims_doc, Mapping) or not isinstance(capture, Mapping):
            return [*problems, "report claims or capture aggregate is missing"]
        problems.extend(claims_mod.validate_claims_document(claims_doc))
        snapshots = claims_doc.get("corpus_snapshots")
        if not isinstance(snapshots, list):
            return [*problems, "claim corpus snapshots are missing"]
        if str(extra.get("stop_rule") or "") != str(claims_doc.get("stop_rule") or ""):
            problems.append("report and claims stop rules differ")
        processed_events = sum(
            int(row.get("fetched") or 0)
            for row in proof_rows
            if row.get("claim") == "C3_WINDOW"
            and row.get("index") in {"botsv1", "botsv2", "botsv3", "portal5_lab"}
        )
        index_counts = extra.get("index_event_counts")
        if not isinstance(index_counts, Mapping):
            return [*problems, "report index event counts are missing"]
        expected_fraction = processed_events / max(sum(int(v) for v in index_counts.values()), 1)
        if not math.isclose(
            expected_fraction, float(extra.get("corpus_fraction", -1.0)), abs_tol=1e-12
        ):
            problems.append("reported corpus fraction does not recompute from C3 rows")
        if not math.isclose(
            expected_fraction, float(claims_doc.get("processed_fraction", -1.0)), abs_tol=1e-12
        ):
            problems.append("claim processed fraction does not recompute from C3 rows")

        recomputed_claims = claims_mod.evaluate_claims(
            proof_rows,
            corpus_snapshots=[str(value) for value in snapshots],
            selftests_passed=passed and capture.get("selftest_passed") is True,
            captures={
                "admitted_count": capture["admitted_count"],
                "total_count": capture["total_count"],
                "rejection_reason_histogram": capture["rejection_reason_histogram"],
                "validator_rule_histogram": capture["validator_rule_histogram"],
                "missing_data_histogram": capture["missing_data_histogram"],
            },
            processed_fraction=expected_fraction,
            stop_rule=str(extra["stop_rule"]),
        )
        if _canonical_json(recomputed_claims) != _canonical_json(claims_doc):
            problems.append("stored claims do not match recomputation from proof_rows")
        drills = extra.get("drills")
        if not isinstance(drills, Mapping) or not all(
            isinstance(drills.get(key), Mapping) and drills[key].get("status") == "PASS"
            for key in ("recovery", "embedder_change", "reader_unreachable")
        ):
            problems.append("one or more required phase-C drills did not pass")
    except (KeyError, TypeError, ValueError, IndexError, StopIteration) as exc:
        problems.append(f"report validation could not complete: {type(exc).__name__}: {exc}")
    return problems


def _fmt_interval(value: Mapping[str, Any]) -> str:
    estimate = value.get("estimate")
    ci = value.get("ci95")
    if estimate is None:
        return "n=0; no estimate"
    if not isinstance(ci, list) or len(ci) != 2:
        return f"n={value.get('n', 0)}; {float(estimate):.3f}; CI unavailable"
    return f"n={value.get('n', 0)}; {float(estimate):.3f} [{float(ci[0]):.3f}, {float(ci[1]):.3f}]"


def _t6_proof(document: Mapping[str, Any] | None, problems: Sequence[str]) -> list[str]:
    lines = ["## T6 proof claims (validated report)", ""]
    if document is None:
        return [*lines, "No T6 proof report exists."]
    if problems:
        return [*lines, "Report validation failed:", "", *[f"- {problem}" for problem in problems]]
    extra = document["extra"]
    claims_doc = extra["claims"]
    lines += [
        f"Processed corpus: `{claims_doc['processed_fraction']:.6%}`. Stop rule: {claims_doc['stop_rule']}.",
        "",
        "| claim | status | n and estimate (95% CI) | control / completeness |",
        "|---|---|---|---|",
    ]
    claim_rows = {row["claim"]: row for row in claims_doc["claims"]}
    c1 = claim_rows["C1"]
    lines.append(
        f"| C1 any source | {c1['status']} | review {_fmt_interval(c1['review_fraction'])} | "
        f"legacy {_fmt_interval(c1['legacy_funnel_fraction'])}; blind: "
        f"{', '.join(c1['blind_sources']) or 'none'} |"
    )
    c2 = claim_rows["C2"]
    c2_classes = c2["by_class"]
    c2_summary = "; ".join(
        f"{name} review {_fmt_interval(c2_classes[name]['review'])}"
        for name in ("known", "cousin", "novel")
    )
    c2_summary += f"; benign n={c2['false_raise']['benign_units']}"
    c2_control = "; ".join(
        f"{name} legacy {_fmt_interval(c2_classes[name]['control'])}"
        for name in ("known", "cousin", "novel")
    )
    c2_control += f"; false-raise/1k={c2['false_raise']['per_1000']}"
    lines.append(f"| C2 same or similar | {c2['status']} | {c2_summary} | {c2_control} |")
    c3 = claim_rows["C3"]
    projected_seconds = c3["projected_full_corpus_seconds"]
    projected_text = (
        f"{float(projected_seconds):.3f}"
        if projected_seconds is not None
        else f"not estimable; bottleneck {c3['bottleneck_stage'] or 'unknown'} has zero throughput"
    )
    lines.append(
        f"| C3 corpus is ground | {c3['status']} | windows n={len(c3['windows'])}; "
        f"stages n={len(c3['stages'])} | fetched {c3['events_fetched']}/{c3['events_expected']}; "
        f"projected full corpus seconds={projected_text} |"
    )
    c4 = claim_rows["C4"]
    c4_classes = c4["by_class"]
    c4_summary = "; ".join(
        f"{name} review {_fmt_interval(c4_classes[name]['review'])}"
        for name in ("cousin", "novel", "evidence_twin")
    )
    c4_control = "; ".join(
        f"{name} legacy {_fmt_interval(c4_classes[name]['control'])}"
        for name in ("cousin", "novel", "evidence_twin")
    )
    capture = c4["capture_admission"]
    c4_control += (
        f"; captures admitted={capture['admitted']}/{capture['total']}, "
        f"rejected={capture['rejected']}, reasons={capture['rejection_reason_histogram']}"
    )
    lines.append(f"| C4 recorded truth | {c4['status']} | {c4_summary} | {c4_control} |")
    lines += [
        "",
        "### Phase-C drills",
        "",
        "| drill | status | evidence |",
        "|---|---|---|",
    ]
    drills = extra["drills"]
    for key in ("recovery", "embedder_change", "reader_unreachable"):
        drill = drills[key]
        detail = ", ".join(
            f"{name}={drill[name]}"
            for name in (
                "interrupted_status",
                "same_hash_skip",
                "metrics_match_control",
                "review_run_id",
                "status",
            )
            if name in drill and name != "status"
        ) or "; ".join(f"{name}={drill[name]}" for name in drill if name != "status")
        lines.append(f"| {key} | {drill['status']} | {detail or 'see aggregate report'} |")
    return lines


def render(
    *,
    census: Mapping[str, Any] | None,
    decisions: Sequence[tuple[decisions_mod.Decision, list[str]]],
    reports: Sequence[Mapping[str, Any]],
    ownership: Mapping[str, Any] | None,
    proof_report: Mapping[str, Any] | None,
    proof_problems: Sequence[str],
) -> str:
    head = [
        "# Bully / Crogl review -- derived state",
        "",
        "DO NOT EDIT. Rendered by `scripts/bully_review_state.py` from the defect census, stamped",
        "evaluation reports and decision records; `--check` fails if this file is stale.",
        "",
    ]
    sections = [
        _claims(census),
        _decisions(decisions),
        _measured(reports),
        _t6_proof(proof_report, proof_problems),
        _ownership(ownership),
    ]
    body: list[str] = []
    for section in sections:
        body += [*section, ""]
    return "\n".join([*head, *body]).rstrip() + "\n"


def _latest_census(directory: Path) -> dict[str, Any] | None:
    files = sorted(directory.glob("census_*.json")) if directory.is_dir() else []
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def _git_commit_time(repo: Path) -> Callable[[str], float | None]:
    def commit_time(path: str) -> float | None:
        run = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "log",
                "--diff-filter=A",
                "--format=%ct",
                "--",
                path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        stamps = [float(x) for x in run.stdout.split() if x.strip()]
        return min(stamps) if stamps else None

    return commit_time


def collect(repo: Path) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    for path in sorted((repo / "reports" / "review_eval").rglob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if "stamp_digest" in doc and "metrics" in doc:
            reports.append(doc)
    binding = None
    for doc in reports:
        ledger = (doc.get("extra") or {}).get("ledger")
        if isinstance(ledger, Mapping) and "binding" in ledger:
            binding = str(ledger["binding"]) or None
    commit_time = _git_commit_time(repo)
    parsed: list[tuple[decisions_mod.Decision, list[str]]] = []
    for path in sorted((repo / "docs" / "review_decisions").glob("D-*.md")):
        rel = str(path.relative_to(repo))
        decision = decisions_mod.parse(path.read_text(encoding="utf-8"))
        parsed.append(
            (
                decision,
                decisions_mod.problems(
                    decision, path=rel, binding_stage=binding, commit_time=commit_time
                ),
            )
        )
    ownership_path = repo / "config" / "security" / "review_ownership.yaml"
    proof_path = repo / "reports" / "review_eval" / "e2e" / "t6_proof.json"
    proof_report = (
        json.loads(proof_path.read_text(encoding="utf-8")) if proof_path.is_file() else None
    )
    proof_problems = (
        _validate_t6_proof(proof_report)
        if isinstance(proof_report, Mapping)
        else ["T6 proof report root is not a mapping"]
        if proof_report is not None
        else []
    )
    return {
        "census": _latest_census(repo / "reports" / "bully_review"),
        "decisions": parsed,
        "reports": reports,
        "ownership": yaml.safe_load(ownership_path.read_text(encoding="utf-8"))
        if ownership_path.is_file()
        else None,
        "proof_report": proof_report,
        "proof_problems": proof_problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--repo", type=Path, default=REPO)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    collected = collect(args.repo)
    text = render(**collected)
    target = args.repo / OUT
    if args.write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(f"wrote {target}")
        return 0
    bad = [f"{d.id}: {p}" for d, probs in collected["decisions"] for p in probs]
    bad.extend(f"T6 proof: {problem}" for problem in collected["proof_problems"])
    stale = not target.is_file() or target.read_text(encoding="utf-8") != text
    for line in bad:
        print("INVALID DECISION", line)
    if stale:
        print(f"STALE: {OUT} is not what the evidence renders to; run --write")
    return 1 if (bad or stale) else 0


if __name__ == "__main__":
    raise SystemExit(main())
