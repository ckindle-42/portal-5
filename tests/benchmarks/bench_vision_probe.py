#!/usr/bin/env python3
"""Vision/VQA capability probe for pending-verdict models flagged as
'vision' by scripts/pending_verdicts_report.py's capability categorizer.

Why this exists: raw TPS (bench_tps.py) doesn't test whether a model's
vision capability actually works — a model with a vision-capable GGUF
export could still fail at basic image understanding, and TPS numbers
tell you nothing about that. This probe sends deterministic, generated
test images (no external dataset dependency) with known ground truth and
scores keyword-match accuracy in the response.

Four synthetic test cases per model, each with a verifiable ground truth:
    color       — solid-color square, "what color is this?"
    text        — rendered text on a plain background, "what text?"
    shape_count — N circles on a plain background, "how many circles?"
    shape_color — a colored square drawn on a contrasting background,
                  "what color is the square?"

Only runs against models whose `ollama show` capabilities list includes
"vision" — models exported without a vision encoder (confirmed via
clip.has_vision_encoder / capabilities field, not inferred from the card)
are skipped with a clear reason, never silently benched as if they were
multimodal.

Emits tests/benchmarks/results/vision_probe_<UTC>.json in the same
{"results": [{"model", "avg_tps", "quality_score", "runs_success",
"runs_total", "prompt_category": "vision"}]} shape bench_tps.py JSON
uses, so scripts/pending_verdicts_evidence.py picks it up automatically
on the next mine.

quality_score here = fraction of the 4 VQA cases answered correctly
(0.0-1.0). avg_tps is still measured (eval_count / eval_duration) so the
TPS floor check remains meaningful too.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OLLAMA_URL = "http://localhost:11434"
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"
TIMEOUT = 120

# TASK_MODEL_BENCH_VALIDITY_V1 follow-up: bench at the temperature the model
# is actually configured to run at (portal.yaml), not its Modelfile default —
# the same "wrong instrument" failure as the token-budget bug, on the
# sampling axis. Fall back to a low default (VQA/captioning wants
# determinism) only when the tag isn't wired to a bench-* workspace yet.
_DEFAULT_TEMPERATURE = 0.2


def _temperature_for_tag(model_tag: str) -> float:
    try:
        import yaml as _yaml

        data = _yaml.safe_load((REPO_ROOT / "config" / "portal.yaml").read_text()) or {}
        for slug, spec in (data.get("workspaces") or {}).items():
            if not slug.startswith("bench-") or not isinstance(spec, dict):
                continue
            if spec.get("model_hint") == model_tag and spec.get("temperature") is not None:
                return float(spec["temperature"])
    except Exception:
        pass
    return _DEFAULT_TEMPERATURE


def _b64_png(img) -> str:
    import base64

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def build_test_cases() -> list[dict]:
    from PIL import Image, ImageDraw

    cases = []

    # 1. Solid color square
    img = Image.new("RGB", (256, 256), color=(220, 30, 30))
    cases.append(
        {
            "id": "color",
            "image_b64": _b64_png(img),
            "question": "What is the dominant color of this image? Answer with a single color word only.",
            "expect_any": ["red"],
        }
    )

    # 2. Rendered text
    img = Image.new("RGB", (256, 96), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((20, 30), "PORTAL5", fill=(0, 0, 0))
    cases.append(
        {
            "id": "text",
            "image_b64": _b64_png(img),
            "question": "What text is written in this image? Reply with just the text you see.",
            "expect_any": ["portal5", "portal 5", "portal-5"],
        }
    )

    # 3. Shape count
    img = Image.new("RGB", (256, 256), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    for cx in (60, 128, 196):
        d.ellipse([cx - 25, 105, cx + 25, 155], fill=(20, 90, 200))
    cases.append(
        {
            "id": "shape_count",
            "image_b64": _b64_png(img),
            "question": "How many circles are in this image? Reply with just the number.",
            "expect_any": ["3", "three"],
        }
    )

    # 4. Shape color on contrasting background
    img = Image.new("RGB", (256, 256), color=(10, 10, 10))
    d = ImageDraw.Draw(img)
    d.rectangle([78, 78, 178, 178], fill=(40, 200, 90))
    cases.append(
        {
            "id": "shape_color",
            "image_b64": _b64_png(img),
            "question": "What color is the square in this image? Answer with a single color word only.",
            "expect_any": ["green"],
        }
    )

    return cases


def model_has_vision(model: str) -> tuple[bool, str]:
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/show",
        data=json.dumps({"model": model}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
    except Exception as e:
        return False, f"api/show failed: {e}"
    caps = data.get("capabilities") or []
    if "vision" in caps:
        return True, "capabilities includes vision"
    return False, f"capabilities={caps} (no vision encoder — not a multimodal export)"


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
    # think:false keeps thinking-capable models from burning the whole
    # num_predict budget on a verbose reasoning preamble before ever
    # reaching the actual VQA answer (found live: gemma4:e2b-it-qat
    # returned an empty "content" and a truncated "thinking" field at
    # num_predict=64 with thinking left on). Models that don't support
    # the flag just ignore it.
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": case["question"],
                "images": [case["image_b64"]],
            }
        ],
        "stream": False,
        "think": False,
        "options": {"num_predict": 256, "temperature": _temperature_for_tag(model)},
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
    thinking = (data.get("message") or {}).get("thinking", "") or ""
    text = (content + " " + thinking).lower()
    matched = any(k in text for k in case["expect_any"])
    eval_count = data.get("eval_count") or 0
    eval_duration_ns = data.get("eval_duration") or 0
    tps = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns else None
    return {
        "id": case["id"],
        "ok": True,
        "matched": matched,
        "response_preview": (content or thinking)[:200],
        "tps": tps,
        "wall_s": time.monotonic() - t0,
    }


def probe_model(model: str, cases: list[dict]) -> dict:
    has_vision, reason = model_has_vision(model)
    if not has_vision:
        return {"model": model, "skipped": True, "reason": reason}

    case_results = []
    for case in cases:
        case_results.append(run_case(model, case))
    unload(model)

    matched = sum(1 for c in case_results if c.get("matched"))
    total = len(case_results)
    tps_vals = [c["tps"] for c in case_results if c.get("tps")]
    avg_tps = round(sum(tps_vals) / len(tps_vals), 2) if tps_vals else None

    return {
        "model": model,
        "skipped": False,
        "avg_tps": avg_tps,
        "quality_score": round(matched / total, 2) if total else None,
        "runs_success": matched,
        "runs_total": total,
        "prompt_category": "vision",
        "cases": case_results,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Vision/VQA capability probe.")
    ap.add_argument(
        "--model", action="append", required=True, help="Model tag to probe (repeatable)"
    )
    args = ap.parse_args(argv)

    cases = build_test_cases()
    print(f"Probing {len(args.model)} model(s) with {len(cases)} VQA test cases each")

    results = []
    for i, model in enumerate(args.model, 1):
        print(f"  [{i}/{len(args.model)}] {model[:80]} ...", flush=True)
        r = probe_model(model, cases)
        results.append(r)
        if r.get("skipped"):
            print(f"    SKIPPED: {r['reason']}")
        else:
            print(
                f"    quality={r['quality_score']} ({r['runs_success']}/{r['runs_total']}) avg_tps={r['avg_tps']}"
            )

    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"vision_probe_{stamp}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"results": [r for r in results if not r.get("skipped")]}, indent=2)
    )
    print(f"\nWrote {out_path.relative_to(REPO_ROOT)}")

    skipped = [r for r in results if r.get("skipped")]
    if skipped:
        print(f"\n{len(skipped)} model(s) skipped (not actually multimodal exports):")
        for r in skipped:
            print(f"  {r['model']}: {r['reason']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
