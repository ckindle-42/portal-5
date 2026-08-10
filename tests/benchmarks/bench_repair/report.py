"""Results renderer — model matrix with arch + delta as first-class columns.

The arch axis (dense vs MoE) is the @danpacary write-up's headline finding
(dense +47 vs MoE +11 on repair), so it belongs in the table, not the
appendix.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from tests.benchmarks.bench_repair.config import ARM_ONESHOT, ARM_REPAIR, arch_from_hint
from tests.benchmarks.bench_repair.runner import SampleResult


def _pass_rate(samples: list[SampleResult]) -> float:
    if not samples:
        return 0.0
    return sum(1 for s in samples if s.passed) / len(samples)


def _harness_error_count(samples: list[SampleResult]) -> int:
    return sum(1 for s in samples if s.detail.startswith("harness_error"))


def render_matrix(
    samples: list[SampleResult],
    *,
    gsha: str,
    breakdown: dict,
    corpus_size: int,
) -> str:
    # Group by workspace × arm
    by_ws_arm: dict[tuple[str, str], list[SampleResult]] = defaultdict(list)
    hint_by_ws: dict[str, str] = {}
    for s in samples:
        by_ws_arm[(s.workspace, s.arm)].append(s)
        hint_by_ws[s.workspace] = s.model_hint

    workspaces = sorted({s.workspace for s in samples})

    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = [
        "# bench_repair — one-shot vs +1-repair matrix",
        "",
        f"**Generated:** {ts}",
        f"**Exam fingerprint (gsha):** `{gsha}`",
        f"**Corpus size:** {corpus_size} problems (`bench_capability_c2_problems.json`)",
        "",
        "```",
        f"corpus_sha     : {breakdown['corpus_sha']}",
        f"prompts_sha    : {breakdown['prompts_sha']}",
        f"ollama_version : {breakdown['ollama_version']}",
        f"gsha           : {breakdown['gsha']}",
        "```",
        "",
        "**Arms:** one-shot n=5, +1-repair n=2, temperature=1.0. "
        "PROMOTE_POLICY: confirm — no auto-promotion.",
        "",
        "## Matrix",
        "",
        "| Workspace | Arch | model_hint | one-shot | +1-repair | Δ | notes |",
        "|---|---|---|---:|---:|---:|---|",
    ]

    for ws in workspaces:
        hint = hint_by_ws[ws]
        arch = arch_from_hint(hint)
        os_samples = by_ws_arm.get((ws, ARM_ONESHOT), [])
        rp_samples = by_ws_arm.get((ws, ARM_REPAIR), [])
        os_rate = _pass_rate(os_samples)
        rp_rate = _pass_rate(rp_samples)
        delta = rp_rate - os_rate
        errs = _harness_error_count(os_samples) + _harness_error_count(rp_samples)
        notes = f"harness_errors={errs}" if errs else ""
        lines.append(
            f"| `{ws}` | {arch} | `{hint}` | "
            f"{os_rate * 100:.1f}% ({len(os_samples)}) | "
            f"{rp_rate * 100:.1f}% ({len(rp_samples)}) | "
            f"{'+' if delta >= 0 else ''}{delta * 100:.1f} | {notes} |"
        )

    # Arch summary
    lines += ["", "## Arch summary (mean pass rate, mean delta)", ""]
    lines += [
        "| Arch | mean one-shot | mean +1-repair | mean Δ | workspaces |",
        "|---|---:|---:|---:|---|",
    ]
    for arch_label in ("dense", "MoE"):
        arch_ws = [ws for ws in workspaces if arch_from_hint(hint_by_ws[ws]) == arch_label]
        if not arch_ws:
            continue
        os_rates = [_pass_rate(by_ws_arm.get((ws, ARM_ONESHOT), [])) for ws in arch_ws]
        rp_rates = [_pass_rate(by_ws_arm.get((ws, ARM_REPAIR), [])) for ws in arch_ws]
        m_os = sum(os_rates) / len(os_rates)
        m_rp = sum(rp_rates) / len(rp_rates)
        lines.append(
            f"| {arch_label} | {m_os * 100:.1f}% | {m_rp * 100:.1f}% | "
            f"{'+' if (m_rp - m_os) >= 0 else ''}{(m_rp - m_os) * 100:.1f} | "
            f"{', '.join(arch_ws)} |"
        )

    # Per-cell detail
    lines += ["", "## Per-sample detail", ""]
    for s in sorted(samples, key=lambda x: (x.workspace, x.arm, x.problem_id, x.sample_idx)):
        mark = "PASS" if s.passed else "FAIL"
        lines.append(
            f"- `{s.workspace}` `{s.arm}` `{s.problem_id}` #{s.sample_idx}: "
            f"**{mark}** ({s.latency_s:.1f}s) — {s.detail}"
        )
    lines.append("")
    return "\n".join(lines)
