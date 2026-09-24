#!/usr/bin/env python3
"""MODULE_COMPLETE_V1 §P2 — hold a conversation: multi-turn sessions on one thread.

Four campaigns of product proofs opened a fresh thread per question; every
"conversation" the module ever had was one turn. This harness runs SESSIONS —
3 sessions of 5 turns, all turns of ONE ``WorkspaceThread`` each, following a
real analyst's path:

  turn 1  an opening question that requires retrieval;
  turn 2  a follow-up that REFERS to something in the first answer without
          naming it ("that one", "the second one");
  turn 3  a NARROWING of one item from turn 1, in detail;
  turn 4  a CROSSING to a different standard, or a procedure-review turn that
          needs the technical basis ("the intent of R2, not just its words");
  turn 5  a CHALLENGE — "are you sure?" — which tests whether the seat
          defends a correct answer and concedes a wrong one.

Judged per turn, mechanically where possible:

  grounding   per-claim, through ``ask_conversational._grounding`` — the ONE
              grounding rule (CITE_AND_SCOPE_V1: quotes resolved by containment
              against the store, tokens by ``resolve_cite_as``). Late-turn
              policy, decided explicitly (see GROUNDING_DECISION): the audit
              rule is store-grounding EVERY turn — an answer may refer to the
              conversation in prose, but every factual claim must carry a quote
              or token that resolves in the corpus. The mechanical check is
              exactly that, so a turn citing the model's own earlier prose
              (words that exist nowhere in the store) FAILS here.
  window      prompt tokens per turn from the router's own usage chunks; growth
              across turns is the prefix-cache measurement (later turns should
              not cost more than the first), and the turn that crosses the
              window is where the session limit bites — recorded as a product
              property, never hidden.

    uv run python scripts/compliance/session_proof.py \\
        --out-dir reports/compliance/module_complete/p2
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import httpx  # noqa: E402
from ask_conversational import _grounding  # noqa: E402
from compliance_acceptance import WorkspaceThread, router_base_url  # noqa: E402

from portal.modules.compliance.core.repository import Repository  # noqa: E402

GROUNDING_DECISION = (
    "AUDIT RULE, decided explicitly: grounding is per-claim against the STORE on every "
    "turn, including turns five of a session. A human reader accepts 'as I said above' as "
    "grounded in the conversation; an audit cannot, because the conversation itself is the "
    "model's own prose — an error repeated across turns never gets caught. So: an answer "
    "may REFER to earlier turns in prose, but every factual claim must carry a citation "
    "that resolves in the corpus (a quote matching a stored section by containment, or a "
    "resolving token). This is not a new rule — it is ask_conversational._grounding, the "
    "one grounding rule, applied to late turns for the first time."
)

SESSIONS: list[dict[str, object]] = [
    {
        "key": "patching",
        "path": (
            "the analyst's real walk: what does our patching practice sit against the "
            "standard, what governs the exception case, what does it demand, does it meet "
            "the INTENT of the requirement, and can the seat defend a correct figure"
        ),
        "turns": [
            (
                "retrieve",
                "Where does our patching practice sit against what the standards require?",
            ),
            (
                "referential",
                (
                    "Of the documents you just named, which one governs emergency or "
                    "out-of-cycle patches?"
                ),
            ),
            (
                "narrow",
                (
                    "Show me exactly what that document requires for the regular patch cycle — "
                    "quote the requirement itself."
                ),
            ),
            (
                "intent",
                (
                    "Does our patch procedure meet the intent of CIP-007-6 R2, not just its "
                    "literal words? Use the standard's technical basis if it helps."
                ),
            ),
            (
                "challenge",
                (
                    "Are you sure? I believe our procedure's patch cycle is stricter than what "
                    "the standard itself requires. Check your own citations again."
                ),
            ),
        ],
    },
    {
        "key": "accounts",
        "path": (
            "accounts and access: shared accounts, where our documents say so, the evidence "
            "an auditor would want, a crossing to CIP-005, and a challenge where the seat "
            "must either defend a true claim or concede a false one"
        ),
        "turns": [
            (
                "retrieve",
                "What do we say about shared accounts, and what does CIP-007-6 require about them?",
            ),
            (
                "referential",
                (
                    "That second item of yours — where exactly in our own documents is that "
                    "stated? Name the section."
                ),
            ),
            (
                "narrow",
                (
                    "What would an auditor need to see as EVIDENCE that we operate it that way — "
                    "quote what our records or procedures commit to."
                ),
            ),
            (
                "cross",
                (
                    "How does that account requirement relate to CIP-005's Electronic Security "
                    "Perimeters, if at all? Do the two standards connect here?"
                ),
            ),
            (
                "challenge",
                (
                    "I think you're wrong that our own documents cover shared accounts — I don't "
                    "believe any of our procedures mention them. Go back and check before you "
                    "insist."
                ),
            ),
        ],
    },
    {
        "key": "personnel",
        "path": (
            "departures and training: what happens when CIP access-holders leave, which "
            "standard/part that came from, whether our own documents say it, whether training "
            "meets the INTENT of CIP-004-7 R1, and a challenge on a specific figure"
        ),
        "turns": [
            (
                "retrieve",
                "What are our obligations when personnel with CIP access leave the company?",
            ),
            (
                "referential",
                (
                    "The last obligation you listed — which standard, requirement and part is "
                    "that from?"
                ),
            ),
            (
                "narrow",
                (
                    "Do our own documents actually commit to that — quote the section that says "
                    "so, or tell me plainly that none does."
                ),
            ),
            (
                "intent",
                (
                    "Does our training procedure meet the intent of CIP-004-7 R1, not just its "
                    "literal words? Use the standard's technical basis if it helps."
                ),
            ),
            (
                "challenge",
                (
                    "Are you sure about the timeframe you gave earlier for revoking a departed "
                    "person's access? Re-check your citations and tell me plainly if you "
                    "misstated it."
                ),
            ),
        ],
    },
]


def main() -> int:  # noqa: PLR0915
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", default="compliance-reading")
    ap.add_argument("--out-dir", required=True, type=pathlib.Path)
    ap.add_argument("--timeout", type=float, default=1800.0)
    ap.add_argument("--only", default="", help="comma-separated session keys (resume aid)")
    args = ap.parse_args()

    tdir = args.out_dir / "transcripts"
    tdir.mkdir(parents=True, exist_ok=True)
    try:
        router = router_base_url()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: cannot resolve the router base url: {exc}", file=sys.stderr)
        return 3

    sessions = SESSIONS
    if args.only:
        wanted = {k.strip() for k in args.only.split(",") if k.strip()}
        sessions = [s for s in SESSIONS if s["key"] in wanted]  # type: ignore[union-attr]

    store = Repository()
    session_rows: list[dict] = []
    try:
        with httpx.Client(timeout=httpx.Timeout(args.timeout, connect=10.0)) as http:
            for spec in sessions:
                thread = WorkspaceThread(http, args.workspace, router)
                turns: list[dict] = []
                for i, (shape, question) in enumerate(spec["turns"], start=1):  # type: ignore[union-attr]
                    try:
                        record = thread.turn(question, timeout=args.timeout)
                    except Exception as exc:  # noqa: BLE001 - a dead turn is a recorded failure
                        turns.append(
                            {
                                "n": i,
                                "shape": shape,
                                "question": question,
                                "verdict": "FAIL",
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        )
                        continue
                    (tdir / f"{spec['key']}_turn{i}.json").write_text(  # type: ignore[union-attr]
                        json.dumps(
                            {
                                "session": spec["key"],
                                "turn": i,
                                "shape": shape,
                                "question": question,
                                **record,
                            },
                            indent=2,
                            default=str,
                        )
                    )
                    answer = str(record.get("answer") or "")
                    grounding = _grounding(store, answer)
                    row = {
                        "n": i,
                        "shape": shape,
                        "question": question,
                        "answer_chars": len(answer),
                        "wall_s": record.get("wall_s"),
                        "prompt_tokens_high_water": record.get("prompt_tokens_high_water"),
                        "prompt_tokens_final_hop": record.get("prompt_tokens_final_hop"),
                        "tool_calls": record.get("tool_calls") or {},
                        "served_model": record.get("served_model"),
                        "finish_reason": record.get("finish_reason"),
                        "error": record.get("error"),
                        "grounding": {
                            "grounded": grounding["grounded"],
                            "n_claims": grounding["n_claims"],
                            "n_ungrounded": grounding["n_ungrounded"],
                            "unsupported_lines": grounding["unsupported_lines"][:5],
                            "n_quotes_resolved": grounding["n_quotes_resolved"],
                            "n_quotes_unresolved": grounding["n_quotes_unresolved"],
                        },
                        "verdict": "PASS"
                        if (
                            answer.strip()
                            and not record.get("turn_budget_exceeded")
                            and record.get("http_status") in (200, None)
                            and not record.get("error")
                            and grounding["grounded"]
                        )
                        else "FAIL",
                    }
                    if not answer.strip():
                        row["reason"] = "empty answer"
                    elif grounding["grounded"] is False:
                        row["reason"] = "ungrounded claims"
                    elif record.get("error"):
                        row["reason"] = str(record["error"])
                    turns.append(row)
                    print(
                        f"[{spec['key']}] turn {i} ({shape}): {row['verdict']} "
                        f"wall={row['wall_s']}s prompt_tok={row['prompt_tokens_final_hop']} "
                        f"grounded={row['grounding']['grounded']}"
                    )
                session_rows.append(
                    {
                        "session": spec["key"],
                        "path": spec["path"],
                        "n_turns": len(turns),
                        "n_pass": sum(1 for t in turns if t.get("verdict") == "PASS"),
                        "turns": turns,
                        # the prefix-cache shape: tokens should not grow superlinearly,
                        # and turn walls should stay near the first once the prefix holds
                        "token_growth": [t.get("prompt_tokens_final_hop") for t in turns],
                        "walls": [t.get("wall_s") for t in turns],
                    }
                )
    finally:
        store.close()

    all_turns = [t for s in session_rows for t in s["turns"]]
    receipt = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "workspace": args.workspace,
        "router": router,
        "grounding_decision": GROUNDING_DECISION,
        "n_sessions": len(session_rows),
        "n_turns": len(all_turns),
        "n_pass": sum(1 for t in all_turns if t.get("verdict") == "PASS"),
        "sessions": session_rows,
        "pass_rule": (
            "a session holds when every turn answers non-empty, inside budget, and every "
            "citing claim is grounded against the STORE by the one grounding rule "
            "(_grounding). Referential resolution, challenge behaviour and intent-review "
            "quality are READING judgments on the transcripts, recorded in the report — "
            "mechanically decidable checks are kept separate from them."
        ),
        "verdict": "PASS" if all(t.get("verdict") == "PASS" for t in all_turns) else "FAIL",
    }
    out = args.out_dir / "session_proof.json"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, default=str))
    print(
        f"WROTE {out}: {receipt['n_pass']}/{receipt['n_turns']} turns pass "
        f"across {len(session_rows)} sessions"
    )
    return 0 if receipt["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
