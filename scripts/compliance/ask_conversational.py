#!/usr/bin/env python3
"""LOAD_AND_CONVERSE_V1 §P4 — the conversation the module was asked for.

Every product question ever asked named a requirement, which exercises the
REGISTER path (``compliance_context``). Nothing exercised the RETRIEVAL path:
finding material by meaning. This harness asks fourteen questions that name no
requirement address at all, on the deployed workspace, and judges each on:

  answered          non-empty answer, HTTP 200, inside the turn budget
  used_search       ``compliance_search`` was ACTUALLY called — read from the
                    router's own tool counters, never assumed
  citations resolve every section id in the answer resolves in the store
  both sides        ≥1 operator AND ≥1 regulatory section cited (the questions
                    are relational by construction)
  honest absence    for ABSENCE questions the rule inverts: the answer must
                    name the requirement and either cite store-linked operator
                    coverage or name the gap. An operator section whose citing
                    sentence POSITIVELY asserts coverage and that carries no
                    recorded edge into that family is INVENTED coverage — the
                    worst outcome, and the one this phase exists to catch
                    (candidate_links.classify_assertion is the instrument).

Two questions are ADDED to the twelve the task file drew (recorded in
``added_questions``): a vocabulary-bridge ask (operator "records" vs standard
"evidence" — the whole point of semantic search is surviving that gap) and a
cross-revision ask (the store holds both CIP-003 revisions by design; a
conversation about "what changed" must find material in each). A proof that
only asks the questions the author imagined is the CIP-007-6 mistake again.

    uv run python scripts/compliance/ask_conversational.py \\
        --workspace compliance-reading \\
        --out-dir reports/compliance/load_and_converse/p4
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import httpx  # noqa: E402
from compliance_acceptance import WorkspaceThread, router_base_url  # noqa: E402

from portal.modules.compliance.core.answer_contract import SECTION_ID_PATTERN  # noqa: E402
from portal.modules.compliance.core.candidate_links import classify_assertion  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402
from portal.modules.compliance.core.section_index import (  # noqa: E402
    parent_section_id,
    resolve_sections,
)

_SECTION_TOKEN = re.compile(rf"\b{SECTION_ID_PATTERN}\b", re.I)
_REQUIREMENT_ADDRESS = re.compile(r"\bCIP-\d{3}-[A-Za-z0-9.]+\s+R\d+\b")

#: the floor set from the task file, plus the two additions argued for above.
QUESTIONS: list[dict[str, str]] = [
    # ── Topic → both sides ────────────────────────────────────────────────
    {
        "key": "remote_access",
        "kind": "topic",
        "question": (
            "What do our procedures say about remote access, and what does CIP require of it?"
        ),
    },
    {
        "key": "patching",
        "kind": "topic",
        "question": ("Where does our patching practice sit against what the standards require?"),
    },
    {
        "key": "vendor_risk",
        "kind": "topic",
        "question": ("Which of our policies touch vendor and supply-chain risk?"),
    },
    {
        "key": "shared_accounts",
        "kind": "topic",
        "question": ("What do we say about shared accounts?"),
    },
    # ── Operator-first ────────────────────────────────────────────────────
    {
        "key": "patch_cycle",
        "kind": "operator_fact",
        "question": ("We have a 30-day patch cycle. Which requirements does that bear on?"),
    },
    {
        "key": "baselines",
        "kind": "operator_fact",
        "question": (
            "Our change-management procedure mentions baselines. Which standards care about that?"
        ),
    },
    {
        "key": "personnel_leaving",
        "kind": "operator_fact",
        "question": ("What are our obligations around personnel leaving the company?"),
    },
    # ── Cross-cutting ─────────────────────────────────────────────────────
    {
        "key": "most_work",
        "kind": "cross_cutting",
        "question": ("Which of our documents are doing the most compliance work?"),
    },
    {
        "key": "overlap",
        "kind": "cross_cutting",
        "question": ("Where do the standards overlap in what they ask of us?"),
    },
    {
        "key": "ciso_handover",
        "kind": "cross_cutting",
        "question": ("If our CISO role changed hands, what would we need to revisit?"),
    },
    # ── Absence ───────────────────────────────────────────────────────────
    {
        "key": "physical_perimeter",
        "kind": "absence",
        "question": ("What do our documents say about physical security perimeters?"),
    },
    {
        "key": "categorization",
        "kind": "absence",
        "question": ("What's our position on BES Cyber System categorization?"),
    },
    # ── Added (see added_questions in the receipt) ─────────────────────────
    {
        "key": "training_evidence_bridge",
        "kind": "topic",
        "question": (
            "Which of our records would serve as evidence for training "
            "requirements, and what do the standards accept as evidence?"
        ),
    },
    {
        "key": "cip003_revision_change",
        "kind": "cross_cutting",
        "question": (
            "Did the newest CIP-003 revision change what it asks of us compared "
            "with the one it replaced?"
        ),
    },
]


def _citations(answer: str) -> list[str]:
    return sorted({parent_section_id(m.group(0)) for m in _SECTION_TOKEN.finditer(answer)})


def _sentence_around(answer: str, needle: str) -> str:
    position = answer.find(needle)
    if position < 0:
        return ""
    start = max(answer.rfind(".", 0, position), answer.rfind("\n", 0, position)) + 1
    end = answer.find(".", position)
    return answer[start : (end + 1 if end >= 0 else len(answer))].strip()


def _store_linked_to_family(repo, section_id: str, families: set[str]) -> bool:
    """Does ANY recorded edge anchor this operator section into one of the
    families the answer's requirement named? The store's own relationships are
    the arbiter of 'coverage the corpus supports'."""
    rows = repo._conn.execute(
        "SELECT src_ref FROM relationship_assertions WHERE dst_ref = ? AND valid_to IS NULL",
        (section_id,),
    ).fetchall()
    for (src_ref,) in rows:
        family = str(src_ref).split(" ")[0].rsplit("-", 1)[0]
        if family in families:
            return True
    return False


def _judge_absence(repo, answer: str, cited: dict[str, dict]) -> dict:
    """Honest-absence adjudication for one answer. See module docstring."""
    families = {m.group(0).rsplit("-", 1)[0] for m in _REQUIREMENT_ADDRESS.finditer(answer)}
    invented: list[dict] = []
    store_backed: list[str] = []
    for section_id, entry in cited.items():
        if not (entry.get("operator_side") or entry.get("jurisdiction") == "operator_note"):
            continue
        sentence = _sentence_around(answer, section_id)
        relation, reason = classify_assertion(sentence)
        if not relation:
            continue  # negated, contrasted or merely discussed — not a coverage claim
        if _store_linked_to_family(repo, section_id, families):
            store_backed.append(section_id)
        else:
            invented.append(
                {
                    "section_id": section_id,
                    "sentence": sentence,
                    "classification": reason,
                }
            )
    named_requirement = bool(_REQUIREMENT_ADDRESS.search(answer))
    return {
        "named_requirement": named_requirement,
        "invented_coverage": invented,
        "store_backed_coverage": store_backed,
        "invented": bool(invented),
    }


def _sides_of(cited: dict[str, dict]) -> set[str]:
    return {e["side"] for e in cited.values()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", default="compliance-reading")
    ap.add_argument("--out-dir", required=True, type=pathlib.Path)
    ap.add_argument("--timeout", type=float, default=1800.0)
    ap.add_argument("--only", default="", help="comma-separated question keys (resume aid)")
    args = ap.parse_args()

    (args.out_dir / "transcripts").mkdir(parents=True, exist_ok=True)
    try:
        router = router_base_url()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: cannot resolve the router base url: {exc}", file=sys.stderr)
        return 3

    questions = QUESTIONS
    if args.only:
        wanted = {k.strip() for k in args.only.split(",") if k.strip()}
        questions = [q for q in QUESTIONS if q["key"] in wanted]

    store = Repository()
    rows: list[dict] = []
    try:
        with httpx.Client(timeout=httpx.Timeout(args.timeout, connect=10.0)) as session:
            for spec in questions:
                thread = WorkspaceThread(session, args.workspace, router)
                try:
                    record = thread.turn(spec["question"], timeout=args.timeout)
                except Exception as exc:  # noqa: BLE001 - a dead turn is a recorded failure
                    rows.append(
                        {
                            **spec,
                            "verdict": "FAIL",
                            "reason": f"turn raised {type(exc).__name__}: {exc}",
                        }
                    )
                    continue
                (args.out_dir / "transcripts" / f"{spec['key']}.json").write_text(
                    json.dumps(record, indent=2, default=str)
                )
                rows.append(_judge(store, spec, record))
    finally:
        store.close()

    receipt = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "workspace": args.workspace,
        "router": router,
        "n_questions": len(rows),
        "n_passed": sum(1 for r in rows if r.get("verdict") == "PASS"),
        "n_used_search": sum(1 for r in rows if r.get("used_search")),
        "invented_coverage_count": sum(1 for r in rows if (r.get("absence") or {}).get("invented")),
        "added_questions": {
            "training_evidence_bridge": (
                "vocabulary bridge: the operator corpus says 'records'/'training "
                "materials', the standards say 'evidence' — semantic search exists "
                "to survive exactly this gap, and no register-path question ever "
                "exercised it"
            ),
            "cip003_revision_change": (
                "cross-revision: the store holds both CIP-003 revisions by design "
                "(_governing_revisions keeps history answerable); a conversation "
                "about 'what changed' must find material in each — a different kind "
                "of ask than any the twelve cover"
            ),
        },
        "rows": rows,
        "pass_rule": (
            "answered + compliance_search actually called (router counters) + every "
            "citation resolves + (relational questions) both sides cited. Absence "
            "questions: name the requirement and either cite store-linked operator "
            "coverage or name the gap; a positively-asserted operator section with "
            "no recorded edge into the named family is invented coverage (FAIL)."
        ),
        "verdict": "PASS" if all(r.get("verdict") == "PASS" for r in rows) else "FAIL",
    }
    out = args.out_dir / "conversational_proof.json"
    out.write_text(json.dumps(receipt, indent=2, default=str))
    print(f"WROTE {out}")
    print(
        f"{receipt['n_passed']}/{len(rows)} passed | retrieval used in {receipt['n_used_search']}"
    )
    for r in rows:
        print(
            f"  [{r.get('verdict', '?')}] {r['kind']:14s} search={r.get('used_search')} "
            f"{r['question'][:56]}"
        )
    print("invented coverage on absence questions:", receipt["invented_coverage_count"])
    return 0 if receipt["verdict"] == "PASS" else 1


def _judge(store, spec: dict, record: dict) -> dict:
    """Mechanical verdict for one turn, from data the turn itself produced."""
    answer = str(record.get("answer") or "")
    answered = (
        bool(answer.strip())
        and not record.get("turn_budget_exceeded")
        and record.get("http_status") in (200, None)
        and not record.get("error")
    )
    used_search = (record.get("tool_calls") or {}).get("compliance_search", 0) > 0
    ids = _citations(answer)
    resolved = resolve_sections(store, ids)
    cited = {}
    for section_id, entry in resolved.items():
        jur = str(entry.get("jurisdiction") or "")
        cited[section_id] = {
            "jurisdiction": jur,
            "operator_side": jur in ("internal", "operator_note"),
            "document": entry.get("document_title") or entry.get("logical_id"),
        }
        if jur in ("internal", "operator_note"):
            cited[section_id]["side"] = "operator"
        elif jur == "US":
            cited[section_id]["side"] = "regulatory"
        else:
            cited[section_id]["side"] = jur or "unknown"
    unresolved = [i for i in ids if i not in resolved]
    sides = _sides_of(cited)

    checks = {
        "answered": answered,
        "used_search": used_search,
        "all_citations_resolve": not unresolved,
    }
    detail: dict = {}
    if spec["kind"] == "absence":
        absence = _judge_absence(store, answer, cited)
        detail["absence"] = absence
        checks["names_requirement"] = absence["named_requirement"]
        checks["no_invented_coverage"] = not absence["invented"]
    else:
        checks["operator_cited"] = "operator" in sides
        checks["regulatory_cited"] = "regulatory" in sides

    verdict = "PASS" if all(checks.values()) else "FAIL"
    failed = [k for k, v in checks.items() if not v]
    return {
        **spec,
        "verdict": verdict,
        "reason": "all checks passed" if verdict == "PASS" else f"failed: {', '.join(failed)}",
        "answer_chars": len(answer),
        "wall_s": record.get("wall_s"),
        "tool_calls": record.get("tool_calls") or {},
        "used_search": used_search,
        "cited_ids": ids,
        "unresolved_ids": unresolved,
        "sides_cited": sorted(sides),
        "checks": checks,
        **detail,
    }


if __name__ == "__main__":
    sys.exit(main())
