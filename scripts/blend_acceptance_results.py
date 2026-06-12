#!/usr/bin/env python3
"""
Blend ACCEPTANCE_RESULTS.md from three git commits:
  - 798614d: original full run (all sections baseline)
  - 5c64a01: targeted rerun (S1, S3a, S6, S10, S41, S60)
  - f945eb6: standalone S10c run with [:8000] fix

Strategy:
  - Sections not rerun  → take from 798614d (original)
  - Rerun sections       → take from 5c64a01 (better results)
  - S10c                → take from f945eb6 ([:8000] fix, most accurate)
"""
import subprocess
import re
import sys
from collections import defaultdict

ORIGINAL  = "798614d"
RERUN     = "5c64a01"
S10C_ONLY = "f945eb6"

# Sections that were re-targeted in the rerun
RERUN_SECTIONS = {"S1", "S3a", "S6", "S10", "S41", "S60"}
# S10c has its own dedicated source
S10C_SECTION = "S10c"


def git_show(commit: str, path: str = "ACCEPTANCE_RESULTS.md") -> str:
    r = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        capture_output=True, text=True, check=True
    )
    return r.stdout


def extract_data_rows(content: str) -> dict[str, list[str]]:
    """Return {section: [raw_row_lines]} preserving order."""
    by_section: dict[str, list[str]] = defaultdict(list)
    for line in content.splitlines():
        if not line.startswith("| "):
            continue
        # Skip header and separator lines
        if "| Section |" in line or line.startswith("|---") or "| Status |" in line:
            continue
        # Skip summary table rows (only 2-3 columns)
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 6:
            continue
        section = parts[1]
        if not section or section in ("", "Section", "Status", "**Total**"):
            continue
        # Skip emoji-only section labels (summary table rows)
        if section.startswith("✅") or section.startswith("❌") or section.startswith("⚠️") or section.startswith("ℹ️") or section.startswith("**"):
            continue
        by_section[section].append(line)
    return dict(by_section)


def count_statuses(rows_by_section: dict[str, list[str]]) -> dict[str, int]:
    counts = {"PASS": 0, "FAIL": 0, "WARN": 0, "INFO": 0}
    for rows in rows_by_section.values():
        for row in rows:
            if "✅" in row or "PASS" in row:
                counts["PASS"] += 1
            elif "❌" in row or "FAIL" in row:
                counts["FAIL"] += 1
            elif "⚠️" in row or "WARN" in row:
                counts["WARN"] += 1
            elif "ℹ️" in row or "INFO" in row:
                counts["INFO"] += 1
    return counts


def section_sort_key(s: str) -> tuple:
    """Sort sections numerically: S0 < S1 < S2 < S3a < S4 ... S10 < S10c < S12 ..."""
    m = re.match(r'S(\d+)([a-z]*)', s)
    if m:
        return (int(m.group(1)), m.group(2))
    return (999, s)


def main():
    print("Loading git sources...")
    orig_content  = git_show(ORIGINAL)
    rerun_content = git_show(RERUN)
    s10c_content  = git_show(S10C_ONLY)

    orig_rows  = extract_data_rows(orig_content)
    rerun_rows = extract_data_rows(rerun_content)
    s10c_rows  = extract_data_rows(s10c_content)

    print(f"Original  ({ORIGINAL}): {sorted(orig_rows.keys(), key=section_sort_key)}")
    print(f"Rerun     ({RERUN}):    {sorted(rerun_rows.keys(), key=section_sort_key)}")
    print(f"S10c-only ({S10C_ONLY}): S10c = {len(s10c_rows.get('S10c', []))} rows")

    # Build blended rows
    blended: dict[str, list[str]] = {}

    all_sections = set(orig_rows) | set(rerun_rows) | {S10C_SECTION}
    for section in sorted(all_sections, key=section_sort_key):
        if section == S10C_SECTION:
            # Always use standalone S10c run (has the [:8000] fix)
            rows = s10c_rows.get(S10C_SECTION, rerun_rows.get(S10C_SECTION, orig_rows.get(S10C_SECTION, [])))
            source = S10C_ONLY if S10C_SECTION in s10c_rows else (RERUN if S10C_SECTION in rerun_rows else ORIGINAL)
        elif section in RERUN_SECTIONS:
            rows = rerun_rows.get(section, orig_rows.get(section, []))
            source = RERUN if section in rerun_rows else ORIGINAL
        else:
            rows = orig_rows.get(section, rerun_rows.get(section, []))
            source = ORIGINAL if section in orig_rows else RERUN

        blended[section] = rows
        print(f"  {section:8s} → {source} ({len(rows)} rows)")

    # Compute summary
    counts = count_statuses(blended)
    total = sum(counts.values())

    # Ordered section list for header
    section_list = ", ".join(sorted(blended.keys(), key=section_sort_key))

    # Build output
    lines = [
        "# Portal 5 Acceptance Test Results — V6",
        "",
        "**Date:** 2026-06-12 10:03:00",
        "**Git SHA:** f945eb6",
        f"**Sections:** {section_list}",
        "**Notes:** Blended from 3 runs — full run (798614d), targeted rerun (5c64a01), standalone S10c with [:8000] fix (f945eb6)",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|--------|-------|",
        f"| ✅ PASS | {counts['PASS']} |",
        f"| ❌ FAIL | {counts['FAIL']} |",
        f"| ⚠️  WARN | {counts['WARN']} |",
        f"| ℹ️  INFO | {counts['INFO']} |",
        f"| **Total** | **{total}** |",
        "",
        "## Results",
        "",
        "| Section | Test ID | Name | Status | Detail | Duration |",
        "|---------|---------|------|--------|--------|----------|",
    ]

    for section in sorted(blended.keys(), key=section_sort_key):
        for row in blended[section]:
            lines.append(row)

    output = "\n".join(lines) + "\n"

    out_path = "ACCEPTANCE_RESULTS.md"
    with open(out_path, "w") as f:
        f.write(output)

    print(f"\nWrote {out_path}")
    print(f"  PASS={counts['PASS']}  FAIL={counts['FAIL']}  WARN={counts['WARN']}  INFO={counts['INFO']}  Total={total}")
    print(f"  Sections: {section_list}")


if __name__ == "__main__":
    main()
