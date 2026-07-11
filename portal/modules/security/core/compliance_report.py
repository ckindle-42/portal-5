"""Compliance/Framework Report Generator — NIST + MITRE Enterprise/OT-ICS + NERC CIP.

Phase 2 of TASK-SEC-COMPLIANCE-REPORT-GENERATOR-V1. Renders a DEFENSE/posture
report FROM Portal's grounded results — capability verdicts, coverage map,
compliance_mapping (Phase 1 of TASK-SEC-DESIGN-GAP-DELIVERY-V1, already landed:
all 30 spl_detections.yaml entries carry matrix + compliance_mapping) — never
inventing a finding or a coverage percentage.

Concept borrowed from AutoPentestX's report-as-first-class-output idea (NOT its
code — its report is offensive-scan-shaped; this is a DEFENSE/compliance report).

Honesty rules (load-bearing):
- Render only what the data supports. A technique with no PROVEN detection is a
  GAP, not glossed over.
- Synthetic-fallback (used_synthetic / blue_used_synthetic_fallback) NEVER
  counts as detected in the report, regardless of what capability_verdict says
  upstream — this report re-checks it independently, defense in depth.
- INSUFFICIENT-DATA for anything without results — never fabricate.
- Every claim in the Findings/Framework sections traces to a result entry, a
  coverage-map gap_id, or a compliance_mapping source — the provenance
  appendix lists them.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPORTS_DIR = _REPO_ROOT / "reports"

_VERDICT_ORDER = ["PROVEN", "FAILED", "INDETERMINATE", "UNAVAILABLE"]


# ── Loading grounded inputs ───────────────────────────────────────────────────


def load_purple_results(path: str | Path) -> list[dict]:
    """Load purple test results from a results file.

    Accepts either the `purple_tests` key (e2e_system_*.json, sec_full_purple_*.json)
    or a bare `results` list — same fallback the e2e runbook's own verification
    script uses. Returns [] (never raises) if the file is missing/malformed —
    callers must render INSUFFICIENT-DATA for an empty list, not crash.
    """
    p = Path(path)
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return d.get("purple_tests") or d.get("results") or []


def _is_really_detected(rec: dict) -> bool:
    """Independent re-check: synthetic-fallback NEVER counts as detected here,
    regardless of what capability_verdict says upstream. Defense in depth for
    the report layer specifically (a presentation bug must not able to launder
    a synthetic result into a stakeholder-facing "detected" claim)."""
    if rec.get("blue_used_synthetic_fallback"):
        return False
    ep = rec.get("episode") or {}
    if ep.get("used_synthetic"):
        return False
    return rec.get("capability_verdict") == "PROVEN"


def _compliance_map() -> dict[str, dict]:
    """tid -> {matrix, compliance_mapping} from spl_detections.yaml (Phase 1)."""
    try:
        import yaml

        path = Path(__file__).resolve().parent / "siem" / "spl_detections.yaml"
        raw = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}
    return {
        tid: {
            "matrix": v.get("matrix", ["enterprise"]),
            "compliance_mapping": v.get("compliance_mapping", []),
        }
        for tid, v in raw.items()
        if isinstance(v, dict)
    }


# ── Report data model ─────────────────────────────────────────────────────────


def build_report_data(
    results_path: str | Path,
    frameworks: list[str] | None = None,
) -> dict[str, Any]:
    """Build the structured report data — the single source every format
    (md/html/pdf) renders from, so they can never drift from each other.
    """
    from portal.modules.security.core.capability_graph import (
        generate_coverage_json,
        generate_navigator_layers,
        seed_graph_from_assets,
        update_graph_from_episode,
    )

    results = load_purple_results(results_path)
    compliance = _compliance_map()

    if not results:
        return {
            "generated_at": time.time(),
            "results_path": str(results_path),
            "insufficient_data": True,
            "verdict_distribution": {},
            "coverage": None,
            "framework_rollup": {},
            "findings": [],
            "provenance": [],
        }

    # ── Executive summary: honest verdict distribution ──────────────────────
    verdict_distribution: dict[str, int] = dict.fromkeys(_VERDICT_ORDER, 0)
    for rec in results:
        v = rec.get("capability_verdict", "UNAVAILABLE")
        verdict_distribution[v] = verdict_distribution.get(v, 0) + 1

    # ── Coverage posture: build the capability graph from these results ─────
    graph = seed_graph_from_assets()
    for rec in results:
        ep = rec.get("episode")
        if ep:
            update_graph_from_episode(graph, ep)
    coverage = generate_coverage_json(graph)
    navigator = generate_navigator_layers(graph)

    # ── Framework rollup: coverage rolled up by compliance framework ────────
    # Denominator = techniques MAPPED to that framework (compliance_mapping);
    # numerator = mapped techniques with a real (non-synthetic) confirmed
    # detection. The coverage map's "CONFIRMED" status already refuses
    # synthetic (derive_detection_status in episode.py), but this report adds
    # an independent second check anyway (_is_really_detected, defense in
    # depth at the presentation layer specifically) — a technique only counts
    # as detected here if BOTH the coverage map says CONFIRMED AND at least
    # one result whose scenario exercises that technique passes the report's
    # own synthetic-never-counts re-check.
    from portal.modules.security.core.exec_chain import SCENARIOS

    really_detected_scenarios = {
        rec.get("episode", {}).get("scenario", rec.get("scenario"))
        for rec in results
        if _is_really_detected(rec)
    }
    really_detected_tids: set[str] = set()
    for name, scenario in SCENARIOS.items():
        if name in really_detected_scenarios:
            really_detected_tids |= set(scenario.get("detect_ground_truth", []))

    proven_tids = {
        tid
        for tid, v in coverage["per_technique"].items()
        if v.get("detection") == "CONFIRMED" and tid in really_detected_tids
    }

    framework_rollup: dict[str, dict] = {}
    for tid, mapping in compliance.items():
        for m in mapping.get("compliance_mapping", []):
            fw = m.get("framework")
            if not fw or (frameworks and fw not in frameworks):
                continue
            key = f"{fw}:{m.get('control') or m.get('tactic') or m.get('requirement') or ''}"
            entry = framework_rollup.setdefault(
                key,
                {
                    "framework": fw,
                    "label": m.get("control") or m.get("tactic") or m.get("requirement") or "",
                    "source": m.get("source", ""),
                    "mapped_techniques": [],
                    "detected_techniques": [],
                },
            )
            if tid not in entry["mapped_techniques"]:
                entry["mapped_techniques"].append(tid)
            if tid in proven_tids and tid not in entry["detected_techniques"]:
                entry["detected_techniques"].append(tid)

    for entry in framework_rollup.values():
        mapped = len(entry["mapped_techniques"])
        detected = len(entry["detected_techniques"])
        entry["mapped_count"] = mapped
        entry["detected_count"] = detected
        entry["detected_pct"] = round(detected / mapped * 100, 1) if mapped else 0.0

    # ── Findings: per-technique, GAP if not PROVEN, never glossed ───────────
    findings: list[dict] = []
    provenance: list[dict] = []
    for tid, cov in sorted(coverage["per_technique"].items()):
        mapping = compliance.get(tid, {"matrix": ["enterprise"], "compliance_mapping": []})
        is_gap = cov.get("detection") != "CONFIRMED"
        findings.append(
            {
                "technique_id": tid,
                "matrix": mapping["matrix"],
                "verdict": "GAP" if is_gap else "CONFIRMED",
                "coverage_summary": cov.get("summary"),
                "gap_id": cov.get("gap_id"),
                "mapped_controls": [
                    m.get("control") or m.get("tactic") or m.get("requirement")
                    for m in mapping["compliance_mapping"]
                ],
                "remediation": (
                    "No confirmed detection — deploy/validate the SPL rule and confirm real "
                    "(non-synthetic) telemetry lands for this technique."
                    if is_gap
                    else "Detection confirmed on real telemetry."
                ),
            }
        )
        if cov.get("gap_id"):
            provenance.append(
                {"claim": f"{tid} coverage", "source": f"coverage-map:{cov['gap_id']}"}
            )
        for m in mapping["compliance_mapping"]:
            provenance.append(
                {"claim": f"{tid} -> {m.get('framework')}", "source": m.get("source", "")}
            )

    return {
        "generated_at": time.time(),
        "results_path": str(results_path),
        "insufficient_data": False,
        "verdict_distribution": verdict_distribution,
        "coverage": coverage,
        "navigator": navigator,
        "framework_rollup": framework_rollup,
        "findings": findings,
        "provenance": provenance,
    }


# ── Rendering (Markdown + HTML) ──────────────────────────────────────────────


def _render_markdown(data: dict) -> str:
    lines = [
        "<!-- GENERATED FROM grounded results + coverage map — do not hand-edit, "
        "re-run `python3 -m bench_security compliance-report` -->",
        "# Portal 5 — Compliance & Framework Posture Report",
        "",
        f"Results source: `{data['results_path']}`",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime(data['generated_at']))}",
        "",
    ]

    if data["insufficient_data"]:
        lines += [
            "## Executive Summary",
            "",
            "**INSUFFICIENT-DATA** — no purple results found at the given path.",
            "",
        ]
        return "\n".join(lines)

    # 1. Executive summary
    lines += ["## 1. Executive Summary", ""]
    vd = data["verdict_distribution"]
    total = sum(vd.values()) or 1
    lines.append("| Verdict | Count | % |")
    lines.append("|---------|-------|---|")
    for v in _VERDICT_ORDER:
        c = vd.get(v, 0)
        lines.append(f"| {v} | {c} | {round(c / total * 100, 1)}% |")
    gaps = [f for f in data["findings"] if f["verdict"] == "GAP"]
    lines += [
        "",
        f"**Top gaps:** {len(gaps)} technique(s) with no confirmed real-telemetry detection "
        f"out of {len(data['findings'])} in scope.",
        "",
    ]

    # 2. Coverage posture (per matrix)
    lines += ["## 2. Coverage Posture", ""]
    for domain, layer in (data.get("navigator") or {}).items():
        n = len(layer["techniques"])
        lines.append(f"- **{domain}**: {n} technique(s) tracked")
    tiers = data["coverage"]["tiers"]
    confirmed_count = sum(1 for f in data["findings"] if f["verdict"] == "CONFIRMED")
    confirmed_pct = (
        round(confirmed_count / len(data["findings"]) * 100, 1) if data["findings"] else 0.0
    )
    lines += [
        "",
        f"- Eligible: {tiers['eligible']}  |  Exercised (real episode ran): {tiers['exercised']} "
        f"({tiers['exercised_pct']}%)  |  Detection rule exists: {tiers['detected']} ({tiers['detected_pct']}%)",
        f"- **Confirmed detected (real, non-synthetic telemetry, this results file): "
        f"{confirmed_count}/{len(data['findings'])} ({confirmed_pct}%)** — the honest number; "
        "a detection RULE existing is not the same as a CONFIRMED detection (see Findings below).",
        "",
    ]

    # 3. Framework mapping (the stakeholder view)
    lines += ["## 3. Framework Mapping", ""]
    if not data["framework_rollup"]:
        lines.append("_No framework mappings matched the requested filter._")
    else:
        lines.append("| Framework | Control/Tactic/Requirement | Mapped | Detected | % |")
        lines.append("|-----------|------------------------------|--------|----------|---|")
        for entry in sorted(
            data["framework_rollup"].values(), key=lambda e: (e["framework"], e["label"])
        ):
            lines.append(
                f"| {entry['framework']} | {entry['label']} | {entry['mapped_count']} | "
                f"{entry['detected_count']} | {entry['detected_pct']}% |"
            )
    lines.append("")

    # 4. Findings
    lines += ["## 4. Findings", ""]
    lines.append("| Technique | Matrix | Verdict | Mapped Controls | Remediation |")
    lines.append("|-----------|--------|---------|------------------|-------------|")
    for f in data["findings"]:
        controls = ", ".join(c for c in f["mapped_controls"] if c) or "—"
        lines.append(
            f"| {f['technique_id']} | {', '.join(f['matrix'])} | {f['verdict']} | {controls} | {f['remediation']} |"
        )
    lines.append("")

    # 5. Provenance appendix
    lines += ["## 5. Provenance Appendix", "", "| Claim | Source |", "|-------|--------|"]
    for p in data["provenance"]:
        lines.append(f"| {p['claim']} | {p['source']} |")

    return "\n".join(lines)


def _render_html(data: dict, markdown: str) -> str:
    """Minimal HTML wrapper around the same markdown-derived content — cheap,
    render-from-source, no separate data path to drift from the .md."""
    import html

    escaped = html.escape(markdown)
    return (
        "<!DOCTYPE html>\n<html><head><meta charset='utf-8'>"
        "<title>Portal 5 Compliance Report</title>"
        "<style>body{font-family:sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}"
        "pre{white-space:pre-wrap}</style></head><body>\n"
        f"<pre>{escaped}</pre>\n</body></html>\n"
    )


def generate_report(
    results_path: str | Path,
    formats: list[str],
    frameworks: list[str] | None = None,
    output_dir: Path | None = None,
) -> dict[str, str]:
    """Generate the report in the requested formats. Returns {format: path}."""
    output_dir = output_dir or _REPORTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    data = build_report_data(results_path, frameworks=frameworks)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(data["generated_at"]))

    written: dict[str, str] = {}
    markdown = _render_markdown(data)

    if "md" in formats:
        path = output_dir / f"compliance_report_{ts}.md"
        path.write_text(markdown, encoding="utf-8")
        written["md"] = str(path)

    if "html" in formats:
        path = output_dir / f"compliance_report_{ts}.html"
        path.write_text(_render_html(data, markdown), encoding="utf-8")
        written["html"] = str(path)

    if "pdf" in formats:
        # PDF is optional and generated from the markdown/HTML via the pdf
        # skill — never hand-rolled. Not implemented in this offline/headless
        # environment (no access to /mnt/skills/public/pdf/SKILL.md tooling
        # here); report that honestly rather than fake a PDF file.
        written["pdf"] = "SKIPPED: pdf skill not available in this environment"

    return written


# ── CLI entry point ───────────────────────────────────────────────────────────


def compliance_report_main(argv: list[str] | None = None) -> int:
    """Entry point for `python3 -m bench_security compliance-report`."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Render a NIST/MITRE-Enterprise-OT-ICS/NERC-CIP compliance posture report "
        "from grounded purple results.",
    )
    parser.add_argument("--results", required=True, metavar="FILE", help="Purple results JSON file")
    parser.add_argument("--format", default="md", help="Comma-separated: md,html,pdf")
    parser.add_argument(
        "--framework", default="", help="Comma-separated filter: nist-800-53,nerc-cip,mitre-attack"
    )
    parser.add_argument(
        "--output-dir", default="", help="Override output directory (default: reports/)"
    )
    args = parser.parse_args(argv)

    formats = [f.strip() for f in args.format.split(",") if f.strip()]
    frameworks = [f.strip() for f in args.framework.split(",") if f.strip()] or None
    output_dir = Path(args.output_dir) if args.output_dir else None

    written = generate_report(args.results, formats, frameworks=frameworks, output_dir=output_dir)
    for fmt, path in written.items():
        print(f"{fmt}: {path}")
    return 0
