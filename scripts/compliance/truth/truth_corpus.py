#!/usr/bin/env python3
"""READING_TRUTH_V1 - inventory and blinding for every compliance transcript.

Offline: no store, no model, no network. Two subcommands.

Nothing here is public. Every run writes under the private runs dir (the
default root), and both subcommands refuse to write anywhere a commit could
carry the result (``_local``).

``provenance`` writes one row per run directory (a directory holding a
``transcripts/`` folder): the grader signature its verdicts were computed
with, the tool path the model actually took, the model that served, how many
cite tokens were the persona's literal placeholder, and whether any verdict in
it was ever reached by reading rather than by a mechanical check. Rows with
different grader signatures are not comparable, and the output says so.

``queue`` turns every transcript into a blinded judging item. The judge sees
the question id, the question and the answer - never the run, era, seat, arm,
route or mechanical verdict. Those go to a separate unblind map that the judge
must not open.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _local  # noqa: E402

REPO = _local.REPO
DEFAULT_ROOTS = (_local.RUNS,)
RECEIPT_NAMES = ("conversational_proof.json", "product_questions_family.json")
#: the persona's literal example token - a value no tool ever prints
PLACEHOLDER = re.compile(r"\b[OR]-xxxxxx\b")  # the persona's placeholder since P1 scrubbed a1b2c3
QUOTE = re.compile(r'"[^"\n]{2,}?"|\u201c[^\u201c\u201d\n]{2,}?\u201d')


def _load(path: pathlib.Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO))
    except ValueError:
        return str(path)


def run_name(
    run_dir: pathlib.Path, roots: tuple[pathlib.Path, ...] | list[pathlib.Path] = ()
) -> str:
    """A run's name relative to the root it was found under (``cite_and_scope/p3/product``),
    so prefixes read the same whether the run is archived history or a new private run."""
    for root in roots:
        try:
            return str(run_dir.resolve().relative_to(root.resolve()))
        except ValueError:
            continue
    return _rel(run_dir)


def run_dirs(root: pathlib.Path) -> list[pathlib.Path]:
    """Every directory that holds a non-empty ``transcripts/`` folder."""
    found = []
    for folder in sorted(root.rglob("transcripts")):
        if folder.is_dir() and any(folder.glob("*.json")):
            found.append(folder.parent)
    return found


def receipt_for(run_dir: pathlib.Path) -> pathlib.Path | None:
    for name in RECEIPT_NAMES:
        candidate = run_dir / name
        if candidate.is_file():
            return candidate
    for candidate in sorted(run_dir.glob("*.json")):
        data = _load(candidate)
        if isinstance(data, dict) and isinstance(data.get("rows"), list):
            return candidate
    return None


def suite_of(receipt_path: pathlib.Path | None) -> str:
    name = receipt_path.name if receipt_path else ""
    if name.startswith("product"):
        return "product"
    if name.startswith("conversational"):
        return "conversational"
    return "other"


def row_index(receipt: Any) -> dict[str, dict]:
    """Receipt rows by transcript stem: ``<standard>__<key>`` or ``<key>``."""
    index: dict[str, dict] = {}
    for row in (receipt or {}).get("rows") or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "")
        standard = str(row.get("standard") or "")
        if standard and key:
            index[f"{standard}__{key}"] = row
        if key:
            index.setdefault(key, row)
    return index


def question_id(suite: str, row: dict, stem: str) -> str:
    """The answer key's id for the question a transcript answered."""
    key = str(row.get("key") or stem.split("__")[-1])
    if suite == "product":
        standard = str(row.get("standard") or stem.split("__")[0])
        return f"product:{standard}:{key}"
    if suite == "conversational":
        return f"conversational:{key}"
    return f"other:{stem}"


def _first_commit(path: pathlib.Path) -> str:
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%h %cI", "--", str(path)],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    lines = out.splitlines()
    return lines[-1] if lines else ""


def provenance_row(
    run_dir: pathlib.Path, *, with_git: bool = True, roots: tuple[pathlib.Path, ...] = ()
) -> dict[str, Any]:
    receipt_path = receipt_for(run_dir)
    receipt = _load(receipt_path) if receipt_path else None
    receipt = receipt if isinstance(receipt, dict) else {}
    rows = [r for r in receipt.get("rows") or [] if isinstance(r, dict)]
    checks = sorted({c for r in rows for c in (r.get("checks") or {})})
    tools: collections.Counter = collections.Counter()
    served: collections.Counter = collections.Counter()
    placeholders = quotes = empty = non_200 = n = 0
    for transcript in sorted((run_dir / "transcripts").glob("*.json")):
        data = _load(transcript)
        if not isinstance(data, dict):
            continue
        n += 1
        for name, count in (data.get("tool_calls") or {}).items():
            try:
                tools[str(name)] += float(count)
            except (TypeError, ValueError):
                continue
        route_tail = str(data.get("route_header") or "").split(";")[-1]
        served[str(data.get("served_model") or route_tail or "unknown")] += 1
        answer = str(data.get("answer") or "")
        placeholders += len(PLACEHOLDER.findall(answer))
        quotes += len(QUOTE.findall(answer))
        empty += 0 if answer.strip() else 1
        non_200 += 0 if data.get("http_status") in (200, None) else 1
    judged = int(receipt.get("n_agent_judged") or 0)
    basis = receipt.get("verdict_basis") or ("judged" if judged else "mechanical")
    return {
        "run_dir": _rel(run_dir),
        "run": run_name(run_dir, roots),
        "suite": suite_of(receipt_path),
        "receipt": receipt_path.name if receipt_path else "",
        "run_id": receipt.get("run_id", ""),
        "workspace": receipt.get("workspace", ""),
        "n_questions": receipt.get("n_questions", len(rows)),
        "n_passed": receipt.get("n_passed"),
        "grader_signature": "+".join(checks) or "unknown",
        "verdict_basis": basis,
        "n_agent_judged": judged,
        "n_transcripts": n,
        "tool_calls": dict(sorted(tools.items())),
        "served_models": dict(sorted(served.items())),
        "placeholder_tokens": placeholders,
        "quoted_spans": quotes,
        "empty_answers": empty,
        "non_200": non_200,
        "provenance_block": bool(receipt.get("provenance")),
        "first_commit": _first_commit(run_dir) if with_git else "",
    }


def provenance_report(
    dirs: list[pathlib.Path], *, with_git: bool = True, roots: tuple[pathlib.Path, ...] = ()
) -> dict[str, Any]:
    rows = [provenance_row(d, with_git=with_git, roots=roots) for d in dirs]
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for row in rows:
        groups[f"{row['suite']}|{row['grader_signature']}"].append(row["run"])
    return {
        "note": (
            "Pass counts are comparable only inside one suite|grader_signature group, and "
            "only as MECHANICAL citation checks. verdict_basis=mechanical means no verdict "
            "in that run was reached by reading the answer."
        ),
        "rows": rows,
        "comparable_groups": dict(sorted(groups.items())),
    }


def provenance_markdown(report: dict[str, Any]) -> str:
    head = (
        "| run | suite | passed | grader signature | basis | tools (top 3) | served | "
        "placeholder | quotes | empty |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    lines = [head]
    for row in report["rows"]:
        top = sorted(row["tool_calls"].items(), key=lambda kv: -kv[1])[:3]
        tools = ", ".join(f"{k} {v:g}" for k, v in top)
        served = ", ".join(row["served_models"])
        passed = f"{row['n_passed']}/{row['n_questions']}" if row["n_passed"] is not None else "-"
        lines.append(
            f"| `{row['run']}` | {row['suite']} | {passed} | {row['grader_signature']} | "
            f"{row['verdict_basis']} | {tools} | {served} | {row['placeholder_tokens']} | "
            f"{row['quoted_spans']} | {row['empty_answers']} |"
        )
    return "\n".join(lines) + "\n"


def build_queue(
    dirs: list[pathlib.Path], salt: str, roots: tuple[pathlib.Path, ...] = ()
) -> tuple[list[dict], dict[str, dict]]:
    items: list[dict] = []
    unblind: dict[str, dict] = {}
    for run_dir in dirs:
        receipt_path = receipt_for(run_dir)
        receipt = _load(receipt_path) if receipt_path else None
        index = row_index(receipt)
        suite = suite_of(receipt_path)
        for transcript in sorted((run_dir / "transcripts").glob("*.json")):
            data = _load(transcript)
            if not isinstance(data, dict):
                continue
            row = index.get(transcript.stem) or {}
            question = data.get("question") or row.get("question") or ""
            answer = str(data.get("answer") or "")
            rel = _rel(transcript)
            item_id = hashlib.sha256(f"{salt}\0{rel}".encode()).hexdigest()[:12]
            qid = question_id(suite, row, transcript.stem)
            items.append(
                {"item_id": item_id, "question_id": qid, "question": question, "answer": answer}
            )
            unblind[item_id] = {
                "transcript": rel,
                "run_dir": _rel(run_dir),
                "run": run_name(run_dir, roots),
                "suite": suite,
                "question_id": qid,
                "mechanical_verdict": row.get("verdict"),
                "failed_checks": [c for c, ok in (row.get("checks") or {}).items() if ok is False],
                "served_model": data.get("served_model"),
                "route_header": data.get("route_header"),
                "tool_calls": data.get("tool_calls") or {},
                "wall_s": data.get("wall_s"),
                "question_missing": not question,
                "answer_empty": not answer.strip(),
            }
    items.sort(key=lambda item: item["item_id"])
    return items, unblind


def split_filter(
    items: list[dict], unblind: dict[str, dict], key_path: pathlib.Path, split: str
) -> tuple[list[dict], dict[str, dict], list[str]]:
    """Keep only items whose question is in ``split`` of the key; name every
    question id the key does not hold (an unkeyed item can never be judged)."""
    import answer_key

    splits = {
        str(e["question_id"]): e.get("split")
        for e in answer_key.load(key_path).get("entries") or []
    }
    unkeyed = sorted({i["question_id"] for i in items if i["question_id"] not in splits})
    kept = [i for i in items if splits.get(i["question_id"]) == split]
    ids = {i["item_id"] for i in kept}
    return kept, {k: v for k, v in unblind.items() if k in ids}, unkeyed


def _roots(args: argparse.Namespace) -> tuple[pathlib.Path, ...]:
    return tuple(args.root) if args.root else tuple(r for r in DEFAULT_ROOTS if r.is_dir())


def _selected(args: argparse.Namespace) -> tuple[list[pathlib.Path], tuple[pathlib.Path, ...]]:
    roots = _roots(args)
    dirs = [d for root in roots for d in run_dirs(root)]
    if args.only:
        dirs = [d for d in dirs if any(run_name(d, roots).startswith(p) for p in args.only)]
    return dirs, roots


def _cmd_provenance(args: argparse.Namespace) -> int:
    refused = _local.refusal(args.out, "the provenance table")
    if refused:
        print(refused, file=sys.stderr)
        return 2
    dirs, roots = _selected(args)
    report = provenance_report(dirs, with_git=not args.no_git, roots=roots)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "receipt_provenance.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.out / "receipt_provenance.md").write_text(provenance_markdown(report))
    print(f"WROTE {args.out}/receipt_provenance.{{json,md}} - {len(report['rows'])} run dirs")
    return 0


def _cmd_queue(args: argparse.Namespace) -> int:
    refused = _local.refusal(args.out, "the judging queue")
    if refused:
        print(refused, file=sys.stderr)
        return 2
    dirs, roots = _selected(args)
    items, unblind = build_queue(dirs, args.salt, roots)
    if args.split:
        if args.key is None:
            print("--split needs --key", file=sys.stderr)
            return 2
        items, unblind, unkeyed = split_filter(items, unblind, args.key, args.split)
        if unkeyed:
            print(f"REFUSED: question ids not in the key: {unkeyed}", file=sys.stderr)
            return 1
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "queue.jsonl").open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    (args.out / "unblind.json").write_text(json.dumps(unblind, indent=2, ensure_ascii=False) + "\n")
    missing = sum(1 for u in unblind.values() if u["question_missing"])
    print(
        f"WROTE {args.out}/queue.jsonl ({len(items)} items; {missing} without a question) + unblind.json"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    prov = sub.add_parser("provenance")
    prov.add_argument(
        "--root", type=pathlib.Path, action="append", help="repeatable; default: archive + runs"
    )
    prov.add_argument("--only", action="append", help="run-name prefix, relative to its root")
    prov.add_argument("--out", type=pathlib.Path, required=True)
    prov.add_argument("--no-git", action="store_true")
    prov.set_defaults(func=_cmd_provenance)
    queue = sub.add_parser("queue")
    queue.add_argument(
        "--root", type=pathlib.Path, action="append", help="repeatable; default: archive + runs"
    )
    queue.add_argument("--only", action="append", help="run-name prefix, relative to its root")
    queue.add_argument("--salt", required=True)
    queue.add_argument("--key", type=pathlib.Path, help="answer key (needed for --split)")
    queue.add_argument("--split", choices=["dev", "holdout"], help="queue only this split")
    queue.add_argument("--out", type=pathlib.Path, required=True)
    queue.set_defaults(func=_cmd_queue)
    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
