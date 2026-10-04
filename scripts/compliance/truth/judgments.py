#!/usr/bin/env python3
"""READING_TRUTH_V1 - judgment records: validate, derive the verdict, aggregate, compare.

The judge (a frontier reader, blind to run/era/seat/arm) records ATOMIC
judgments per item against the answer key: each key fact conveyed correctly,
conveyed wrongly, or omitted; each other substantive claim correct, incorrect
or unverifiable from the corpus; each absence claim correct or incorrect; any
trap the answer fell into. The overall verdict is DERIVED here from those
atoms by one rule - the judge never types it - so two judges who agree on the
atoms cannot disagree on the verdict:

* NON_ANSWER - the item is empty, an error, or a refusal (judge flags it)
* WRONG      - any fact conveyed wrongly, any incorrect claim, any incorrect
               absence claim, or any trap hit
* CORRECT    - every required fact conveyed correctly and nothing wrong
* PARTIAL    - nothing wrong, but a required fact omitted
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _local  # noqa: E402
import answer_key  # noqa: E402

FACT_VERDICTS = {"correct", "wrong", "omitted"}
CLAIM_VERDICTS = {"correct", "incorrect", "unverifiable"}
ABSENCE_VERDICTS = {"correct", "incorrect"}
OVERALL = ("CORRECT", "PARTIAL", "WRONG", "NON_ANSWER")
PASSES = {"A", "B", "C"}
RULE = (
    "NON_ANSWER if flagged; WRONG if any fact conveyed wrongly, incorrect claim, incorrect "
    "absence claim or trap hit; CORRECT if every required fact conveyed correctly; else PARTIAL"
)


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError as exc:
                raise ValueError(f"{path}:{number}: {exc}") from exc
    return rows


def key_entries(key: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(e["question_id"]): e for e in key.get("entries") or []}


def derive_overall(record: dict[str, Any], entry: dict[str, Any]) -> str:
    if record.get("non_answer"):
        return "NON_ANSWER"
    facts = record.get("facts") or {}
    wrong = any(v == "wrong" for v in facts.values())
    wrong = wrong or any(c.get("verdict") == "incorrect" for c in record.get("claims") or [])
    wrong = wrong or any(
        a.get("verdict") == "incorrect" for a in record.get("absence_claims") or []
    )
    if wrong or record.get("traps_hit"):
        return "WRONG"
    required = [f["id"] for f in entry.get("facts") or [] if f.get("required", True)]
    if all(facts.get(fid) == "correct" for fid in required):
        return "CORRECT"
    return "PARTIAL"


def validate(records: list[dict[str, Any]], entries: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for n, rec in enumerate(records):
        where = f"record[{n}] ({rec.get('item_id')}/{rec.get('pass')})"
        if not rec.get("item_id") or rec.get("pass") not in PASSES:
            errors.append(f"{where}: needs item_id and pass in {sorted(PASSES)}")
            continue
        pair = (str(rec["item_id"]), str(rec["pass"]))
        if pair in seen:
            errors.append(f"{where}: duplicate item/pass")
        seen.add(pair)
        entry = entries.get(str(rec.get("question_id")))
        if entry is None:
            errors.append(f"{where}: question_id {rec.get('question_id')!r} is not in the key")
            continue
        if rec.get("non_answer"):
            continue
        fact_ids = {f["id"] for f in entry.get("facts") or []}
        given = rec.get("facts") or {}
        if set(given) != fact_ids:
            errors.append(
                f"{where}: facts must judge exactly {sorted(fact_ids)}; got {sorted(given)}"
            )
        bad = {k: v for k, v in given.items() if v not in FACT_VERDICTS}
        if bad:
            errors.append(f"{where}: fact verdicts must be {sorted(FACT_VERDICTS)}: {bad}")
        for claim in rec.get("claims") or []:
            if not claim.get("text") or claim.get("verdict") not in CLAIM_VERDICTS:
                errors.append(
                    f"{where}: every claim needs text and verdict in {sorted(CLAIM_VERDICTS)}"
                )
        for claim in rec.get("absence_claims") or []:
            if not claim.get("text") or claim.get("verdict") not in ABSENCE_VERDICTS:
                errors.append(
                    f"{where}: every absence claim needs text and verdict in {sorted(ABSENCE_VERDICTS)}"
                )
        traps = {t["id"] for t in entry.get("traps") or []}
        unknown = [t for t in rec.get("traps_hit") or [] if t not in traps]
        if unknown:
            errors.append(f"{where}: traps_hit not in the key entry: {unknown}")
    return errors


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (round((centre - margin) / denom, 4), round((centre + margin) / denom, 4))


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(1 for a, b in pairs if a == b) / n
    left = collections.Counter(a for a, _ in pairs)
    right = collections.Counter(b for _, b in pairs)
    expected = sum(left[label] * right[label] for label in OVERALL) / (n * n)
    if expected >= 1.0:
        return 1.0
    return round((observed - expected) / (1 - expected), 4)


def _summary(scored: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(scored)
    counts = collections.Counter(s["overall"] for s in scored)
    required = sum(s["n_required"] for s in scored)
    required_ok = sum(s["n_required_correct"] for s in scored)
    return {
        "n": n,
        "counts": {label: counts.get(label, 0) for label in OVERALL},
        "correct_rate": round(counts.get("CORRECT", 0) / n, 4) if n else None,
        "correct_ci95": wilson(counts.get("CORRECT", 0), n),
        "wrong_rate": round(counts.get("WRONG", 0) / n, 4) if n else None,
        "wrong_ci95": wilson(counts.get("WRONG", 0), n),
        "required_fact_recall": round(required_ok / required, 4) if required else None,
        "items_with_incorrect_claim": sum(1 for s in scored if s["incorrect_claims"]),
        "items_with_trap": sum(1 for s in scored if s["traps_hit"]),
    }


def score(
    records: list[dict[str, Any]], entries: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    out = []
    for rec in records:
        entry = entries[str(rec["question_id"])]
        required = [f["id"] for f in entry.get("facts") or [] if f.get("required", True)]
        facts = rec.get("facts") or {}
        out.append(
            {
                "item_id": rec["item_id"],
                "pass": rec["pass"],
                "question_id": rec["question_id"],
                "split": entry.get("split") or "unassigned",
                "history_only": bool(entry.get("history")),
                "overall": derive_overall(rec, entry),
                "n_required": len(required),
                "n_required_correct": sum(1 for fid in required if facts.get(fid) == "correct"),
                "incorrect_claims": sum(
                    1 for c in rec.get("claims") or [] if c.get("verdict") == "incorrect"
                ),
                "traps_hit": list(rec.get("traps_hit") or []),
            }
        )
    return out


def aggregate(
    records: list[dict[str, Any]],
    unblind: dict[str, dict[str, Any]],
    entries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    # The primary set is the A pass with C arbitrating where it ran: in a final
    # set (A with C substituted) every record is primary; in a double-judged
    # A/B round the B records stay out of the headline. Feeding a final set
    # through a bare pass=="A" filter would silently drop exactly the
    # contested items pass C settled (A6: it hid a keep-rule regression).
    has_b = any(r.get("pass") == "B" for r in records)
    primary_records = [
        r for r in records if r.get("pass") == "A" or (r.get("pass") == "C" and not has_b)
    ]
    primary = score(primary_records, entries)
    by_group: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    by_split: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    confusion: collections.Counter = collections.Counter()
    for s in primary:
        meta = unblind.get(s["item_id"], {})
        by_group[f"{meta.get('run_dir', '?')}|{meta.get('suite', '?')}"].append(s)
        by_split[s["split"]].append(s)
        mech = meta.get("mechanical_verdict")
        if mech in ("PASS", "FAIL"):
            confusion[f"mechanical_{mech}__judged_{s['overall']}"] += 1
    passes: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for s in score(records, entries):
        passes[s["item_id"]][s["pass"]] = s["overall"]
    pairs = [(p["A"], p["B"]) for p in passes.values() if "A" in p and "B" in p]
    disagreements = sorted(
        i for i, p in passes.items() if "A" in p and "B" in p and p["A"] != p["B"]
    )
    coverage: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for rec in records:
        if rec.get("pass") != "A" or rec.get("non_answer"):
            continue
        entry = entries[str(rec["question_id"])]
        for fact in entry.get("facts") or []:
            if "coverage" in fact:
                cell = coverage[entry.get("split") or "unassigned"]
                cell[0] += 1
                cell[1] += 1 if (rec.get("facts") or {}).get(fact["id"]) == "correct" else 0
    return {
        "rule": RULE,
        "coverage_part_facts": {
            split: {"n": n, "correct": ok, "rate": round(ok / n, 4) if n else None}
            for split, (n, ok) in sorted(coverage.items())
        },
        "overall": _summary(primary),
        "by_group": {g: _summary(v) for g, v in sorted(by_group.items())},
        "by_split": {g: _summary(v) for g, v in sorted(by_split.items())},
        "mechanical_vs_judged": dict(sorted(confusion.items())),
        "agreement": {
            "n_double_judged": len(pairs),
            "percent_agreement": round(sum(1 for a, b in pairs if a == b) / len(pairs), 4)
            if pairs
            else None,
            "cohen_kappa": cohen_kappa(pairs),
            "disagreements": disagreements,
        },
    }


def compare(
    records: list[dict[str, Any]],
    unblind: dict[str, dict[str, Any]],
    entries: dict[str, dict[str, Any]],
    baseline: list[str],
    arm: list[str],
    *,
    split: str = "dev",
    min_net: int = 3,
) -> dict[str, Any]:
    """Paired per-question comparison of two arms (run-dir prefixes), on one split.

    Predeclared keep rule for an OPTIMISATION: net improved questions must reach
    max(min_net, ceil(noisy_baseline_questions / 2)), and no question whose
    baseline reps were all CORRECT may show a WRONG rep in the arm. A TRUTH
    FIX (a false statement removed) is kept unless it regresses: the second
    condition alone. The caller says which kind the change is."""
    # The caller is expected to pass a final set (A with C substituted) or a
    # single-pass set. Filtering to pass=="A" here dropped exactly the
    # contested items pass C settled, biasing every comparison toward the
    # pass-A status quo (A6: it hid a keep-rule regression on the arm side).
    # Scoring the set as given is only sound for a final set, so refuse the
    # shapes that would silently count a rep twice.
    if any(r.get("pass") == "B" for r in records):
        raise ValueError("compare takes a final set (A with C substituted), not a pass-B set")
    ids = [r["item_id"] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError("compare takes a final set: an item_id appears more than once")
    scored = [s for s in score(records, entries) if s["split"] == split]

    def reps(prefixes: list[str]) -> dict[str, list[str]]:
        out: dict[str, list[str]] = collections.defaultdict(list)
        for s in scored:
            meta = unblind.get(s["item_id"], {})
            names = (str(meta.get("run", "")), str(meta.get("run_dir", "")))
            if any(name.startswith(p) for name in names for p in prefixes):
                out[s["question_id"]].append(s["overall"])
        return out

    base, cand = reps(baseline), reps(arm)
    shared = sorted(set(base) & set(cand))
    improved, worsened, regressions = [], [], []
    noisy = sum(1 for q in base.values() if len({v == "CORRECT" for v in q}) > 1)
    for qid in shared:
        b = sum(v == "CORRECT" for v in base[qid]) / len(base[qid])
        c = sum(v == "CORRECT" for v in cand[qid]) / len(cand[qid])
        if c > b:
            improved.append(qid)
        elif c < b:
            worsened.append(qid)
        if all(v == "CORRECT" for v in base[qid]) and any(v == "WRONG" for v in cand[qid]):
            regressions.append(qid)
    threshold = max(min_net, math.ceil(noisy / 2))
    net = len(improved) - len(worsened)
    return {
        "split": split,
        "questions_compared": len(shared),
        "missing_in_arm": sorted(set(base) - set(cand)),
        "improved": improved,
        "worsened": worsened,
        "net_improved": net,
        "noisy_baseline_questions": noisy,
        "optimisation_threshold": threshold,
        "regressions_correct_to_wrong": regressions,
        "keep_if_optimisation": net >= threshold and not regressions,
        "keep_if_truth_fix": not regressions,
    }


def _load_all(paths: list[pathlib.Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        records.extend(read_jsonl(path))
    return records


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("command", choices=["validate", "aggregate", "compare"])
    ap.add_argument("--key", type=pathlib.Path, required=True)
    ap.add_argument("--judgments", type=pathlib.Path, action="append", required=True)
    ap.add_argument("--unblind", type=pathlib.Path, action="append")
    ap.add_argument("--baseline", action="append", default=[])
    ap.add_argument("--arm", action="append", default=[])
    ap.add_argument("--split", default="dev")
    ap.add_argument("--out", type=pathlib.Path)
    args = ap.parse_args(argv)
    if args.out is not None:
        refused = _local.refusal(args.out, "judged results")
        if refused:
            print(refused, file=sys.stderr)
            return 2
    key = answer_key.load(args.key)
    key_errors = answer_key.validate(key)
    if key_errors:
        print(
            f"KEY INVALID ({len(key_errors)} errors) - run answer_key.py validate", file=sys.stderr
        )
        return 1
    entries = key_entries(key)
    records = _load_all(args.judgments)
    errors = validate(records, entries)
    for line in errors:
        print(f"JUDGMENT ERROR: {line}")
    if errors:
        print(f"JUDGMENTS INVALID ({len(errors)} errors)")
        return 1
    if args.command == "validate":
        print(f"JUDGMENTS VALID ({len(records)} records)")
        return 0
    unblind: dict[str, dict[str, Any]] = {}
    for path in args.unblind or []:
        unblind.update(json.loads(path.read_text(encoding="utf-8")))
    if args.command == "aggregate":
        result = aggregate(records, unblind, entries)
    else:
        try:
            result = compare(records, unblind, entries, args.baseline, args.arm, split=args.split)
        except ValueError as exc:
            print(f"JUDGMENTS INVALID: {exc}", file=sys.stderr)
            return 1
    result["key_manifest_sha256"] = answer_key.manifest(key, args.key.read_bytes())["key_sha256"]
    result["key_status"] = key.get("status")
    text = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        print(f"WROTE {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
