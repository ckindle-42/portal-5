#!/usr/bin/env python3
"""Seat-qualification probe for the compliance judgment step
(TASK_COMPLIANCE_REASONING_V6 D0-M).

Runs every candidate seat model against the 30 authored cases in
``tests/compliance_probe/judgment_probe_v6.jsonl`` and measures the seat
properties §D0-M requires — *not* leaderboard position:

  - F2 (recall x2) primary; F1 and MCC secondary
  - abstention honesty  : ABSTAIN cases must abstain; complete cases must not
  - JSON validity rate  : fraction of runs that emit one parseable object
  - citation discipline : cited refs must be a superset of gold_citation and
                          must not name a ref outside the packet
  - must-not-flag FP    : stricter-than-required cases flagged as violations
  - throughput          : tokens/sec at real packet size on this hardware

The judge prompt hands the model a STRUCTURED JSON packet (governing CU +
premises + candidate) and forbids inference from silence, mirroring the P5
council contract. Output must be a single JSON object:
  {"determination": "SUPPORTED|PARTIAL|CONTRADICTED|ABSENT|ABSTAIN",
   "finding_type": null|"GAP"|"CONTRADICTION"|"OUTDATED_LANGUAGE"|"WEAK_MAPPING",
   "cited_refs": ["<register ref>", ...],
   "rationale": "<one sentence>"}

Emits tests/benchmarks/results/judgment_probe_v6_<UTC>.json (harness prefix
``judgment_probe_v6``).

Usage:
  uv run python tests/benchmarks/bench_judgment_probe_v6.py \
      --models granite4.2:30b-q4_K_M hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k
  uv run python tests/benchmarks/bench_judgment_probe_v6.py --seats-file seats.txt
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import json
import math
import re
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OLLAMA_URL = "http://localhost:11434"
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"
PROBE = REPO_ROOT / "tests" / "compliance_probe" / "judgment_probe_v6.jsonl"
TIMEOUT = 300

_VIOLATION_LABELS = {"PARTIAL", "CONTRADICTED", "ABSENT"}
_ALL_LABELS = {"SUPPORTED", "PARTIAL", "CONTRADICTED", "ABSENT", "ABSTAIN"}


def load_cases() -> list[dict]:
    return [json.loads(line) for line in PROBE.read_text().splitlines() if line.strip()]


def packet(case: dict) -> str:
    """The structured JSON packet handed to the seat — the pre-analyzed
    problem, exactly what P4's gate would produce for a single anchor."""
    return json.dumps(
        {
            "governing_unit": {
                "ref": case["governing_ref"],
                "text": case["governing_text"],
            },
            "premises": case.get("premises", []),
            "candidate_implementation": case["candidate_text"],
            "packet_complete": case["packet_complete"],
        },
        indent=2,
    )


_SYSTEM = (
    "You are one sealed seat on a compliance review council. You are given a "
    "PRE-ANALYZED problem: one governing compliance unit, the premises the "
    "analyst attached, and one candidate internal implementation (or null). "
    "Decide only whether the candidate satisfies the governing unit.\n"
    "RULES:\n"
    "- Judge ONLY the governing unit given. Do not invent obligations.\n"
    "- A stricter internal rule (more frequent, shorter deadline, longer "
    "retention) SATISFIES a governing maximum/minimum — it is never a violation.\n"
    "- Do NOT infer from silence. If the packet is incomplete, or a premise you "
    "need (a defined term, an applicability fact) is missing, return ABSTAIN.\n"
    "- ABSENT means: the packet is complete and no candidate addresses the unit.\n"
    "- Cite every register ref your determination rests on, and cite nothing "
    "that is not in the packet.\n"
    "Return ONE JSON object, no prose around it:\n"
    '{"determination":"SUPPORTED|PARTIAL|CONTRADICTED|ABSENT|ABSTAIN",'
    '"finding_type":null|"GAP"|"CONTRADICTION"|"OUTDATED_LANGUAGE"|"WEAK_MAPPING",'
    '"cited_refs":["..."],"rationale":"one sentence"}'
)


def parse_output(text: str) -> dict | None:
    """Extract the last balanced JSON object. None => schema-invalid."""
    depth = 0
    start = -1
    best = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                best = text[start : i + 1]
    if not best:
        return None
    try:
        obj = json.loads(best)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or "determination" not in obj:
        return None
    return obj


def norm_ref(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().upper()


_STD_RE = re.compile(r"CIP[-\s]?0?(\d{2,3})", re.I)


def std_nums(text: str) -> set[str]:
    """CIP standard numbers named in a string, e.g. 'CIP-007-6 R2' -> {'7'}."""
    return {m.group(1).lstrip("0") for m in _STD_RE.finditer(text or "")}


def score_case(case: dict, obj: dict | None, packet_refs: set[str]) -> dict:
    gold = case["gold_label"]
    if obj is None:
        return {
            "schema_ok": False,
            "pred": None,
            "correct": False,
            "false_supported": gold in _VIOLATION_LABELS,
            "missed_abstain": gold == "ABSTAIN",
            "must_not_flag_fp": False,
            "citation_ok": False,
        }
    pred = norm_ref(obj.get("determination"))
    pred = pred if pred in _ALL_LABELS else "?"
    cited = [str(r) for r in (obj.get("cited_refs") or []) if r]
    cited_norm = {norm_ref(r) for r in cited}
    gold_cite = {norm_ref(r) for r in case["gold_citation"]}
    # gold refs must be present (substring-tolerant: "CIP-007-6 R2 Part 2.2"
    # is satisfied by a cite of the same, case/space-insensitive)
    gold_present = all(any(g in c or c in g for c in cited_norm) for g in gold_cite)
    # discipline: no cited ref may name a CIP standard absent from the packet
    allowed_stds = packet_refs | {s for g in case["gold_citation"] for s in std_nums(g)}
    off_allowlist = any((std_nums(r) - allowed_stds) for r in cited)
    citation_ok = gold_present and not off_allowlist and bool(cited)
    correct = pred == norm_ref(gold)
    false_supported = gold in _VIOLATION_LABELS and pred == "SUPPORTED"
    missed_abstain = gold == "ABSTAIN" and pred != "ABSTAIN"
    spurious_abstain = gold != "ABSTAIN" and pred == "ABSTAIN"
    mnf_fp = bool(case.get("must_not_flag")) and pred in _VIOLATION_LABELS
    return {
        "schema_ok": True,
        "pred": pred,
        "correct": correct,
        "false_supported": false_supported,
        "missed_abstain": missed_abstain,
        "spurious_abstain": spurious_abstain,
        "must_not_flag_fp": mnf_fp,
        "citation_ok": citation_ok,
    }


def prf(tp: int, fp: int, fn: int, beta: float) -> float:
    if tp == 0:
        return 0.0
    p = tp / (tp + fp)
    r = tp / (tp + fn)
    if p + r == 0:
        return 0.0
    b2 = beta * beta
    return (1 + b2) * p * r / (b2 * p + r)


def aggregate(rows: list[dict], cases: list[dict]) -> dict:
    # violation detection: positive class = "this CU is not satisfied"
    tp = fp = fn = tn = 0
    for case, row in zip(cases, rows, strict=True):
        if not row.get("schema_ok"):
            if case["gold_label"] in _VIOLATION_LABELS:
                fn += 1
            continue
        gold_pos = case["gold_label"] in _VIOLATION_LABELS
        pred_pos = row["pred"] in _VIOLATION_LABELS
        if gold_pos and pred_pos:
            tp += 1
        elif gold_pos and not pred_pos:
            fn += 1
        elif not gold_pos and pred_pos:
            fp += 1
        else:
            tn += 1
    mcc_d = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    mcc = ((tp * tn) - (fp * fn)) / mcc_d if mcc_d else 0.0
    n = len(cases)
    schema_ok = sum(1 for r in rows if r.get("schema_ok"))
    abst = [r for c, r in zip(cases, rows, strict=True) if c["category"] == "ABSTAIN"]
    complete = [(c, r) for c, r in zip(cases, rows, strict=True) if c["packet_complete"]]
    return {
        "n": n,
        "exact_accuracy": round(sum(1 for r in rows if r.get("correct")) / n, 4),
        "F2_violation": round(prf(tp, fp, fn, 2.0), 4),
        "F1_violation": round(prf(tp, fp, fn, 1.0), 4),
        "MCC_violation": round(mcc, 4),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "false_supported_count": sum(1 for r in rows if r.get("false_supported")),
        "schema_valid_rate": round(schema_ok / n, 4),
        "citation_ok_rate": round(sum(1 for r in rows if r.get("citation_ok")) / n, 4),
        "abstain_recall": round(sum(1 for r in abst if r.get("pred") == "ABSTAIN") / len(abst), 4)
        if abst
        else None,
        "spurious_abstain_rate": round(
            sum(1 for _, r in complete if r.get("spurious_abstain")) / len(complete), 4
        )
        if complete
        else None,
        "must_not_flag_fp_count": sum(1 for r in rows if r.get("must_not_flag_fp")),
    }


def unload(model: str) -> None:
    with contextlib.suppress(Exception):
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=json.dumps({"model": model, "keep_alive": 0}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=20).read()


_SAMPLING_KEYS = ("temperature", "top_p", "top_k", "min_p", "repeat_penalty", "num_ctx")


def _post(path: str, payload: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA_URL}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed localhost
        return json.load(r)


def preflight(model: str) -> dict:
    """Verify the seat is usable before scoring it (Y28 + the operator's note
    that chat templates / sampling settings are often wrong out of the box):

    - capture the modelfile's baked sampling params + context length
    - a strict-JSON round-trip: is the output one parseable object?
    - a thinking-leak check: does raw output contain <think>?
    - a system-honored check: does a system instruction override a naive read
      of the user message?

    Returns the baked options to use for scoring and a verdict; a seat that
    fails preflight is still scored but every number is flagged config_unverified.
    """
    out: dict = {"model": model}
    with contextlib.suppress(Exception):
        show = _post("/api/show", {"model": model}, timeout=60)
        params = {}
        for line in (show.get("parameters") or "").splitlines():
            k, _, v = line.strip().partition(" ")
            if k in _SAMPLING_KEYS:
                with contextlib.suppress(ValueError):
                    params[k] = float(v) if "." in v else int(v)
        out["baked_params"] = params
        out["template_sha"] = _sha(show.get("template", ""))
        out["num_ctx_baked"] = params.get("num_ctx")

    opts = {"temperature": 0.0, "num_predict": 200}
    try:
        r1 = _post(
            "/api/chat",
            {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": 'Reply with exactly {"ok": true} and nothing else.',
                    },
                    {"role": "user", "content": "go"},
                ],
                "stream": False,
                "format": "json",
                "think": False,
                "options": opts,
            },
        )
        raw = (r1.get("message") or {}).get("content", "") or ""
        out["json_ok"] = parse_output(raw) is not None or _is_json(raw)
        out["think_leak"] = "<think>" in raw.lower()
    except Exception as e:  # noqa: BLE001
        out["json_ok"] = False
        out["error"] = str(e)

    try:
        r2 = _post(
            "/api/chat",
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": "Always answer the single word: BLUE."},
                    {"role": "user", "content": "What colour is grass? Answer in one word."},
                ],
                "stream": False,
                "think": False,
                "options": {"temperature": 0.0, "num_predict": 20},
            },
        )
        out["system_honored"] = (
            "blue" in ((r2.get("message") or {}).get("content", "") or "").lower()
        )
    except Exception:  # noqa: BLE001
        out["system_honored"] = None

    out["verdict"] = (
        "OK" if (out.get("json_ok") and not out.get("think_leak")) else "CONFIG_UNVERIFIED"
    )
    unload(model)
    return out


def _sha(s: str) -> str:
    import hashlib

    return hashlib.sha256(s.encode()).hexdigest()[:12]


def _is_json(s: str) -> bool:
    with contextlib.suppress(json.JSONDecodeError):
        json.loads(s.strip())
        return True
    return False


def run_case(model: str, case: dict, baked: dict | None = None) -> dict:
    # the model's own baked sampling params (from /api/show), with a
    # deterministic temperature and a fixed predict budget for the task
    opts = {k: v for k, v in (baked or {}).items() if k != "num_ctx"}
    opts.update({"temperature": 0.0, "num_predict": 700})
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": packet(case)},
        ],
        "stream": False,
        "format": "json",
        "think": False,  # Qwen3/DeepSeek/GLM-Z1 templates open <think> by default
        # and loop or truncate on a strict-JSON task unless reasoning is suppressed
        "options": opts,
    }
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.load(r)
    except Exception as e:
        return {"id": case["id"], "error": str(e), "wall_s": round(time.monotonic() - t0, 2)}
    content = (data.get("message") or {}).get("content", "") or ""
    obj = parse_output(content)
    ec, ed = data.get("eval_count") or 0, data.get("eval_duration") or 0
    pc = data.get("prompt_eval_count") or 0
    return {
        "id": case["id"],
        "raw": content[:2000],
        "raw_full": content,  # untruncated — for offline re-scoring
        "request": payload,  # the exact request sent — reproduces the call
        "parsed": obj,
        "prompt_tokens": pc,
        "eval_tokens": ec,
        "tps": round(ec / (ed / 1e9), 1) if ed else None,
        "wall_s": round(time.monotonic() - t0, 2),
    }


_MODEL_BUDGET_S = 2400  # a model that cannot finish 30 cases in 40 min is a
# capability/thinking-mode failure — record what ran and move on


def _debug_line(case: dict, prefs: set[str], run: dict, score: dict) -> dict:
    """One fully self-contained record per case — the request, the untruncated
    raw response, the parse, the per-field score, the gold, the packet
    allowlist. `rescore_debug_dir` replays these without touching a model."""
    return {
        "id": case["id"],
        "category": case["category"],
        "gold_label": case["gold_label"],
        "gold_finding_type": case.get("gold_finding_type"),
        "gold_citation": case["gold_citation"],
        "must_not_flag": bool(case.get("must_not_flag")),
        "packet_std_allowlist": sorted(prefs),
        "request": run.get("request"),
        "raw_response": run.get("raw_full", run.get("raw", "")),
        "parsed": run.get("parsed"),
        "error": run.get("error"),
        "prompt_tokens": run.get("prompt_tokens"),
        "tps": run.get("tps"),
        "wall_s": run.get("wall_s"),
        "score": score,
    }


def run_model(model: str, cases: list[dict], *, debug_dir: Path | None = None) -> dict:
    pf = preflight(model)
    print(
        f"  preflight: {pf['verdict']}  json_ok={pf.get('json_ok')} "
        f"think_leak={pf.get('think_leak')} system_honored={pf.get('system_honored')} "
        f"ctx_baked={pf.get('num_ctx_baked')} params={pf.get('baked_params')}",
        flush=True,
    )
    baked = pf.get("baked_params", {})
    dbg = None
    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", model)[:120]
        dbg = (debug_dir / f"{slug}.debug.jsonl").open("w")
        dbg.write(json.dumps({"_meta": "preflight", "model": model, **pf}) + "\n")
    packet_refs_by_case = []
    for c in cases:
        blob = " ".join([c["governing_ref"], c["governing_text"], *c.get("premises", [])])
        packet_refs_by_case.append(std_nums(blob))
    runs, scored = [], []
    t_start = time.monotonic()
    for case, prefs in zip(cases, packet_refs_by_case, strict=True):
        if time.monotonic() - t_start > _MODEL_BUDGET_S:
            run = {"id": case["id"], "error": "model budget exceeded — skipped"}
            sc = score_case(case, None, prefs)
            runs.append(run)
            scored.append(sc)
            if dbg:
                dbg.write(json.dumps(_debug_line(case, prefs, run, sc)) + "\n")
            print(f"  {case['id']:8} SKIPPED (model over {_MODEL_BUDGET_S}s budget)", flush=True)
            continue
        run = run_case(model, case, baked)
        sc = score_case(case, run.get("parsed"), prefs)
        runs.append(run)
        scored.append(sc)
        if dbg:
            dbg.write(json.dumps(_debug_line(case, prefs, run, sc)) + "\n")
            dbg.flush()
        print(
            f"  {case['id']:8} gold={case['gold_label']:12} "
            f"pred={(sc.get('pred') or 'ERR'):12} "
            f"{'ok' if sc.get('correct') else '  '} "
            f"cite={'y' if sc.get('citation_ok') else 'n'} "
            f"{run.get('tps') or '-'}tps",
            flush=True,
        )
    if dbg:
        dbg.close()
    # keep the results JSON small — the debug JSONL holds the full payloads
    for r in runs:
        r.pop("raw_full", None)
        r.pop("request", None)
    unload(model)
    agg = aggregate(scored, cases)
    prompt_toks = [r["prompt_tokens"] for r in runs if r.get("prompt_tokens")]
    tpss = [r["tps"] for r in runs if r.get("tps")]
    agg["median_prompt_tokens"] = (
        sorted(prompt_toks)[len(prompt_toks) // 2] if prompt_toks else None
    )
    agg["max_prompt_tokens"] = max(prompt_toks) if prompt_toks else None
    agg["median_tps"] = sorted(tpss)[len(tpss) // 2] if tpss else None
    agg["errors"] = sum(1 for r in runs if r.get("error"))
    agg["config_unverified"] = pf["verdict"] != "OK"
    return {"model": model, "preflight": pf, "aggregate": agg, "runs": runs, "case_scores": scored}


def rescore_debug_dir(debug_dir: Path) -> list[dict]:
    """Re-score every seat from its saved ``.debug.jsonl`` WITHOUT touching a
    model. Use after a scorer change or bug fix — the raw responses are kept
    verbatim, so the F2 numbers can be regenerated in seconds."""
    cases = load_cases()
    by_id = {c["id"]: c for c in cases}
    out = []
    for f in sorted(debug_dir.glob("*.debug.jsonl")):
        lines = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
        pf = next((x for x in lines if x.get("_meta") == "preflight"), {})
        rows = [x for x in lines if x.get("_meta") != "preflight"]
        scored, runs, ordered_cases = [], [], []
        for row in rows:
            c = by_id.get(row["id"])
            if not c:
                continue
            prefs = set(row.get("packet_std_allowlist", []))
            obj = parse_output(row.get("raw_response", "")) if not row.get("error") else None
            sc = score_case(c, obj, prefs)
            scored.append(sc)
            runs.append(
                {
                    "id": row["id"],
                    "parsed": obj,
                    "tps": row.get("tps"),
                    "prompt_tokens": row.get("prompt_tokens"),
                    "error": row.get("error"),
                }
            )
            ordered_cases.append(c)
        agg = aggregate(scored, ordered_cases)
        tpss = sorted(r["tps"] for r in runs if r.get("tps"))
        ptoks = sorted(r["prompt_tokens"] for r in runs if r.get("prompt_tokens"))
        agg["median_tps"] = tpss[len(tpss) // 2] if tpss else None
        agg["median_prompt_tokens"] = ptoks[len(ptoks) // 2] if ptoks else None
        agg["max_prompt_tokens"] = max(ptoks) if ptoks else None
        agg["errors"] = sum(1 for r in runs if r.get("error"))
        agg["config_unverified"] = pf.get("verdict", "OK") != "OK"
        out.append(
            {
                "model": pf.get("model", f.stem),
                "preflight": pf,
                "aggregate": agg,
                "runs": runs,
                "case_scores": scored,
                "rescored": True,
            }
        )
    return out


def _write_results(
    out: Path, ts: str, cases: list[dict], results: list[dict], complete: bool
) -> None:
    out.write_text(
        json.dumps(
            {
                "probe": "judgment_probe_v6",
                "probe_sha": _probe_sha(),
                "utc": ts,
                "hardware": _hw(),
                "n_cases": len(cases),
                "models": results,
                "complete": complete,
            },
            indent=2,
        )
    )


def _notify(event_type: str, message: str, metadata: dict | None = None) -> None:
    """Best-effort push to the enabled channels (Slack/Telegram/Pushover/…),
    gated on NOTIFICATIONS_ENABLED — same pattern as tests/uat/notify.py."""
    import os

    with contextlib.suppress(Exception):
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
    if os.environ.get("NOTIFICATIONS_ENABLED", "false").lower() not in ("true", "1", "yes"):
        return
    with contextlib.suppress(Exception):
        import asyncio

        from portal.platform.inference.notifications.channels.pushover import PushoverChannel
        from portal.platform.inference.notifications.channels.slack import SlackChannel
        from portal.platform.inference.notifications.channels.telegram import TelegramChannel
        from portal.platform.inference.notifications.dispatcher import NotificationDispatcher
        from portal.platform.inference.notifications.events import AlertEvent, EventType

        d = NotificationDispatcher()
        for ch in (SlackChannel, TelegramChannel, PushoverChannel):
            d.add_channel(ch())
        asyncio.run(
            d.dispatch(
                AlertEvent(
                    type=EventType(event_type),
                    message=message,
                    workspace="compliance-seat-sweep",
                    metadata=metadata or {},
                )
            )
        )


def _seat_summary(r: dict) -> str:
    a = r["aggregate"]
    flag = "  [CONFIG_UNVERIFIED]" if a.get("config_unverified") else ""
    return (
        f"{r['model']}{flag}\n"
        f"  F2 {a['F2_violation']}  F1 {a['F1_violation']}  MCC {a['MCC_violation']}  "
        f"acc {a['exact_accuracy']}\n"
        f"  schema {a['schema_valid_rate']}  citation {a['citation_ok_rate']}  "
        f"abstain-recall {a.get('abstain_recall')}\n"
        f"  false-supported {a['false_supported_count']}  must-not-flag-FP "
        f"{a['must_not_flag_fp_count']}  errors {a.get('errors', 0)}\n"
        f"  median {a.get('median_tps')} tps @ {a.get('max_prompt_tokens')} prompt tokens"
    )


def _per_case_table(r: dict) -> str:
    rows = []
    for cs in r.get("case_scores", []):
        mark = "ok" if cs.get("correct") else "  "
        rows.append(f"  {mark} gold={cs.get('pred', '?')}")
    return "\n".join(
        f"  {'ok' if cs.get('correct') else 'XX'}  pred={cs.get('pred') or 'ERR':13} "
        f"cite={'y' if cs.get('citation_ok') else 'n'} "
        f"{'<fSUP>' if cs.get('false_supported') else ''}"
        for cs in r.get("case_scores", [])
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=[])
    ap.add_argument("--seats-file", type=Path)
    ap.add_argument("--debug-dir", type=Path, help="write a full per-case .debug.jsonl per seat")
    ap.add_argument("--rescore", type=Path, help="re-score a debug dir; no model calls")
    ap.add_argument(
        "--notify", action="store_true", help="push start/per-seat/done to enabled channels"
    )
    args = ap.parse_args()

    cases = load_cases()
    assert len(cases) == 30, f"probe has {len(cases)} cases, expected 30"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")

    if args.rescore:
        results = rescore_debug_dir(args.rescore)
        out = RESULTS_DIR / f"judgment_probe_v6_rescored_{ts}.json"
        _write_results(out, ts, cases, results, complete=True)
        _print_table(results)
        print(f"\nre-scored {len(results)} seat(s) from {args.rescore} -> {out}")
        return

    models = list(args.models)
    if args.seats_file:
        models += [
            ln.strip()
            for ln in args.seats_file.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
    if not models:
        ap.error("no models given (--models or --seats-file)")

    debug_dir = args.debug_dir
    out = RESULTS_DIR / f"judgment_probe_v6_{ts}.json"
    if args.notify:
        _notify(
            "test_start",
            f"compliance seat sweep started — {len(models)} seat(s), {len(cases)} cases\n"
            f"results: {out.name}   debug: {debug_dir or '(none)'}",
            {"seats": models, "cases": len(cases)},
        )
    results = []
    for i, m in enumerate(models, 1):
        print(f"\n=== [{i}/{len(models)}] {m} ===", flush=True)
        t0 = time.monotonic()
        results.append(run_model(m, cases, debug_dir=debug_dir))
        _write_results(out, ts, cases, results, complete=False)
        elapsed = round(time.monotonic() - t0)
        summary = _seat_summary(results[-1])
        print(summary, flush=True)
        if args.notify:
            extra = ""
            if i == 1:
                extra = (
                    "\n\n— baseline: this is what a working seat looks like; "
                    "later seats compare against this —\n" + _per_case_table(results[-1])
                )
            _notify(
                "test_summary",
                f"seat [{i}/{len(models)}] done in {elapsed}s\n{summary}{extra}",
                {"seat": m, "index": i, "f2": results[-1]["aggregate"]["F2_violation"]},
            )
    _write_results(out, ts, cases, results, complete=True)
    _print_table(results)
    if args.notify:
        ranked = sorted(results, key=lambda r: -r["aggregate"]["F2_violation"])
        best = ranked[0]
        _notify(
            "test_end",
            f"compliance seat sweep complete — {len(results)} seat(s)\n"
            f"best F2: {best['model']} @ {best['aggregate']['F2_violation']}\n"
            f"{out}",
            {"best_seat": best["model"], "best_f2": best["aggregate"]["F2_violation"]},
        )
    print(f"\nwrote {out}")


def _print_table(results: list[dict]) -> None:
    print(
        f"\n{'model':52} {'F2':>6} {'F1':>6} {'MCC':>6} {'acc':>6} {'sch':>5} "
        f"{'cite':>5} {'abst':>5} {'fSUP':>5} {'MNF':>4} {'tps':>6} {'ptok':>6}"
    )
    for r in results:
        a = r["aggregate"]
        print(
            f"{r['model'][:52]:52} {a['F2_violation']:6.3f} {a['F1_violation']:6.3f} "
            f"{a['MCC_violation']:6.3f} {a['exact_accuracy']:6.3f} "
            f"{a['schema_valid_rate']:5.2f} {a['citation_ok_rate']:5.2f} "
            f"{(a['abstain_recall'] or 0):5.2f} {a['false_supported_count']:5d} "
            f"{a['must_not_flag_fp_count']:4d} {(a['median_tps'] or 0):6.1f} "
            f"{(a['max_prompt_tokens'] or 0):6d}"
        )


def _probe_sha() -> str:
    import hashlib

    return hashlib.sha256(PROBE.read_bytes()).hexdigest()[:16]


def _hw() -> dict:
    import platform
    import subprocess

    info = {"platform": platform.platform(), "machine": platform.machine()}
    with contextlib.suppress(Exception):
        info["chip"] = subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True, timeout=5
        ).strip()
    return info


if __name__ == "__main__":
    main()
