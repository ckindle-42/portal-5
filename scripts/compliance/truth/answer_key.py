#!/usr/bin/env python3
"""READING_TRUTH_V1 - the reference reading (answer key): validate, split, manifest, verify.

The key is the module's first written definition of a CORRECT answer. It is a
reference reading, not a rubric: each fact states a meaning a correct answer
must convey, and a judge decides by reading whether an answer conveys it. No
string of the key is ever matched against an answer, and the key never enters
a prompt, a persona, a tool result or a store write.

The key is the agent's: every contestable reading is DECIDED by the agent and
recorded as an interpretation (the readings considered, the one chosen, the
rationale and the sources it rests on). Nothing waits on a ruling. The operator
reviews the finished key afterwards; a correction is logged in ``changelog``
and only the affected items are re-judged.

The key, its manifest and every output here are local (``_local``): the key
carries operator text, and the manifest is per-item detail. Neither is public.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from typing import Any

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _local  # noqa: E402

SUITES = {"product", "conversational", "acceptance"}
CONFIDENCE = {"high", "medium", "low"}
STATUS = {"IN_PROGRESS", "AGENT_FINAL", "OPERATOR_REVIEWED"}
COVERAGE = {"covered", "partial", "not_covered", "not_applicable"}
SPLITS = {"dev", "holdout"}
#: facts that may stand without a cited section: an absence (nothing in scope
#: does X) or a judgment criterion for a meta question ("which documents do
#: the most work") - both still need a statement a judge can apply
EVIDENCE_OPTIONAL_KINDS = {"absence", "criterion"}
SPLIT_SEED = "reading-truth-v1"


def load(path: pathlib.Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: the key must be a mapping")
    return data


def _header_errors(entry: dict[str, Any], where: str, qid: str) -> list[str]:
    errors = [
        f"{where}: missing {name}"
        for name in ("question_id", "suite", "question", "governing", "facts", "confidence")
        if not entry.get(name)
    ]
    suite = entry.get("suite")
    if suite not in SUITES:
        errors.append(f"{where}: suite must be one of {sorted(SUITES)}")
    elif qid and not qid.startswith(f"{suite}:"):
        errors.append(f"{where}: question_id must start with '{suite}:'")
    if entry.get("confidence") not in CONFIDENCE:
        errors.append(f"{where}: confidence must be one of {sorted(CONFIDENCE)}")
    if entry.get("split") is not None and entry.get("split") not in SPLITS:
        errors.append(f"{where}: split must be one of {sorted(SPLITS)}")
    return errors


def _source_errors(entry: dict[str, Any], where: str) -> tuple[list[str], set[str]]:
    errors: list[str] = []
    cited: set[str] = set()
    for side in ("governing", "operator_evidence"):
        for item in entry.get(side) or []:
            if not isinstance(item, dict) or not item.get("section_id") or not item.get("text"):
                errors.append(f"{where}: every {side} item needs section_id and verbatim text")
                continue
            cited.add(str(item["section_id"]))
            if side == "governing" and not item.get("ref"):
                errors.append(f"{where}: governing item {item['section_id']} needs its ref")
    return errors, cited


def _fact_errors(entry: dict[str, Any], where: str, cited: set[str]) -> tuple[list[str], set[str]]:
    errors: list[str] = []
    fact_ids: set[str] = set()
    for fact in entry.get("facts") or []:
        if not isinstance(fact, dict) or not fact.get("id") or not fact.get("statement"):
            errors.append(f"{where}: every fact needs id and statement")
            continue
        if fact["id"] in fact_ids:
            errors.append(f"{where}: duplicate fact id {fact['id']}")
        fact_ids.add(fact["id"])
        if not isinstance(fact.get("required", True), bool):
            errors.append(f"{where}: fact {fact['id']} required must be true/false")
        if "coverage" in fact and (fact.get("coverage") not in COVERAGE or not fact.get("part")):
            errors.append(
                f"{where}: fact {fact['id']} coverage must be one of {sorted(COVERAGE)} with its part"
            )
        evidence = [str(e) for e in fact.get("evidence") or []]
        if not evidence and fact.get("kind") not in EVIDENCE_OPTIONAL_KINDS:
            errors.append(
                f"{where}: fact {fact['id']} has no evidence and is not an absence/criterion"
            )
        unknown = [e for e in evidence if e not in cited]
        if unknown:
            errors.append(
                f"{where}: fact {fact['id']} cites sections not in governing/operator_evidence: {unknown}"
            )
    return errors, fact_ids


def _trap_errors(entry: dict[str, Any], where: str, fact_ids: set[str]) -> list[str]:
    errors: list[str] = []
    trap_ids: set[str] = set()
    for trap in entry.get("traps") or []:
        if not isinstance(trap, dict) or not trap.get("id") or not trap.get("statement"):
            errors.append(f"{where}: every trap needs id and statement")
            continue
        if trap["id"] in trap_ids or trap["id"] in fact_ids:
            errors.append(f"{where}: trap id {trap['id']} collides")
        trap_ids.add(trap["id"])
    return errors


def _interpretation_errors(entry: dict[str, Any], where: str, taken: set[str]) -> list[str]:
    errors: list[str] = []
    for item in entry.get("interpretations") or []:
        if not isinstance(item, dict) or not item.get("id") or not item.get("question"):
            errors.append(f"{where}: every interpretation needs id and question")
            continue
        readings = item.get("readings") or []
        chosen = item.get("chosen")
        if len(readings) < 2 or not isinstance(chosen, int) or not 0 <= chosen < len(readings):
            errors.append(
                f"{where}: interpretation {item['id']} needs >=2 readings and a chosen index"
            )
        if not item.get("rationale") or not item.get("sources"):
            errors.append(f"{where}: interpretation {item['id']} needs its rationale and sources")
        if item["id"] in taken:
            errors.append(f"{where}: interpretation id {item['id']} collides")
        taken.add(item["id"])
    return errors


def _entry_errors(entry: Any, position: int) -> list[str]:
    if not isinstance(entry, dict):
        return [f"entries[{position}]: not a mapping"]
    qid = str(entry.get("question_id") or "")
    where = f"entries[{position}] ({qid or 'no question_id'})"
    errors = _header_errors(entry, where, qid)
    source_errors, cited = _source_errors(entry, where)
    fact_errors, fact_ids = _fact_errors(entry, where, cited)
    trap_ids = {str(t.get("id")) for t in entry.get("traps") or [] if isinstance(t, dict)}
    return [
        *errors,
        *source_errors,
        *fact_errors,
        *_trap_errors(entry, where, fact_ids),
        *_interpretation_errors(entry, where, fact_ids | trap_ids),
    ]


def validate(key: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(key.get("key_version"), int):
        errors.append("key_version must be an integer")
    if key.get("status") not in STATUS:
        errors.append(f"status must be one of {sorted(STATUS)}")
    if key.get("status") == "OPERATOR_REVIEWED" and not key.get("reviewed_by"):
        errors.append("an OPERATOR_REVIEWED key names who reviewed it")
    if key.get("status") in ("AGENT_FINAL", "OPERATOR_REVIEWED") and not key.get(
        "documents_considered"
    ):
        errors.append("a finished key records documents_considered (the search space it read)")
    snapshot = key.get("store_snapshot")
    if not isinstance(snapshot, dict) or not snapshot.get("db_sha256"):
        errors.append("store_snapshot.db_sha256 is required (the store the key was read from)")
    entries = key.get("entries")
    if not isinstance(entries, list) or not entries:
        return [*errors, "entries must be a non-empty list"]
    seen: set[str] = set()
    for position, entry in enumerate(entries):
        errors.extend(_entry_errors(entry, position))
        qid = str((entry or {}).get("question_id") or "") if isinstance(entry, dict) else ""
        if qid and qid in seen:
            errors.append(f"duplicate question_id {qid}")
        seen.add(qid)
    return errors


def _unit_interval(question_id: str) -> float:
    digest = hashlib.sha256(f"{SPLIT_SEED}\0{question_id}".encode()).hexdigest()
    return int(digest[:8], 16) / 2**32


def assign_split(key: dict[str, Any], holdout_fraction: float) -> list[str]:
    """Deterministic, stable split. Existing assignments are never changed;
    acceptance questions are always holdout (they are the in-service gate, and
    tuning against the gate is overfitting it). Returns the ids it assigned."""
    assigned = []
    for entry in key.get("entries") or []:
        if entry.get("split") in SPLITS:
            continue
        if entry.get("suite") == "acceptance":
            entry["split"] = "holdout"
        else:
            entry["split"] = (
                "holdout" if _unit_interval(entry["question_id"]) < holdout_fraction else "dev"
            )
        assigned.append(entry["question_id"])
    return assigned


def manifest(key: dict[str, Any], key_bytes: bytes) -> dict[str, Any]:
    """Public: ids, counts and hashes only - no text, no document titles."""
    entries = key.get("entries") or []
    by_suite: dict[str, int] = {}
    by_split: dict[str, int] = {}
    rows = []
    for entry in entries:
        by_suite[entry["suite"]] = by_suite.get(entry["suite"], 0) + 1
        split = entry.get("split") or "unassigned"
        by_split[split] = by_split.get(split, 0) + 1
        facts = entry.get("facts") or []
        rows.append(
            {
                "question_id": entry["question_id"],
                "suite": entry["suite"],
                "split": split,
                "history_only": bool(entry.get("history")),
                "n_facts": len(facts),
                "n_required": sum(1 for f in facts if f.get("required", True)),
                "n_traps": len(entry.get("traps") or []),
                "confidence": entry.get("confidence"),
                "n_interpretations": len(entry.get("interpretations") or []),
                "n_coverage_parts": sum(1 for f in facts if "coverage" in f),
                "governing_refs": sorted({str(g.get("ref")) for g in entry.get("governing") or []}),
                "operator_section_ids": sorted(
                    {str(o.get("section_id")) for o in entry.get("operator_evidence") or []}
                ),
            }
        )
    return {
        "key_version": key.get("key_version"),
        "status": key.get("status"),
        "reviewed_by": key.get("reviewed_by", ""),
        "key_sha256": hashlib.sha256(key_bytes).hexdigest(),
        "store_snapshot": key.get("store_snapshot"),
        "n_entries": len(entries),
        "by_suite": dict(sorted(by_suite.items())),
        "by_split": dict(sorted(by_split.items())),
        "entries": rows,
    }


def verify_store(key: dict[str, Any]) -> list[str]:
    """Every quoted text is verbatim in its section (same fold as the store's
    own verbatim check) and every section id resolves. Store-dependent."""
    from portal.modules.compliance.core.candidate_links import _norm_for_verbatim as fold
    from portal.modules.compliance.core.repository import Repository
    from portal.modules.compliance.core.section_index import resolve_sections

    problems: list[str] = []
    repo = Repository()
    try:
        for entry in key.get("entries") or []:
            for side in ("governing", "operator_evidence"):
                for item in entry.get(side) or []:
                    sid = str(item.get("section_id"))
                    got = resolve_sections(repo, [sid]).get(sid)
                    if not got:
                        problems.append(f"{entry['question_id']}: {side} {sid} does not resolve")
                        continue
                    if fold(str(item.get("text", ""))) not in fold(str(got.get("text", ""))):
                        problems.append(
                            f"{entry['question_id']}: {side} {sid} text is not verbatim in the section"
                        )
    finally:
        repo.close()
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["validate", "split", "manifest", "verify-store"])
    ap.add_argument("key", type=pathlib.Path)
    ap.add_argument("--holdout-fraction", type=float, default=0.34)
    ap.add_argument("--out", type=pathlib.Path)
    args = ap.parse_args(argv)
    if args.command == "manifest" and args.out is not None:
        refused = _local.refusal(args.out, "the key manifest")
        if refused:
            print(refused, file=sys.stderr)
            return 2
    raw = args.key.read_bytes()
    key = load(args.key)
    errors = validate(key)
    if args.command == "validate" or errors:
        for line in errors:
            print(f"KEY ERROR: {line}")
        print("KEY VALID" if not errors else f"KEY INVALID ({len(errors)} errors)")
        return 0 if not errors else 1
    if args.command == "split":
        assigned = assign_split(key, args.holdout_fraction)
        args.key.write_text(
            yaml.safe_dump(key, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        print(f"assigned {len(assigned)} split(s); existing assignments unchanged")
        return 0
    if args.command == "manifest":
        if args.out is None:
            print("--out is required", file=sys.stderr)
            return 2
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(manifest(key, raw), indent=2) + "\n")
        print(f"WROTE {args.out}")
        return 0
    problems = verify_store(key)
    for line in problems:
        print(f"STORE MISMATCH: {line}")
    print("KEY MATCHES STORE" if not problems else f"{len(problems)} mismatches")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
