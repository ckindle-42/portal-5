"""Static configuration for the repair-loop bench.

TARGETS is a curated 10-workspace set across three tiers so a full run
covers direct chart reproduction, same-family arch pairs, and code
specialists in one pass. Override via --models to compare additional
workspaces without editing this file.

Arch is derived from the model_hint string (a3b/a4b/a1b markers → MoE);
this keeps arch labelling in sync with the fleet without a second source
of truth. If a future MoE model uses a different marker, add it here.
"""

from __future__ import annotations

OLLAMA_URL = "http://localhost:11434"

# Curated first-run set: ten workspaces across three tiers.
# See task file "Model selection" section for rationale.
#   Tier A — direct chart reproduction of @danpacary's headline models
#   Tier B — same-family dense/MoE arch pairs (independent replication)
#   Tier C — code specialists (Portal 5's actual coding fleet)
TARGETS: list[str] = [
    # Tier A — @danpacary chart rows
    "bench-qwen36-27b",  # Chart row 1: Qwen3.6-27B dense +47
    "bench-qwen36-35b-a3b",  # Chart row 3: Qwen3.6-35B-A3B MoE +11
    "bench-ornith-35b",  # Chart row 2: Ornith 1.0 35B dense +36
    # Tier B — controlled same-family dense-vs-MoE
    "bench-glm",  # GLM 4.7 Flash dense
    "bench-glm-reap",  # GLM 4.7 Flash REAP 23B-A3B MoE
    "bench-gemma4-31b-qat",  # Gemma 4 31B dense
    "bench-gemma4-26b-qat",  # Gemma 4 26B-a4b MoE
    # Tier C — code specialists
    "bench-devstral",  # Devstral 24B dense (Mistral code)
    "bench-qwen3-coder-30b",  # Qwen3-Coder 30B MoE
    "bench-qwopus-coder-mtp-v2",  # Qwopus3.6 27B dense (Qwen+Opus distill)
]

ARM_ONESHOT = "one_shot"
ARM_REPAIR = "one_repair"
ARMS = (ARM_ONESHOT, ARM_REPAIR)

ONESHOT_N = 5
REPAIR_N = 2
TEMPERATURE = 1.0

# Prompt templates. Kept as module constants so compute_gsha can hash them
# alongside the corpus — changing either resets fingerprint comparability.

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

# MoE detection markers found in Ollama model tags
_MOE_MARKERS = ("a3b", "a4b", "a1b", "-moe", "-MoE")


def arch_from_hint(model_hint: str) -> str:
    lower = model_hint.lower()
    for m in _MOE_MARKERS:
        if m.lower() in lower:
            return "MoE"
    return "dense"
