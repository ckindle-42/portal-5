#!/usr/bin/env python3
"""LOAD_AND_CONVERSE_V1 §P4 — the conversation the module was asked for.

Every product question ever asked named a requirement, which exercises the
REGISTER path (``compliance_context``). Nothing exercised the RETRIEVAL path:
finding material by meaning. This harness asks fourteen questions that name no
requirement address at all, on the deployed workspace, and judges each on:

  answered          non-empty answer, HTTP 200, inside the turn budget
  used_search       ``compliance_search`` was ACTUALLY called — read from the
                    router's own tool counters, never assumed
  grounding         per-claim (LOAD_AND_CONVERSE_V1 §P5; CITE_AND_SCOPE_V1 §P1):
                    every claim unit that cites anything cites support that
                    RESOLVES — a double-quoted span matching a store section by
                    containment, or a token that resolves (full id, ``cite_as``
                    token, unique prefix) — or is a mistyped restatement of a
                    resolving citation elsewhere in the same answer. A quote
                    matching several sections grounds with every match recorded
                    (multi-match policy decided on the p1 distribution). A quote
                    matching nothing stays unresolved and fails, exactly as an
                    id does; nothing is ever repaired onto a near neighbour.
  both sides        ≥1 operator AND ≥1 regulatory section cited (the questions
                    are relational by construction)
  honest absence    for ABSENCE questions the rule inverts. Mechanical floor: a
                    positively-asserted operator section must RESOLVE — support
                    that names no real section is invented coverage (FAIL).
                    Whether resolvable coverage is REAL is a reading judgment,
                    not a mechanical one: the store's link graph is sparse by
                    construction, so "no recorded edge" never means "no
                    coverage" (P4 run 1 measured that mistake: the operator's
                    CIP Cyber Security Policy genuinely covers physical
                    security perimeters with no recorded edge anywhere).
                    Absence rows are therefore marked ``absence_judgment:
                    agent``; verdicts land via --overrides with the reading
                    recorded, and both verdicts stay visible.

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

from portal.modules.compliance.core.addressing import resolve_cite_as  # noqa: E402
from portal.modules.compliance.core.answer_contract import (  # noqa: E402
    _CITEAS_TOKEN,
    SECTION_ID_PATTERN,
    _mistyped_variant_of,
)
from portal.modules.compliance.core.candidate_links import classify_assertion  # noqa: E402
from portal.modules.compliance.core.citation_by_quote import (  # noqa: E402
    quoted_spans,
    resolve_quote,
)
from portal.modules.compliance.core.repository import Repository  # noqa: E402
from portal.modules.compliance.core.section_index import parent_section_id  # noqa: E402

_SECTION_TOKEN = re.compile(rf"\b{SECTION_ID_PATTERN}\b", re.I)
_REQUIREMENT_ADDRESS = re.compile(r"\bCIP-\d{3}-[A-Za-z0-9.]+(\s+R\d+)?\b")

#: obligation language — a line saying what the standard DEMANDS. The
#: normative-basis check (MODULE_COMPLETE_V1 §P0.5) applies only to these:
#: guidance text (technical basis / rationale) may be quoted freely as long as
#: it is not doing the work of a requirement.
_OBLIGATION_LANGUAGE = re.compile(
    r"\b(requires?|required|requirement|must|shall|obligat\w+|mandat\w+)\b", re.I
)

#: obligation attributed to the NORMATIVE voice — the standard, a requirement,
#: a Part, the regulation. This is the only conflation the two-layers rule
#: forbids: a line that honestly attributes a demand to guidance ("the
#: technical rationale states …") or to the operator ("our procedure mandates …")
#: is labelled truth-telling, not a violation.
_STANDARD_ATTRIBUTION = re.compile(
    r"(the\s+(?:standard|requirement|requirements|regulation|regulations|rule|clause|part)\b[^.]{0,60}?"
    r"\b(requires?|required|mandat\w+|obligat\w+|demands?|states?|says))"
    r"|((?:CIP-\d{3}(?:-[A-Za-z0-9.]+)?(?:\s+R\d[\w.]*)?)\s+(?:requires?|mandat\w+|obligat\w+|demands?))"
    r"|(the\s+standard\s+(?:is\s+that|is\s+clear))",
    re.I,
)

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


def _resolve_token(store: Repository, raw: str) -> dict | None:
    """Full id → ``cite_as`` token → unique prefix. Ambiguous or absent
    resolves to None — never a guess, never a near neighbour."""
    parent = parent_section_id(raw)
    full = raw.split("#")[0].lower()
    resolved = parent_section_id(full)
    from portal.modules.compliance.core.section_index import resolve_sections

    got = resolve_sections(store, [resolved])
    if got:
        return got.get(resolved)
    if _CITEAS_TOKEN.fullmatch(raw) is not None:
        # by the rule that minted it — side letter, not id prefix
        return resolve_cite_as(store, raw)
    # "csection-<hex>" / "isection-<hex>" — plain split; the section-id shape is
    # decided in answer_contract alone, so this module compiles no second regex
    stem, _, hex_prefix = full.partition("-")
    if stem.lower() in ("csection", "isection") and len(hex_prefix) >= 6 and hex_prefix.isalnum():
        rows = store._conn.execute(
            "SELECT section_id FROM source_sections WHERE section_id LIKE ?",
            (f"{stem.lower()}-{hex_prefix.lower()}%",),
        ).fetchall()
        if len(rows) == 1:
            got = resolve_sections(store, [str(rows[0][0])])
            return got.get(str(rows[0][0]))
    return None


def _sentence_around(answer: str, needle: str) -> str:
    position = answer.find(needle)
    if position < 0:
        return ""
    start = max(answer.rfind(".", 0, position), answer.rfind("\n", 0, position)) + 1
    end = answer.find(".", position)
    return answer[start : (end + 1 if end >= 0 else len(answer))].strip()


def _grounding(store: Repository, answer: str) -> dict:
    """Per-claim grounding against the STORE (the conversational answers have
    no render contract in scope — the store is what the tools read from).

    The citation is the QUOTE (CITE_AND_SCOPE_V1 §P1): a line's double-quoted
    spans are resolved by containment over the whole store
    (``citation_by_quote.resolve_quote`` — the verbatim check inverted), and
    any identifier the answer also carries resolves as before (full id,
    ``cite_as`` token, unique prefix). A line is grounded when at least one of
    its quotes or tokens resolves, or its only unresolved tokens are mistyped
    restatements of ids that resolved elsewhere in the same answer. A quote
    matching several sections grounds with EVERY match recorded — the words
    demonstrably exist in the store; the multi-match policy was decided on the
    measured distribution in p1/quote_resolution.json (27% multi-match, tail
    to 88, all repeated boilerplate — a floor would not fix it). Everything
    unresolved is reported as written, never repaired: an unresolvable quote
    stays unresolvable exactly as an unresolvable id does, and a claim
    supported by nothing still fails."""
    resolving_raw: list[str] = []
    lines: list[dict] = []
    for raw_line in answer.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        tokens_here = [m.group(0) for m in _SECTION_TOKEN.finditer(stripped)]
        tokens_here += [m.group(0) for m in _CITEAS_TOKEN.finditer(stripped)]
        quotes_here = quoted_spans(stripped)
        if not tokens_here and not quotes_here:
            continue
        resolved_here, unresolved_here = [], []
        section_ids_here: list[str] = []
        quoted_resolved: list[dict] = []
        quoted_unresolved: list[str] = []
        for token in tokens_here:
            entry = _resolve_token(store, token)
            if entry is not None:
                resolved_here.append(token)
                resolving_raw.append(token)
                section_ids_here.append(str(entry["section_id"]))
            else:
                unresolved_here.append(token)
        for quote in quotes_here:
            hits = resolve_quote(store, quote)
            if hits:
                quoted_resolved.append({"quote": quote, "sections": hits})
                section_ids_here.extend(hits)
            else:
                quoted_unresolved.append(quote)
        lines.append(
            {
                "claim": stripped,
                "resolved": sorted(dict.fromkeys(resolved_here)),
                "unresolved": sorted(dict.fromkeys(unresolved_here)),
                "quoted": quoted_resolved,
                "quoted_unresolved": quoted_unresolved,
                "section_ids": sorted(dict.fromkeys(section_ids_here)),
            }
        )
    for line in lines:
        line["grounded"] = bool(line["section_ids"]) or any(
            _mistyped_variant_of(raw, resolving_raw) for raw in line["unresolved"]
        )
    unsupported = [line for line in lines if not line["grounded"]]
    return {
        "claims": lines,
        "n_claims": len(lines),
        "n_ungrounded": len(unsupported),
        "unsupported_lines": [c["claim"] for c in unsupported],
        "n_quotes_resolved": sum(len(c["quoted"]) for c in lines),
        "n_quotes_unresolved": sum(len(c["quoted_unresolved"]) for c in lines),
        "grounded": bool(lines) and not unsupported,
    }


def normative_basis(store: Repository, section_ids: list[str]) -> dict[str, bool]:
    """Which cited sections can carry a NORMATIVE claim at all (MODULE_COMPLETE_V1
    §P0.5): a section joined to a requirement by anything other than
    ``technical_basis`` — the GTB/rationale anchors mark intent, not obligation.
    A section with no join either way (e.g. an operator section) is reported
    ``False`` here; operator sections answer for operator side, never for what
    the standard requires."""
    if not section_ids:
        return {}
    marks = {
        str(r[0]): str(r[1])
        for r in store._conn.execute(
            f"""SELECT section_id, GROUP_CONCAT(DISTINCT relation) FROM requirement_sections
                 WHERE section_id IN ({",".join("?" * len(section_ids))})
                GROUP BY section_id""",  # noqa: S608
            section_ids,
        ).fetchall()
    }
    return {
        sid: bool(relations) and any(r.strip() != "technical_basis" for r in relations.split(","))
        for sid, relations in marks.items()
    }


def obligation_normative_check(store: Repository, grounding: dict) -> dict:
    """A line attributing obligation to the STANDARD must stand on normative text.

    Mechanical and one-directional: for every citing line that attributes a
    demand to the standard/requirement (not merely containing obligation
    words — honest attributions to guidance or to the operator's own
    documents are truth-telling and exempt), at least one cited section must
    be normative-capable. A line saying ``the standard requires`` whose
    citations join only as technical_basis — or that cites only operator
    sections — conflates guidance or practice with obligation and FAILS. The
    strictening can only turn a pass into a fail, never the reverse, so it
    cannot be tuned to pass."""
    normative = normative_basis(
        store, sorted({sid for c in grounding["claims"] for sid in c["section_ids"]})
    )
    violations: list[dict] = []
    checked = 0
    for claim in grounding["claims"]:
        if not claim["section_ids"] or not _STANDARD_ATTRIBUTION.search(claim["claim"]):
            continue
        checked += 1
        if not any(normative.get(sid) for sid in claim["section_ids"]):
            violations.append(
                {
                    "claim": claim["claim"],
                    "cited": claim["section_ids"],
                    "why": (
                        "obligation attributed to the standard, but every cited section "
                        "joins only as technical_basis (guidance) or carries no normative "
                        "join at all"
                    ),
                }
            )
    return {
        "checked_lines": checked,
        "violations": violations,
        "ok": not violations,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", default="compliance-reading")
    ap.add_argument("--out-dir", required=True, type=pathlib.Path)
    ap.add_argument("--timeout", type=float, default=1800.0)
    ap.add_argument("--only", default="", help="comma-separated question keys (resume aid)")
    ap.add_argument(
        "--overrides",
        type=pathlib.Path,
        default=None,
        help="JSON {key: {verdict, reading}} — the agent's absence-question "
        "judgments, folded into the final verdicts and recorded verbatim",
    )
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

    overrides: dict = {}
    if args.overrides and args.overrides.is_file():
        overrides = json.loads(args.overrides.read_text())
    for row in rows:
        override = overrides.get(row.get("key", ""))
        if override:
            row["mechanical_verdict"] = row["verdict"]
            row["verdict"] = override["verdict"]
            row["agent_reading"] = override["reading"]

    receipt = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "workspace": args.workspace,
        "router": router,
        "n_questions": len(rows),
        "n_passed": sum(1 for r in rows if r.get("verdict") == "PASS"),
        "n_used_search": sum(1 for r in rows if r.get("used_search")),
        "n_agent_judged": sum(1 for r in rows if r.get("agent_reading")),
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
            "answered + compliance_search actually called (router counters) + "
            "per-claim grounding (a quoted span that matches a store section by "
            "containment, or a resolving token: full id, cite_as token, unique "
            "prefix; multi-match quotes ground with all matches recorded; "
            "mistyped restatements of resolving citations absorbed; nothing "
            "repaired — an unmatched quote or id fails as written) + "
            "(relational questions) both sides cited. Absence questions: "
            "positively-asserted operator coverage must RESOLVE, by quote or by "
            "id (mechanical); whether resolvable coverage is real is the "
            "agent's reading, folded via --overrides and recorded on the row."
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


def _judge(store: Repository, spec: dict, record: dict) -> dict:
    """Mechanical verdict for one turn, from data the turn itself produced."""
    answer = str(record.get("answer") or "")
    answered = (
        bool(answer.strip())
        and not record.get("turn_budget_exceeded")
        and record.get("http_status") in (200, None)
        and not record.get("error")
    )
    used_search = (record.get("tool_calls") or {}).get("compliance_search", 0) > 0
    grounding = _grounding(store, answer)

    # every section a resolving token OR a resolving quote names, one lookup:
    # quotes arrive as section ids already, tokens resolve through
    # _resolve_token
    from portal.modules.compliance.core.section_index import resolve_sections

    cited_ids = {sid for c in grounding["claims"] for sid in c["section_ids"]}
    token_ids = {
        str(entry["section_id"])
        for c in grounding["claims"]
        for token in c["resolved"]
        if (entry := _resolve_token(store, token)) is not None
    }
    resolved_entries = resolve_sections(store, sorted(cited_ids | token_ids))
    obligation = obligation_normative_check(store, grounding)
    cited: dict[str, dict] = {}
    for sid, entry in resolved_entries.items():
        jur = str(entry.get("jurisdiction") or "")
        cited[sid] = {
            "jurisdiction": jur,
            "operator_side": jur in ("internal", "operator_note"),
            "document": entry.get("document_title") or entry.get("logical_id"),
            "side": (
                "operator"
                if jur in ("internal", "operator_note")
                else ("regulatory" if jur == "US" else (jur or "unknown"))
            ),
        }
    sides = {e["side"] for e in cited.values()}
    unresolved_tokens = sorted({t for c in grounding["claims"] for t in c["unresolved"]})

    checks = {
        "answered": answered,
        "used_search": used_search,
        "grounding_per_claim": grounding["grounded"],
        "obligation_on_normative": obligation["ok"],
    }
    detail: dict = {}
    detail["obligation_normative"] = obligation
    if spec["kind"] == "absence":
        absence = _judge_absence(store, answer, cited, grounding)
        detail["absence"] = absence
        checks["no_invented_coverage"] = not absence["invented"]
        detail["absence_judgment"] = "agent"
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
        "cited_ids": sorted(cited),
        "unresolved_ids": unresolved_tokens,
        "n_quotes_resolved": grounding["n_quotes_resolved"],
        "n_quotes_unresolved": grounding["n_quotes_unresolved"],
        "sides_cited": sorted(sides),
        "grounding": {
            "n_claims": grounding["n_claims"],
            "n_ungrounded": grounding["n_ungrounded"],
            "unsupported_lines": grounding["unsupported_lines"],
        },
        "checks": checks,
        **detail,
    }


def _judge_absence(store: Repository, answer: str, cited: dict[str, dict], grounding: dict) -> dict:
    """Honest-absence floor for one answer.

    MECHANICAL: a citing sentence that POSITIVELY asserts operator coverage
    (``classify_assertion``) must rest on a section that RESOLVES — support
    naming no real section is invented coverage, and in the quote contract
    that includes a quotation that matches no section in the store: the words
    it offers as support demonstrably do not exist there. Negated, contrasted
    or merely discussed sections are not coverage claims.
    READING (agent, via --overrides): whether resolvable operator material
    really covers what the sentence claims — the link graph is never the
    arbiter, because it is sparse by construction.
    """
    invented: list[dict] = []
    grounded_support: list[str] = []
    for claim in grounding["claims"]:
        for token in claim["unresolved"]:
            sentence = _sentence_around(answer, token)
            relation, reason = classify_assertion(sentence)
            if not relation:
                continue
            invented.append(
                {
                    "section_id": token,
                    "sentence": sentence,
                    "classification": reason,
                    "why": "a coverage claim whose cited section resolves to nothing",
                }
            )
        for quote in claim.get("quoted_unresolved", []):
            sentence = _sentence_around(answer, quote)
            relation, reason = classify_assertion(sentence)
            if not relation:
                continue
            invented.append(
                {
                    "section_id": f'"{quote[:80]}"',
                    "sentence": sentence,
                    "classification": reason,
                    "why": "a coverage claim whose quoted support matches no section in the store",
                }
            )
    for section_id, entry in cited.items():
        if not entry.get("operator_side"):
            continue
        sentence = _sentence_around(answer, section_id)
        relation, _reason = classify_assertion(sentence)
        if relation:
            grounded_support.append(section_id)
    named_requirement = bool(_REQUIREMENT_ADDRESS.search(answer))
    return {
        "named_requirement": named_requirement,
        "named_standard_or_requirement": bool(re.search(r"\bCIP-\d{3}-[A-Za-z0-9.]+", answer)),
        "invented_coverage": invented,
        "grounded_support": grounded_support,
        "invented": bool(invented),
    }


if __name__ == "__main__":
    sys.exit(main())
