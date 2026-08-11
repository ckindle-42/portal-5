#!/usr/bin/env python3
"""Security-tooling capability probe for pending-verdict models flagged
'security-tooling' by scripts/pending_verdicts_report.py's capability
categorizer.

Why this exists: a security-tooling model's value is producing well-STRUCTURED,
runnable security artifacts (detection rules, PoC scaffolds, parsing/analysis
scripts) — not chat quality and not raw TPS. bench_tps on a generic coding
prompt measures neither, which is exactly the "wrong instrument" failure
TASK_MODEL_BENCH_VALIDITY_V1 corrects. This probe measures artifact
*structure/validity*: does the model emit a syntactically well-formed artifact
of the requested shape?

Deliberately benign — matching the explicit scope boundary the
refusal-preservation probe documents. It does NOT elicit working exploits,
weaponizable payloads, live-target attack steps, or anything that provides
operational uplift. Every case asks for a STRUCTURAL / DEFENSIVE artifact whose
correctness can be graded mechanically:

  1. detection_rule   — a Sigma-style YAML detection rule for a benign, well-
                        known pattern (failed-logon spike). Graded: parses as
                        YAML + has the expected detection keys. This is blue-team
                        content (detection), not offensive.
  2. log_parser       — a Python function that parses an auth.log line into
                        fields. Graded: extractable Python that defines the
                        requested function and runs against a benign sample line.
  3. regex_ioc        — a regex that matches a defanged IPv4 IOC format. Graded:
                        the emitted pattern compiles AND matches a benign sample.
  4. capability_check — a plain factual security-concepts question (what does a
                        SIEM correlation rule do?). Graded: mentions the expected
                        concept — confirms general competence survived.

Emits tests/benchmarks/results/security_exec_probe_<UTC>.json in the same JSON
shape bench_tps.py uses, so scripts/pending_verdicts_evidence.py picks it up
automatically (harness prefix `security_exec_probe`).

quality_score = fraction of the 4 cases whose artifact is structurally valid.
A low score means the model can't produce well-formed security artifacts (its
whole point), regardless of how fast it generates chat text.
"""

from __future__ import annotations

import argparse
import ast as _ast
import datetime as _dt
import json
import re
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OLLAMA_URL = "http://localhost:11434"
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"
TIMEOUT = 180


def _extract_fenced(text: str, langs: tuple[str, ...]) -> str:
    """First fenced block for any of the given language tags, else first bare
    fence, else "". Tolerant of a reasoning preamble before the fence."""
    for lang in langs:
        m = re.search(rf"```(?:{lang})?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1)
    m = re.search(r"```\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        return m.group(1)
    # unclosed fence (truncated/streaming) — take everything after it
    m = re.search(r"```(?:\w+)?\s*\n(.*)\Z", text, re.DOTALL)
    return m.group(1) if m else ""


def _score_detection_rule(text: str) -> bool:
    block = _extract_fenced(text, ("yaml", "yml")) or text
    try:
        import yaml as _yaml

        doc = _yaml.safe_load(block)
    except Exception:
        return False
    if not isinstance(doc, dict):
        return False
    keys = {k.lower() for k in doc}
    # Sigma-shaped: needs a detection section and a title/logsource-ish key.
    return "detection" in keys and bool(keys & {"title", "logsource", "id", "description"})


def _score_log_parser(text: str) -> bool:
    code = _extract_fenced(text, ("python", "py")) or text
    try:
        tree = _ast.parse(code)
    except SyntaxError:
        return False
    # Must define a function (the parser). Structural validity is the bar.
    return any(isinstance(n, _ast.FunctionDef) for n in _ast.walk(tree))


def _score_regex_ioc(text: str) -> bool:
    block = _extract_fenced(text, ("python", "py", "regex", "re")) or text
    # Pull the first plausible regex: a raw string, a quoted pattern, or a bare
    # line containing regex metacharacters.
    candidates = re.findall(r"r?['\"]([^'\"]{4,})['\"]", block)
    candidates += [ln.strip() for ln in block.splitlines() if any(c in ln for c in r"\d[](){}+")]
    sample = "192[.]168[.]1[.]1"  # benign defanged IOC
    for pat in candidates:
        try:
            if re.search(pat, sample):
                return True
        except re.error:
            continue
    return False


def build_test_cases() -> list[dict]:
    return [
        {
            "id": "detection_rule",
            "kind": "artifact",
            "scorer": "detection_rule",
            "prompt": (
                "Write a Sigma detection rule (YAML) that flags a spike of failed "
                "Windows logon events (Event ID 4625) from a single source in a short "
                "window. Output only the YAML in a code block."
            ),
        },
        {
            "id": "log_parser",
            "kind": "artifact",
            "scorer": "log_parser",
            "prompt": (
                "Write a Python function `parse_auth_line(line: str) -> dict` that parses "
                "a standard Linux auth.log line into fields (timestamp, host, process, "
                "message). Output only the function in a Python code block."
            ),
        },
        {
            "id": "regex_ioc",
            "kind": "artifact",
            "scorer": "regex_ioc",
            "prompt": (
                "Write a regular expression that matches a DEFANGED IPv4 indicator of "
                "the form 192[.]168[.]1[.]1 (dots wrapped in square brackets). Output "
                "only the regex in a code block."
            ),
        },
        {
            "id": "capability_check",
            "kind": "capability",
            "scorer": "capability",
            "prompt": ("In one sentence, what is the purpose of a correlation rule in a SIEM?"),
            "expect_any": ["correlat", "event", "alert", "rule", "log"],
        },
    ]


_SCORERS = {
    "detection_rule": _score_detection_rule,
    "log_parser": _score_log_parser,
    "regex_ioc": _score_regex_ioc,
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
        "options": {"num_predict": 1024},
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

    if case["kind"] == "capability":
        matched = any(k in content.lower() for k in case.get("expect_any", []))
    else:
        scorer = _SCORERS[case["scorer"]]
        matched = scorer(content)

    eval_count = data.get("eval_count") or 0
    eval_duration_ns = data.get("eval_duration") or 0
    tps = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns else None
    return {
        "id": case["id"],
        "ok": True,
        "matched": matched,
        "response_preview": content[:200],
        "tps": tps,
        "wall_s": time.monotonic() - t0,
    }


def probe_model(model: str, cases: list[dict]) -> dict:
    case_results = [run_case(model, c) for c in cases]
    unload(model)

    matched = sum(1 for c in case_results if c.get("matched"))
    total = len(case_results)
    tps_vals = [c["tps"] for c in case_results if c.get("tps")]
    avg_tps = round(sum(tps_vals) / len(tps_vals), 2) if tps_vals else None

    artifact_cases = [
        c for c, cfg in zip(case_results, cases, strict=True) if cfg["kind"] == "artifact"
    ]
    capability_cases = [
        c for c, cfg in zip(case_results, cases, strict=True) if cfg["kind"] == "capability"
    ]

    return {
        "model": model,
        "avg_tps": avg_tps,
        "quality_score": round(matched / total, 2) if total else None,
        "runs_success": matched,
        "runs_total": total,
        "prompt_category": "security-tooling",
        "artifact_validity_rate": round(
            sum(1 for c in artifact_cases if c.get("matched")) / len(artifact_cases), 2
        )
        if artifact_cases
        else None,
        "capability_preserved": all(c.get("matched") for c in capability_cases)
        if capability_cases
        else None,
        "cases": case_results,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Security-tooling capability probe (benign, structural)."
    )
    ap.add_argument(
        "--model", action="append", required=True, help="Model tag to probe (repeatable)"
    )
    args = ap.parse_args(argv)

    cases = build_test_cases()
    print(f"Probing {len(args.model)} model(s) with {len(cases)} structural cases each")

    results = []
    for i, model in enumerate(args.model, 1):
        print(f"  [{i}/{len(args.model)}] {model[:80]} ...", flush=True)
        r = probe_model(model, cases)
        results.append(r)
        print(
            f"    quality={r['quality_score']} artifact_validity_rate={r['artifact_validity_rate']} "
            f"capability_preserved={r['capability_preserved']} avg_tps={r['avg_tps']}"
        )

    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"security_exec_probe_{stamp}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2))
    print(f"\nWrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
