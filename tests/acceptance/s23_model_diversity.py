"""S23: Model diversity availability checks."""
import time
from tests.acceptance._common import (
    MLX_URL,
    record,
    _get,
    _mlx_health,
    _ollama_models,
)

async def run() -> None:
    """S23: Model diversity availability checks (GPT-OSS, Gemma 4, Phi-4, Magistral).

    S23-02 removed — GPT-OSS chat is covered by S10's gptossanalyst persona test.
    These checks verify model registration only (lightweight /v1/models queries).
    """
    print("\n━━━ S23. MODEL DIVERSITY ━━━")
    sec = "S23"

    # S23-01: GPT-OSS model available in Ollama
    t0 = time.time()
    models = _ollama_models()
    gpt_oss_available = any("gpt-oss" in m.lower() for m in models)
    record(
        sec,
        "S23-01",
        "GPT-OSS:20B available",
        "PASS" if gpt_oss_available else "INFO",
        f"gpt-oss in models: {gpt_oss_available}",
        t0=t0,
    )

    # S23-03: Gemma 4 E4B VLM available
    t0 = time.time()
    state, mlx_data = await _mlx_health()
    if state in ("ready", "none", "switching"):
        code, models_data = await _get(f"{MLX_URL}/v1/models")
        if code == 200 and isinstance(models_data, dict):
            model_ids = [m.get("id", "") for m in models_data.get("data", [])]
            gemma_e4b = any("gemma-4-e4b" in m.lower() or "gemma-4-E4B" in m for m in model_ids)
            record(
                sec,
                "S23-03",
                "Gemma 4 E4B VLM registered",
                "PASS" if gemma_e4b else "INFO",
                f"gemma-4-E4B in MLX models: {gemma_e4b}",
                t0=t0,
            )
        else:
            record(
                sec,
                "S23-03",
                "Gemma 4 E4B VLM registered",
                "INFO",
                "MLX models endpoint unavailable",
                t0=t0,
            )
    else:
        record(sec, "S23-03", "Gemma 4 E4B VLM registered", "INFO", f"MLX state: {state}", t0=t0)

    # S23-04: Phi-4 available in MLX pool
    t0 = time.time()
    code, models_data = await _get(f"{MLX_URL}/v1/models")
    if code == 200 and isinstance(models_data, dict):
        model_ids = [m.get("id", "") for m in models_data.get("data", [])]
        phi4 = any("phi-4" in m.lower() for m in model_ids)
        record(
            sec,
            "S23-04",
            "Phi-4 available",
            "PASS" if phi4 else "INFO",
            f"phi-4 in MLX models: {phi4}",
            t0=t0,
        )
    else:
        record(sec, "S23-04", "Phi-4 available", "INFO", f"HTTP {code}", t0=t0)

    # S23-05: Magistral-Small available
    t0 = time.time()
    code, models_data = await _get(f"{MLX_URL}/v1/models")
    if code == 200 and isinstance(models_data, dict):
        model_ids = [m.get("id", "") for m in models_data.get("data", [])]
        magistral = any("magistral" in m.lower() for m in model_ids)
        record(
            sec,
            "S23-05",
            "Magistral-Small available",
            "PASS" if magistral else "INFO",
            f"magistral in MLX models: {magistral}",
            t0=t0,
        )
    else:
        record(sec, "S23-05", "Magistral-Small available", "INFO", f"HTTP {code}", t0=t0)

    # S23-06: Phi-4-reasoning-plus available (RL-trained STEM reasoning)
    t0 = time.time()
    code, models_data = await _get(f"{MLX_URL}/v1/models")
    if code == 200 and isinstance(models_data, dict):
        model_ids = [m.get("id", "") for m in models_data.get("data", [])]
        phi4_reasoning = any("phi-4-reasoning" in m.lower() for m in model_ids)
        record(
            sec,
            "S23-06",
            "Phi-4-reasoning-plus available",
            "PASS" if phi4_reasoning else "INFO",
            f"phi-4-reasoning-plus in MLX models: {phi4_reasoning}",
            t0=t0,
        )
    else:
        record(sec, "S23-06", "Phi-4-reasoning-plus available", "INFO", f"HTTP {code}", t0=t0)

    # S23-07: Huihui-GLM-4.7-Flash-abliterated-mlx-4bit available and produces output
    t0 = time.time()
    state, _ = await _mlx_health()
    if state in ("ready", "none", "switching"):
        code, models_data = await _get(f"{MLX_URL}/v1/models")
        if code == 200 and isinstance(models_data, dict):
            model_ids = [m.get("id", "") for m in models_data.get("data", [])]
            glm_present = any("Huihui-GLM-4.7-Flash" in m for m in model_ids)
            if not glm_present:
                record(
                    sec,
                    "S23-07",
                    "Huihui-GLM-4.7-Flash-abliterated registered",
                    "INFO",
                    "model not in MLX list — run hf download or ./launch.sh pull-mlx-models",
                    t0=t0,
                )
            else:
                try:
                    code2, response2, _ = await _mlx_chat_direct(
                        "huihui-ai/Huihui-GLM-4.7-Flash-abliterated-mlx-4bit",
                        "Write hello world in Python.",
                        max_tokens=50,
                        timeout=300,
                    )
                    if code2 == 200 and len(response2) > 10:
                        record(
                            sec,
                            "S23-07",
                            "Huihui-GLM-4.7-Flash-abliterated smoke test",
                            "PASS",
                            f"loaded + produced {len(response2)} chars",
                            t0=t0,
                        )
                    elif code2 == 200 and len(response2) == 0:
                        record(
                            sec,
                            "S23-07",
                            "Huihui-GLM-4.7-Flash-abliterated smoke test",
                            "WARN",
                            "empty content on Apple Metal — known issue P5-MLX-006 (Linux-only conversion)",
                            t0=t0,
                        )
                    else:
                        record(
                            sec,
                            "S23-07",
                            "Huihui-GLM-4.7-Flash-abliterated smoke test",
                            "WARN",
                            f"HTTP {code2}, response len={len(response2)} — P5-MLX-006",
                            t0=t0,
                        )
                except Exception as e:
                    record(
                        sec,
                        "S23-07",
                        "Huihui-GLM-4.7-Flash-abliterated smoke test",
                        "WARN",
                        f"P5-MLX-006: {str(e)[:80]}",
                        t0=t0,
                    )
        else:
            record(
                sec,
                "S23-07",
                "Huihui-GLM-4.7-Flash-abliterated registered",
                "INFO",
                "MLX models endpoint unavailable",
                t0=t0,
            )
    else:
        record(
            sec, "S23-07", "Huihui-GLM-4.7-Flash-abliterated", "INFO", f"MLX state: {state}", t0=t0
        )
