"""QAT report writers: results.jsonl, QAT_REPORT.md, review.html.

The markdown report is the capability-by-capability acceptance matrix with
exposure gaps and categorized defects; review.html is the operator [GATE]
sign-off packet with an exportable verdicts JSON and a screenshot gallery.
"""

from __future__ import annotations

import html
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .config import Discovery
from .models import QATResult, QATScenario, Status

VERDICT_STATUSES: tuple[Status, ...] = (
    Status.PASS,
    Status.WARN,
    Status.FAIL,
    Status.SKIP,
    Status.BLOCKED,
)


def write_results_jsonl(run_dir: Path, results: list[QATResult]) -> Path:
    path = run_dir / "results.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row in results:
            fh.write(json.dumps(row.to_dict(), sort_keys=True) + "\n")
    return path


def capability(scenario: QATScenario) -> str:
    """Capability column: stage + phase + workspace family."""
    family = scenario.model_slug.split("::")[0]
    return f"stage {scenario.stage} · {scenario.phase} · {family}"


def write_markdown(
    run_dir: Path,
    discovery: Discovery,
    scenarios: list[QATScenario],
    results: list[QATResult],
    provenance: dict[str, object] | None = None,
) -> Path:
    by_id = {r.scenario_id: r for r in results}
    counts = Counter(r.status.value for r in results)
    failed_rows = [row for row in results if row.status is Status.FAIL]
    defects = Counter(
        row.defect_class.value if row.defect_class else "UNCLASSIFIED" for row in failed_rows
    )
    lines: list[str] = [
        "# Portal 5 — Release 1.0 QAT Report",
        "",
        f"Generated: {datetime.now(tz=UTC).isoformat(timespec='seconds')}",
        "",
        f"Verdict: **{counts['PASS']} PASS / {counts['WARN']} WARN / {counts['FAIL']} FAIL"
        f" / {counts['SKIP']} SKIP / {counts['BLOCKED']} BLOCKED**"
        f" over {len(results)} scenarios.",
        "",
    ]
    if provenance:
        sha = str(provenance.get("git_sha") or "")
        lines += [
            "## Run provenance",
            "",
            f"- this run's git sha: {sha or 'unknown (no git metadata)'}",
            f"- created: {provenance.get('created_at', '')}",
        ]
        resume_dir = str(provenance.get("resume_dir") or "")
        if resume_dir:
            resume_sha = str(provenance.get("resume_sha") or "")
            lines.append(
                f"- stitched rows: {provenance.get('stitched_rows', 0)} of {len(results)} "
                f"from {resume_dir} ({provenance.get('resume_mode')}), graded by that run — "
                f"its git sha: {resume_sha or 'unknown (predates provenance records)'}"
            )
    lines += [
        "## Acceptance matrix (capability by capability)",
        "",
        "| Capability | Scenario | Model | Status | Detail |",
        "|---|---|---|---|---|",
    ]
    for scenario in scenarios:
        row = by_id.get(scenario.scenario_id)
        if row is None:
            continue
        detail = row.detail.replace("|", "\\|")[:160]
        model = row.served_model or scenario.model_slug
        lines.append(
            f"| {capability(scenario)} | {scenario.scenario_id} | {model} "
            f"| {row.status.value} | {detail} |"
        )
    lines += ["", "## Exposure gaps (designed vs seeded)", ""]
    if discovery.gaps:
        lines += [f"- {gap}" for gap in discovery.gaps]
    else:
        lines.append("- none: designed roster == OWUI presets")
    lines += ["", "## Categorized defects (FAIL rows)", ""]
    if failed_rows:
        lines += [f"- {kind}: {count}" for kind, count in sorted(defects.items())]
        lines += ["", "| Scenario | Defect class | Detail |", "|---|---|---|"]
        for scenario in scenarios:
            row = by_id.get(scenario.scenario_id)
            if row is None or row.status is not Status.FAIL:
                continue
            klass = row.defect_class.value if row.defect_class else "UNCLASSIFIED"
            lines.append(f"| {scenario.scenario_id} | {klass} | {row.detail[:120]} |")
    else:
        lines.append("- none recorded")
    annotations = [
        scenario.notes for scenario in scenarios if scenario.notes and scenario.scenario_id in by_id
    ]
    if annotations:
        lines += ["", "## Annotations", ""]
        lines += [f"- {html.escape(a)}" for a in dict.fromkeys(annotations)]
    path = run_dir / "QAT_REPORT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _verdicts_json(results: list[QATResult]) -> str:
    payload = [row.to_dict() for row in results]
    return json.dumps(payload, indent=2).replace("</", "<\\/")


def write_review_html(
    run_dir: Path,
    scenarios: list[QATScenario],
    results: list[QATResult],
    shots_dir: Path | None = None,
) -> Path:
    by_id = {r.scenario_id: r for r in results}
    rows: list[str] = []
    for scenario in scenarios:
        row = by_id.get(scenario.scenario_id)
        if row is None:
            continue
        rows.append(
            f"<tr class='{row.status.value.lower()}'><td>{html.escape(scenario.scenario_id)}"
            f"</td><td>{html.escape(scenario.model_slug)}</td>"
            f"<td>{row.status.value}</td><td>{html.escape(row.detail[:200])}</td>"
            f"<td><select data-sid='{html.escape(scenario.scenario_id)}'>"
            + "<option selected>PENDING</option>"
            + "".join(f"<option>{s.value}</option>" for s in VERDICT_STATUSES)
            + "</select></td></tr>"
        )
    shots: list[str] = []
    if shots_dir is not None and shots_dir.is_dir():
        shots = [
            f"<figure><img src='screenshots/{html.escape(p.name)}' "
            f"alt='{html.escape(p.stem)}'><figcaption>{html.escape(p.stem)}</figcaption></figure>"
            for p in sorted(shots_dir.glob("*.png"))
        ]
    body = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>QAT Release 1.0 — Gate sign-off</title>
<style>
body{{font-family:monospace;margin:2rem}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:.3rem .5rem;text-align:left}}
tr.fail{{background:#fdd}}tr.blocked{{background:#fbb}}tr.warn{{background:#ffd}}
tr.pass{{background:#dfd}}tr.skip{{background:#eee}}
select{{width:7rem}}figure{{margin:.5rem;display:inline-block}}
img{{max-width:320px;border:1px solid #999}}
</style></head><body>
<h1>QAT Release 1.0 — operator [GATE] sign-off packet</h1>
<p>Set each verdict, then export. Exported verdicts JSON drops next to this file.</p>
<table><thead><tr><th>Scenario</th><th>Model</th><th>Runner status</th>
<th>Detail</th><th>Operator verdict</th></tr></thead><tbody>
{"".join(rows)}
</tbody></table>
<h2>Screenshot gallery</h2>
<div id='gallery'>{"".join(shots) or "<p>(no screenshots in this run)</p>"}</div>
<button onclick='exportVerdicts()'>Export verdicts JSON</button>
<script id='verdicts' type='application/json'>{_verdicts_json(results)}</script>
<script>
function exportVerdicts() {{
  const rows = document.querySelectorAll('tbody tr');
  const verdicts = {{}};
  rows.forEach(r => {{
    const sel = r.querySelector('select');
    if (sel) verdicts[sel.dataset.sid] = sel.value;
  }});
  const blob = new Blob([JSON.stringify(verdicts, null, 2)], {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'gate_verdicts.json';
  a.click();
}}
</script></body></html>
"""
    path = run_dir / "review.html"
    path.write_text(body, encoding="utf-8")
    return path


def write_reports(
    run_dir: Path,
    discovery: Discovery,
    scenarios: list[QATScenario],
    results: list[QATResult],
    shots_dir: Path | None = None,
    provenance: dict[str, object] | None = None,
) -> dict[str, Path]:
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "jsonl": write_results_jsonl(run_dir, results),
        "markdown": write_markdown(run_dir, discovery, scenarios, results, provenance),
        "html": write_review_html(run_dir, scenarios, results, shots_dir),
    }
