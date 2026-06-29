"""ComfyUI-specific result writer — writes to ACCEPTANCE_RESULTS_COMFYUI.md."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ._common import _blocked, _log

ROOT = Path(__file__).parent.parent.resolve()


def _write_results(elapsed: int, sha: str) -> dict[str, int]:
    """Write ACCEPTANCE_RESULTS_COMFYUI.md."""
    counts: dict[str, int] = {}
    for r in _log:
        counts[r.status] = counts.get(r.status, 0) + 1

    rpt = ROOT / "ACCEPTANCE_RESULTS_COMFYUI.md"
    with open(rpt, "w") as f:
        f.write("# Portal 5 — ComfyUI / Image & Video Acceptance Test Results\n\n")
        f.write(f"**Run:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ({elapsed}s)  \n")
        f.write(f"**Git SHA:** {sha}  \n\n")
        f.write("## Summary\n\n")
        for s in ["PASS", "FAIL", "BLOCKED", "WARN", "INFO"]:
            if s in counts:
                f.write(f"- **{s}**: {counts[s]}\n")
        f.write(f"- **Total**: {sum(counts.values())}\n")
        f.write("\n## All Results\n\n")
        f.write(
            "| # | Status | Section | Test | Detail | Duration |\n"
            "|---|--------|---------|------|--------|----------|\n"
        )
        for i, r in enumerate(_log, 1):
            det = (r.detail or "")[:160].replace("|", "\u2223")
            f.write(
                f"| {i} | {r.status} | {r.section} | {r.name[:60]} | {det} | {r.duration:.1f}s |\n"
            )
        if _blocked:
            f.write("\n## Blocked Items Register\n\n")
            f.write(
                "| # | Section | Test | Evidence | Required Fix |\n"
                "|---|---------|------|----------|---------------|\n"
            )
            for i, r in enumerate(_blocked, 1):
                f.write(
                    f"| {i} | {r.section} | {r.name[:60]} "
                    f"| {r.detail[:120].replace('|', '\u2223')} "
                    f"| {r.fix[:120].replace('|', '\u2223')} |\n"
                )
        else:
            f.write("\n## Blocked Items Register\n\n*No blocked items.*\n")
        f.write("\n---\n*ComfyUI outputs: check ComfyUI output/ directory*\n")

    print(f"\nReport \u2192 {rpt}")
    return counts
