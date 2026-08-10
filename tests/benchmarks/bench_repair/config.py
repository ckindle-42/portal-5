"""Static configuration for the repair-loop bench."""

from __future__ import annotations

OLLAMA_URL = "http://localhost:11434"

# Tier A: @danpacary chart rows. Tier B: same-family dense/MoE pairs.
# Tier C: code specialists. See task file "Model selection" for rationale.
TARGETS: list[str] = [
    "bench-qwen36-27b",
    "bench-qwen36-35b-a3b",
    "bench-ornith-35b",
    "bench-glm",
    "bench-glm-reap",
    "bench-gemma4-31b-qat",
    "bench-gemma4-26b-qat",
    "bench-devstral",
    "bench-qwen3-coder-30b",
    "bench-qwopus-coder-mtp-v2",
]

ARM_ONESHOT = "one_shot"
ARM_REPAIR = "one_repair"
ARMS = (ARM_ONESHOT, ARM_REPAIR)

ONESHOT_N = 5
REPAIR_N = 2
TEMPERATURE = 1.0

# compute_gsha hashes these alongside the corpus, so changing either resets
# fingerprint comparability.
ONE_SHOT_TEMPLATE = "{prompt}"

REPAIR_TEMPLATE = (
    "{prompt}\n\n"
    "---\n\n"
    "Your previous attempt was:\n"
    "```python\n{prev_code}\n```\n\n"
    "Running the hidden tests produced this output:\n"
    "```\n{pytest_output}\n```\n\n"
    "The tests above failed. Fix only what failed. Return the corrected "
    "complete function in a ```python fenced code block."
)

_MOE_MARKERS = ("a3b", "a4b", "a1b", "-moe", "-MoE")


def arch_from_hint(model_hint: str) -> str:
    lower = model_hint.lower()
    for m in _MOE_MARKERS:
        if m.lower() in lower:
            return "MoE"
    return "dense"
