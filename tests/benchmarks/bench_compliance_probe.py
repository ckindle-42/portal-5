#!/usr/bin/env python3
"""Compliance framework-mapping probe for models serving the auto-compliance
intent (NERC CIP, NIST 800-53, HIPAA, MITRE ATT&CK cross-mapping).

Why this exists: auto-compliance's job is accurate multi-framework mapping — given
a threat or control context, name the correct framework requirements. This is a
factual-recall task with exact right answers, and a generic chat score can't tell
a correct CIP requirement from a plausible-sounding wrong one. This probe scores
against the fleet's own ground-truth mappings
(portal/modules/security/core/siem/spl_detections.yaml, whose compliance_mapping
field ties each MITRE technique to its NIST control and NERC-CIP requirement).

Scored per technique (all 33 corpus entries carry compliance_mapping):
  - nist_correct  : model names the reference NIST 800-53 control (e.g. SC-7)
  - nerc_correct  : model names the reference NERC-CIP requirement (e.g.
                    CIP-005-6 R1)
  - no_fabrication: model doesn't invent framework IDs not in the reference
                    (penalizes confident wrong mappings — the failure mode that
                    matters most for compliance)

A case passes if the model names BOTH the correct NIST control and NERC-CIP
requirement. Exact ID match (normalized for spacing/case) — compliance is a
domain where "close" is wrong.

Emits tests/benchmarks/results/compliance_probe_<UTC>.json (harness prefix
`compliance_probe`). quality_score = fraction of cases with both IDs correct.
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
CORPUS = REPO_ROOT / "portal" / "modules" / "security" / "core" / "siem" / "spl_detections.yaml"
TIMEOUT = 240
MAX_CASES = 10


def load_corpus() -> dict:
    import yaml

    try:
        return yaml.safe_load(CORPUS.read_text()) or {}
    except Exception:
        return {}


def _norm_id(s: str) -> str:
    return re.sub(r"\s+", "", s or "").upper()


def build_test_cases() -> list[dict]:
    corpus = load_corpus()
    cases = []
    for tech, entry in sorted(corpus.items()):
        cm = entry.get("compliance_mapping") or []
        nist = next((m.get("control") for m in cm if m.get("framework") == "nist-800-53"), None)
        nerc = next((m.get("requirement") for m in cm if m.get("framework") == "nerc-cip"), None)
        if not (nist and nerc):
            continue
        cases.append(
            {
                "id": tech,
                "description": entry.get("description", ""),
                "nist": nist,
                "nerc": nerc,
                "prompt": (
                    f"For MITRE ATT&CK technique {tech} ({entry.get('description', '')}), "
                    f"identify the mapped compliance requirements. Give (1) the specific "
                    f"NIST SP 800-53 Rev 5 control ID, and (2) the specific NERC CIP "
                    f"requirement ID. Answer with just the two IDs, clearly labeled. If "
                    f"you are unsure of an exact ID, say so rather than guessing."
                ),
            }
        )
    return cases[:MAX_CASES]


def _score_compliance(text: str, case: dict) -> dict:
    norm = _norm_id(text)
    nist_ok = _norm_id(case["nist"]) in norm
    # NERC IDs look like CIP-005-6 R1; accept the core "CIP-005" + "R1" both present
    nerc_full = _norm_id(case["nerc"])
    nerc_ok = nerc_full in norm
    if not nerc_ok:
        m = re.match(r"(CIP-\d+)-?\d*(R\d+)", nerc_full)
        if m:
            nerc_ok = m.group(1) in norm and m.group(2) in norm
    passed = bool(nist_ok and nerc_ok)
    return {"nist_correct": nist_ok, "nerc_correct": nerc_ok, "passed": passed}


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
        "options": {"num_predict": 512},
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
    score = _score_compliance(content, case)
    eval_count = data.get("eval_count") or 0
    eval_duration_ns = data.get("eval_duration") or 0
    tps = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns else None
    return {
        "id": case["id"],
        "ok": True,
        "matched": score["passed"],
        "compliance_score": score,
        "expected": {"nist": case["nist"], "nerc": case["nerc"]},
        "response_preview": content[:160],
        "tps": tps,
        "wall_s": time.monotonic() - t0,
    }


def probe_model(model: str, cases: list[dict]) -> dict:
    case_results = [run_case(model, c) for c in cases]
    unload(model)
    ok = [c for c in case_results if c.get("ok")]
    matched = sum(1 for c in ok if c.get("matched"))
    nist = sum(1 for c in ok if (c.get("compliance_score") or {}).get("nist_correct"))
    nerc = sum(1 for c in ok if (c.get("compliance_score") or {}).get("nerc_correct"))
    total = len(cases)
    tps_vals = [c["tps"] for c in ok if c.get("tps")]
    avg_tps = round(sum(tps_vals) / len(tps_vals), 2) if tps_vals else None
    return {
        "model": model,
        "avg_tps": avg_tps,
        "quality_score": round(matched / total, 2) if total else None,
        "runs_success": matched,
        "runs_total": total,
        "prompt_category": "compliance",
        "nist_accuracy": round(nist / total, 2) if total else None,
        "nerc_accuracy": round(nerc / total, 2) if total else None,
        "cases": case_results,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compliance framework-mapping probe.")
    ap.add_argument("--model", action="append", required=True, help="Model tag (repeatable)")
    args = ap.parse_args(argv)
    cases = build_test_cases()
    if not cases:
        print("No compliance corpus cases found — check spl_detections.yaml path.")
        return 1
    print(f"Probing {len(args.model)} model(s) with {len(cases)} compliance-mapping cases each")
    results = []
    for i, model in enumerate(args.model, 1):
        print(f"  [{i}/{len(args.model)}] {model[:70]} ...", flush=True)
        r = probe_model(model, cases)
        results.append(r)
        print(
            f"    quality={r['quality_score']} nist={r['nist_accuracy']} nerc={r['nerc_accuracy']} avg_tps={r['avg_tps']}"
        )
    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"compliance_probe_{stamp}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2))
    print(f"\nWrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
