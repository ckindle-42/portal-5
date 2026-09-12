#!/usr/bin/env python3
"""WFE report compiler — turns a campaign directory into the operator artifact.

Deterministic: no model calls, no judgement. Its contract is to present evidence
against each recorded stop rule and leave the disposition to the operator, since
the stop rules in the closeout register are prose ("grounded-citation quality >
incumbent on real documents -> INTEGRATE as RAG seat; else REMOVED") and are
therefore operator judgement by construction.

Three properties are non-negotiable in the output:
  1. Instrument failures are quarantined out of every rate and reported
     separately. A harness defect must never read as a model verdict.
  2. Every rate carries a Wilson interval, and overlapping intervals are
     labelled NOT SEPARATED rather than ranked. Two binary tasks cannot order
     two models, and the report must say so rather than imply otherwise.
  3. Every disposition inherits the provisionality of the dimensions the
     campaign did NOT exercise, printed inline.

Usage:
  uv run python -m tests.wfe.report --campaign wfe_20260908T0100Z
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from tests.wfe.schema import (
    INSTRUMENT_OUTCOMES,
    MODEL_QUALITY_OUTCOMES,
    Outcome,
    sha12,
    wilson,
)

REPO = Path(__file__).resolve().parents[2]
CAMPAIGNS = REPO / "tests" / "wfe" / "results" / "campaigns"
DIMENSIONS = REPO / "tests" / "wfe" / "dimensions.yaml"
CLOSEOUT = REPO / "docs" / "MODEL_FLEET_CLOSEOUT_20260906.tasks.json"


def _rate(rows: list[dict]) -> tuple[int, int]:
    counted = [r for r in rows if Outcome(r["outcome"]) in MODEL_QUALITY_OUTCOMES]
    return sum(1 for r in counted if r["outcome"] == Outcome.PASS.value), len(counted)


def _fmt_ci(passes: int, n: int) -> str:
    if n == 0:
        return "n/a (0 gradeable)"
    p, lo, hi = wilson(passes, n)
    return f"{passes}/{n} = {p:.2f} [{lo:.2f}–{hi:.2f}]"


def _load(campaign_dir: Path) -> tuple[dict, list[dict], dict]:
    manifest = json.loads((campaign_dir / "manifest.json").read_text())
    rows = []
    for f in sorted((campaign_dir / "rows").glob("*.json")):
        try:
            rows.append(json.loads(f.read_text()))
        except Exception:
            continue
    preflights = {}
    for f in sorted((campaign_dir / "preflight").glob("*.json")):
        try:
            d = json.loads(f.read_text())
            preflights[d.get("model", f.stem)] = d
        except Exception:
            continue
    return manifest, rows, preflights


def _review_scores(campaign_dir: Path) -> dict:
    q = campaign_dir / "review_queue.jsonl"
    if not q.exists():
        return {}
    out = {}
    for line in q.read_text().splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("score") is not None:
            out[d["blind_id"]] = d
    return out


def _fingerprint_check(rows: list[dict], allow_mixed: bool) -> list[str]:
    """Dimension 22 as a standing gate: an Ollama upgrade changes behaviour, so
    results from different environments must not be silently pooled."""
    fps = Counter((r.get("env") or {}).get("fingerprint", "unknown") for r in rows)
    if len(fps) <= 1:
        return []
    msg = f"MIXED ENVIRONMENT FINGERPRINTS across results: {dict(fps)}"
    if allow_mixed:
        return [msg + " (pooled under --allow-mixed; comparisons are not sound)"]
    raise SystemExit(
        msg + "\nRe-run the affected arms or pass --allow-mixed to pool them explicitly."
    )


def _collect_warnings(rows: list[dict], manifest: dict, allow_mixed: bool) -> list[str]:
    warnings = _fingerprint_check(rows, allow_mixed)
    degen = sorted({r["repeat_degeneracy"] for r in rows if r.get("repeat_degeneracy")})
    warnings += [
        f"repeats are not independent draws: {d} — n>1 counts one observation "
        f"more than once for the affected workspaces"
        for d in degen
    ]
    if manifest.get("rescores"):
        last = manifest["rescores"][-1]
        warnings.append(
            f"verdicts re-scored offline on {last['utc']} from {last['debug_dir']} "
            f"({last['changed']} of {last['runs']} changed) — no models were re-run"
        )
    return warnings


def _build_matrix(by_key: dict, role_of: dict, home_of: dict) -> list[dict]:
    matrix: list[dict] = []
    for (ws, suite, arm), rs in sorted(by_key.items()):
        passes, n = _rate(rs)
        p, lo, hi = wilson(passes, n)
        instr = [r for r in rs if Outcome(r["outcome"]) in INSTRUMENT_OUTCOMES]
        pending = [r for r in rs if r["outcome"] == Outcome.PENDING_REVIEW.value]
        econ = [r.get("economics") or {} for r in rs]
        tok = [e.get("total_tokens") for e in econ if e.get("total_tokens")]
        wall = [e.get("wall_s") for e in econ if e.get("wall_s")]
        cold = [e.get("load_ms") for e in econ if e.get("cold_load") and e.get("load_ms")]
        matrix.append(
            {
                "workspace": ws,
                "suite": suite,
                "arm": arm,
                "role": role_of.get((ws, arm), "?"),
                "is_home": suite == home_of.get(ws),
                "passes": passes,
                "n": n,
                "point": p,
                "lo": lo,
                "hi": hi,
                "instrument_excluded": len(instr),
                "pending_review": len(pending),
                "outcomes": dict(Counter(r["outcome"] for r in rs)),
                "median_tokens": sorted(tok)[len(tok) // 2] if tok else None,
                "median_wall_s": sorted(wall)[len(wall) // 2] if wall else None,
                "cold_load_ms": max(cold) if cold else None,
                "persona": next((r.get("persona_slug") for r in rs if r.get("persona_slug")), None),
                "repeats": sorted({r["repeat"] for r in rs}),
            }
        )
    return matrix


def build(campaign_dir: Path, allow_mixed: bool = False, only_arm: str | None = None) -> dict:
    manifest, rows, preflights = _load(campaign_dir)
    if only_arm:
        rows = [r for r in rows if r["arm"] == only_arm]
    warnings = _collect_warnings(rows, manifest, allow_mixed)
    reviews = _review_scores(campaign_dir)

    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by_key[(r["workspace"], r["suite"], r["arm"])].append(r)

    incumbent_of, role_of, home_of = {}, {}, {}
    for m in manifest["rows"]:
        role_of[(m["workspace"], m["arm"])] = m["arm_role"]
        if m["arm_role"] == "incumbent":
            incumbent_of[m["workspace"]] = m["arm"]
        if m.get("is_home"):
            home_of[m["workspace"]] = m["suite"]

    matrix = _build_matrix(by_key, role_of, home_of)

    comparisons = []
    for row in matrix:
        inc = incumbent_of.get(row["workspace"])
        if not inc or row["arm"] == inc:
            continue
        base = next(
            (
                m
                for m in matrix
                if m["workspace"] == row["workspace"]
                and m["suite"] == row["suite"]
                and m["arm"] == inc
            ),
            None,
        )
        if base is None:
            continue
        if row["n"] == 0 or base["n"] == 0:
            verdict = "NO GRADEABLE RUNS"
        elif row["lo"] > base["hi"]:
            verdict = "CHALLENGER BETTER (separated)"
        elif row["hi"] < base["lo"]:
            verdict = "INCUMBENT BETTER (separated)"
        else:
            verdict = "NOT SEPARATED (n insufficient)"
        comparisons.append(
            {
                "workspace": row["workspace"],
                "suite": row["suite"],
                "lane": "home" if row["is_home"] else "discovery",
                "challenger": row["arm"],
                "incumbent": inc,
                "challenger_rate": _fmt_ci(row["passes"], row["n"]),
                "incumbent_rate": _fmt_ci(base["passes"], base["n"]),
                "verdict": verdict,
                "delta_point": round(row["point"] - base["point"], 3),
            }
        )

    taxonomy = Counter(r["outcome"] for r in rows)
    blocked = [m for m in manifest["rows"] if m.get("state") in (Outcome.BLOCKED.value, "PENDING")]
    packets = _decision_packets(matrix, comparisons)
    dims = _coverage(rows)

    return {
        "campaign_id": manifest["campaign_id"] + (f" / {only_arm}" if only_arm else ""),
        "only_arm": only_arm,
        "generated_utc": dt.datetime.now(dt.UTC).isoformat(),
        "env": manifest.get("env", {}),
        "warnings": warnings
        + (
            [f"config/ modified during the campaign: {manifest['config_dirty_at_end']}"]
            if manifest.get("config_dirty_at_end")
            and manifest.get("config_dirty_at_end") != manifest.get("config_dirty_at_start")
            else []
        ),
        "matrix": matrix,
        "comparisons": comparisons,
        # Lanes that were measured but have nothing to rank against, because the
        # plan carries no incumbent arm for them. Recorded explicitly so their
        # absence from `comparisons` is a stated fact, not a silent omission.
        "no_baseline": sorted(
            {m["workspace"] for m in matrix} - set(incumbent_of) - {""},
        ),
        "taxonomy": dict(taxonomy),
        "not_run": [
            {"run_id": m["run_id"], "state": m.get("state"), "note": m.get("note", "")}
            for m in blocked
        ],
        "preflight": {
            k: {
                "verdict": v.get("verdict"),
                "findings": v.get("findings", []),
                "notes": v.get("notes", []),
            }
            for k, v in preflights.items()
        },
        "review": {
            "scored": len(reviews),
            "pending": taxonomy.get(Outcome.PENDING_REVIEW.value, 0),
        },
        "decision_packets": packets,
        "coverage": dims,
    }


def _decision_packets(matrix: list[dict], comparisons: list[dict]) -> list[dict]:
    """One packet per closeout row that named a test. The stop rule is quoted
    verbatim; the measured evidence is filled in beneath it; the disposition
    stays an operator gate."""
    if not CLOSEOUT.exists():
        return []
    data = json.loads(CLOSEOUT.read_text())
    candidates = []
    for it in data.get("items", []):
        if it.get("stop_rule") and it.get("test_if_needed"):
            candidates.append(
                {
                    "identity": it.get("exact_identity"),
                    "question": it.get("decision_question"),
                    "test": it.get("test_if_needed"),
                    "stop_rule": it.get("stop_rule"),
                    "prior_disposition": it.get("final_disposition"),
                }
            )
    for c in data.get("contender_test_plan", []) or []:
        candidates.append(
            {
                "identity": c.get("identity"),
                "question": c.get("question"),
                "test": c.get("test"),
                "stop_rule": c.get("stop_rule"),
                "prior_disposition": "contender_test_plan",
            }
        )
    packets = []
    for c in candidates:
        ident = c["identity"] or ""
        ev_matrix = [m for m in matrix if m["arm"] == ident]
        ev_cmp = [x for x in comparisons if x["challenger"] == ident]
        if not ev_matrix and not ev_cmp:
            packets.append({**c, "evidence": [], "comparisons": [], "status": "NO WFE EVIDENCE"})
            continue
        packets.append(
            {
                **c,
                "evidence": [
                    {
                        "workspace": m["workspace"],
                        "suite": m["suite"],
                        "lane": "home" if m["is_home"] else "discovery",
                        "rate": _fmt_ci(m["passes"], m["n"]),
                        "excluded": m["instrument_excluded"],
                        "median_tokens": m["median_tokens"],
                        "median_wall_s": m["median_wall_s"],
                    }
                    for m in ev_matrix
                ],
                "comparisons": ev_cmp,
                "status": "EVIDENCE PRESENT — OPERATOR GATE",
            }
        )
    return packets


def _coverage(rows: list[dict]) -> dict:
    if not DIMENSIONS.exists():
        return {"note": "dimensions.yaml absent"}
    d = yaml.safe_load(DIMENSIONS.read_text()) or {}
    dims = d.get("dimensions", [])
    exercised, pending = [], []
    for dim in dims:
        line = f"{dim['id']}. {dim['name']}"
        if dim.get("note"):
            line += f" — _{dim['note']}_"
        (exercised if dim.get("status") == "BUILT" else pending).append(line)
    return {
        "exercised": exercised,
        "not_exercised": pending,
        "rule": d.get(
            "rule",
            "A disposition that depends on a dimension this campaign did not exercise is provisional.",
        ),
    }


def _sec_header(a, rep) -> None:
    a(f"# WFE Fitness Report — `{rep['campaign_id']}`")
    a("")
    a(f"Generated {rep['generated_utc']}")
    env = rep.get("env", {})
    a(
        f"Environment: git `{env.get('git_sha')}` · Ollama `{env.get('ollama_version')}` · "
        f"fingerprint `{env.get('fingerprint')}`"
    )
    a("")
    if rep["warnings"]:
        a("## Warnings")
        a("")
        for w in rep["warnings"]:
            a(f"- **{w}**")
        a("")


def _sec_instrument(a, rep) -> None:
    a("## 1. Instrument health")
    a("")
    # Every outcome, not only the excluded ones: a reader has to be able to see
    # the whole census to judge whether the instrument or the models produced it.
    # The heading used to promise only exclusions while the table listed all of
    # them, which read as "every run was an instrument failure".
    a("Every run by outcome. Rows marked *(excluded)* are instrument failures —")
    a("the harness, not the model — and are removed from every rate below.")
    a("")
    a("| Outcome | Count |")
    a("|---|---|")
    excluded = 0
    for k, v in sorted(rep["taxonomy"].items()):
        is_instrument = Outcome(k) in INSTRUMENT_OUTCOMES
        excluded += v if is_instrument else 0
        a(f"| {k}{' *(excluded)*' if is_instrument else ''} | {v} |")
    a("")
    total = sum(rep["taxonomy"].values())
    a(f"{excluded} of {total} run(s) excluded as instrument failures.")
    a("")
    rev = [k for k, v in rep["preflight"].items() if v["verdict"] != "OK"]
    if rev:
        a("Arms blocked by preflight:")
        a("")
        for k in rev:
            a(f"- `{k}` — {'; '.join(rep['preflight'][k]['findings'])}")
        a("")
    noted = [(k, v["notes"]) for k, v in rep["preflight"].items() if v.get("notes")]
    if noted:
        a("Preflight notes (informational — did not block the arm):")
        a("")
        for k, notes in noted:
            for n in notes:
                a(f"- `{k}` — {n}")
        a("")
    if rep["not_run"]:
        a(f"{len(rep['not_run'])} matrix rows did not produce a result:")
        a("")
        for nr in rep["not_run"][:25]:
            a(f"- `{nr['run_id']}` — {nr['state']} {nr['note']}")
        a("")


def _sec_matrix(a, rep) -> None:
    a("## 2. Fitness matrix")
    a("")
    a("Rates count only model-attributable outcomes. Brackets are Wilson 95% intervals.")
    a("")
    a("| Workspace | Lane | Arm | Role | Persona | Rate | Excluded | Med tok | Med s |")
    a("|---|---|---|---|---|---|---|---|---|")
    for m in rep["matrix"]:
        a(
            f"| {m['workspace']} | {'home' if m['is_home'] else 'disc'}:{m['suite']} | "
            f"`{m['arm']}` | {m['role']} | {m['persona'] or '—'} | "
            f"{_fmt_ci(m['passes'], m['n'])} | {m['instrument_excluded']} | "
            f"{m['median_tokens'] or '—'} | {m['median_wall_s'] or '—'} |"
        )
    a("")


def _sec_comparisons(a, rep) -> None:
    a("## 3. Incumbent vs challenger")
    a("")
    if not rep["comparisons"]:
        a("_No challenger produced a comparable result._")
    else:
        a("| Workspace | Lane | Challenger | Challenger rate | Incumbent rate | Verdict |")
        a("|---|---|---|---|---|---|")
        for c in rep["comparisons"]:
            a(
                f"| {c['workspace']} | {c['lane']}:{c['suite']} | `{c['challenger']}` | "
                f"{c['challenger_rate']} | {c['incumbent_rate']} | **{c['verdict']}** |"
            )
    a("")
    a(
        "_NOT SEPARATED means the intervals overlap: the evidence does not order the two "
        "arms. It is not a tie and must not be read as one._"
    )
    a("")
    # A lane whose incumbent was excluded has challengers and no baseline. Saying
    # so is the point: without it those challengers simply have no rows in this
    # table, which reads as "nothing to report" rather than "nothing to compare".
    if rep.get("no_baseline"):
        a("Workspaces with challengers but **no incumbent arm** — no comparison was made:")
        a("")
        for ws in rep["no_baseline"]:
            a(f"- `{ws}` — challengers were measured (section 2) but rank against nothing here.")
        a("")
    a("## 4. Creative lane (blinded review)")
    a("")
    a(
        f"{rep['review']['pending']} responses queued; {rep['review']['scored']} scored. "
        "Unscored items are excluded from every rate above."
    )
    a("")


def _sec_packets(a, rep) -> None:
    a("## 5. Decision packets")
    a("")
    a("Stop rules quoted verbatim from the closeout register. Dispositions are operator gates.")
    a("")
    for p in rep["decision_packets"]:
        a(f"### `{p['identity']}`")
        a("")
        a(f"- **Question:** {p.get('question') or '—'}")
        a(f"- **Recorded test:** {p.get('test') or '—'}")
        a(f"- **Stop rule:** {p.get('stop_rule') or '—'}")
        a(f"- **Prior disposition:** {p.get('prior_disposition') or '—'}")
        a(f"- **Status:** {p['status']}")
        for e in p.get("evidence", []):
            a(
                f"  - {e['workspace']} / {e['lane']}:{e['suite']} — {e['rate']} "
                f"(excluded {e['excluded']}, med {e['median_tokens'] or '—'} tok / "
                f"{e['median_wall_s'] or '—'} s)"
            )
        for c in p.get("comparisons", []):
            a(f"  - vs incumbent `{c['incumbent']}` on {c['suite']}: **{c['verdict']}**")
        a("")
        a("  `[GATE] operator disposition: ______________  reason: ______________`")
        a("")


def _sec_coverage(a, rep) -> None:
    a("## 6. Coverage and provisionality")
    a("")
    cov = rep["coverage"]
    a(f"_{cov.get('rule', '')}_")
    a("")
    a("**Exercised by this campaign:**")
    a("")
    for x in cov.get("exercised", []):
        a(f"- {x}")
    a("")
    a("**NOT exercised — every disposition above is provisional against these:**")
    a("")
    for x in cov.get("not_exercised", []):
        a(f"- {x}")
    a("")


def render_markdown(rep: dict) -> str:
    lines: list[str] = []
    a = lines.append
    for section in (
        _sec_header,
        _sec_instrument,
        _sec_matrix,
        _sec_comparisons,
        _sec_packets,
        _sec_coverage,
    ):
        section(a, rep)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--arm", help="per-model review document for one arm")
    ap.add_argument("--allow-mixed", action="store_true")
    ap.add_argument("--out-dir", default=str(REPO / "docs"))
    args = ap.parse_args()
    campaign_dir = CAMPAIGNS / args.campaign
    if not campaign_dir.is_dir():
        raise SystemExit(f"no such campaign: {campaign_dir}")
    rep = build(campaign_dir, args.allow_mixed, args.arm)
    stem = args.campaign + (f"_{sha12(args.arm)}" if args.arm else "")
    out_md = Path(args.out_dir) / f"WFE_FITNESS_REPORT_{stem}.md"
    out_json = campaign_dir / (f"report_{sha12(args.arm)}.json" if args.arm else "report.json")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_markdown(rep))
    out_json.write_text(json.dumps(rep, indent=1))
    print(f"report: {out_md}\njson:   {out_json}")
    print(f"sha:    {sha12(out_md.read_text())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
