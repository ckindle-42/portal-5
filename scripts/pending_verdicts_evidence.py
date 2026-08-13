#!/usr/bin/env python3
"""Mine per-model evidence from PENDING_MODEL_VERDICTS.md into a decision sheet.

For each entry in config/PENDING_MODEL_VERDICTS.md, walks its cited evidence
files and extracts:

    * avg_tps + quality_score aggregated across bench_tps JSON per-model rows
      that match the tag or a same-lane bench workspace slug
    * a closeout-report verdict signal (promote-candidate | pass | decline |
      stage-pending | blocked | follow-on) if any BATCH_BENCH_*.md,
      *_CLOSEOUT_*.md, or capability report names the tag in a verdict column
    * newest-evidence-date per row (parsed from evidence filename YYYYMMDD or
      mtime fallback) — drives the freshness safety flag
    * the bench-* workspace(s) that route to this model in config/portal.yaml
    * a same-lane production incumbent (the production workspace's model_hint
      whose module tag matches the bench-* workspace's) + that incumbent's
      most recent avg_tps / quality_score for a side-by-side delta

Emits reports/PENDING_VERDICTS_EVIDENCE_<UTC>.md — biggest-reclaim-first,
with a data-driven suggested verdict per row. Vocabulary the executor
accepts:

    decline              — evidence supports removal
    promote              — evidence shows a real edge; wire in a follow-on task
    keep-open            — active investigation; retain
    investigate          — no clear signal; needs another bench
    investigate-refresh  — evidence exists but is >60 days old; re-bench
                           against current fleet before verdict

Never writes to config/PENDING_MODEL_VERDICTS.md. Never calls ollama.
Read-only outside of reports/ (gitignored per repo convention).
"""

from __future__ import annotations

import datetime as _dt
import glob
import json
import re
import statistics
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / "config" / "PENDING_MODEL_VERDICTS.md"
PORTAL_PATH = REPO_ROOT / "config" / "portal.yaml"

ENTRY_RE = re.compile(r"^- \[[x ]\] `([^`]+)` — ([\d.]+) GB")
EVIDENCE_RE = re.compile(r"^  - evidence: `([^`]+)`")
TS_RE = re.compile(r"(20\d{6})T?\d*Z?")

STALE_DAYS = 60
# Evidence from before STACK_BOUNDARY_DAYS ago is INVALID (not just stale).
# The Ollama + oMLX stack changed materially — TPS and quality numbers
# captured under a prior stack do not reflect current behavior. Numeric
# averages skip pre-boundary rows entirely; decline suggestions require at
# least one post-boundary row. Override with --stack-boundary-days on the
# CLI when the stack has been stable long enough that the window can widen.
STACK_BOUNDARY_DAYS = 3


def parse_ledger() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    entries: list[dict] = []
    cur = None
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        m = ENTRY_RE.match(line)
        if m:
            cur = {"tag": m.group(1), "size_gb": float(m.group(2)), "evidence": []}
            entries.append(cur)
            continue
        me = EVIDENCE_RE.match(line)
        if me and cur is not None:
            cur["evidence"].append(me.group(1))
    return entries


def bench_workspaces_by_tag() -> dict[str, list[str]]:
    d = yaml.safe_load(PORTAL_PATH.read_text())
    out: dict[str, list[str]] = {}
    for slug, spec in d.get("workspaces", {}).items():
        if not slug.startswith("bench-"):
            continue
        hint = spec.get("model_hint")
        if hint:
            out.setdefault(hint.lower(), []).append(slug)
        for var in (spec.get("variants") or {}).values():
            if isinstance(var, dict) and var.get("model_hint"):
                out.setdefault(var["model_hint"].lower(), []).append(slug)
    return out


def workspace_modules() -> dict[str, tuple[str, ...]]:
    d = yaml.safe_load(PORTAL_PATH.read_text())
    return {slug: tuple(spec.get("tags") or []) for slug, spec in d.get("workspaces", {}).items()}


def production_incumbents_by_module() -> dict[str, list[dict]]:
    d = yaml.safe_load(PORTAL_PATH.read_text())
    out: dict[str, list[dict]] = {}
    for slug, spec in d.get("workspaces", {}).items():
        if slug.startswith("bench-"):
            continue
        hint = spec.get("model_hint")
        if not hint:
            continue
        for tag in spec.get("tags") or []:
            out.setdefault(tag, []).append({"workspace": slug, "model_hint": hint})
    return out


def evidence_date(rel_path: str) -> _dt.date | None:
    """Extract YYYYMMDD from evidence filename; fall back to file mtime."""
    m = TS_RE.search(rel_path)
    if m:
        try:
            return _dt.datetime.strptime(m.group(1), "%Y%m%d").date()
        except ValueError:
            pass
    p = REPO_ROOT / rel_path
    try:
        return _dt.date.fromtimestamp(p.stat().st_mtime)
    except OSError:
        return None


def harness_of(rel_path: str) -> str:
    """Infer which bench harness produced a results file from its filename
    prefix. TASK_BENCH_VALIDITY_V1: harness provenance drives the coherence
    gate — a bench_tps row is not valid evidence for a capability that needs
    a dedicated probe."""
    base = rel_path.rsplit("/", 1)[-1]
    for prefix, harness in (
        ("bench_tps_", "bench_tps"),
        ("mtp_probe_", "mtp_probe"),
        ("vision_probe_", "vision_probe"),
        ("refusal_preservation_probe_", "refusal_preservation_probe"),
        ("long_context_probe_", "long_context_probe"),
        ("cad_probe_", "cad_probe"),
        ("fara_cua_probe_", "fara_cua_probe"),
        ("security_exec_probe_", "security_exec_probe"),
        ("tool_use_probe_", "tool_use_probe"),
        ("reasoning_probe_", "reasoning_probe"),
        ("cad_probe_", "cad_probe"),
        ("spl_probe_", "spl_probe"),
        ("compliance_probe_", "compliance_probe"),
        ("data_probe_", "data_probe"),
        ("research_probe_", "research_probe"),
        ("persona_matrix_", "persona_matrix"),
        ("v11_capability_", "capability_probe"),
    ):
        if base.startswith(prefix):
            return harness
    return "unknown"


def mine_tps_json(path: Path, needles: set[str]) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("results") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    rel = str(path.relative_to(REPO_ROOT))
    harness = harness_of(rel)
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        model_l = str(r.get("model") or "").lower()
        routed_l = str(r.get("routed_model") or "").lower()
        if not any(n in model_l or n in routed_l for n in needles):
            continue
        out.append(
            {
                "path": rel,
                "harness": harness,
                "model": r.get("model"),
                "avg_tps": r.get("avg_tps"),
                "quality_score": r.get("quality_score"),
                "runs_success": r.get("runs_success"),
                "runs_total": r.get("runs_total"),
                "prompt_category": r.get("prompt_category"),
            }
        )
    return out


VERDICT_TOKENS = (
    "promote-candidate",
    "promote candidate",
    "decline",
    "declined",
    "not.adopted",
    "not adopted",
    "stage-pending",
    "stage pending",
    "blocked",
    "follow-on",
    "follow on",
    "pass",
)


def mine_closeout_verdict(path: Path, tag: str) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    tl = text.lower()
    tag_l = tag.lower()
    candidates = [tag_l]
    if "/" in tag_l:
        candidates.append(tag_l.rsplit("/", 1)[-1].split(":", 1)[0])
    for needle in candidates:
        idx = tl.find(needle)
        if idx == -1:
            continue
        # A "final verdict" marker near the tag supersedes the window below —
        # reports that retract an early verdict (e.g. "declined ... **wrong**")
        # would otherwise mine the retracted word. Closest-to-marker wins, not
        # VERDICT_TOKENS priority order, since "decline" is a substring of an
        # unrelated later word like "declines" too.
        wide = tl[max(0, idx - 2000) : idx + 2000]
        fv_idx = wide.find("final verdict")
        if fv_idx != -1:
            fv_window = wide[fv_idx : fv_idx + 200]
            hits = [(fv_window.find(t), t) for t in VERDICT_TOKENS if t in fv_window]
            if hits:
                _, token = min(hits)
                return token.replace(" ", "-")
        window = tl[max(0, idx - 400) : idx + 400]
        for token in VERDICT_TOKENS:
            if token in window:
                return token.replace(" ", "-")
    return None


def collect_evidence(
    tag: str,
    evidence_paths: list[str],
    bench_slugs: list[str],
    stack_boundary_days: int = STACK_BOUNDARY_DAYS,
) -> dict:
    needles = {tag.lower(), *(s.lower() for s in bench_slugs)}
    tps_rows: list[dict] = []  # every row, tagged with its evidence date
    verdicts: list[tuple[str, str, _dt.date | None]] = []  # (verdict, path, date)
    dates: list[_dt.date] = []
    today = _dt.date.today()
    boundary = today - _dt.timedelta(days=stack_boundary_days)

    for rel in evidence_paths:
        p = REPO_ROOT / rel
        if not p.exists():
            continue
        d = evidence_date(rel)
        if d:
            dates.append(d)
        if p.suffix == ".json":
            for r in mine_tps_json(p, needles):
                r["evidence_date"] = d.isoformat() if d else None
                r["valid"] = d is not None and d >= boundary
                tps_rows.append(r)
        elif p.suffix in {".md", ".txt"}:
            v = mine_closeout_verdict(p, tag)
            if v:
                verdicts.append((v, rel, d))

    valid_rows = [r for r in tps_rows if r["valid"]]
    invalid_rows = [r for r in tps_rows if not r["valid"]]

    def _avg(xs: list) -> float | None:
        xs = [x for x in xs if isinstance(x, (int, float))]
        return round(statistics.mean(xs), 2) if xs else None

    newest = max(dates) if dates else None
    oldest = min(dates) if dates else None
    age_days = (today - newest).days if newest else None
    newest_valid = max((d for d in dates if d >= boundary), default=None)

    return {
        "tps_rows": tps_rows,
        "n_rows": len(tps_rows),
        "n_valid_rows": len(valid_rows),
        "n_invalid_rows": len(invalid_rows),
        # averages computed ONLY over post-boundary rows — pre-boundary
        # numbers were captured under a materially different stack and
        # are not comparable
        "avg_tps": _avg([r["avg_tps"] for r in valid_rows]),
        "avg_quality": _avg([r["quality_score"] for r in valid_rows]),
        # legacy fields kept for compatibility; consumers should prefer
        # avg_tps/avg_quality above, which are post-boundary-only
        "avg_tps_all": _avg([r["avg_tps"] for r in tps_rows]),
        "verdicts": [(v, rel) for v, rel, _ in verdicts],  # legacy tuple shape
        "verdicts_dated": verdicts,  # (v, rel, date)
        "verdicts_valid": [(v, rel) for v, rel, d in verdicts if d is not None and d >= boundary],
        "verdicts_invalid": [(v, rel) for v, rel, d in verdicts if d is None or d < boundary],
        "newest_date": newest,
        "oldest_date": oldest,
        "newest_age_days": age_days,
        "newest_valid_date": newest_valid,
        "stack_boundary_date": boundary.isoformat(),
        "stack_boundary_days": stack_boundary_days,
        "has_valid_evidence": len(valid_rows) > 0
        or any(d is not None and d >= boundary for _, _, d in verdicts),
    }


def _compare_to_incumbent(
    tps: float, q: float | None, incumbent_tps: dict, pre_note: str | None
) -> tuple[str, str]:
    inc_tps = incumbent_tps["avg_tps"]
    inc_q = incumbent_tps.get("avg_quality")
    tps_delta = round(tps - inc_tps, 2)
    q_delta = round((q or 0) - (inc_q or 0), 2) if q is not None and inc_q is not None else None
    if q_delta is not None and q_delta <= -0.1 and tps_delta <= 0:
        return (
            "decline",
            f"post-boundary: quality Δ={q_delta} + tps Δ={tps_delta} vs incumbent {incumbent_tps['tag']} — no edge either axis"
            + (f"; {pre_note}" if pre_note else ""),
        )
    if q_delta is not None and q_delta >= 0.1 and tps_delta >= 0:
        return (
            "promote",
            f"post-boundary: quality Δ=+{q_delta} + tps Δ=+{tps_delta} vs incumbent {incumbent_tps['tag']} — real edge",
        )
    return (
        "investigate",
        f"post-boundary mixed: quality Δ={q_delta} tps Δ={tps_delta} vs {incumbent_tps['tag']}",
    )


def _pre_boundary_note(ev: dict) -> str | None:
    if not ev["verdicts_invalid"]:
        return None
    v, src = ev["verdicts_invalid"][0]
    return f"pre-boundary closeout signal '{v}' in {src} — captured under prior stack, re-affirm before treating as authoritative"


def _no_valid_evidence_verdict(ev: dict, pre_note: str | None) -> tuple[str, str]:
    if ev["n_invalid_rows"]:
        reason = f"only pre-boundary evidence ({ev['n_invalid_rows']} rows before {ev['stack_boundary_date']}); re-bench required"
    else:
        reason = "no numeric evidence at all; manual review or re-bench"
    if pre_note:
        reason = f"{reason}; {pre_note}"
    return "investigate-refresh", reason


def suggest_verdict(tag: str, ev: dict, incumbent_tps: dict | None) -> tuple[str, str]:
    """Data-driven suggestion — never a decision.

    Freshness gate: evidence older than the stack boundary is INVALID —
    the Ollama+oMLX stack changed materially and old TPS/quality readings
    do not reflect current behavior. Numeric-driven declines require at
    least one post-boundary row; otherwise suggestion downgrades to
    investigate-refresh (re-bench first).

    Closeout hard signals from before the boundary are surfaced but are
    NOT treated as authoritative — the human decided under numbers that
    no longer hold.
    """
    # Post-boundary closeout signals first — these are current-stack decisions
    hard_decline = next(
        (v for v, _ in ev["verdicts_valid"] if v in ("decline", "declined", "not-adopted")),
        None,
    )
    if hard_decline:
        return "decline", f"post-boundary closeout already declined ({hard_decline})"

    if any(v == "promote-candidate" for v, _ in ev["verdicts_valid"]):
        return (
            "promote",
            "post-boundary closeout marked promote-candidate; wire per PROMOTE_POLICY=confirm",
        )

    if any(v == "stage-pending" for v, _ in ev["verdicts_valid"]):
        return "keep-open", "post-boundary closeout stage-pending; retain until gate clears"

    if any(v == "follow-on" for v, _ in ev["verdicts_valid"]):
        return (
            "investigate",
            "post-boundary closeout follow-on; deeper eval required before verdict",
        )

    # Pre-boundary closeout signals — surface but do not decide on them
    pre_note = _pre_boundary_note(ev)

    if not ev["has_valid_evidence"]:
        # No post-boundary numeric evidence at all — cannot decide numerically
        return _no_valid_evidence_verdict(ev, pre_note)

    tps = ev["avg_tps"]  # already post-boundary-only
    q = ev["avg_quality"]

    if tps is None and q is None and ev["n_valid_rows"] == 0:
        return "investigate", "no post-boundary numeric evidence extractable; manual review"

    if incumbent_tps and incumbent_tps.get("avg_tps") and tps:
        return _compare_to_incumbent(tps, q, incumbent_tps, pre_note)

    if tps and tps < 20:
        return (
            "decline",
            f"post-boundary: below 20 t/s floor (avg {tps} across {ev['n_valid_rows']} valid rows)"
            + (f"; {pre_note}" if pre_note else ""),
        )

    return (
        "investigate",
        f"post-boundary evidence (tps={tps}, q={q}, n={ev['n_valid_rows']}) but no incumbent to compare",
    )


def latest_tps_for_tag(tag: str, needles: set[str]) -> dict | None:
    files = sorted(
        glob.glob(str(REPO_ROOT / "tests/benchmarks/results/bench_tps_*.json")),
        reverse=True,
    )
    for f in files[:30]:
        rows = mine_tps_json(Path(f), needles)
        if rows:
            avg_tps = (
                statistics.mean(
                    [r["avg_tps"] for r in rows if isinstance(r.get("avg_tps"), (int, float))]
                    or [0]
                )
                or None
            )
            avg_q = (
                statistics.mean(
                    [
                        r["quality_score"]
                        for r in rows
                        if isinstance(r.get("quality_score"), (int, float))
                    ]
                    or [0]
                )
                or None
            )
            return {
                "tag": tag,
                "avg_tps": round(avg_tps, 2) if avg_tps else None,
                "avg_quality": round(avg_q, 2) if avg_q else None,
                "source": str(Path(f).relative_to(REPO_ROOT)),
            }
    return None


def render_sheet(rows: list[dict], stack_boundary_days: int) -> str:
    total_gb = sum(r["size_gb"] for r in rows)
    boundary_date = (_dt.date.today() - _dt.timedelta(days=stack_boundary_days)).isoformat()
    n_no_valid = sum(1 for r in rows if not r["evidence_summary"]["has_valid_evidence"])
    n_only_invalid = sum(
        1
        for r in rows
        if r["evidence_summary"]["n_invalid_rows"] > 0
        and r["evidence_summary"]["n_valid_rows"] == 0
    )
    out = [
        f"# Pending model verdicts — decision-support sheet ({_dt.datetime.now(_dt.UTC).strftime('%Y-%m-%d %H:%M')} UTC)",
        "",
        f"{len(rows)} pending entries, {total_gb:.1f} GB total reclaim potential.",
        "",
        "## ⚠ Stack boundary in effect",
        "",
        f"**Boundary date: {boundary_date}** (`--stack-boundary-days={stack_boundary_days}`).",
        "",
        "The Ollama + oMLX inference stack has changed materially. Evidence",
        "captured before the boundary was measured under a prior stack and",
        "**does not reflect current behavior**. All TPS/quality averages in",
        "this sheet are computed over post-boundary rows only; pre-boundary",
        "rows are counted but excluded from decision math. Numeric-driven",
        "decline suggestions require ≥1 post-boundary row — otherwise the",
        "suggestion downgrades to `investigate-refresh` (re-bench first).",
        "",
        f"Models with NO post-boundary evidence: **{n_no_valid} / {len(rows)}**"
        + (f" (of which {n_only_invalid} have only pre-boundary data)" if n_only_invalid else ""),
        "",
        "If most pending models fall into that bucket, a fleet-wide bench",
        "sweep is the real prerequisite — this task will otherwise mostly",
        "emit `investigate-refresh` suggestions.",
        "",
        "## How to use",
        "",
        "For each row, review the mined evidence + suggested verdict, then",
        "record the decision inline in `config/PENDING_MODEL_VERDICTS.md` as:",
        "",
        "```",
        "- [x] `tag` — X.X GB",
        "  - verdict: decline (superseded by <incumbent>; quality Δ ≤ 0)",
        "  - evidence: `...` (regenerated each audit run)",
        "```",
        "",
        "Verdict vocabulary: `decline` | `promote` | `keep-open` | `investigate` | `investigate-refresh`.",
        f"`investigate-refresh` = evidence is missing, pre-boundary only, or >{STALE_DAYS} days old — re-bench first.",
        "The verdict/reason line survives audit reruns (Part A of this task).",
        "",
        "Sorted biggest-reclaim-first.",
        "",
    ]
    for r in rows:
        ev = r["evidence_summary"]
        inc = r["incumbent"]
        sug_verdict, sug_reason = r["suggested"]
        out.append(f"## `{r['tag']}` — {r['size_gb']:.1f} GB")
        out.append("")
        out.append(f"- **Suggested verdict:** `{sug_verdict}` — {sug_reason}")
        out.append(
            f"- **Bench workspaces routing to this tag:** {', '.join(r['bench_slugs']) or '(none — bench-orphaned)'}"
        )
        out.append(
            f"- **Mined evidence:** {ev['n_rows']} tps rows total "
            f"(**{ev['n_valid_rows']} valid** post-boundary, {ev['n_invalid_rows']} invalid pre-boundary) "
            f"across {len(r['evidence_paths'])} files"
        )
        if ev["newest_valid_date"]:
            out.append(f"  - newest post-boundary evidence: **{ev['newest_valid_date']}**")
        elif ev["newest_date"]:
            out.append(
                f"  - newest evidence: **{ev['newest_date']}** ({ev['newest_age_days']}d old) — ⚠ **all pre-boundary**"
            )
        if ev["avg_tps"] is not None:
            out.append(
                f"  - avg TPS (post-boundary only): **{ev['avg_tps']}** t/s   ({'PASS' if ev['avg_tps'] >= 20 else 'BELOW FLOOR'})"
            )
        elif ev["avg_tps_all"] is not None:
            out.append(
                f"  - avg TPS (pre-boundary, INVALID for decisions): {ev['avg_tps_all']} t/s"
            )
        if ev["avg_quality"] is not None:
            out.append(f"  - avg quality_score (post-boundary only): **{ev['avg_quality']}**")
        if ev["verdicts_valid"]:
            uniq = sorted({v for v, _ in ev["verdicts_valid"]})
            out.append(f"  - **post-boundary** closeout signals: {', '.join(uniq)}")
            for v, src in ev["verdicts_valid"][:2]:
                out.append(f"    - `{v}` in `{src}`")
        if ev["verdicts_invalid"]:
            uniq = sorted({v for v, _ in ev["verdicts_invalid"]})
            out.append(
                f"  - pre-boundary closeout signals (re-affirm before trusting): {', '.join(uniq)}"
            )
            for v, src in ev["verdicts_invalid"][:2]:
                out.append(f"    - `{v}` in `{src}`")
        if inc:
            out.append(
                f"- **Same-lane incumbent:** `{inc['tag']}` (avg_tps={inc.get('avg_tps')}, quality={inc.get('avg_quality')}, from {inc.get('source')})"
            )
        else:
            out.append(
                "- **Same-lane incumbent:** (none identified — no matching production module tag)"
            )
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Evidence miner for pending model verdicts.")
    ap.add_argument(
        "--stack-boundary-days",
        type=int,
        default=STACK_BOUNDARY_DAYS,
        help=f"Evidence older than N days ago is INVALID (stack changed). Default {STACK_BOUNDARY_DAYS}.",
    )
    args = ap.parse_args(argv)
    boundary_days = args.stack_boundary_days

    entries = parse_ledger()
    print(f"Parsed {len(entries)} ledger entries")
    print(
        f"Stack boundary: {boundary_days} days ({(_dt.date.today() - _dt.timedelta(days=boundary_days)).isoformat()})"
    )
    bench_by_tag = bench_workspaces_by_tag()
    ws_modules = workspace_modules()
    incumbents_by_module = production_incumbents_by_module()

    rows: list[dict] = []
    for e in entries:
        tag = e["tag"]
        bench_slugs = bench_by_tag.get(tag.lower(), [])
        ev = collect_evidence(tag, e["evidence"], bench_slugs, stack_boundary_days=boundary_days)

        incumbent = None
        for slug in bench_slugs:
            for module_tag in ws_modules.get(slug, ()):
                for peer in incumbents_by_module.get(module_tag, []):
                    inc_lookup = latest_tps_for_tag(
                        peer["model_hint"], {peer["model_hint"].lower()}
                    )
                    if inc_lookup:
                        incumbent = inc_lookup
                        break
                if incumbent:
                    break
            if incumbent:
                break

        suggested = suggest_verdict(tag, ev, incumbent)
        rows.append(
            {
                "tag": tag,
                "size_gb": e["size_gb"],
                "evidence_paths": e["evidence"],
                "bench_slugs": bench_slugs,
                "evidence_summary": ev,
                "incumbent": incumbent,
                "suggested": suggested,
            }
        )

    rows.sort(key=lambda r: -r["size_gb"])
    out_path = (
        REPO_ROOT
        / "reports"
        / f"PENDING_VERDICTS_EVIDENCE_{_dt.datetime.now(_dt.UTC).strftime('%Y%m%dT%H%M%SZ')}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_sheet(rows, boundary_days))
    print(f"Wrote {out_path.relative_to(REPO_ROOT)} ({len(rows)} rows)")

    from collections import Counter

    hist = Counter(r["suggested"][0] for r in rows)
    for verdict, n in sorted(hist.items(), key=lambda x: -x[1]):
        gb = sum(r["size_gb"] for r in rows if r["suggested"][0] == verdict)
        print(f"  suggest {verdict}: {n} models, {gb:.1f} GB")

    n_no_valid = sum(1 for r in rows if not r["evidence_summary"]["has_valid_evidence"])
    print("\nPre-flight signal:")
    print(f"  models with NO post-boundary evidence: {n_no_valid} / {len(rows)}")
    if n_no_valid >= len(rows) * 0.7 and len(rows) >= 10:
        print(f"  ⚠ {n_no_valid}/{len(rows)} pending models lack post-boundary evidence.")
        print("  ⚠ Consider running a fleet-wide bench sweep BEFORE the operator decision gate.")
        print("  ⚠ Otherwise most verdicts will be forced to `investigate-refresh`.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
