"""Result model and recording helpers for Portal 5 acceptance tests."""
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.resolve()


@dataclass
class R:
    """Test result record."""

    section: str
    tid: str
    name: str
    status: str  # PASS | FAIL | BLOCKED | WARN | INFO
    detail: str = ""
    evidence: list[str] = field(default_factory=list)
    fix: str = ""
    duration: float = 0.0


_log: list[R] = []
_blocked: list[R] = []
_ICON = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "🚫", "WARN": "⚠️ ", "INFO": "ℹ️ "}

# Routing telemetry — each entry: {tid, workspace, intended, actual, matched}
_ROUTING_LOG: list[dict] = []

_ERROR_PATTERNS_CODE_DEFECT = [
    r"No such file or directory.*portal_metrics",
    r"model_hint.*not in",
    r"workspace_model.*not in WORKSPACES",
    r"AttributeError|TypeError|NameError",
    r"port.*already in use|address already in use",
    r"semaphore.*concurrency limit",
]
_ERROR_PATTERNS_ENV_ISSUE = [
    r"All connection attempts failed",
    r"name resolution|getaddrinfo",
    r"docker.*registry|registry-1\.docker\.io",
    r"insufficient memory|out of memory",
    r"missing dependency|No module named",
    r"port.*not running|not running",
    r"ConnectError|Connection refused",
]

# Mutable flags — set by cli.py before sections run
_verbose = False
_PROGRESS_LOG = "/tmp/portal5_progress.log"


def _classify(detail: str) -> str:
    """Classify a FAIL/WARN detail string as CODE-DEFECT, ENV-ISSUE, or UNCLASSIFIED."""
    for pat in _ERROR_PATTERNS_CODE_DEFECT:
        if re.search(pat, detail, re.IGNORECASE):
            return "CODE-DEFECT"
    for pat in _ERROR_PATTERNS_ENV_ISSUE:
        if re.search(pat, detail, re.IGNORECASE):
            return "ENV-ISSUE"
    return "UNCLASSIFIED"


def _emit(r: R) -> R:
    """Print and log a test result."""
    icon = _ICON.get(r.status, "  ")
    dur = f"({r.duration:.1f}s)" if r.duration else ""
    line = f"  {icon} [{r.tid}] {r.name}  {r.detail}  {dur}"
    print(line)
    if _verbose and r.evidence:
        for e in r.evidence:
            print(f"       {e}")
    # Write to live progress log
    try:
        ts = time.strftime("%H:%M:%S")
        counts = _progress_counts()
        with open(_PROGRESS_LOG, "a") as pf:
            pf.write(
                f"[{ts}] {icon} [{r.section}/{r.tid}] {r.name[:60]}  {r.detail[:60]}  {dur}  {counts}\n"
            )
    except Exception:
        pass
    return r


def _progress_counts() -> str:
    """Return live PASS/WARN/FAIL counts for progress log."""
    p = sum(1 for x in _log if x.status == "PASS")
    w = sum(1 for x in _log if x.status == "WARN")
    f = sum(1 for x in _log if x.status == "FAIL")
    b = sum(1 for x in _log if x.status == "BLOCKED")
    return f"[{p}P {w}W {f}F {b}B]"


def record(
    section: str,
    tid: str,
    name: str,
    status: str,
    detail: str = "",
    evidence: list[str] | None = None,
    fix: str = "",
    t0: float | None = None,
) -> R:
    """Record a test result."""
    dur = time.time() - t0 if t0 else 0.0
    if status in ("FAIL", "WARN") and detail:
        cls = _classify(detail)
        detail = f"{detail}  [{cls}]"
    r = R(section, tid, name, status, detail, evidence or [], fix, dur)
    _log.append(r)
    if status == "BLOCKED":
        _blocked.append(r)
    return _emit(r)


def _git_sha() -> str:
    """Get current git SHA."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        ).stdout.strip()
    except Exception:
        return "unknown"


def _write_results(elapsed: int, sections_run: list[str]) -> None:
    """Write ACCEPTANCE_RESULTS.md."""
    counts: dict[str, int] = {}
    for r in _log:
        counts[r.status] = counts.get(r.status, 0) + 1

    total = sum(counts.values())

    lines = [
        "# Portal 5 Acceptance Test Results — V6",
        "",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Git SHA:** {_git_sha()}",
        f"**Sections:** {', '.join(sections_run)}",
        f"**Runtime:** {elapsed}s ({elapsed // 60}m {elapsed % 60}s)",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|--------|-------|",
    ]

    for status in ["PASS", "FAIL", "BLOCKED", "WARN", "INFO"]:
        if status in counts:
            lines.append(f"| {_ICON.get(status, '')} {status} | {counts[status]} |")
    lines.append(f"| **Total** | **{total}** |")

    # Classifier breakdown for FAIL/WARN
    fail_warn = [r for r in _log if r.status in ("FAIL", "WARN")]
    if fail_warn:
        code_defects = sum(1 for r in fail_warn if "CODE-DEFECT" in r.detail)
        env_issues = sum(1 for r in fail_warn if "ENV-ISSUE" in r.detail)
        unclassified = len(fail_warn) - code_defects - env_issues
        lines.extend(
            [
                "",
                f"**Code defects: {code_defects} · Env issues: {env_issues} · Unclassified: {unclassified}**",
            ]
        )

    lines.extend(
        [
            "",
            "## Results",
            "",
            "| Section | ID | Name | Status | Detail | Duration |",
            "|---------|-----|------|--------|--------|----------|",
        ]
    )

    for r in _log:
        icon = _ICON.get(r.status, "")
        detail = r.detail.replace("|", "\\|")[:80]
        dur = f"{r.duration:.1f}s" if r.duration is not None else ""
        lines.append(
            f"| {r.section} | {r.tid} | {r.name[:40]} | {icon} {r.status} | {detail} | {dur} |"
        )

    if _blocked:
        lines.extend(
            [
                "",
                "## Blocked Items Register",
                "",
            ]
        )
        for i, r in enumerate(_blocked, 1):
            lines.extend(
                [
                    f"### BLOCKED-{i}: {r.name}",
                    "",
                    f"**Test ID:** {r.tid}",
                    f"**Section:** {r.section}",
                    f"**Detail:** {r.detail}",
                    f"**Fix:** {r.fix or 'TBD'}",
                    "",
                ]
            )

    (ROOT / "ACCEPTANCE_RESULTS.md").write_text("\n".join(lines))
    print("\n📄 Results written to ACCEPTANCE_RESULTS.md")


def _load_prior_results(sections_to_skip: set[str]) -> None:
    """Load ACCEPTANCE_RESULTS.md into _log, skipping sections being re-run."""
    results_path = ROOT / "ACCEPTANCE_RESULTS.md"
    if not results_path.exists():
        print("  [append] No prior ACCEPTANCE_RESULTS.md found — starting fresh")
        return
    loaded = 0
    for line in results_path.read_text().splitlines():
        if not line.startswith("| ") or "| Section |" in line or line.startswith("|---"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 7:
            continue
        section = parts[1]
        if not section or section in sections_to_skip:
            continue
        tid = parts[2]
        name = parts[3]
        status_raw = parts[4]
        detail = parts[5].replace("\\|", "|")
        dur_str = parts[6]
        status = next(
            (s for s in ("PASS", "FAIL", "BLOCKED", "WARN", "INFO") if s in status_raw),
            None,
        )
        if not status:
            continue
        dur = 0.0
        if dur_str.endswith("s"):
            try:
                dur = float(dur_str[:-1])
            except ValueError:
                pass
        r = R(section=section, tid=tid, name=name, status=status, detail=detail, duration=dur)
        _log.append(r)
        if status == "BLOCKED":
            _blocked.append(r)
        loaded += 1
    print(
        f"  [append] Loaded {loaded} prior results (excluding: {', '.join(sorted(sections_to_skip))})"
    )


def _print_routing_summary() -> None:
    """Print a routing intent-vs-actual summary after all sections complete."""
    if not _ROUTING_LOG:
        return

    correct = [r for r in _ROUTING_LOG if r["matched"]]
    unmatched = [r for r in _ROUTING_LOG if not r["matched"] and r["actual"]]
    no_actual = [r for r in _ROUTING_LOG if not r["actual"]]

    print("\n" + "=" * 70)
    print("ROUTING SUMMARY")
    print("=" * 70)
    total_checked = len(_ROUTING_LOG)
    print(f"  Checked : {total_checked}")
    print(f"  ✅ Correct   : {len(correct)}")
    if unmatched:
        print(f"  ⚠️  Unmatched model : {len(unmatched)}")
    if no_actual:
        print(f"  ℹ️  No model in response : {len(no_actual)}")

    if unmatched:
        print("\n  ── Unmatched Routing ──")
        for r in unmatched:
            print(f"    {r['tid']:20s}  ws={r['workspace']:22s}  actual={r['actual'][:45]}")
            print(f"    {'':20s}  expected: {r['intended']}")

    print("=" * 70)
