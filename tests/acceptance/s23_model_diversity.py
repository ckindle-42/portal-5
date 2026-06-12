"""S23: Model diversity availability checks (Ollama-only).

MLX-proxy queries retired in commit 3a0c58e (TASK_MLX_RETIRE_TRUEUP_V1/V2).
All target models now live in the Ollama catalog; these checks verify
registration via the Ollama /api/tags listing only (lightweight).
"""

import time

from tests.acceptance._common import (
    _ollama_models,
    record,
)


def _present(models: list[str], *needles: str) -> bool:
    lowered = [m.lower() for m in models]
    return any(any(n.lower() in m for m in lowered) for n in needles)


async def run() -> None:
    """S23: Model diversity availability (GPT-OSS, Gemma 4, Phi-4, Magistral, GLM).

    Registration-only checks against the Ollama catalog. Chat smoke tests
    for these models live in S10/UAT/bench, not here.
    """
    print("\n━━━ S23. MODEL DIVERSITY ━━━")
    sec = "S23"
    models = _ollama_models()

    checks = [
        ("S23-01", "GPT-OSS:20B available", ("gpt-oss",)),
        ("S23-03", "Gemma 4 E4B VLM available", ("gemma4:e4b", "gemma-4-e4b")),
        ("S23-04", "Phi-4 available", ("phi4:14b", "phi-4")),
        ("S23-05", "Magistral-Small available", ("magistral",)),
        ("S23-06", "Phi-4-reasoning-plus available", ("phi4-reasoning", "phi-4-reasoning")),
        ("S23-07", "GLM-4.7-Flash available", ("glm-4.7-flash",)),
    ]

    for cid, label, needles in checks:
        t0 = time.time()
        found = _present(models, *needles)
        record(
            sec,
            cid,
            label,
            "PASS" if found else "INFO",
            f"{needles[0]} in Ollama catalog: {found}",
            t0=t0,
        )
