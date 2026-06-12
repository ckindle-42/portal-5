"""Portal 5 UAT — UAT_RESULTS.md recorder, summary + rerun row management.

Extracted verbatim from tests/portal5_uat_driver.py (TASK_UAT_MODULARIZE_V1
phase A). RESULTS_FILE is accessed attribute-form (config.RESULTS_FILE) so
unit-test monkeypatching of tests.uat.config.RESULTS_FILE takes effect here.
"""

from __future__ import annotations

from tests.uat import config, state

# Result recorder
# ---------------------------------------------------------------------------


def init_results(run_ts: str) -> None:
    config.RESULTS_FILE.write_text(
        f"# Portal 5 — UAT Results\n\n"
        f"**Run:** {run_ts}  \n"
        f"**Catalog:** TEST_CATALOG (see tests/portal5_uat_driver.py)  \n"
        f"**Reviewer:** (fill in)\n\n"
        f"## Summary\n\n"
        f"- **PASS**: 0\n- **WARN**: 0\n- **FAIL**: 0\n- **SKIP**: 0\n- **BLOCKED**: 0\n- **MANUAL**: 0\n\n"
        f"## Results\n\n"
        f"| # | Status | Test | Model | Detail | Elapsed |\n"
        f"|---|--------|------|-------|--------|---------|\n"
    )


def update_summary(counts: dict) -> None:
    text = config.RESULTS_FILE.read_text()
    for status in ("PASS", "WARN", "FAIL", "SKIP", "BLOCKED", "MANUAL"):
        old = f"- **{status}**: "
        lines = [l for l in text.split("\n") if l.startswith(old)]
        if lines:
            text = text.replace(lines[0], f"{old}{counts.get(status, 0)}")
    config.RESULTS_FILE.write_text(text)


def _parse_test_ids_from_results() -> set[str]:
    """Return the set of test IDs already present as rows in UAT_RESULTS.md."""
    if not config.RESULTS_FILE.exists():
        return set()
    import re as _re

    text = config.RESULTS_FILE.read_text()
    ids: set[str] = set()
    # Result rows: "| N | STATUS | [TEST_ID name](url) | `model` | ... | Ns |"
    pattern = _re.compile(r"^\|\s*\d+\s*\|\s*\w+\s*\|\s*\[([A-Za-z0-9][A-Za-z0-9_.-]*)\s")
    for line in text.split("\n"):
        m = pattern.match(line)
        if m:
            ids.add(m.group(1))
    return ids


def _parse_failed_test_ids(statuses: set[str] | None = None) -> set[str]:
    """Return test IDs from UAT_RESULTS.md whose status is in ``statuses``.

    Defaults to FAIL and BLOCKED. Used by --rerun-failed to auto-select
    broken tests without requiring the caller to enumerate IDs manually.
    """
    if statuses is None:
        statuses = {"FAIL", "BLOCKED"}
    if not config.RESULTS_FILE.exists():
        return set()
    import re as _re

    text = config.RESULTS_FILE.read_text()
    ids: set[str] = set()
    pattern = _re.compile(r"^\|\s*\d+\s*\|\s*(\w+)\s*\|\s*\[([A-Za-z0-9][A-Za-z0-9_.-]*)\s")
    for line in text.split("\n"):
        m = pattern.match(line)
        if m and m.group(1).strip() in statuses:
            ids.add(m.group(2))
    return ids


def _remove_rows_for_test_ids(test_ids: set[str]) -> int:
    """Remove existing rows from UAT_RESULTS.md whose test_id is in ``test_ids``.

    Returns the number of rows removed. The summary header is NOT updated here —
    callers should run ``_rebuild_summary_from_rows`` after the run completes.
    """
    if not config.RESULTS_FILE.exists():
        return 0
    import re as _re

    text = config.RESULTS_FILE.read_text()
    out_lines: list[str] = []
    removed = 0
    pattern = _re.compile(r"^\|\s*\d+\s*\|\s*\w+\s*\|\s*\[([A-Za-z0-9][A-Za-z0-9_.-]*)\s")
    for line in text.split("\n"):
        m = pattern.match(line)
        if m and m.group(1) in test_ids:
            removed += 1
            continue
        out_lines.append(line)
    config.RESULTS_FILE.write_text("\n".join(out_lines))
    return removed


def _rebuild_summary_from_rows() -> None:
    """Recompute the PASS/WARN/FAIL/SKIP/MANUAL counts in the summary header
    by parsing the rows in UAT_RESULTS.md. Source of truth is the file contents,
    not the in-memory ``counts`` dict (which is per-invocation).
    """
    if not config.RESULTS_FILE.exists():
        return
    import re as _re

    text = config.RESULTS_FILE.read_text()
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0, "BLOCKED": 0, "MANUAL": 0}
    pattern = _re.compile(r"^\|\s*\d+\s*\|\s*(\w+)\s*\|\s*\[")
    for line in text.split("\n"):
        m = pattern.match(line)
        if m:
            status = m.group(1).strip()
            if status in counts:
                counts[status] += 1
    for status in counts:
        old_re = _re.compile(rf"^- \*\*{status}\*\*: \d+", _re.MULTILINE)
        text = old_re.sub(f"- **{status}**: {counts[status]}", text)
    config.RESULTS_FILE.write_text(text)


def _write_routing_summary() -> None:
    """Append a Routing Summary section to UAT_RESULTS.md.

    Groups by: correct | routing mismatch | wrong model | no-actual.
    Also breaks down the pipeline-confirmed backend for correctly-matched
    tests — surfaces silent fallbacks where the test passes on general
    capability but the intended model was never exercised.
    """
    if not state._ROUTING_LOG:
        return

    correct = [r for r in state._ROUTING_LOG if r["matched"]]
    tier_fallbacks = [r for r in state._ROUTING_LOG if not r["matched"] and r.get("tier_mismatch")]
    wrong_model = [r for r in state._ROUTING_LOG if not r["matched"] and not r.get("tier_mismatch") and r["actual"]]
    no_actual = [r for r in state._ROUTING_LOG if not r["actual"]]

    # Pipeline backend breakdown: among correctly-matched tests that had an ollama-intended
    # workspace, how many confirmed correct routing.
    ollama_intended_correct = [r for r in correct if r.get("intended_ollama") and r.get("pipeline_backend")]
    confirmed_ollama = [r for r in ollama_intended_correct if r.get("pipeline_backend")]

    lines: list[str] = [
        "",
        "## Routing Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Routing checked | {len(state._ROUTING_LOG)} |",
        f"| Correct | {len(correct)} |",
        f"| Routing mismatch (wrong model) | {len(tier_fallbacks)} |",
        f"| Wrong model (same tier) | {len(wrong_model)} |",
        f"| No actual model returned | {len(no_actual)} |",
        "",
    ]

    if ollama_intended_correct:
        lines += [
            "### Pipeline Backend (Ollama primary, pipeline-confirmed)",
            "",
            "Tests that matched expected routing — breakdown of which backend *actually* served:",
            "",
            "| Metric | Count |",
            "|--------|-------|",
            f"| Ollama primary confirmed | {len(confirmed_ollama)} |",
            f"| Backend unconfirmed (log gap) | {len(ollama_intended_correct) - len(confirmed_ollama)} |",
            "",
        ]
        if confirmed_ollama:
            lines += [
                "**Ollama-served** — these tests passed with backend confirmed:",
                "",
                "| Test ID | Name | Section | Pipeline Backend |",
                "|---------|------|---------|-----------------|",
            ]
            for r in confirmed_ollama:
                backend = r.get("pipeline_backend", "?")
                lines.append(
                    f"| {r['test_id']} | {r['name'][:40]} | {r['section']} | `{backend}` |"
                )
            lines.append("")

    if tier_fallbacks:
        lines += [
            "### Routing Mismatches (intended model not served)",
            "",
            "A different model served these tests than the workspace intended.",
            "The test may have passed on general capability — the **intended model was never exercised**.",
            "",
            "| Test ID | Name | Section | Intended | Actual |",
            "|---------|------|---------|----------|--------|",
        ]
        for r in tier_fallbacks:
            lines.append(
                f"| {r['test_id']} | {r['name'][:40]} | {r['section']} "
                f"| {r['intended'][:40]} | {r['actual'][:40]} |"
            )
        lines.append("")

    if wrong_model:
        lines += [
            "### Wrong Model (tier OK, model mismatch)",
            "",
            "| Test ID | Name | Section | Intended | Actual |",
            "|---------|------|---------|----------|--------|",
        ]
        for r in wrong_model:
            lines.append(
                f"| {r['test_id']} | {r['name'][:40]} | {r['section']} "
                f"| {r['intended'][:40]} | {r['actual'][:40]} |"
            )
        lines.append("")

    if not tier_fallbacks and not wrong_model and not no_actual:
        lines.append("All routing checks passed — every test was served by its intended primary model.\n")

    with config.RESULTS_FILE.open("a") as f:
        f.write("\n".join(lines))


def record_result(
    n: int,
    status: str,
    test_id: str,
    name: str,
    model: str,
    assertions: list,
    elapsed: float,
    chat_url: str,
    routed_model: str = "",
) -> None:
    passed = sum(1 for a in assertions if a[1])
    total = len(assertions)
    pct = f"{passed}/{total}({passed * 100 // total}%)" if total else "0/0"
    detail = "; ".join(f"{a[0]}={'✓' if a[1] else '✗'}({a[2]})" for a in assertions)
    if routed_model and status in ("FAIL", "WARN"):
        detail = f"[routed: {routed_model}] {detail}" if detail else f"[routed: {routed_model}]"
    with config.RESULTS_FILE.open("a") as f:
        f.write(
            f"| {n} | {status} | [{test_id} {name}]({chat_url}) | "
            f"`{model}` | {pct} {detail} | {elapsed:.1f}s |\n"
        )
    icon = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠", "SKIP": "–", "BLOCKED": "⊘", "MANUAL": "✎"}.get(
        status, "?"
    )
    routed_suffix = f" [→{routed_model}]" if routed_model else ""
    print(
        f"  [{icon} {status}] {test_id} {name} ({passed}/{total}={passed * 100 // total if total else 0}%) ({elapsed:.1f}s){routed_suffix}"
    )
