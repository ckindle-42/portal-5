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
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from portal.modules.security.core.review_eval import decisions as decisions_mod  # noqa: E402

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


def render(
    *,
    census: Mapping[str, Any] | None,
    decisions: Sequence[tuple[decisions_mod.Decision, list[str]]],
    reports: Sequence[Mapping[str, Any]],
    ownership: Mapping[str, Any] | None,
) -> str:
    head = [
        "# Bully / Crogl review -- derived state",
        "",
        "DO NOT EDIT. Rendered by `scripts/bully_review_state.py` from the defect census, stamped",
        "evaluation reports and decision records; `--check` fails if this file is stale.",
        "",
    ]
    sections = [_claims(census), _decisions(decisions), _measured(reports), _ownership(ownership)]
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
                "--follow",
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
    return {
        "census": _latest_census(repo / "reports" / "bully_review"),
        "decisions": parsed,
        "reports": reports,
        "ownership": yaml.safe_load(ownership_path.read_text(encoding="utf-8"))
        if ownership_path.is_file()
        else None,
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
    text = render(**collect(args.repo))
    target = args.repo / OUT
    if args.write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(f"wrote {target}")
        return 0
    bad = [f"{d.id}: {p}" for d, probs in collect(args.repo)["decisions"] for p in probs]
    stale = not target.is_file() or target.read_text(encoding="utf-8") != text
    for line in bad:
        print("INVALID DECISION", line)
    if stale:
        print(f"STALE: {OUT} is not what the evidence renders to; run --write")
    return 1 if (bad or stale) else 0


if __name__ == "__main__":
    raise SystemExit(main())
