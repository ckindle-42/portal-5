#!/usr/bin/env python3
"""Emit an ordered, category-grouped re-bench run plan from the latest
pending-verdicts analysis. TASK_MODEL_BENCH_VALIDITY_V1 Part 3a.

Reads the newest reports/PENDING_VERDICTS_ANALYSIS_<UTC>.md and turns its
per-model capability categories + slot-fix flags into a concrete run list:
which harness to run for which models, slot fixes to clear first, and which
categories have no harness yet (honestly still-owed). Report-only.
"""

from __future__ import annotations

import datetime as _dt
import glob
import re
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS = REPO_ROOT / "reports"

# category -> the command that benches it correctly (None = harness not built)
CATEGORY_HARNESS_CMD: dict[str, str | None] = {
    "cad": "python3 tests/benchmarks/bench_cad_probe.py",
    "spl": "python3 tests/benchmarks/bench_spl_probe.py",
    "compliance": "python3 tests/benchmarks/bench_compliance_probe.py",
    "data": "python3 tests/benchmarks/bench_data_probe.py",
    "general": "python3 -m tests.benchmarks.bench_tps --mode pipeline|direct",
    "moe": "python3 -m tests.benchmarks.bench_tps --mode pipeline|direct",
    "reasoning-explicit": "python3 tests/benchmarks/bench_reasoning_probe.py",
    "vision": "python3 tests/benchmarks/bench_vision_probe.py",
    "mtp-speculative": "python3 tests/benchmarks/bench_mtp_probe.py",
    "abliterated": "python3 tests/benchmarks/bench_refusal_preservation_probe.py",
    "long-context": "python3 tests/benchmarks/bench_long_context_probe.py",
    "cua": "python3 tests/benchmarks/bench_fara_cua_probe.py",
    "security-tooling": "python3 tests/benchmarks/bench_security_exec_probe.py",
    "agent-toolcall": "python3 tests/benchmarks/bench_tool_use_probe.py",
}


def newest_analysis() -> Path | None:
    files = sorted(glob.glob(str(REPORTS / "PENDING_VERDICTS_ANALYSIS_*.md")))
    return Path(files[-1]) if files else None


def parse_analysis(path: Path) -> list[dict]:
    txt = path.read_text(encoding="utf-8")
    # Each entry: ## `TAG` — N.N GB ... Capability category:** `CAT`
    entries = []
    for m in re.finditer(r"## `([^`]+)` — ([\d.]+) GB(.*?)(?=\n## `|\Z)", txt, re.DOTALL):
        tag, gb, block = m.group(1), float(m.group(2)), m.group(3)
        cat_m = re.search(r"Capability category:\*\* `([^`]+)`", block)
        cat = cat_m.group(1) if cat_m else "general"
        needs = (
            "Re-bench REQUIRED" in block
            or "Not decision-grade" in block
            or "Capability-appropriate re-bench required" in block
        )
        wrong = "Wrong-instrument evidence" in block
        slotfix = "Slot fixes REQUIRED" in block or "slot fixes REQUIRED" in block
        entries.append(
            {
                "tag": tag,
                "gb": gb,
                "category": cat,
                "needs_rebench": needs,
                "wrong_instrument": wrong,
                "slot_blocked": slotfix,
            }
        )
    return entries


def _render_slot_fix_step(slot_blocked: list[dict]) -> list[str]:
    lines = [f"## Step 1 — slot fixes first ({len(slot_blocked)} workspaces) [GATE]", ""]
    if slot_blocked:
        lines.append(
            "These cannot produce valid data until portal.yaml is fixed + sync_config re-run:"
        )
        for e in slot_blocked:
            lines.append(f"- `{e['tag']}` ({e['category']})")
    else:
        lines.append("None — no slot-blocked workspaces.")
    lines.append("")
    return lines


def _render_category_step(by_cat: dict[str, list[dict]]) -> tuple[list[str], list[str]]:
    lines = ["## Step 2 — category runs (grouped by shared harness)", ""]
    still_owed: list[str] = []
    for cat in sorted(by_cat, key=lambda c: -len(by_cat[c])):
        models = by_cat[cat]
        cmd = CATEGORY_HARNESS_CMD.get(cat, "python3 -m tests.benchmarks.bench_tps")
        gb = sum(e["gb"] for e in models)
        if cmd is None:
            still_owed.append(cat)
            lines.append(
                f"### `{cat}` — {len(models)} models, {gb:.1f} GB — ⚠ HARNESS NOT BUILT (still-owed)"
            )
        else:
            lines.append(f"### `{cat}` — {len(models)} models, {gb:.1f} GB")
            lines.append(f"Run: `{cmd}`")
        for e in models:
            flags = []
            if e["wrong_instrument"]:
                flags.append("wrong-instrument")
            if e["needs_rebench"]:
                flags.append("needs-rebench")
            lines.append(f"- `{e['tag']}`" + (f"  [{', '.join(flags)}]" if flags else ""))
        lines.append("")
    return lines, still_owed


def _render_still_owed(by_cat: dict[str, list[dict]], still_owed: list[str]) -> list[str]:
    if not still_owed:
        return []
    lines = ["## ⚠ Categories still owed a dedicated harness (build next, do NOT fake-green):"]
    for c in still_owed:
        lines.append(f"- `{c}`: {len(by_cat[c])} model(s) waiting on a purpose-built harness")
    lines.append("")
    return lines


def main() -> int:
    ap = newest_analysis()
    if ap is None:
        print("No PENDING_VERDICTS_ANALYSIS_*.md found — run pending_verdicts_report.py first.")
        return 1
    entries = parse_analysis(ap)
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_cat[e["category"]].append(e)

    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out = REPORTS / f"REBENCH_PLAN_{stamp}.md"
    slot_blocked = [e for e in entries if e["slot_blocked"]]

    lines: list[str] = [
        f"# Re-bench plan ({stamp})",
        "",
        f"Source analysis: `{ap.relative_to(REPO_ROOT)}`",
        f"{len(entries)} models across {len(by_cat)} categories.",
        "",
    ]
    lines.extend(_render_slot_fix_step(slot_blocked))
    category_lines, still_owed = _render_category_step(by_cat)
    lines.extend(category_lines)
    lines.append(
        "## Step 3 — regenerate evidence + analysis, then run the validation gate (Part 3e)"
    )
    lines.append("")
    lines.extend(_render_still_owed(by_cat, still_owed))

    out.write_text("\n".join(lines))
    print(f"Wrote {out.relative_to(REPO_ROOT)} ({len(entries)} models, {len(by_cat)} categories)")
    print(f"  slot-blocked: {len(slot_blocked)}")
    print(f"  categories still owed a harness: {still_owed or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
