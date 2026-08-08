"""Prompt library and category maps for the bench package.

Extracted byte-for-byte from tests/benchmarks/bench_tps.py.
"""

from portal.platform.data_loader import load_data

# ── Prompt library ────────────────────────────────────────────────────────────
# Category-mapped prompts designed to produce ~150-250 tokens of structured
# output. Each prompt targets a specific capability so TPS comparisons are
# apples-to-apples within a category. The "general" prompt is used as fallback.


PROMPTS: dict[str, str] = load_data("tests/data", "bench_prompts_prompts")

# Map workspace IDs → prompt category
WORKSPACE_PROMPT_MAP: dict[str, str] = load_data("tests/data", "bench_prompts_workspace_prompt_map")

# Map Ollama backend group → prompt category
GROUP_PROMPT_MAP: dict[str, str] = {
    "general": "general",
    "coding": "coding",
    "security": "security",
    "reasoning": "reasoning",
    "vision": "vision",
    "creative": "creative",
    "math": "math",
}

# Map persona category (from YAML) → prompt category
PERSONA_CATEGORY_PROMPT_MAP: dict[str, str] = {
    "security": "security",
    "redteam": "security",
    "blueteam": "security",
    "pentesting": "security",
    "coding": "coding",
    "software": "coding",
    "development": "coding",
    "systems": "coding",  # linuxterminal, sqlterminal
    "architecture": "reasoning",  # itarchitect — system design = reasoning
    "reasoning": "reasoning",
    "research": "reasoning",
    "analysis": "reasoning",
    "creative": "creative",
    "writing": "creative",
    "vision": "vision",
    "multimodal": "vision",
    "data": "reasoning",
    "compliance": "reasoning",
    "general": "general",  # itexpert, techreviewer
    "benchmark": "coding",  # benchmark personas test coding capability
}


def _get_prompt_for_model(model: str, group: str = "") -> str:
    """Get the right prompt for a model based on its group."""
    if group and group in GROUP_PROMPT_MAP:
        return PROMPTS[GROUP_PROMPT_MAP[group]]
    return PROMPTS["general"]


def _prompt_category_for_model(model: str, group: str = "") -> str:
    """Return the prompt category name for a model."""
    if group and group in GROUP_PROMPT_MAP:
        return GROUP_PROMPT_MAP[group]
    return "general"


def _get_prompt_for_workspace(workspace_id: str) -> str:
    category = WORKSPACE_PROMPT_MAP.get(workspace_id, "general")
    return PROMPTS[category]


def _get_prompt_for_persona_category(category: str) -> str:
    cat_lower = category.lower() if category else ""
    for key, prompt_cat in PERSONA_CATEGORY_PROMPT_MAP.items():
        if key in cat_lower:
            return PROMPTS[prompt_cat]
    return PROMPTS["general"]


def _prompt_category_for_persona(category: str) -> str:
    """Return the prompt category name for a persona category string."""
    cat_lower = category.lower() if category else ""
    for key, prompt_cat in PERSONA_CATEGORY_PROMPT_MAP.items():
        if key in cat_lower:
            return prompt_cat
    return "general"
