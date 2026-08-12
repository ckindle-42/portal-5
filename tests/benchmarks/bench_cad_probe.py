#!/usr/bin/env python3
"""CAD capability probe for pending-verdict models flagged 'cad' (or serving the
auto-cad intent).

Why this exists: auto-cad's job is parametric 3D-model generation — the model
writes OpenSCAD source that must COMPILE to a valid, printable solid. bench_tps
on a chat prompt measures none of that. This probe scores the artifact the way
the render pipeline does: emit OpenSCAD → run the `openscad` binary to export STL
→ load with trimesh → check the mesh is a real, watertight, positive-volume
solid. Same binary path the production render_openscad MCP tool uses
(portal/modules/cad/tools/cad_render_mcp.py), but self-contained (no MCP server
needed) so it runs in a bench sweep.

Scored on STRUCTURE, per case:
  1. compiles      — openscad exits 0 and produces a non-empty STL
  2. watertight    — trimesh reports the mesh is watertight (a printable solid,
                     not loose faces)
  3. positive vol  — mesh volume > 0 (it enclosed space; not a degenerate plane)
  4. dims sane     — bounding box roughly matches any dimension the prompt asked
                     for (loose ±30% tolerance — we're checking the model honored
                     a parametric constraint, not exact CAD precision)

Emits tests/benchmarks/results/cad_probe_<UTC>.json in the bench_tps JSON shape
(harness prefix `cad_probe`). quality_score = fraction of cases that produced a
watertight positive-volume solid — the bar that separates "wrote real CAD" from
"wrote plausible-looking code that doesn't compile."

Requires the `openscad` binary (set OPENSCAD_BIN to override) and trimesh. If
openscad is absent the probe records compiles=False honestly rather than
crashing — a true BLOCKED result, not a fake pass.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OLLAMA_URL = "http://localhost:11434"
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"
TIMEOUT = 300
OPENSCAD_BIN = os.getenv("OPENSCAD_BIN", "openscad")


def build_test_cases() -> list[dict]:
    return [
        {
            "id": "param_box",
            "prompt": (
                "Write OpenSCAD code for a rectangular box 40mm wide, 20mm deep, "
                "10mm tall, with a 2mm wall thickness (hollow). Output only the "
                "OpenSCAD code in a code block."
            ),
            "expect_dims": (40, 20, 10),
        },
        {
            "id": "cylinder_hole",
            "prompt": (
                "Write OpenSCAD code for a cylinder 30mm diameter and 15mm tall "
                "with a 10mm diameter hole through the center (a washer/tube). "
                "Output only the OpenSCAD code in a code block."
            ),
            "expect_dims": (30, 30, 15),
        },
        {
            "id": "bracket",
            "prompt": (
                "Write OpenSCAD code for a simple L-shaped bracket: two 30mm x 20mm "
                "x 4mm plates meeting at a right angle. Output only the OpenSCAD "
                "code in a code block."
            ),
            "expect_dims": None,
        },
        {
            "id": "param_gear_blank",
            "prompt": (
                "Write OpenSCAD code for a round gear blank: a 50mm diameter, 6mm "
                "thick disc with a 8mm center bore and six 4mm lightening holes on "
                "a 30mm bolt circle. Output only the OpenSCAD code in a code block."
            ),
            "expect_dims": (50, 50, 6),
        },
    ]


def _extract_scad(text: str) -> str:
    m = re.search(r"```(?:openscad|scad|c)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"```(?:openscad|scad|c)?\s*\n(.*)\Z", text, re.DOTALL)
    if m:
        return m.group(1)
    # bare code fallback: OpenSCAD primitives present without a fence
    if re.search(r"\b(cube|cylinder|sphere|difference|union|translate)\s*\(", text):
        return text
    return ""


def _score_scad(code: str, expect_dims) -> dict:
    result = {"compiles": False, "watertight": False, "positive_volume": False,
              "dims_sane": None, "error": None}
    if not code.strip():
        result["error"] = "no OpenSCAD code extracted"
        return result
    try:
        import trimesh
    except Exception as e:  # pragma: no cover
        result["error"] = f"trimesh unavailable: {e}"
        return result
    with tempfile.TemporaryDirectory() as td:
        scad = Path(td) / "m.scad"
        stl = Path(td) / "m.stl"
        scad.write_text(code)
        try:
            proc = subprocess.run(
                [OPENSCAD_BIN, "--render", "-o", str(stl), str(scad)],
                capture_output=True, text=True, timeout=120, check=False,
            )
        except FileNotFoundError:
            result["error"] = f"openscad binary not found (set OPENSCAD_BIN); tried {OPENSCAD_BIN}"
            return result
        except subprocess.TimeoutExpired:
            result["error"] = "openscad render timed out"
            return result
        if proc.returncode != 0 or not stl.exists() or stl.stat().st_size == 0:
            result["error"] = f"openscad failed rc={proc.returncode}: {proc.stderr[:200]}"
            return result
        result["compiles"] = True
        try:
            mesh = trimesh.load(str(stl))
            result["watertight"] = bool(mesh.is_watertight)
            result["positive_volume"] = bool(mesh.volume and mesh.volume > 0)
            if expect_dims:
                ext = sorted(mesh.bounding_box.extents)
                want = sorted(expect_dims)
                result["dims_sane"] = all(
                    abs(g - w) <= max(0.3 * w, 3.0) for g, w in zip(ext, want, strict=False)
                )
        except Exception as e:
            result["error"] = f"trimesh load/inspect failed: {e}"
    return result


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
    code = _extract_scad(content)
    score = _score_scad(code, case.get("expect_dims"))
    # "matched" = produced a real printable solid
    matched = bool(score["compiles"] and score["watertight"] and score["positive_volume"])
    eval_count = data.get("eval_count") or 0
    eval_duration_ns = data.get("eval_duration") or 0
    tps = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns else None
    return {
        "id": case["id"], "ok": True, "matched": matched,
        "scad_score": score, "response_preview": content[:160],
        "tps": tps, "wall_s": time.monotonic() - t0,
    }


def probe_model(model: str, cases: list[dict]) -> dict:
    case_results = [run_case(model, c) for c in cases]
    unload(model)
    ok = [c for c in case_results if c.get("ok")]
    matched = sum(1 for c in ok if c.get("matched"))
    compiles = sum(1 for c in ok if (c.get("scad_score") or {}).get("compiles"))
    total = len(cases)
    tps_vals = [c["tps"] for c in ok if c.get("tps")]
    avg_tps = round(sum(tps_vals) / len(tps_vals), 2) if tps_vals else None
    return {
        "model": model, "avg_tps": avg_tps,
        "quality_score": round(matched / total, 2) if total else None,
        "runs_success": matched, "runs_total": total,
        "prompt_category": "cad",
        "compile_rate": round(compiles / total, 2) if total else None,
        "cases": case_results,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CAD (OpenSCAD→STL) capability probe.")
    ap.add_argument("--model", action="append", required=True, help="Model tag (repeatable)")
    args = ap.parse_args(argv)
    cases = build_test_cases()
    print(f"Probing {len(args.model)} model(s) with {len(cases)} CAD cases each")
    results = []
    for i, model in enumerate(args.model, 1):
        print(f"  [{i}/{len(args.model)}] {model[:70]} ...", flush=True)
        r = probe_model(model, cases)
        results.append(r)
        print(f"    quality={r['quality_score']} compile_rate={r['compile_rate']} avg_tps={r['avg_tps']}")
    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"cad_probe_{stamp}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2))
    print(f"\nWrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
