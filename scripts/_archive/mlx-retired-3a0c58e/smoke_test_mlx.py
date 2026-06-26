#!/usr/bin/env python3
"""V5 Apple Metal smoke test — 50-token greedy generation.

Per TASK_MODEL_REFRESH_V5 §3. Detects P5-MLX-006/008-class empty-content
defects and runtime failures. JSON results gate which models proceed to
Phase E bench (failed models are skipped to avoid wasting bench time).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HF_CACHE = Path(os.environ.get("HF_HUB_CACHE", str(Path.home() / ".cache/huggingface/hub")))

MODELS_TO_TEST = {
    # Reasoning ladder
    "mlx-community/Olmo-3-1125-32B-4bit": "text",
    "mlx-community/Olmo-3-1125-32B-6bit": "text",
    "mlx-community/Olmo-3-1125-32B-8bit": "text",
    "mlx-community/DeepSeek-R1-Distill-Llama-70B-3bit": "text",
    "mlx-community/DeepSeek-R1-Distill-Llama-70B-4bit": "text",
    # Compliance
    "mlx-community/granite-4.1-30b-mxfp4": "text",
    "mlx-community/granite-4.1-30b-mxfp8": "text",
    "mlx-community/granite-4.1-30b-nvfp4": "text",
    # Vision
    "mlx-community/gemma-4-26b-a4b-it-4bit": "vlm",
    "mlx-community/gemma-4-26b-a4b-it-6bit": "vlm",
    "mlx-community/gemma-4-26b-a4b-it-8bit": "vlm",
    "mlx-community/gemma-4-31b-8bit": "vlm",
    # Creative
    "mlx-community/gemma-4-26B-A4B-it-heretic-4bit": "vlm",
    # Coding
    "mlx-community/Devstral-Small-2505-4bit": "text",
    "mlx-community/Devstral-Small-2505-4bit-DWQ": "text",
    "mlx-community/Devstral-Small-2505-6bit": "text",
    "mlx-community/Devstral-Small-2505-8bit": "text",
    # Security/Redteam
    "mlx-community/Qwen3.6-27B-AEON-Ultimate-Uncensored-BF16-mlx-4Bit": "text",
    "mlx-community/Qwen3.6-27B-AEON-Ultimate-Uncensored-BF16-mlx-6Bit": "text",
    "mlx-community/Qwen3.6-27B-AEON-Ultimate-Uncensored-BF16-mlx-8Bit": "text",
    "cs2764/DeepSeek-R1-Distill-Llama-70B-Abliterated-MLX-4Bit": "text",
    # Speed-class
    "mlx-community/granite-4.1-3b-mxfp8": "text",
    # MTP bench
    "mlx-community/gemma-4-26b-a4b-it-bf16": "vlm",
}

PROMPT = "In one sentence, what is the capital of France?"


def smoke_one(model_id: str, kind: str) -> dict:
    import sys as _sys
    exe = _sys.executable
    cmd = (
        [exe, "-m", "mlx_vlm.generate", "--model", model_id,
         "--prompt", PROMPT, "--max-tokens", "50", "--temperature", "0.0"]
        if kind == "vlm" else
        [exe, "-m", "mlx_lm", "generate", "--model", model_id,
         "--prompt", PROMPT, "--max-tokens", "50", "--temp", "0"]
    )
    env = os.environ.copy()
    env.setdefault("HF_HUB_CACHE", str(HF_CACHE))
    env.setdefault("HF_HOME", str(HF_CACHE.parent))
    timeout = 600 if any(x in model_id for x in ("70B", "80B")) else 300
    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)
        out = result.stdout.strip()
        body_chars = sum(1 for c in out if c.isalnum())
        if result.returncode != 0:
            return {"model": model_id, "status": "FAIL_RUNTIME",
                    "stderr_tail": result.stderr[-500:], "stdout_tail": out[-200:]}
        if body_chars < 10:
            return {"model": model_id, "status": "FAIL_EMPTY_CONTENT",
                    "body_chars": body_chars,
                    "diagnosis": "Likely P5-MLX-006/008 — Apple Metal compatibility defect"}
        return {"model": model_id, "status": "PASS",
                "stdout_tail": out[-200:], "body_chars": body_chars}
    except subprocess.TimeoutExpired:
        return {"model": model_id, "status": "FAIL_TIMEOUT", "timeout_s": timeout}
    except Exception as e:
        return {"model": model_id, "status": "FAIL_EXCEPTION", "err": str(e)}


def main():
    results = []
    for model_id, kind in MODELS_TO_TEST.items():
        # HF cache stores models as models--<org>--<name>
        cache_dir = HF_CACHE / f"models--{model_id.replace('/', '--')}"
        if not cache_dir.exists():
            results.append({"model": model_id, "status": "SKIP_NOT_DOWNLOADED"})
            continue
        print(f"\n=== Smoke {model_id} ({kind}) ===", flush=True)
        r = smoke_one(model_id, kind)
        results.append(r)
        print(json.dumps(r, indent=2), flush=True)
    out_path = Path("tests/results/smoke_test_v5.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_fail = sum(1 for r in results if r["status"].startswith("FAIL"))
    n_skip = sum(1 for r in results if r["status"].startswith("SKIP"))
    print(f"\nPASS: {n_pass}  FAIL: {n_fail}  SKIP: {n_skip}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
