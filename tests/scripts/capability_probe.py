#!/usr/bin/env python3
"""Portal 5 — Coding Capability Probe (7 dimensions, execution-validated).

Drives each model (via its bench workspace through the pipeline) over the
capability_scenarios.yaml set. For execution-tested scenarios it extracts the
model's code, appends the hidden test_harness, runs it in the sandbox MCP, and
scores PASS = exit_code 0 AND expected_stdout present. Emits a comparative
matrix (model x dimension). No verdict — operator-only promotions.

Network scenarios (requires_network) need the sandbox started with
SANDBOX_ALLOW_NETWORK=true (operator does this before the run — see the task).

Usage:
  python3 tests/scripts/capability_probe.py \
      [--scenarios tests/fixtures/capability_scenarios.yaml] \
      [--models <comma-list of bench slugs>] \
      [--output tests/benchmarks/results/CAPABILITY_PROBE_<UTC>.md] \
      [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
PIPELINE_URL = "http://localhost:9099"
SANDBOX_URL = "http://localhost:8914"

PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "")
if not PIPELINE_API_KEY:
    # Fallback: try to read from .env in the project root
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("PIPELINE_API_KEY="):
                PIPELINE_API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

HEADERS = {"Authorization": f"Bearer {PIPELINE_API_KEY}"} if PIPELINE_API_KEY else {}

DEFAULT_MODELS = [
    # V1 incumbents
    "bench-qwen3-coder-next", "bench-qwen3-coder-30b", "bench-devstral-small-2",
    "bench-laguna", "bench-glm", "bench-omnicoder2", "bench-qwen36-27b",
    "bench-deepseek-coder-v2", "bench-qwopus-coder-mtp",
    "bench-gemma4-12b-coder",
    # V2 additions — fast-lane / reasoning probes (TASK_CODING_CAPABILITY_PROBE_V2)
    "bench-lfm25-8b", "bench-granite41-8b", "bench-granite41-30b",
    "bench-r1-0528-qwen3-8b", "bench-r1-0528-abliterated", "bench-harness1",
    # V3 additions — new fleet candidates (TASK_MODEL_EVAL_V9_CANDIDATES)
    "bench-devstral", "bench-magistral", "bench-apriel-nemotron",
    "bench-qwopus-coder-mtp-v2", "bench-fastcontext",
]

CODE_FENCE = re.compile(r"```(?:[a-zA-Z+]*)\n([\s\S]+?)\n```", re.MULTILINE)


def extract_code(response: str) -> str | None:
    blocks = CODE_FENCE.findall(response)
    if not blocks:
        return None
    # Prefer the longest block (usually the full solution).
    return max(blocks, key=len)


_MAIN_GUARD_RE = re.compile(r'\nif __name__\s*==\s*[\'"]__main__[\'"]\s*:.*', re.DOTALL)
# Also catches bare unindented `main()` / `main(sys.argv[1:])` calls without a guard.
_MODULE_MAIN_CALL_RE = re.compile(r'^main\s*\(.*?\)\s*$', re.MULTILINE)


def _strip_main_guard(code: str) -> str:
    # Models often append `if __name__ == '__main__': main()` which fires before the
    # test harness runs (argparse sees sys.argv=['/code'] and exits 2). Strip it.
    # Also strip bare module-level main() calls that skip the guard entirely.
    code = _MAIN_GUARD_RE.sub("", code)
    code = _MODULE_MAIN_CALL_RE.sub("", code)
    return code.rstrip()


async def chat(client: httpx.AsyncClient, workspace: str, prompt: str,
               history: list | None = None) -> str:
    msgs = list(history or []) + [{"role": "user", "content": prompt}]
    r = await client.post(
        f"{PIPELINE_URL}/v1/chat/completions",
        json={"model": workspace, "messages": msgs, "stream": False},
        headers=HEADERS,
        timeout=600,
    )
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]


async def sandbox_exec(client: httpx.AsyncClient, code: str,
                       language: str, timeout: int = 120) -> dict:
    tool = {"python": "execute_python", "javascript": "execute_nodejs",
            "bash": "execute_bash", "powershell": "execute_powershell"}.get(language, "execute_python")
    key = "command" if tool == "execute_bash" else "code"
    r = await client.post(
        f"{SANDBOX_URL}/tools/{tool}",
        json={"arguments": {key: code, "timeout": timeout}},
        timeout=timeout + 30,
    )
    r.raise_for_status()
    return r.json()


def score_execution(result: dict, expected_stdout: str) -> tuple[bool, str]:
    if not isinstance(result, dict):
        return False, "no sandbox result"
    out = result.get("stdout", "") or ""
    if result.get("timed_out"):
        return False, "execution timed out"
    if expected_stdout and expected_stdout in out:
        return True, "expected stdout matched"
    if result.get("exit_code", 1) != 0:
        return False, f"exit {result.get('exit_code')}: {(result.get('stderr','') or '')[:120]}"
    return False, f"expected '{expected_stdout}' not in stdout: {out[:120]}"


async def run_scenario(client, workspace, scn, context_text="") -> dict:
    prompt = scn["prompt"]
    if context_text:
        prompt = f"{context_text}\n\n---\n\n{prompt}"
    lang = scn.get("language", "python")
    cell = {"model": workspace, "dimension": scn["dimension"],
            "id": scn["id"], "passed": False, "detail": ""}

    if scn.get("manual_review"):
        resp = await chat(client, workspace, prompt)
        cell["detail"] = "MANUAL: " + resp[:160].replace("\n", " ")
        cell["passed"] = None  # not auto-scored
        return cell

    # Multi-turn (D5)
    if scn.get("turns"):
        history = []
        turn_results = []
        turns = [{"prompt": prompt, "test_harness": scn.get("test_harness"),
                  "expected_stdout": scn.get("expected_stdout")}] + scn["turns"]
        for t in turns:
            resp = await chat(client, workspace, t["prompt"], history)
            history += [{"role": "user", "content": t["prompt"]},
                        {"role": "assistant", "content": resp}]
            code = extract_code(resp)
            if not code:
                turn_results.append(False)
                continue
            full = _strip_main_guard(code) + "\n\n" + (t.get("test_harness") or "")
            res = await sandbox_exec(client, full, lang)
            ok, _ = score_execution(res, t.get("expected_stdout", ""))
            turn_results.append(ok)
        cell["passed"] = all(turn_results)
        cell["detail"] = f"turns {sum(turn_results)}/{len(turn_results)} passed"
        return cell

    # Single-turn execution-validated
    resp = await chat(client, workspace, prompt)
    code = extract_code(resp)
    if not code:
        cell["detail"] = "no code block in response"
        return cell
    harness = scn.get("test_harness")
    if not harness:
        # static-only scenario
        cell["passed"] = "```" in resp
        cell["detail"] = "static: code block present" if cell["passed"] else "no code"
        return cell
    stripped = _strip_main_guard(code)
    full = stripped + "\n\n" + harness
    res = await sandbox_exec(client, full, lang)
    ok, detail = score_execution(res, scn.get("expected_stdout", ""))
    cell["passed"] = ok
    cell["detail"] = detail
    return cell


DIM_LABELS = {
    # D1/D2/D3/D5 moved to UAT keyword-graded tests (g_auto_coding, g_auto_data, g_auto_security).
    # Probe focuses on execution-validated routing dimensions only.
    "D4": "D4 LongCtx", "D6": "D6 Security",
    "D7": "D7 Domain", "D8": "D8 PowerShell", "D9": "D9 PyProd",
    "D10": "D10 SecAPI",  # Nessus, Splunk, SolarWinds, Tripwire, MSSQL, SSRS×2, ChangeGear×2, BigFix
}


def render_matrix(cells: list[dict], source: str) -> str:
    dims = sorted({c["dimension"] for c in cells}, key=lambda d: int(d[1:]))
    by_model: dict[str, dict[str, list]] = {}
    for c in cells:
        by_model.setdefault(c["model"], {}).setdefault(c["dimension"], []).append(c)
    dim_headers = " | ".join(DIM_LABELS.get(d, d) for d in dims)
    out = [
        "# Coding Capability Probe — Matrix",
        "",
        f"**Source**: `{source}` · generated "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "Execution-validated where applicable: PASS = the model's code ran in "
        "the sandbox and produced correct output. D6 is manual-review "
        "(refusal disposition). No verdict — promotions operator-only.",
        "",
        f"| Model | {dim_headers} |",
        "|---|" + "---|" * len(dims),
    ]
    def frac(lst):
        scored = [c for c in lst if c["passed"] is not None]
        if not scored:
            return "manual"
        p = sum(1 for c in scored if c["passed"])
        return f"{p}/{len(scored)}"
    for model in sorted(by_model):
        row = [model]
        for d in dims:
            row.append(frac(by_model[model].get(d, [])))
        out.append("| " + " | ".join(row) + " |")
    out += ["", "## Per-cell detail", ""]
    for c in sorted(cells, key=lambda x: (x["model"], x["dimension"], x["id"])):
        mark = "manual" if c["passed"] is None else ("PASS" if c["passed"] else "FAIL")
        out.append(f"- `{c['model']}` {c['dimension']} {c['id']}: **{mark}** — {c['detail']}")
    out.append("")
    return "\n".join(out)


async def main_async(args) -> int:
    scn_data = yaml.safe_load(Path(args.scenarios).read_text())
    scenarios = scn_data["scenarios"]
    if args.dimensions:
        dim_filter = set(args.dimensions.split(","))
        scenarios = [s for s in scenarios if s["dimension"] in dim_filter]
    models = args.models.split(",") if args.models else DEFAULT_MODELS

    # Pre-load D4 context files
    ctx_cache: dict[str, str] = {}
    for s in scenarios:
        cf = s.get("context_file")
        if cf and cf not in ctx_cache:
            p = ROOT / cf
            ctx_cache[cf] = p.read_text() if p.exists() else ""

    if args.dry_run:
        print(f"models: {len(models)}  scenarios: {len(scenarios)}  "
              f"cells: {len(models)*len(scenarios)}")
        for m in models:
            print(f"  {m}")
        return 0

    cells = []
    probe_start = time.monotonic()
    total_scenarios = len(models) * len(scenarios)
    done_count = 0

    async with httpx.AsyncClient() as client:
        for mi, model in enumerate(models, 1):
            model_start = time.monotonic()
            print(f"\n[{mi}/{len(models)}] {model}", flush=True)
            # Evict others first (model-major; one resident at a time)
            try:
                ps = (await client.get("http://localhost:11434/api/ps", timeout=5)).json()
                for m in ps.get("models", []):
                    await client.post("http://localhost:11434/api/generate",
                                      json={"model": m["name"], "keep_alive": 0},
                                      timeout=10)
            except Exception:
                pass
            model_pass = model_fail = model_manual = 0
            for _si, scn in enumerate(scenarios, 1):
                ctx = ctx_cache.get(scn.get("context_file", ""), "")
                done_count += 1
                elapsed_probe = time.monotonic() - probe_start
                # Show what's in flight before the call blocks
                print(
                    f"  [{done_count:3d}/{total_scenarios}] "
                    f"{scn['dimension']} {scn['id']:<24} running...  "
                    f"(probe {elapsed_probe/60:.0f}m{elapsed_probe%60:.0f}s)",
                    end="\r", flush=True,
                )
                t0 = time.monotonic()
                try:
                    cell = await run_scenario(client, model, scn, ctx)
                except Exception as e:  # noqa: BLE001
                    cell = {"model": model, "dimension": scn["dimension"],
                            "id": scn["id"], "passed": False,
                            "detail": f"harness error: {e}"}
                scn_elapsed = time.monotonic() - t0
                mark = "manual" if cell["passed"] is None else (
                    "PASS" if cell["passed"] else "FAIL")
                icon = "~" if cell["passed"] is None else ("✓" if cell["passed"] else "✗")
                if cell["passed"] is None:
                    model_manual += 1
                elif cell["passed"]:
                    model_pass += 1
                else:
                    model_fail += 1
                print(
                    f"  [{done_count:3d}/{total_scenarios}] "
                    f"{icon} {scn['dimension']} {scn['id']:<24} {mark:<6} "
                    f"{scn_elapsed:5.0f}s  {cell['detail'][:55]}",
                    flush=True,
                )
                cells.append(cell)
            model_elapsed = time.monotonic() - model_start
            print(
                f"  ── {model}: {model_pass}P/{model_fail}F/{model_manual}M  "
                f"({model_elapsed/60:.0f}m{model_elapsed%60:.0f}s)",
                flush=True,
            )

    out_path = args.output or str(
        ROOT / "tests" / "benchmarks" / "results" /
        ("CAPABILITY_PROBE_" +
         datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".md"))
    Path(out_path).write_text(render_matrix(cells, args.scenarios))
    total_elapsed = time.monotonic() - probe_start
    passed = sum(1 for c in cells if c["passed"] is True)
    failed = sum(1 for c in cells if c["passed"] is False)
    manual = sum(1 for c in cells if c["passed"] is None)
    print(
        f"\n── probe complete: {passed}P/{failed}F/{manual}M  "
        f"total {total_elapsed/60:.0f}m{total_elapsed%60:.0f}s"
    )
    print(f"wrote {out_path} ({len(cells)} cells)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios",
                    default=str(ROOT / "tests" / "fixtures" / "capability_scenarios.yaml"))
    ap.add_argument("--models", default="")
    ap.add_argument("--dimensions", default="",
                    help="Comma-separated list of dimensions to run (e.g. D8,D9,D10). "
                         "Empty means all.")
    ap.add_argument("--output", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
