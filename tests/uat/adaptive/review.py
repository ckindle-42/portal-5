"""Adaptive UAT — operator review packet (TASK_UAT_ADAPTIVE_OVERHAUL_V1, Ph 5).

Consumes the standard UAT corpus (tests/uat_corpus/uat_<run>.jsonl) that the
OWUI runner emits, enriched with per-challenge ``rubric``/``dimension`` fields
(see tests/uat/calibration._emit_corpus_row). Produces:

  * a single self-contained HTML review packet grouped by space — prompt, the
    full OWUI response, a link to the actual chat, the machine-assertion result,
    and the rubric with numeric inputs + verdict selector, and
  * ADAPTIVE_UAT_RESULTS.md — the v9 release sign-off scorecard, including the
    designed-but-unreachable exposure-gap finding and an operator [GATE].

Pure rendering + aggregation — no model calls.
"""

from __future__ import annotations

import html
import json
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
REVIEW_DIR = _ROOT / "tests" / "uat_adaptive" / "review"
RESULTS_MD = _ROOT / "tests" / "ADAPTIVE_UAT_RESULTS.md"
UNREACHABLE_MANIFEST = _ROOT / "tests" / "uat_adaptive" / "designed_unreachable.json"


def load_corpus(corpus_path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in Path(corpus_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("adaptive"):  # only adaptive rows are reviewable here
            rows.append(row)
    return rows


def _esc(s: str) -> str:
    return html.escape(str(s or ""))


def _status_class(status: str) -> str:
    return {
        "PASS": "ok",
        "WARN": "warn",
        "FAIL": "bad",
        "BLOCKED": "blocked",
        "SKIP": "blocked",
        "MANUAL": "warn",
    }.get(status, "warn")


def _space_of(row: dict) -> str:
    """Derive the space id from a corpus row (rubric carries it)."""
    return (row.get("rubric") or {}).get("space_id") or row.get("workspace", "")


def _capability_of(row: dict) -> str:
    """The Portal capability area a challenge belongs to (its module)."""
    return (row.get("section", "") or "").replace("adaptive-", "") or "general"


def _final_verdict(row: dict) -> str:
    """Operator verdict if set, else the agent's first-pass proposal."""
    return row.get("operator_verdict") or row.get("agent_verdict") or ""


def _capability_status(chs: list[dict]) -> str:
    """Descriptive posture for a capability — acceptance itself is the operator's."""
    verdicts = [_final_verdict(c) for c in chs]
    assessed = [v for v in verdicts if v]
    if not assessed:
        return "pending review"
    if any(v == "FAIL" for v in assessed):
        return f"{sum(v == 'FAIL' for v in assessed)} FAIL — blocks acceptance"
    if len(assessed) < len(chs):
        return f"{len(assessed)}/{len(chs)} reviewed"
    if any(v == "PARTIAL" for v in assessed):
        return "all reviewed — PARTIALs to weigh"
    return "all PASS"


def render_html(rows: list[dict], run_id: str) -> str:
    rid = _esc(run_id)
    by_space: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_space[_space_of(r)].append(r)

    parts: list[str] = []
    parts.append(
        """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Adaptive UAT Review — __RID__</title>
<style>
 body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:1100px;
      margin:0 auto;padding:24px;background:#0d1117;color:#c9d1d9;}
 h1{border-bottom:2px solid #30363d;padding-bottom:8px;}
 a{color:#58a6ff;}
 .space{margin:28px 0;border:1px solid #30363d;border-radius:10px;overflow:hidden;}
 .space>summary{padding:12px 16px;background:#161b22;cursor:pointer;font-weight:600;}
 .ch{padding:14px 18px;border-top:1px solid #21262d;}
 .dim{display:inline-block;padding:2px 8px;border-radius:12px;background:#21262d;
      font-size:12px;text-transform:uppercase;letter-spacing:.5px;margin-right:8px;}
 .prompt{background:#161b22;border-left:3px solid #58a6ff;padding:10px 14px;
         margin:8px 0;white-space:pre-wrap;border-radius:0 6px 6px 0;}
 .resp{background:#0b0f14;border:1px solid #21262d;border-radius:6px;padding:10px 14px;
       max-height:360px;overflow:auto;white-space:pre-wrap;font-size:13px;}
 .ok{color:#3fb950;} .warn{color:#d29922;} .bad{color:#f85149;} .blocked{color:#a371f7;}
 .assert{font-size:12px;color:#8b949e;margin:6px 0;}
 .agent{background:#12261c;border:1px solid #1f3d2b;border-radius:6px;padding:8px 12px;
        margin:8px 0;font-size:13px;color:#aecfba;}
 td.ag{text-align:center;color:#7ee2a8;font-weight:600;}
 table.rub{width:100%;border-collapse:collapse;margin:10px 0;font-size:13px;}
 table.rub td,table.rub th{border:1px solid #30363d;padding:5px 8px;text-align:left;}
 .auto{color:#3fb950;font-weight:600;}
 input[type=number]{width:44px;background:#0b0f14;color:#c9d1d9;border:1px solid #30363d;
     border-radius:4px;padding:2px;}
 select,textarea{background:#0b0f14;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;}
 .bar{position:sticky;top:0;background:#0d1117;padding:8px 0;z-index:5;}
 button{background:#238636;color:#fff;border:0;border-radius:6px;padding:8px 16px;
        cursor:pointer;font-weight:600;}
</style></head><body>
<div class="bar"><h1>Portal 5 Capability UAT — Acceptance — __RID__</h1>
<button onclick="dump()">Export verdicts JSON</button>
<span id="prog" style="margin-left:14px;color:#8b949e;"></span></div>
<p style="color:#8b949e">User acceptance test of Portal's capabilities, run by an
independent agent on your behalf through OWUI. The agent proposed a score and
verdict for each challenge; confirm or override, then Export verdicts JSON and
ingest it. Auto criteria come from machine checks.</p>
""".replace("__RID__", rid)
    )

    for space_id, chs in sorted(by_space.items()):
        name = chs[0].get("test_name", space_id).split(" — ")[0]
        module = (chs[0].get("section", "") or "").replace("adaptive-", "")
        parts.append(
            f'<details class="space" open><summary>{_esc(name)} '
            f'<span class="dim">{_esc(module)}</span> '
            f'<span class="dim">{_esc(space_id)}</span> · {len(chs)} challenges</summary>'
        )
        for r in chs:
            cid = r.get("test_id", "")
            status = r.get("status", "")
            dim = r.get("dimension", "")
            chat = r.get("chat_url", "")
            parts.append(f'<div class="ch" data-cid="{_esc(cid)}">')
            link = f' · <a href="{_esc(chat)}" target="_blank">open chat</a>' if chat else ""
            parts.append(
                f'<span class="dim">{_esc(dim)}</span><b>{_esc(cid)}</b> · machine: '
                f'<span class="{_status_class(status)}">{_esc(status)}</span>{link}'
            )
            parts.append(f'<div class="prompt">{_esc(r.get("prompt", ""))}</div>')
            parts.append(f'<div class="resp">{_esc(r.get("response_text", ""))}</div>')
            for a in r.get("assertions_result", []):
                lab, ok = (a[0], a[1]) if len(a) >= 2 else (str(a), False)
                cls = "ok" if ok else "bad"
                parts.append(f'<div class="assert"><span class="{cls}">●</span> {_esc(lab)}</div>')

            rub = r.get("rubric", {}) or {}
            autos = r.get("auto_scores", {}) or {}
            agent_scores = r.get("agent_scores", {}) or {}
            agent_verdict = r.get("agent_verdict", "")
            agent_rationale = r.get("agent_rationale", "")
            if agent_rationale or agent_verdict:
                parts.append(
                    f'<div class="agent"><b>Agent assessment</b> '
                    f'<span class="dim">{_esc(agent_verdict)}</span> '
                    f"{_esc(agent_rationale)}</div>"
                )
            parts.append(
                '<table class="rub"><tr><th>Criterion</th><th>Guidance</th>'
                "<th>Wt</th><th>Agent</th><th>Operator 1-5</th></tr>"
            )
            for c in rub.get("criteria", []):
                key = c["key"]
                # operator field defaults to the agent's proposal, else the auto value
                pre = agent_scores.get(key, autos.get(key, ""))
                ag = agent_scores.get(key, "")
                auto_tag = ' <span class="auto">(auto)</span>' if c.get("auto") else ""
                parts.append(
                    f"<tr><td>{_esc(c.get('label', key))}{auto_tag}</td>"
                    f"<td>{_esc(c.get('guidance', ''))}</td><td>{c.get('weight', 1)}</td>"
                    f'<td class="ag">{ag}</td>'
                    f'<td><input type="number" min="1" max="5" class="score" '
                    f'data-key="{_esc(key)}" value="{pre}"></td></tr>'
                )
            parts.append("</table>")
            # operator verdict defaults to the agent's verdict
            vsel = "".join(
                f"<option{' selected' if agent_verdict == v else ''}>{v}</option>"
                for v in ("PASS", "PARTIAL", "FAIL")
            )
            parts.append(
                f'<div>Verdict: <select class="verdict"><option value=""></option>{vsel}'
                "</select> "
                'Notes: <textarea class="notes" rows="1" cols="60"></textarea></div>'
            )
            parts.append("</div>")
        parts.append("</details>")

    parts.append(
        """<script>
function collect(){const out=[];document.querySelectorAll('.ch').forEach(ch=>{
 const scores={};ch.querySelectorAll('.score').forEach(i=>{if(i.value)scores[i.dataset.key]=+i.value;});
 out.push({test_id:ch.dataset.cid,operator_scores:scores,
   operator_verdict:ch.querySelector('.verdict').value,
   operator_notes:ch.querySelector('.notes').value});});return out;}
function dump(){const blob=new Blob([JSON.stringify(collect(),null,2)],{type:'application/json'});
 const a=document.createElement('a');a.href=URL.createObjectURL(blob);
 a.download='verdicts___RID__.json';a.click();}
function prog(){const all=document.querySelectorAll('.ch').length;let done=0;
 document.querySelectorAll('.verdict').forEach(v=>{if(v.value)done++;});
 document.getElementById('prog').textContent=done+' / '+all+' reviewed';}
document.addEventListener('change',prog);prog();
</script></body></html>""".replace("__RID__", rid)
    )
    return "\n".join(parts)


def write_review_packet(corpus_path: Path) -> Path:
    rows = load_corpus(corpus_path)
    run_id = rows[0].get("corpus_run_id", "unknown") if rows else "unknown"
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    out = REVIEW_DIR / f"review_{run_id}.html"
    out.write_text(render_html(rows, run_id), encoding="utf-8")
    return out


def ingest_verdicts(corpus_path: Path, verdicts_json: Path) -> Path:
    """Merge an exported verdicts JSON back into the corpus, in place."""
    verdicts = {v["test_id"]: v for v in json.loads(Path(verdicts_json).read_text())}
    lines = Path(corpus_path).read_text(encoding="utf-8").splitlines()
    out_lines: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        v = verdicts.get(row.get("test_id"))
        if v and row.get("adaptive"):
            row["operator_scores"] = v.get("operator_scores", {})
            row["operator_verdict"] = v.get("operator_verdict", "")
            row["operator_notes"] = v.get("operator_notes", "")
        out_lines.append(json.dumps(row, ensure_ascii=False))
    Path(corpus_path).write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return corpus_path


def _weighted(row: dict) -> float:
    rub = {c["key"]: c.get("weight", 1.0) for c in (row.get("rubric") or {}).get("criteria", [])}
    # precedence: auto < agent < operator (later overrides earlier)
    scores = dict(row.get("auto_scores", {}) or {})
    scores.update(row.get("agent_scores", {}) or {})
    scores.update(row.get("operator_scores", {}) or {})
    num = sum(scores.get(k, 0) * w for k, w in rub.items() if k in scores)
    den = sum(w for k, w in rub.items() if k in scores)
    return round(num / den, 2) if den else 0.0


def rollup_markdown(corpus_path: Path) -> Path:
    rows = load_corpus(corpus_path)
    run_id = rows[0].get("corpus_run_id", "unknown") if rows else "unknown"
    by_space: dict[str, list[dict]] = defaultdict(list)
    by_capability: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_space[_space_of(r)].append(r)
        by_capability[_capability_of(r)].append(r)

    lines = [
        f"# Portal 5 — Capability UAT — v9 Release Acceptance — {run_id}",
        "",
        "User acceptance test of Portal's capabilities, conducted by an independent",
        "Claude Code agent on the operator's behalf, exercising each capability through",
        "OWUI the way it is meant to be used. `Machine` is auto assertions; `Agent` is",
        "the independent agent's first-pass verdict; `Operator` is the human sign-off",
        "(defaults to the agent's proposal until changed). Acceptance is the operator's",
        "call at the `[GATE]` below. PROMOTE_POLICY=confirm — nothing auto-promotes.",
        "",
        "## Capability acceptance — does Portal do what it's for?",
        "",
        "Each row is one Portal capability area (module). This is the view to accept",
        "v9 against: a capability is acceptable when its challenges are reviewed with no",
        "FAILs. Per-space evidence follows below.",
        "",
        "| Capability | Spaces | Chal. | Machine PASS | Reviewed | Avg (1-5) | Status |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for cap, chs in sorted(by_capability.items()):
        spaces = len({_space_of(c) for c in chs})
        mpass = sum(1 for c in chs if c.get("status") == "PASS")
        reviewed = [c for c in chs if _final_verdict(c)]
        avg = round(sum(_weighted(c) for c in reviewed) / len(reviewed), 2) if reviewed else None
        lines.append(
            f"| {cap} | {spaces} | {len(chs)} | {mpass}/{len(chs)} | "
            f"{len(reviewed)}/{len(chs)} | {avg if avg is not None else '—'} "
            f"| {_capability_status(chs)} |"
        )
    lines += [
        "",
        "## Per-space evidence",
        "",
        "Each row is one space (workspace or persona) that implements part of a",
        "capability, tested with deep, intended-use challenges through OWUI.",
        "",
        "| Space | Module | Chal. | Machine PASS | Agent | Operator | Avg (1-5) | Verdicts |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    total = agent_done = op_done = 0
    for sid, chs in sorted(by_space.items()):
        total += len(chs)
        mpass = sum(1 for c in chs if c.get("status") == "PASS")
        agentd = [c for c in chs if c.get("agent_verdict")]
        opd = [c for c in chs if c.get("operator_verdict")]
        agent_done += len(agentd)
        op_done += len(opd)
        # final verdict per challenge: operator if set, else agent
        final = [c for c in chs if c.get("operator_verdict") or c.get("agent_verdict")]
        avg = round(sum(_weighted(c) for c in final) / len(final), 2) if final else None
        vc: dict[str, int] = defaultdict(int)
        for c in final:
            vc[c.get("operator_verdict") or c.get("agent_verdict")] += 1
        vstr = ", ".join(f"{k}:{v}" for k, v in sorted(vc.items())) or "—"
        name = chs[0].get("test_name", sid).split(" — ")[0]
        module = (chs[0].get("section", "") or "").replace("adaptive-", "")
        lines.append(
            f"| {name} | {module} | {len(chs)} | {mpass}/{len(chs)} | "
            f"{len(agentd)}/{len(chs)} | {len(opd)}/{len(chs)} | "
            f"{avg if avg is not None else '—'} | {vstr} |"
        )

    lines += [
        "",
        f"**Totals:** {total} challenges across {len(by_space)} spaces · "
        f"{agent_done}/{total} agent-assessed · {op_done}/{total} operator-confirmed.",
        "",
    ]

    # Exposure-gap finding: designed but not reachable in OWUI.
    if UNREACHABLE_MANIFEST.exists():
        try:
            un = json.loads(UNREACHABLE_MANIFEST.read_text())
        except Exception:
            un = []
        if un:
            lines += [
                "## Exposure-gap finding — designed but not OWUI-addressable",
                "",
                f"{len(un)} spaces have a system prompt / declared purpose but no OWUI",
                "workspace or ide_expose signal, so they are not selectable in OWUI and",
                "were not executed. Before the clean-slate migration, decide per space:",
                "expose it, retire it, or accept it as internal-only.",
                "",
                "| Space | Module | Kind |",
                "|---|---|---|",
            ]
            for u in sorted(un, key=lambda x: (x.get("module", ""), x.get("space_id", ""))):
                lines.append(
                    f"| {u.get('name', u.get('space_id'))} | {u.get('module', '')} "
                    f"| {u.get('kind', '')} |"
                )
            lines.append("")

    lines += [
        "## Operator acceptance",
        "",
        "`[GATE]` v9 acceptance is the operator's decision. Confirm the verdicts (the",
        "agent proposed them; override where you disagree), then accept Portal",
        "capability by capability using the top table — a capability is acceptable when",
        "its challenges are reviewed with no FAILs. Resolve or accept each exposure-gap",
        "entry. Record the outcome here, e.g.:",
        "",
        "`ACCEPTED <date> — capabilities [security, compliance, cad, coding, research,",
        "documents] accepted for v9; [image] deferred; K exposure gaps accepted.`",
        "",
        "Do not auto-promote any model or space on the basis of this run.",
        "",
    ]
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")
    return RESULTS_MD
