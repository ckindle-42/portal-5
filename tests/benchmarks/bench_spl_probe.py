#!/usr/bin/env python3
"""SPL / detection-authoring capability probe for models serving the auto-spl
intent (Splunk SPL queries, YARA rules, detection-search authoring).

Why this exists: auto-spl's job is authoring detection logic — given a threat,
write an SPL search that would actually catch it. A generic coding/chat score
says nothing about whether the emitted SPL targets the right index, sourcetype,
and the literal indicators that distinguish the attack. This probe scores against
the fleet's own ground-truth detection library
(portal/modules/security/core/siem/spl_detections.yaml): for a MITRE technique,
ask the model to author a detection, then check its SPL contains the reference
detection's discriminator tokens and expected signal.

Scored per technique (only the 16 techniques in the corpus that carry
discriminator_tokens are used, so every case has a gradeable ground truth):
  - targets_index    : SPL references the lab index (index=portal5_lab or similar)
  - discriminators   : fraction of the reference discriminator_tokens present in
                       the model's SPL (the literal markers that make the search
                       actually match the attack)
  - has_stats        : uses a transforming/stats command (a real detection
                       aggregates, not just a bare search)

A case passes if it names the index AND covers >=50% of discriminators. This
measures detection *validity against known-good reference logic*, not prose.

Emits tests/benchmarks/results/spl_probe_<UTC>.json (harness prefix `spl_probe`).
quality_score = fraction of cases passed.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OLLAMA_URL = "http://localhost:11434"
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"
SPL_CORPUS = REPO_ROOT / "portal" / "modules" / "security" / "core" / "siem" / "spl_detections.yaml"
TIMEOUT = 300
MAX_CASES = 8  # cap the sweep length; deterministic selection below


def load_corpus() -> dict:
    import yaml
    try:
        return yaml.safe_load(SPL_CORPUS.read_text()) or {}
    except Exception:
        return {}


def build_test_cases() -> list[dict]:
    corpus = load_corpus()
    cases = []
    for tech, entry in sorted(corpus.items()):
        df = entry.get("distinguishing_features") or {}
        toks = df.get("discriminator_tokens") or []
        if not toks:
            continue
        cases.append({
            "id": tech,
            "description": entry.get("description", ""),
            "expected_signal": entry.get("expected_signal", ""),
            "discriminators": toks,
            "reference_spl": entry.get("spl", ""),
            "prompt": (
                f"You are authoring a Splunk detection for MITRE ATT&CK technique "
                f"{tech} ({entry.get('description','')}). The lab data is in "
                f"`index=portal5_lab`. Write a single SPL search that detects this "
                f"technique — target the correct index and sourcetype, match the "
                f"literal indicators of the attack, and aggregate with stats. "
                f"Output only the SPL query in a code block."
            ),
        })
    return cases[:MAX_CASES]


def _extract_spl(text: str) -> str:
    m = re.search(r"```(?:spl|splunk|sql)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"```(?:spl|splunk|sql)?\s*\n(.*)\Z", text, re.DOTALL)
    if m:
        return m.group(1)
    # bare fallback: a line starting with index= or search
    for ln in text.splitlines():
        if re.search(r"\bindex\s*=", ln) or ln.strip().lower().startswith("search "):
            return text
    return ""


def _core_literal(tok: str) -> str:
    """Reduce a discriminator token to the literal that must appear in the SPL.
    Tokens are field patterns like 'NewProcessName=*lsass*'; the meaningful
    indicator is the value ('lsass'), stripped of field name, globs, and quotes."""
    v = tok.split("=", 1)[1] if "=" in tok else tok
    return v.strip('*"\' ').lower()


def _score_spl(spl: str, case: dict) -> dict:
    spl_l = spl.lower()
    targets_index = bool(re.search(r"index\s*=", spl_l))
    toks = case["discriminators"]
    cores = {c for c in (_core_literal(t) for t in toks) if c}
    present = sorted(c for c in cores if c in spl_l)
    disc_cov = round(len(present) / len(cores), 3) if cores else 0.0
    has_stats = bool(re.search(r"\b(stats|tstats|timechart|chart|eventstats)\b", spl_l))
    passed = targets_index and disc_cov >= 0.5
    return {
        "targets_index": targets_index,
        "discriminator_coverage": disc_cov,
        "discriminators_hit": present,
        "has_stats": has_stats,
        "passed": passed,
    }


def unload(model: str) -> None:
    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=json.dumps({"model": model, "keep_alive": 0}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=15).read()
    except Exception:
        pass


def run_case(model: str, case: dict) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": case["prompt"]}],
        "stream": False,
        "options": {"num_predict": 768},
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
        return {"id": case["id"], "ok": False, "error": str(e), "wall_s": time.monotonic() - t0}
    content = (data.get("message") or {}).get("content", "") or ""
    spl = _extract_spl(content)
    score = _score_spl(spl, case)
    eval_count = data.get("eval_count") or 0
    eval_duration_ns = data.get("eval_duration") or 0
    tps = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns else None
    return {
        "id": case["id"], "ok": True, "matched": score["passed"],
        "spl_score": score, "response_preview": content[:160],
        "tps": tps, "wall_s": time.monotonic() - t0,
    }


def probe_model(model: str, cases: list[dict]) -> dict:
    case_results = [run_case(model, c) for c in cases]
    unload(model)
    ok = [c for c in case_results if c.get("ok")]
    matched = sum(1 for c in ok if c.get("matched"))
    total = len(cases)
    tps_vals = [c["tps"] for c in ok if c.get("tps")]
    avg_tps = round(sum(tps_vals) / len(tps_vals), 2) if tps_vals else None
    cov = [c["spl_score"]["discriminator_coverage"] for c in ok if c.get("spl_score")]
    return {
        "model": model, "avg_tps": avg_tps,
        "quality_score": round(matched / total, 2) if total else None,
        "runs_success": matched, "runs_total": total,
        "prompt_category": "spl",
        "avg_discriminator_coverage": round(sum(cov) / len(cov), 3) if cov else None,
        "cases": case_results,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SPL / detection-authoring capability probe.")
    ap.add_argument("--model", action="append", required=True, help="Model tag (repeatable)")
    args = ap.parse_args(argv)
    cases = build_test_cases()
    if not cases:
        print("No SPL corpus cases found — check spl_detections.yaml path.")
        return 1
    print(f"Probing {len(args.model)} model(s) with {len(cases)} SPL detection cases each")
    results = []
    for i, model in enumerate(args.model, 1):
        print(f"  [{i}/{len(args.model)}] {model[:70]} ...", flush=True)
        r = probe_model(model, cases)
        results.append(r)
        print(f"    quality={r['quality_score']} disc_cov={r['avg_discriminator_coverage']} avg_tps={r['avg_tps']}")
    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"spl_probe_{stamp}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2))
    print(f"\nWrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
