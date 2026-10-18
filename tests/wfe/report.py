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
  uv run python -m tests.wfe.report --fitness-map    # merged-ledger dispositions, no campaign
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

import yaml

from portal.platform.inference.router.metrics import MIN_ANSWER_TOKENS_FOR_RATE
from tests.wfe import decision
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
MAP_DOC = REPO / "docs" / "WFE_FITNESS_MAP.md"


def _rate(rows: list[dict]) -> tuple[int, int]:
    counted = [r for r in rows if Outcome(r["outcome"]) in MODEL_QUALITY_OUTCOMES]
    return sum(1 for r in counted if r["outcome"] == Outcome.PASS.value), len(counted)


def _fmt_ci(passes: int, n: int) -> str:
    if n == 0:
        return "n/a (0 gradeable)"
    p, lo, hi = wilson(passes, n)
    return f"{passes}/{n} = {p:.2f} [{lo:.2f}–{hi:.2f}]"


def _speed_economics(row: dict) -> dict:
    """Return row speed fields, repairing pre-T4 splits from stored text lengths."""
    economics = row.get("economics") if isinstance(row.get("economics"), dict) else row
    answer_tokens = economics.get("answer_tokens")
    answer_tps = economics.get("answer_tps")
    if not economics.get("split_source"):
        completion_tokens = economics.get("completion_tokens")
        reasoning_chars = economics.get("reasoning_chars")
        if not isinstance(reasoning_chars, int | float) or isinstance(reasoning_chars, bool):
            reasoning_chars = row.get("reasoning_chars")
        if not isinstance(reasoning_chars, int | float) or isinstance(reasoning_chars, bool):
            reasoning_chars = sum(
                turn.get("reasoning_chars", 0)
                for turn in (row.get("transcript") or [])
                if isinstance(turn, dict)
                and isinstance(turn.get("reasoning_chars", 0), int | float)
                and not isinstance(turn.get("reasoning_chars", 0), bool)
            )
        answer_chars = economics.get("answer_chars")
        if not isinstance(answer_chars, int | float) or isinstance(answer_chars, bool):
            final_text = row.get("final_text")
            if not isinstance(final_text, str):
                transcript = row.get("transcript") or []
                final_text = next(
                    (
                        turn.get("content")
                        for turn in reversed(transcript)
                        if isinstance(turn, dict) and isinstance(turn.get("content"), str)
                    ),
                    row.get("final_text_head"),
                )
            answer_chars = len(final_text) if isinstance(final_text, str) else None
        if (
            isinstance(completion_tokens, int | float)
            and not isinstance(completion_tokens, bool)
            and isinstance(reasoning_chars, int | float)
            and not isinstance(reasoning_chars, bool)
            and isinstance(answer_chars, int | float)
            and not isinstance(answer_chars, bool)
            and reasoning_chars + answer_chars > 0
        ):
            answer_tokens = round(
                completion_tokens * answer_chars / (reasoning_chars + answer_chars)
            )
            answer_s = economics.get("answer_s")
            answer_tps = (
                round(answer_tokens / answer_s, 3)
                if isinstance(answer_s, int | float)
                and not isinstance(answer_s, bool)
                and answer_s > 0
                else None
            )

    completion_tokens = economics.get("completion_tokens")
    reasoning_s, answer_s = economics.get("reasoning_s"), economics.get("answer_s")
    reasoning_s = (
        reasoning_s
        if isinstance(reasoning_s, int | float) and not isinstance(reasoning_s, bool)
        else 0
    )
    answer_s = (
        answer_s if isinstance(answer_s, int | float) and not isinstance(answer_s, bool) else 0
    )
    decode_s = reasoning_s + answer_s
    decode_tps = (
        completion_tokens / decode_s
        if isinstance(completion_tokens, int | float)
        and not isinstance(completion_tokens, bool)
        and decode_s > 0
        else None
    )
    if (
        not isinstance(answer_tokens, int | float)
        or isinstance(answer_tokens, bool)
        or answer_tokens < MIN_ANSWER_TOKENS_FOR_RATE
    ):
        answer_tps = None
    return {
        "answer_tokens": answer_tokens,
        "answer_tps": answer_tps,
        "ttft_s": economics.get("ttft_s"),
        "total_s": economics.get("total_s"),
        "decode_tps": decode_tps,
    }


def _speed_summary(rows: list[dict]) -> dict:
    economics = [_speed_economics(row) for row in rows]

    def stats(field: str) -> tuple[float | None, float | None, int]:
        values = sorted(
            float(e[field])
            for e in economics
            if isinstance(e.get(field), int | float) and not isinstance(e.get(field), bool)
        )
        if not values:
            return None, None, 0
        p90 = values[max(0, math.ceil(0.9 * len(values)) - 1)]
        return median(values), p90, len(values)

    result = {}
    for field in ("answer_tps", "decode_tps", "ttft_s", "total_s"):
        med, p90, n = stats(field)
        result[f"{field}_median"] = med
        result[f"{field}_p90"] = p90
        result[f"{field}_n"] = n
    return result


def _fmt_speed(speed: dict, key: str) -> str:
    return f"{speed[key]:.2f}" if speed.get(key) is not None else "—"


def _fmt_speed_median(speed: dict, field: str) -> str:
    return f"{_fmt_speed(speed, f'{field}_median')} (n={speed.get(f'{field}_n', 0)})"


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


def _instrument_check(rows: list[dict], allow_mixed: bool) -> list[str]:
    """Refuse to pool rows measured by different harness code or config."""
    fps = Counter((r.get("instrument") or {}).get("fingerprint", "legacy") for r in rows)
    if len(fps) <= 1:
        return []
    msg = f"MIXED INSTRUMENT FINGERPRINTS across results: {dict(fps)}"
    if allow_mixed:
        return [msg + " (pooled under --allow-mixed; comparisons are not sound)"]
    raise SystemExit(
        msg + "\nThe harness or its config changed mid-campaign. Re-run the affected "
        "rows under one instrument or pass --allow-mixed to pool them explicitly."
    )


def _grader_of(row: dict) -> str:
    """The instrument that graded this row; 'original' when never re-scored."""
    return (row.get("rescore") or {}).get("grader", {}).get("fingerprint", "original")


def _grader_check(rows: list[dict], allow_mixed: bool) -> list[str]:
    """Refuse to pool rows graded by different instruments (R-7)."""
    graders = Counter(_grader_of(r) for r in rows)
    if len(graders) <= 1:
        return []
    msg = f"MIXED GRADERS across results: {dict(graders)}"
    if allow_mixed:
        return [msg + " (pooled under --allow-mixed; comparisons are not sound)"]
    raise SystemExit(
        msg + "\nSome rows were re-scored under one instrument and others under another "
        "(or not at all). Re-score the whole comparison or pass --allow-mixed to pool "
        "them explicitly."
    )


def _identity_check(rows: list[dict], manifest: dict, allow_mixed: bool) -> list[str]:
    """Refuse to compare a row whose serving build is not its pair's frozen one. In
    a pipeline campaign every scored row must carry an observed identity equal to
    the freeze: a missing one is a refusal, never a pass (doc: identity)."""
    if (manifest.get("instrument") or {}).get("engine") != "pipeline":
        return []
    frozen = manifest.get("identity_map") or {}
    scored = {o.value for o in MODEL_QUALITY_OUTCOMES}
    bad: list[str] = []
    for r in rows:
        if r.get("outcome") not in scored:
            continue
        key = f"{r.get('workspace')}|{r.get('model') or r.get('arm')}"
        ident, want = r.get("identity") or {}, frozen.get(key)
        if not ident.get("content") or ident != want:
            bad.append(f"{key}: served {ident or None}, frozen {want}")
    if not bad:
        return []
    msg = f"IDENTITY DRIFT across results: {len(bad)} row(s)"
    if allow_mixed:
        return [msg + " (pooled under --allow-mixed; comparisons are not sound)"]
    raise SystemExit(
        msg
        + "\n  "
        + "\n  ".join(sorted(set(bad))[:8])
        + "\nThe serving build changed within a (workspace, arm) after preflight froze it. "
        "Re-run the affected rows under one build or pass --allow-mixed explicitly."
    )


def expected_sets(manifest: dict, workspace: str) -> dict[str, set]:
    """Each arm's expected (suite, task) set for one workspace, from the matrix.

    The expected set comes from the matrix, not from the rows that happen to
    exist: a task missing from both arms has to count against the excluded
    budget, or a half-finished campaign reads as a complete one."""
    out: dict[str, set] = {}
    for m in manifest["rows"]:
        if m["workspace"] != workspace:
            continue
        out.setdefault(m["arm"], set()).add((m["suite"], m["task_id"]))
    return out


def screen_expected(manifest: dict, workspace: str, arm: str) -> set:
    """The screen tasks for one arm: the rows a screen expansion created."""
    return {
        (m["suite"], m["task_id"])
        for m in manifest["rows"]
        if m["workspace"] == workspace and m["arm"] == arm and m.get("tier") == "screen"
    }


def cell_expected(manifest: dict, workspace: str, incumbent: str, candidate: str) -> set:
    """The compared set for one cell. Both arms must expect exactly the same
    tasks, or the comparison is between two different suites."""
    sets = expected_sets(manifest, workspace)
    inc, cand = sets.get(incumbent, set()), sets.get(candidate, set())
    if inc != cand:
        raise SystemExit(
            f"{workspace}: {candidate} and {incumbent} do not expect the same tasks "
            f"({len(cand)} vs {len(inc)}); incumbent-only {sorted(inc - cand)[:4]}, "
            f"candidate-only {sorted(cand - inc)[:4]}"
        )
    return inc


def _collect_warnings(rows: list[dict], manifest: dict, allow_mixed: bool) -> list[str]:
    warnings = (
        _fingerprint_check(rows, allow_mixed)
        + _instrument_check(rows, allow_mixed)
        + _grader_check(rows, allow_mixed)
        + _identity_check(rows, manifest, allow_mixed)
    )
    degen = sorted({r["repeat_degeneracy"] for r in rows if r.get("repeat_degeneracy")})
    warnings += [
        f"repeats are not independent draws: {d} — n>1 counts one observation "
        f"more than once for the affected workspaces"
        for d in degen
    ]
    dropped = Counter((r["arm"], k) for r in rows for k in (r.get("sampling_undelivered") or []))
    warnings += [
        f"{arm}: {k} was requested on {n} row(s) but the engine does not apply it — "
        f"the served value is the tag's baked value (row `baked_params`), not the request"
        for (arm, k), n in sorted(dropped.items())
    ]
    if manifest.get("rescores"):
        last = manifest["rescores"][-1]
        warnings.append(
            f"verdicts re-scored offline on {last['utc']} from {last['debug_dir']} "
            f"({last['changed']} of {last['runs']} changed) — no models were re-run"
        )
    return warnings


def _one_draw_per_task(rows: list[dict]) -> list[dict]:
    """Deterministic repeats (temperature 0, pinned seed) are one observation:
    counting them n times narrowed the Wilson interval threefold and made a
    temperature-0 arm "separated" from a sampled one on a third of the data."""
    if not any(r.get("repeat_degeneracy") for r in rows):
        return rows
    first: dict = {}
    for r in sorted(rows, key=lambda r: r.get("repeat", 0)):
        first.setdefault(r["task_id"], r)
    return list(first.values())


def _build_matrix(by_key: dict, role_of: dict, home_of: dict) -> list[dict]:
    matrix: list[dict] = []
    for (ws, suite, arm), rs in sorted(by_key.items()):
        passes, n = _rate(_one_draw_per_task(rs))
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
                "speed": _speed_summary(rs),
                "cold_load_ms": max(cold) if cold else None,
                "persona": next((r.get("persona_slug") for r in rs if r.get("persona_slug")), None),
                "repeats": sorted({r["repeat"] for r in rs}),
            }
        )
    return matrix


def _queue(path: Path | None = None) -> dict:
    """The candidate queue: what each model is for, and whether it is measurable."""
    p = Path(path) if path else (REPO / "tests" / "wfe" / "candidate_queue.yaml")
    if not p.exists():
        return {}
    return (yaml.safe_load(p.read_text()) or {}).get("models") or {}


def _tag(arm: str) -> str:
    """The model tag of an arm id: a variant arm is `<tag>@<label>-<digest>` and the
    candidate queue is keyed by the bare tag."""
    return arm.split("@", 1)[0]


def _intended(queue: dict, model: str) -> set:
    return set((queue.get(_tag(model)) or {}).get("intended") or [])


def _by_cell(rows: list[dict]) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        out[(r["workspace"], r["arm"])].append(r)
    return out


def _incumbents(manifest: dict) -> dict[str, str]:
    return {m["workspace"]: m["arm"] for m in manifest["rows"] if m["arm_role"] == "incumbent"}


def _candidates(by: dict, ws: str, inc: str) -> list[str]:
    return sorted({a for (w, a) in by if w == ws and a != inc})


def arguable_tasks(suite_paths) -> set:
    """The (suite, task) pairs a suite marks `arguable`."""
    from tests.wfe.runner import load_suite

    out: set = set()
    for sp in sorted({str(p) for p in suite_paths}):
        if not Path(sp).exists():  # a recorded suite that has since been renamed
            continue
        for t in load_suite(sp):
            if t.get("arguable"):
                out.add((Path(sp).stem, t["id"]))
    return out


def screen_out(
    campaign_dir: Path, queue_path: Path | None = None, allow_mixed: bool = False
) -> dict:
    """One screen verdict per (workspace, candidate).

    A screen DROP is a cost filter, never a decision, and an intended workspace
    is always advanced: the model was queued for that lane, so only a full
    confirm may take it away."""
    manifest, rows, _ = _load(campaign_dir)
    _collect_warnings(rows, manifest, allow_mixed)
    queue = _queue(queue_path)
    by = _by_cell(rows)
    advance: dict[str, list[str]] = {}
    cells = []
    for ws, inc in sorted(_incumbents(manifest).items()):
        for arm in _candidates(by, ws, inc):
            cell = decision.screen(by[(ws, inc)], by[(ws, arm)], screen_expected(manifest, ws, arm))
            if cell.verdict == decision.DROP and ws in _intended(queue, arm):
                cell.verdict = decision.ADVANCE
                cell.reason += "; intended workspace, always confirmed"
            cells.append({"workspace": ws, "candidate": arm, **vars(cell)})
            if cell.verdict == decision.ADVANCE:
                advance.setdefault(ws, []).append(arm)
    return {"advance": advance, "cells": cells}


def _draws(rows: list[dict]) -> dict:
    """The repeat count and the served temperature(s) the rows recorded for one arm."""
    temps = {r["served_temperature"] for r in rows if r.get("served_temperature") is not None}
    return {"repeats": len({r["repeat"] for r in rows}), "served_temperature": sorted(temps)}


def fitness(campaign_dir: Path, queue_path: Path | None = None, allow_mixed: bool = False) -> dict:
    """The confirm verdict per cell, then one disposition per model."""
    manifest, rows, _ = _load(campaign_dir)
    _collect_warnings(rows, manifest, allow_mixed)
    queue = _queue(queue_path)
    by = _by_cell(rows)
    suites = [r["suite_path"] for r in manifest["rows"] if r.get("suite_path")]
    arguable = arguable_tasks(suites)
    repeats = max((r["repeat"] for r in manifest["rows"]), default=0) + 1
    # `tier` is a property of the matrix, so the manifest is what says whether a
    # cell was ever confirmed: a candidate the screen dropped has screen rows and
    # nothing else, which is an absent cell rather than a mismatched comparison.
    confirmed = {(m["workspace"], m["arm"]) for m in manifest["rows"] if m.get("tier") == "confirm"}
    per_model: dict[str, dict[str, str]] = {}
    cells = []
    for ws, inc in sorted(_incumbents(manifest).items()):
        for arm in _candidates(by, ws, inc):
            if (ws, arm) not in confirmed:
                continue
            expected = cell_expected(manifest, ws, inc, arm)
            cell = decision.confirm(
                by[(ws, inc)], by[(ws, arm)], expected, repeats=repeats, arguable=arguable
            )
            cells.append(
                {
                    "workspace": ws,
                    "incumbent": inc,
                    "candidate": arm,
                    **vars(cell),
                    "draws": {
                        "incumbent": _draws(by[(ws, inc)]),
                        "candidate": _draws(by[(ws, arm)]),
                    },
                }
            )
            per_model.setdefault(_tag(arm), {})[ws] = cell.verdict
    # The queue is the roster: a model it names and no cell covers still gets a
    # disposition, which is what turns "queued but unmeasured" into NO_DECISION
    # instead of silence.
    for model in queue:
        per_model.setdefault(model, {})
    lineages = Counter((queue.get(m) or {}).get("lineage") or m for m in per_model)
    dispositions = []
    for model in sorted(per_model):
        lineage = (queue.get(model) or {}).get("lineage") or model
        verdict, reason = decision.dispose(
            per_model[model], _intended(queue, model), lineages[lineage] == 1
        )
        dispositions.append(
            {
                "model": model,
                "disposition": verdict,
                "reason": reason,
                "intended": sorted(_intended(queue, model)),
                "cells": per_model[model],
            }
        )
    return {"instrument": manifest.get("instrument"), "cells": cells, "dispositions": dispositions}


def _rel(p: Path) -> str:
    """A repo-relative path for display; the full path when it points outside."""
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


def fitness_map(queue_path: Path | None = None, ledger_path: Path | None = None) -> dict:
    """One disposition per queued model from EVERY cell in the fitness ledger.

    fitness() disposes a model from one campaign's confirm cells, so a model whose
    intended lanes were confirmed in different campaigns (granite4.1:30b-ctx64k in
    auto-compliance AND auto-data; Qwen3.8-ctx32k in auto-documents AND auto-data)
    never reaches a terminal verdict there. The ledger is the cross-campaign record
    and record_ledger already refused anything that was not decision-grade (see
    ledger_refusals), so disposing from all of its cells is the P5-B1 map: one
    verdict per queued model, whichever campaign measured each lane.
    """
    queue = _queue(queue_path)
    path = Path(ledger_path) if ledger_path else LEDGER
    doc = (yaml.safe_load(path.read_text()) if path.exists() else None) or {}
    cells: dict[str, dict[str, str]] = defaultdict(dict)
    campaigns: dict[str, dict[str, str]] = defaultdict(dict)
    for c in doc.get("cells") or []:
        model, ws, verdict = c.get("model"), c.get("workspace"), c.get("verdict")
        if not (model and ws and verdict):
            continue
        cells[model][ws] = verdict  # the ledger holds one cell per (model, workspace)
        campaigns[model][ws] = c.get("campaign") or ""
    # The queue is the roster; a ledger cell it does not name still surfaces —
    # an unqueued measured model is a queue gap, not silence (same rule as fitness()).
    for model in queue:
        cells.setdefault(model, {})
    lineages = Counter((queue.get(m) or {}).get("lineage") or m for m in cells)
    dispositions = []
    for model in sorted(cells):
        lineage = (queue.get(model) or {}).get("lineage") or model
        verdict, reason = decision.dispose(
            dict(cells[model]), _intended(queue, model), lineages[lineage] == 1
        )
        dispositions.append(
            {
                "model": model,
                "disposition": verdict,
                "reason": reason,
                "intended": sorted(_intended(queue, model)),
                "cells": dict(cells[model]),
                "campaigns": dict(campaigns.get(model, {})),
                "queued": model in queue,
            }
        )
    return {"ledger": _rel(path), "dispositions": dispositions}


def render_fitness_map(mp: dict) -> str:
    """The map as a markdown table: cells with their campaigns, then the verdict."""
    lines = [
        "# WFE fitness map — one disposition per queued model",
        "",
        f"Source: `{mp['ledger']}` — every decision-grade cell (recording refuses "
        "anything else), merged across campaigns; intents and lineages from "
        "`tests/wfe/candidate_queue.yaml`. Generated by `report --write-map`.",
        "",
        "| model | intended | cells (workspace: verdict @ campaign) | disposition | reason |",
        "|---|---|---|---|---|",
    ]
    for d in mp["dispositions"]:
        cells = (
            "; ".join(
                f"{ws}: {v} @{d['campaigns'].get(ws) or '?'}"
                for ws, v in sorted(d["cells"].items())
            )
            or "(no cells)"
        )
        intended = ", ".join(d["intended"]) or "(none)"
        queued = "" if d["queued"] else " (not queued)"
        lines.append(
            f"| {d['model']}{queued} | {intended} | {cells} | {d['disposition']} | {d['reason']} |"
        )
    lines.append("")
    return "\n".join(lines)


LEDGER = Path(
    os.environ.get("WFE_FITNESS_LEDGER") or REPO / "tests" / "wfe" / "fitness_ledger.yaml"
)
LEDGER_HEADER = """\
# Fitness ledger: one cell per (model, workspace), written by
# `report --campaign <id> --record`; never hand-edited.
#
# A cell is the evidence behind a seat decision, so recording refuses anything
# that is not decision-grade: a campaign that did not run through the pipeline,
# rows measured by more than one instrument, a controls gate that did not run or
# did not pass, or a side whose serving build was never observed. Each cell names
# the incumbent it was compared against and carries both sides' served identity
# (backend, model, content), so check HP can tell whether the measurement still
# describes what production serves. Part 5's sweep fills it.
"""


def ledger_receipts(campaign_dir: Path) -> list[dict]:
    p = campaign_dir / "controls_receipts.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def ledger_refusals(campaign_dir: Path, manifest: dict, rows: list[dict]) -> list[str]:
    """Why this campaign may not be written to the fitness ledger; empty means it may.

    A seat decision has to be traceable to decision-grade evidence: rows served
    through the pipeline, measured by one instrument, gated by controls that all
    passed. Anything else is a diagnostic and stays out of the ledger."""
    why = []
    if (manifest.get("instrument") or {}).get("engine") != "pipeline":
        why.append("not a pipeline-mode campaign: only pipeline rows are decision-grade")
    fps = {(r.get("instrument") or {}).get("fingerprint") for r in rows}
    if len(fps) != 1 or None in fps:
        why.append(f"rows do not share one instrument fingerprint: {sorted(map(str, fps))}")
    if not manifest.get("identity_map"):
        why.append("no frozen identities: no arm's preflight observed what served it")
    receipts = ledger_receipts(campaign_dir)
    if not receipts:
        why.append("no controls receipt: the controls gate never ran for this campaign")
    failed = [r for r in receipts if r.get("failures")]
    if failed:
        why.append(f"{len(failed)} controls receipt(s) record failures")
    return why


def record_ledger(
    campaign_dir: Path,
    queue_path: Path | None = None,
    ledger_path: Path | None = None,
    allow_mixed: bool = False,
) -> dict:
    """Write one cell per (model, workspace) to the fitness ledger."""
    manifest, rows, _ = _load(campaign_dir)
    why = ledger_refusals(campaign_dir, manifest, rows)
    if why:
        raise SystemExit("refusing to record the fitness ledger:\n  " + "\n  ".join(why))
    fit = fitness(campaign_dir, queue_path, allow_mixed)
    ident = manifest.get("identity_map") or {}
    model_of = {m["arm"]: m.get("model") or m["arm"] for m in manifest["rows"]}
    instrument = manifest.get("instrument") or {}
    receipts = {
        path: digest
        for rec in ledger_receipts(campaign_dir)
        for path, digest in (rec.get("suites") or {}).items()
    }
    now = dt.datetime.now(dt.UTC).isoformat()
    cells = [
        {
            "model": model_of.get(c["candidate"], c["candidate"]),
            "arm": c["candidate"],
            "workspace": c["workspace"],
            "incumbent": model_of.get(c["incumbent"], c["incumbent"]),
            "tier": "confirm",
            "verdict": c["verdict"],
            "reason": c["reason"],
            "n": c["n"],
            "wins": c["wins"],
            "losses": c["losses"],
            "ties": c["ties"],
            "p": c["p"],
            "campaign": manifest.get("campaign_id"),
            "instrument": instrument.get("fingerprint"),
            "served": ident.get(f"{c['workspace']}|{model_of.get(c['candidate'])}"),
            "incumbent_served": ident.get(f"{c['workspace']}|{model_of.get(c['incumbent'])}"),
            "receipts": receipts,
            "recorded_utc": now,
        }
        for c in fit["cells"]
    ]
    unseen = [
        f"{c['workspace']}|{c['arm']}"
        for c in cells
        if not (c["served"] or {}).get("content")
        or not (c["incumbent_served"] or {}).get("content")
    ]
    if unseen:
        raise SystemExit(
            f"refusing to record the fitness ledger: no observed identity for {unseen}"
        )
    path = Path(ledger_path) if ledger_path else LEDGER
    doc = (yaml.safe_load(path.read_text()) if path.exists() else None) or {}
    fresh = {(c["model"], c["workspace"]) for c in cells}
    kept = [
        e for e in (doc.get("cells") or []) if (e.get("model"), e.get("workspace")) not in fresh
    ]
    doc["cells"] = [*kept, *cells]
    path.write_text(LEDGER_HEADER + yaml.safe_dump(doc, sort_keys=False))
    return {"path": str(path), "cells": cells, "kept": len(kept)}


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


def _sec_speed(a, rep) -> None:
    a("## 2a. Speed by arm")
    a("")
    a(
        "Decode tok/s and TTFT are the primary speed measures. Answer tok/s includes only "
        f"rows with at least {MIN_ANSWER_TOKENS_FOR_RATE} answer tokens; n is the number "
        "of observations in each median, and p90 uses nearest-rank percentile."
    )
    a("")
    a(
        "| Workspace | Lane | Arm | Decode tok/s med (n) | Decode tok/s p90 | "
        "TTFT s med (n) | TTFT s p90 | "
        f"Answer tok/s med (n, >={MIN_ANSWER_TOKENS_FOR_RATE} tokens) | "
        "Answer tok/s p90 | Total s med (n) | Total s p90 |"
    )
    a("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in rep["matrix"]:
        speed = row.get("speed") or {}
        a(
            f"| {row['workspace']} | {'home' if row['is_home'] else 'disc'}:{row['suite']} | "
            f"`{row['arm']}` | {_fmt_speed_median(speed, 'decode_tps')} | "
            f"{_fmt_speed(speed, 'decode_tps_p90')} | "
            f"{_fmt_speed_median(speed, 'ttft_s')} | {_fmt_speed(speed, 'ttft_s_p90')} | "
            f"{_fmt_speed_median(speed, 'answer_tps')} | {_fmt_speed(speed, 'answer_tps_p90')} | "
            f"{_fmt_speed_median(speed, 'total_s')} | {_fmt_speed(speed, 'total_s_p90')} |"
        )
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
        _sec_speed,
        _sec_comparisons,
        _sec_packets,
        _sec_coverage,
    ):
        section(a, rep)
    return "\n".join(lines)


def _fitness_map_cli(args) -> bool:
    """--fitness-map / --write-map: print the merged-ledger map (writing it too
    with --write-map); True when the campaign modes do not apply."""
    if not (args.fitness_map or args.write_map):
        return False
    text = render_fitness_map(fitness_map(args.queue, args.ledger))
    print(text)
    if args.write_map:
        MAP_DOC.write_text(text)
        print(f"map: {MAP_DOC}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", help="campaign id under tests/wfe/results/campaigns")
    ap.add_argument("--arm", help="per-model review document for one arm")
    ap.add_argument("--allow-mixed", action="store_true")
    ap.add_argument("--out-dir", default=str(REPO / "docs"))
    ap.add_argument("--queue", type=Path, help="candidate queue (default candidate_queue.yaml)")
    ap.add_argument("--screen-out", type=Path, help="write the screen's advance list here")
    ap.add_argument("--fitness", action="store_true", help="confirm verdicts and dispositions")
    ap.add_argument(
        "--fitness-map",
        action="store_true",
        help="one disposition per queued model from all ledger cells (no campaign needed)",
    )
    ap.add_argument("--write-map", action="store_true", help="also write docs/WFE_FITNESS_MAP.md")
    ap.add_argument("--record", action="store_true", help="write --fitness cells to the ledger")
    ap.add_argument("--ledger", type=Path, help="fitness ledger path (default fitness_ledger.yaml)")
    args = ap.parse_args()
    if _fitness_map_cli(args):
        return 0
    if not args.campaign:
        ap.error("--campaign is required unless --fitness-map or --write-map is given")
    campaign_dir = CAMPAIGNS / args.campaign
    if not campaign_dir.is_dir():
        raise SystemExit(f"no such campaign: {campaign_dir}")

    if args.screen_out:
        res = screen_out(campaign_dir, args.queue, args.allow_mixed)
        for c in res["cells"]:
            print(f"  {c['verdict']:9s} {c['workspace']} <- {c['candidate']}: {c['reason']}")
        args.screen_out.parent.mkdir(parents=True, exist_ok=True)
        args.screen_out.write_text(yaml.safe_dump(res["advance"], sort_keys=True))
        n = sum(len(v) for v in res["advance"].values())
        print(f"advance: {args.screen_out} ({n} candidate cell(s))")
        return 0

    if args.record:
        res = record_ledger(campaign_dir, args.queue, args.ledger, args.allow_mixed)
        for c in res["cells"]:
            print(f"  {c['verdict']:14s} {c['workspace']} {c['model']}: {c['reason']}")
        print(f"ledger: {res['path']} (+{len(res['cells'])} cell(s), {res['kept']} kept)")
        return 0

    if args.fitness:
        res = fitness(campaign_dir, args.queue, args.allow_mixed)
        for c in res["cells"]:
            d = c["draws"]
            print(
                f"  {c['verdict']:14s} {c['workspace']} {c['candidate']}: {c['reason']} "
                f"[repeats {d['incumbent']['repeats']}/{d['candidate']['repeats']}, "
                f"served temperature {d['incumbent']['served_temperature']}/"
                f"{d['candidate']['served_temperature']}]"
            )
        for d in res["dispositions"]:
            print(f"  {d['disposition']:16s} {d['model']}: {d['reason']}")
        out = campaign_dir / "fitness.json"
        out.write_text(json.dumps(res, indent=1))
        print(f"fitness: {out}")
        return 0

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
