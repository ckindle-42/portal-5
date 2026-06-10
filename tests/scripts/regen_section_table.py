#!/usr/bin/env python3
"""Regenerate the Section Reference table in tests/PORTAL5_PROMPT_V6.md.

Reads:
  - tests/portal5_acceptance_v6.py (introspect section funcs, count record() calls)

Writes:
  - tests/PORTAL5_ACCEPTANCE_EXECUTE_V8.md (replaces the marked block; rest of file untouched)

Markers in the prompt file (must be present, on their own lines):
    <!-- SECTION_TABLE_BEGIN -->
    <!-- SECTION_TABLE_END -->

Anything between the markers is replaced. Anything outside is preserved exactly.

Usage:
    python3 tests/scripts/regen_section_table.py             # write changes
    python3 tests/scripts/regen_section_table.py --check     # exit 1 if drift
    python3 tests/scripts/regen_section_table.py --diff      # show diff, no write
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ACCEPTANCE_FILE = ROOT / "tests" / "portal5_acceptance_v6.py"
PROMPT_FILE = ROOT / "tests" / "PORTAL5_ACCEPTANCE_EXECUTE_V8.md"
BACKENDS_YAML = ROOT / "config" / "backends.yaml"
PERSONAS_DIR = ROOT / "config" / "personas"

BEGIN_MARKER = "<!-- SECTION_TABLE_BEGIN -->"
END_MARKER = "<!-- SECTION_TABLE_END -->"

# Static phase grouping — sections in each phase. Update here if phase plan
# changes; verified against PORTAL5_ACCEPTANCE_EXECUTE_V8.md phase commands.
PHASE_FOR_SECTION: dict[str, int] = {
    # Phase 1: no-model
    "S0": 1, "S1": 1, "S2": 1, "S12": 1, "S13": 1,
    "S15": 1, "S16": 1, "S40": 1, "S41": 1, "S42": 1,
    # Phase 2: Ollama
    "S3a": 2, "S6": 2, "S10": 2,
    # Phase 3: router + diversity (Ollama)
    "S21": 3, "S23": 3,
    # Phase 4: MCPs
    "S4": 4, "S5": 4, "S50": 4, "S60": 4, "S70": 4,
    # Phase 5: audio
    "S8": 5, "S9": 5, "S7": 5,
    # Phase 6: ComfyUI last
    "S30": 6, "S31": 6,
    # Wrapper / not in phases
    "S3": 0,
}

# Human-readable labels for each section. Kept brief — table column has limited
# width. New sections without a label here render as "<section name>" so the
# generator never blocks on missing metadata.
SECTION_LABELS: dict[str, str] = {
    "S0":  "Prerequisites",
    "S1":  "Config consistency",
    "S2":  "Service health",
    "S3":  "Workspace routing (wrapper for S3a)",
    "S3a": "Workspaces (Ollama)",
    "S4":  "Document generation",
    "S5":  "Code sandbox",
    "S6":  "Security workspaces",
    "S7":  "Music generation",
    "S8":  "Text-to-Speech",
    "S9":  "Speech-to-Text",
    "S10": "Personas (Ollama)",
    "S12": "Web search",
    "S13": "RAG/Embedding",
    "S15": "Shared workspace verification",
    "S16": "Security MCP tools (CIRCL VLAI)",
    "S21": "LLM Intent Router",
    "S23": "Model diversity",
    "S30": "Image generation (ComfyUI/FLUX)",
    "S31": "Video generation (Wan2.2)",
    "S40": "Metrics/monitoring",
    "S41": "M6 production hardening",
    "S42": "M5 browser automation",
    "S50": "Negative testing",
    "S60": "M2 tool-calling orchestration",
    "S70": "M3 information access MCPs",
}


def _discover_sections(source: str) -> list[tuple[str, int]]:
    """Return [(section_name, approx_test_count), ...] sorted by phase then name.

    Section name = function name (S0, S1, S3a, S3b, ...).
    Test count = number of record() invocations inside that function body.
    """
    # Match: async def S<digits><optional letter>(  ... up to next async def or EOF
    pattern = re.compile(
        r"^async def (S\d+[a-z]?)\(\) -> None:.*?(?=^async def |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    out: list[tuple[str, int]] = []
    for match in pattern.finditer(source):
        name = match.group(1)
        body = match.group(0)
        # Approximate test count: number of distinct record() call sites.
        # Some sections call record() inside loops; the static count is a
        # lower bound but matches the table's intent ("test cases defined").
        record_calls = body.count("record(")
        out.append((name, record_calls))
    return out


def _count_workspaces() -> int:
    import yaml  # noqa: PLC0415
    cfg = yaml.safe_load(BACKENDS_YAML.read_text())
    return len(cfg.get("workspace_routing", {}))


def _count_personas() -> int:
    return len(list(PERSONAS_DIR.glob("*.yaml")))


def _build_table(sections: list[tuple[str, int]]) -> str:
    """Render the markdown table."""
    rows = ["| Phase | Section | Description | Tests |",
            "|-------|---------|-------------|-------|"]

    # Order: by phase, then by numeric portion of section name.
    def sort_key(item: tuple[str, int]) -> tuple[int, int, str]:
        name, _ = item
        phase = PHASE_FOR_SECTION.get(name, 99)
        # Extract digits for ordering: "S3a" -> 3, "S70" -> 70
        m = re.match(r"S(\d+)([a-z]?)", name)
        num = int(m.group(1)) if m else 99
        suffix = m.group(2) if m else ""
        return (phase, num, suffix)

    for name, count in sorted(sections, key=sort_key):
        phase = PHASE_FOR_SECTION.get(name, "?")
        label = SECTION_LABELS.get(name, name)
        rows.append(f"| {phase} | {name} | {label} | {count} |")
    return "\n".join(rows)


def _generate_block() -> str:
    """Generate the full block to slot between BEGIN/END markers."""
    source = ACCEPTANCE_FILE.read_text()
    sections = _discover_sections(source)
    workspaces_n = _count_workspaces()
    personas_n = _count_personas()
    table = _build_table(sections)

    return (
        f"{BEGIN_MARKER}\n"
        f"\n"
        f"_Auto-generated by `tests/scripts/regen_section_table.py`. "
        f"Edit the generator, not the table. "
        f"`make regen-section-table` or `python3 tests/scripts/regen_section_table.py` to refresh._\n"
        f"\n"
        f"**Coverage:** {workspaces_n} workspaces, {personas_n} personas, "
        f"{len(sections)} acceptance sections.\n"
        f"\n"
        f"{table}\n"
        f"\n"
        f"**Memory cleanup points:** After S10 (Personas→Audio/MCP), "
        f"after S7 (Audio→ComfyUI)\n"
        f"\n"
        f"{END_MARKER}"
    )


def _replace_block(prompt_text: str, new_block: str) -> str:
    """Replace content between markers. Adds markers if missing."""
    if BEGIN_MARKER in prompt_text and END_MARKER in prompt_text:
        pattern = re.compile(
            re.escape(BEGIN_MARKER) + r".*?" + re.escape(END_MARKER),
            re.DOTALL,
        )
        return pattern.sub(new_block, prompt_text, count=1)

    # Markers missing — find the last "## Section Quick Reference" or
    # similar header and replace the table that follows it.
    section_header_re = re.compile(
        r"(## Section Quick Reference\s*\n)(.*?)(\n---\n|\Z)",
        re.DOTALL,
    )
    m = section_header_re.search(prompt_text)
    if m:
        return (
            prompt_text[: m.start(2)] + "\n" + new_block + "\n\n" + prompt_text[m.end(2) :]
        )

    # Last resort: append at end with an h2 header.
    return (
        prompt_text.rstrip()
        + "\n\n## Section Quick Reference\n\n"
        + new_block
        + "\n"
    )


def _diff(a: str, b: str) -> str:
    import difflib  # noqa: PLC0415
    return "".join(
        difflib.unified_diff(
            a.splitlines(keepends=True),
            b.splitlines(keepends=True),
            fromfile="PORTAL5_PROMPT_V6.md (current)",
            tofile="PORTAL5_PROMPT_V6.md (regenerated)",
            n=3,
        )
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true",
                   help="Exit 1 if regeneration would change the file")
    p.add_argument("--diff", action="store_true",
                   help="Print diff and exit; do not write")
    args = p.parse_args(argv)

    current = PROMPT_FILE.read_text()
    new_block = _generate_block()
    new_text = _replace_block(current, new_block)

    if args.diff:
        sys.stdout.write(_diff(current, new_text))
        return 0
    if args.check:
        if current != new_text:
            sys.stderr.write(
                "DRIFT: section table in PORTAL5_PROMPT_V6.md is out of sync.\n"
                "Run: python3 tests/scripts/regen_section_table.py\n\n"
            )
            sys.stderr.write(_diff(current, new_text))
            return 1
        print("Section table is up to date.")
        return 0

    if current == new_text:
        print("Section table already up to date — no changes written.")
        return 0
    PROMPT_FILE.write_text(new_text)
    print(f"Updated {PROMPT_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
