#!/usr/bin/env python3
"""Supervise a campaign in flight and exit the moment it needs a human.

Three things already watch a sweep: the harness halts one arm whose task kind has gone bad
(`run_arm.py`, ~4 rows), `campaign.py --health` gives one verdict on the instrument (Ollama,
disk, instrument failures, stall), and the orchestrator reads rows on a 30-minute tick. The
gap between them is what costs hours: an auto-halt stops *one arm* and `wfe_campaign.sh`
moves straight to the next, so a whole sweep can halt arm by arm and still reach its end
before anyone reads `arm_exits.log`.

This closes that gap without burning anything while the run is healthy. It polls every
`--interval` seconds and exits non-zero on the first HALT, the first non-OK health verdict,
or a cross-arm tripwire (pass rate, zero-tool-call rows). Run it as a background job: its
exit is the signal to come and look.

    uv run python scripts/wfe_supervise.py wfe_documents_20261017f &
    uv run python scripts/wfe_supervise.py wfe_documents_20261017f --once   # one tick
    uv run python scripts/wfe_supervise.py wfe_documents_20261017f --sample 5
    uv run python scripts/wfe_supervise.py wfe_documents_20261017f --sample 5 --json

The 30-minute tick is `tail -5 <campaign dir>/supervisor.log` plus `--sample 5`: the automatic
checks cover the failures we have already had, and reading five answers covers the one we
haven't. A run whose rows land, pass their checkers and say the wrong thing is healthy by
every exit code in this file.

Exit codes:  0 campaign DONE   2 needs attention (the reason is printed)   3 supervisor error
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tests.wfe.campaign import CAMPAIGNS, health  # noqa: E402
from tests.wfe.schema import INSTRUMENT_OUTCOMES, Outcome  # noqa: E402

#: Rows of one (arm, suite) before its pass rate is allowed to mean anything. The harness
#: halts a bad *task kind* at 4; this is the cross-kind view, so it needs more evidence.
MIN_ROWS_FOR_RATE = 12
#: A cell at or below this is not a model being weak — it is the instrument, a prompt or a
#: delivery defect. Every near-zero cell this program has seen turned out to be one of those.
BAD_PASS_RATE = 0.1
#: Tool-call-less rows in a cell whose suite expects tools. Uniform zero means delivery.
BAD_NO_TOOL_RATE = 0.9
#: Rows in a cell carrying a spoiled answer before the cell's evidence is called void. A
#: campaign that runs to the end on garbled answers is the expensive failure: healthy by every
#: exit code, unusable as evidence.
BAD_SMELL_RATE = 0.25
#: Distinct tasks in one arm answered with the identical text before the seat is called stuck.
STUCK_ANSWER_TASKS = 3
#: Zero-width characters: the tool-name garbling defect writes them into the answer.
ZERO_WIDTH = "​‌‍﻿"


def load_rows(campaign_dir: Path, cache: dict) -> dict:
    """Row files by name, read once each — a finished sweep is hundreds of files."""
    for f in (campaign_dir / "rows").glob("*.json"):
        if f.name in cache:
            continue
        try:
            r = json.loads(f.read_text())
        except Exception:  # a row being written right now; next tick picks it up
            continue
        text = r.get("final_text") or r.get("final_text_head") or ""
        cache[f.name] = {
            "arm": r.get("arm", "?"),
            "suite": r.get("suite", "?"),
            "task_id": r.get("task_id", "?"),
            "outcome": r.get("outcome"),
            "tool_calls": r.get("tool_calls", 0),
            "tool_surface": _offered_tools(r),
            "notes": (r.get("notes") or "")[:160],
            "text": text[:600],
        }
    return cache


def _offered_tools(r: dict) -> bool:
    """Whether the seat was offered any tool. A pipeline row's eval scope is the truth (an empty
    allowlist means none, as on a no_tools task); `tool_surface` is only the client-side default
    and is recorded even then (wfe_math_20261018b: a false "15/15 rows called no tool")."""
    scope = (r.get("evidence") or {}).get("eval_scope")
    if isinstance(scope, dict):
        return bool(scope.get("allow"))
    return bool(r.get("tool_surface"))


def answer_smells(row: dict) -> list[str]:
    """Defects that leave a row *looking* fine. Each one has voided a campaign here.

    This is the check no exit code makes: the sweep is healthy, the rows are landing, the
    checker is passing them, and the answers are not usable as evidence."""
    text, out = row["text"], []
    if any(c in text for c in ZERO_WIDTH):
        out.append("zero-width characters in the answer (tool-name garbling)")
    if "<tool_call>" in text or "</tool_call>" in text:
        out.append("raw <tool_call> markup left in the answer")
    if "read" in row["task_id"] and "Download:" in text:
        out.append("a download link in the answer to a read task (link bleed)")
    if row["outcome"] == Outcome.PASS.value and len(text.strip()) < 20 and not _is_json(text):
        out.append(f"PASS on {len(text.strip())} characters of answer — check the checker")
    return out


def _is_json(text: str) -> bool:
    """A terse JSON object is what an "Answer only as JSON" task asks for, not a spoiled row
    (campaign wfe_documents_20261017h: `{"answer": "Ilse Mott"}` voided a clean cell)."""
    try:
        return isinstance(json.loads(text.strip()), dict)
    except ValueError:
        return False


def cell_problems(rows: dict) -> list[str]:
    """Cross-arm tripwires: what a per-arm halt and an instrument health check both miss."""
    cells: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows.values():
        cells[(r["arm"], r["suite"])].append(r)

    out = []
    for (arm, suite), rs in sorted(cells.items()):
        graded = [r for r in rs if r["outcome"] not in {o.value for o in INSTRUMENT_OUTCOMES}]
        if len(graded) < MIN_ROWS_FOR_RATE:
            continue
        passed = sum(1 for r in graded if r["outcome"] == Outcome.PASS.value)
        rate = passed / len(graded)
        if rate <= BAD_PASS_RATE:
            out.append(f"{arm} / {suite}: {passed}/{len(graded)} PASS — instrument suspect first")
        with_tools = [r for r in graded if r["tool_surface"]]
        if with_tools:
            silent = sum(1 for r in with_tools if not r["tool_calls"])
            if silent / len(with_tools) >= BAD_NO_TOOL_RATE:
                out.append(
                    f"{arm} / {suite}: {silent}/{len(with_tools)} rows called no tool — "
                    "check delivery (tools_offered, prompt-token delta, dropped call text)"
                )
        spoiled = [(r, s) for r in graded for s in [answer_smells(r)] if s]
        if len(spoiled) / len(graded) >= BAD_SMELL_RATE:
            reasons = sorted({s for _, ss in spoiled for s in ss})
            out.append(
                f"{arm} / {suite}: {len(spoiled)}/{len(graded)} rows have spoiled answers "
                f"({'; '.join(reasons)}) — the cell runs clean but its evidence is void"
            )
        out += stuck_answers(arm, graded)
    return out


def stuck_answers(arm: str, rows: list[dict]) -> list[str]:
    """One answer repeated across different tasks: the seat stopped reading the task.
    A graded PASS is not stuck: several tasks can share one correct answer (the
    research suite's absent-fact tasks all expect NOT_FOUND)."""
    by_text: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r.get("outcome") == "PASS":
            continue
        if len(r["text"].strip()) >= 20:
            by_text[r["text"]].add(r["task_id"])
    out = []
    for text, tasks in by_text.items():
        if len(tasks) >= STUCK_ANSWER_TASKS:
            out.append(
                f"{arm}: {len(tasks)} different tasks answered with the identical text "
                f"({text.strip()[:60]!r}…) — the seat is stuck, not answering"
            )
    return out


def new_halts(campaign_dir: Path, seen: int) -> tuple[list[str], int]:
    """Lines appended to arm_exits.log since the last tick."""
    log = campaign_dir / "arm_exits.log"
    if not log.exists():
        return [], seen
    lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
    return lines[seen:], len(lines)


def sample_items(campaign_dir: Path, n: int) -> list[tuple[dict, str]]:
    """The newest n rows as (row, answer head) pairs — the sample's shared data."""
    files = sorted((campaign_dir / "rows").glob("*.json"), key=lambda f: f.stat().st_mtime)
    rows = load_rows(campaign_dir, {})
    out: list[tuple[dict, str]] = []
    for f in files[-n:]:
        r = rows.get(f.name)
        if not r:
            continue
        out.append((r, " ".join(r["text"].split())[:220]))
    return out


def sample(campaign_dir: Path, n: int) -> str:
    """The 30-minute read: the newest rows as they actually came out.

    Automatic checks catch the shapes we already know. This is for the shape we don't: read
    the answers and ask whether you would accept the row as evidence."""
    out = []
    for r, head in sample_items(campaign_dir, n):
        out.append(
            f"{r['outcome']:<9} {r['arm']}  {r['task_id']}  tool_calls={r['tool_calls']}\n"
            f"  notes  {r['notes'] or '—'}\n"
            f"  answer {head or '(empty)'}"
        )
        out += [f"  !      {s}" for s in answer_smells(r)]
    return "\n".join(out) or "no rows yet"


def sample_json(campaign_dir: Path, n: int) -> list[dict]:
    """The same newest rows as a machine-readable list: one element per row, same values
    the text sample shows."""
    return [
        {
            "outcome": r["outcome"],
            "model": r["arm"],
            "task_id": r["task_id"],
            "tool_calls": r["tool_calls"],
            "notes": r["notes"] or "—",
            "answer": head or "(empty)",
        }
        for r, head in sample_items(campaign_dir, n)
    ]


def tick(campaign_dir: Path, state: dict, rows: dict) -> tuple[str, list[str], str]:
    """One poll. Returns (verdict, problems, one-line digest)."""
    h = health(campaign_dir)
    halts, state["halts_seen"] = new_halts(campaign_dir, state.get("halts_seen", 0))
    rows = load_rows(campaign_dir, rows)
    problems = [f"HALT {ln}" for ln in halts] + list(h["problems"]) + cell_problems(rows)

    outcomes = Counter(r["outcome"] for r in rows.values())
    healthy = "DONE" if h["verdict"] == "DONE" else "OK"
    verdict = "ATTENTION" if problems else healthy
    digest = (
        f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {verdict} {h['done']}/{h['total']} rows  "
        + "  ".join(f"{k}={v}" for k, v in sorted(outcomes.items()) if k)
        + (f"  !{len(problems)}" if problems else "")
    )
    return verdict, problems, digest


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("campaign_id", help="campaign id, or a path to the campaign dir")
    ap.add_argument("--interval", type=int, default=300, help="seconds between polls (default 300)")
    ap.add_argument("--once", action="store_true", help="one tick, then exit on its verdict")
    ap.add_argument(
        "--sample",
        type=int,
        metavar="N",
        help="print the newest N rows (answers, notes, smells) and exit — the 30-minute read",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="with --sample N: print the rows as one JSON array instead of text",
    )
    args = ap.parse_args()

    campaign_dir = Path(args.campaign_id)
    if not campaign_dir.is_dir():
        campaign_dir = CAMPAIGNS / args.campaign_id
    if not (campaign_dir / "manifest.json").exists():
        print(f"no manifest under {campaign_dir}", file=sys.stderr)
        return 3

    if args.sample:
        if args.json:
            print(json.dumps(sample_json(campaign_dir, args.sample), indent=2, ensure_ascii=False))
        else:
            print(sample(campaign_dir, args.sample))
        return 0

    state_f = campaign_dir / "supervisor_state.json"
    state = {}
    try:
        state = json.loads(state_f.read_text())
    except Exception:
        pass
    log = campaign_dir / "supervisor.log"
    rows: dict = {}

    while True:
        verdict, problems, digest = tick(campaign_dir, state, rows)
        print(digest, flush=True)
        with log.open("a") as fh:
            fh.write(digest + "\n")
            for p in problems:
                fh.write(f"  ! {p}\n")
        state_f.write_text(json.dumps(state))

        if problems:
            print(f"\n{len(problems)} problem(s) — stopping so the orchestrator looks:")
            for p in problems:
                print(f"  ! {p}")
            print(f"\ncampaign {campaign_dir.name} is still running; decide whether to stop it.")
            return 2
        if verdict == "DONE":
            print(f"campaign {campaign_dir.name} finished clean")
            return 0
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
