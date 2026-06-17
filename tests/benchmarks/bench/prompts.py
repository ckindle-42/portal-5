"""Prompt library and category maps for the bench package.

Extracted byte-for-byte from tests/benchmarks/bench_tps.py.
"""

# ── Prompt library ────────────────────────────────────────────────────────────
# Category-mapped prompts designed to produce ~150-250 tokens of structured
# output. Each prompt targets a specific capability so TPS comparisons are
# apples-to-apples within a category. The "general" prompt is used as fallback.

PROMPTS: dict[str, str] = {
    "general": (
        "You are a helpful assistant. Answer concisely.\n\n"
        "List the 7 OSI model layers from bottom to top. For each layer, provide: "
        "1) the layer number, 2) the standard name, 3) one example protocol or technology. "
        "Format as a numbered list with one line per layer."
    ),
    "coding": (
        "You are a code assistant. Write clean, production-quality code.\n\n"
        "Write a Python function called `merge_intervals` that takes a list of "
        "tuples (each tuple is a pair of integers representing a start and end value) "
        "and returns a new list with overlapping intervals merged. "
        "Example: [(1,3),(2,6),(8,10),(15,18)] → [(1,6),(8,10),(15,18)]. "
        "Include type hints, a docstring with the algorithm explanation, and "
        "handle edge cases (empty list, single interval, fully overlapping). "
        "Return only the function, no explanation outside the docstring."
    ),
    "security": (
        "You are a cybersecurity analyst. Be precise and cite frameworks.\n\n"
        "Analyze the following scenario and provide a structured response:\n"
        "A company's SIEM detected repeated SSH brute-force attempts from 47 "
        "unique IPs over 2 hours targeting port 22 on 3 servers in the DMZ. "
        "Two IPs are on the CrowdSec community blocklist.\n\n"
        "For each item below, provide 2-3 sentences:\n"
        "1. Classification (MITRE ATT&CK tactic + technique ID)\n"
        "2. Immediate containment actions (first 30 minutes)\n"
        "3. Detection rule to write (field names + logic)\n"
        "4. Root cause question to investigate"
    ),
    "reasoning": (
        "You are a structured reasoner. Think step-by-step before concluding.\n\n"
        "A hospital emergency room has 30 patients arriving per hour during peak "
        "hours. The ER has 8 beds, 3 doctors, and 12 nurses. Average treatment "
        "time is 45 minutes per patient. Current wait time is 3.5 hours.\n\n"
        "Identify: 1) the primary bottleneck (beds, doctors, or nurses — show "
        "the math), 2) the minimum number of additional resources of each type "
        "needed to reduce wait time to under 1 hour, 3) one process change that "
        "could help without adding resources. Show your calculations."
    ),
    "creative": (
        "You are a creative writer with strong narrative voice.\n\n"
        "Write the opening scene (exactly 8-10 sentences) of a noir detective "
        "story set in a city where memories can be extracted and traded as "
        "currency. The detective has just been hired to find a stolen memory — "
        "but it belongs to the detective themselves. End the scene on a hook. "
        "Use vivid sensory details and short, punchy sentences."
    ),
    "vision": (
        "You are a multimodal vision analyst. Describe what you see precisely.\n\n"
        "For any image provided, respond with this exact structure:\n"
        "1. OBJECTS: List every distinct object visible (name + color + position)\n"
        "2. TEXT: Transcribe any visible text exactly as written\n"
        "3. SCENE: Describe the setting in 2-3 sentences\n"
        "4. ANOMALIES: Note anything unusual, damaged, or out of place\n"
        "5. CONFIDENCE: Rate your analysis certainty (high/medium/low) per category\n\n"
        "Since no image is provided for this text-only test, describe this prompt "
        "template itself — what it expects, what each section does, and suggest "
        "one improvement to the analysis framework."
    ),
    "math": (
        "You are a precise mathematical reasoner. Show all steps.\n\n"
        "Solve the following three problems. For each, show your work step by step "
        "and state your final answer clearly.\n\n"
        "1. ALGEBRA: Two trains travel toward each other. Train A leaves Station X "
        "at 8:00 AM at 60 km/h. Train B leaves Station Y (300 km away) at 8:00 AM "
        "at 40 km/h. At what time do they meet, and how far from Station X?\n\n"
        "2. COMBINATORICS: A team of 3 is chosen from 4 men and 5 women such that "
        "at least 2 women are on the team. How many distinct teams are possible? "
        "Show the case breakdown.\n\n"
        "3. NUMBER THEORY: Find all integers n such that n² + 3n − 18 = 0. "
        "Factor the expression and verify each solution by substitution."
    ),
}

# Map workspace IDs → prompt category
WORKSPACE_PROMPT_MAP: dict[str, str] = {
    "auto": "general",
    "auto-coding": "coding",
    # auto-agentic has tools enabled (execute_python etc.) — the coding prompt's
    # "Return only the function" instruction causes empty synthesis after tool execution
    # (model considers task done via tool, outputs nothing in hop-2).  Use reasoning
    # prompt instead: ER bottleneck analysis is qualitative and doesn't trigger tool calls.
    "auto-agentic": "reasoning",
    "auto-spl": "coding",
    "auto-security": "security",
    "auto-redteam": "security",
    "auto-redteam-deep": "security",
    "auto-blueteam": "security",
    "auto-pentest": "security",
    "auto-purpleteam-deep": "security",
    "auto-purpleteam-exec": "security",
    "auto-creative": "creative",
    "auto-reasoning": "reasoning",
    "auto-documents": "coding",
    "auto-video": "creative",
    "auto-music": "creative",
    "auto-research": "reasoning",
    "auto-vision": "vision",
    "auto-data": "reasoning",
    "auto-compliance": "reasoning",
    "auto-mistral": "reasoning",
    "auto-math": "reasoning",
    # Benchmark workspaces — prompt matches the model's primary capability
    "bench-qwen3-coder-next": "coding",
    "bench-qwen3-coder-30b": "coding",
    "bench-llama33-70b": "coding",
    "bench-phi4": "reasoning",
    "bench-phi4-reasoning": "reasoning",
    "bench-dolphin8b": "creative",
    "bench-glm": "coding",
    "bench-laguna": "reasoning",
    "bench-gptoss": "reasoning",
    # Granite 4.1 — IBM dense, no-think, tool-calling-first.
    # CC-01 is a creative-coding bench, but to keep cross-bench numbers
    # comparable Granite gets the same coding category as the other coders.
    # Granite's *strength* is tool calling/IFEval, not creative coding —
    # interpret a low CC-01 score against Laguna/GLM as expected, not a defect.
    "bench-granite41-8b": "coding",
    "bench-granite41-30b": "coding",
    "bench-qwen35-abliterated": "general",  # huihui_ai/qwen3.5-abliterated:9b — uncensored, AUTO primary baseline
    # ── V6 bench workspaces (TASK_MODEL_REFRESH_V6) — ascending size, family-grouped ──
    # 9B tier
    "bench-omnicoder2": "coding",  # omnicoder2:9b — Qwen3.5-9B SFT on agentic traces
    "bench-negentropy": "reasoning",  # Jackrong Negentropy 9B — trace-inversion CoT
    # Qwen3.6 family — 27B dense then 35B-A3B MoE (family-grouped, ascending)
    "bench-qwen36-27b": "coding",  # Qwen3.6-27B Q8 — dense 27B + vision, SWE-bench 77.2%
    "bench-qwen36-27b-mtp": "coding",  # Qwen3.6-27B MTP — speculative decoding bench
    "bench-qwen36-35b-a3b": "coding",  # Qwen3.6-35B-A3B — MoE 3B active, agentic-coding
    # 32B standalone
    "bench-olmo3-32b": "reasoning",  # OLMo-3-32B — Allen AI dense 32B, non-Qwen lineage
    # V7 bench workspaces — OCR, MoE creative, security reasoning, tools
    "bench-olmocr2": "vision",  # Allen AI olmOCR-2-7B — OCR/document understanding
    "bench-nanonets-ocr2": "vision",  # Nanonets OCR2-3B — OCR specialist
    "bench-lfm2-moe": "creative",  # LFM2-8B-A1B MoE — creative generation
    "bench-foundation-sec": "reasoning",  # Foundation-Sec-8B-Reasoning — security CoT
    "bench-toolace25": "coding",  # ToolACE-2.5 — tool-calling; "coding" is closest proxy
    # Auto workspaces added after TC-6 audit — fall back to "general" without these
    "auto-daily": "general",  # gemma4:26b-a4b-it-qat daily driver
    "auto-audio": "general",  # gemma4:12b-it-qat audio analyst
    "auto-phi4": "reasoning",  # phi4-reasoning:plus — STEM/chain-of-thought specialist
    "auto-bigfix": "coding",  # IBM BigFix endpoint management — coding prompt (API scripting)
    # auto-cad uses the coding prompt: OpenSCAD code generation is pure text output;
    # the CAD render MCP (:8926) is optional and does not affect TPS measurement.
    "auto-cad": "coding",  # OpenSCAD / 3D-print workspace — parametric code generation
    # ── V7-final catalog refresh (TASK_MODEL_REFRESH_V7) ─────────────────
    # Unsloth Dynamic 2.0 Qwen3.6 pair — quant-method probe vs stock 4-bit
    "bench-qwen36-27b-ud": "coding",
    "bench-qwen36-35b-a3b-ud": "coding",
    # TASK_QUANT_TRUEUP_V1 — optimized-quant + uncensored-refresh A/B candidates
    "bench-qwen36-27b-optiq": "coding",  # OptiQ vs plain 4-bit dense (Finding A)
    "bench-gemma4-26b-optiq": "general",  # OptiQ vs plain gemma-4 (Finding A; fp16 KV only)
    "bench-huihui-qwen36-27b": "general",  # Qwen3.6 abliterated dense (Finding B)
    "bench-huihui-qwen36-35b-a3b": "general",  # Qwen3.6 abliterated MoE (Finding B, speed play)
    # ── V8 bench workspaces (TASK_MODEL_REFRESH_V8) ─────────────────────
    # Gemma 4 family — encoder-free multimodal, ascending size
    "bench-gemma4-e2b": "vision",  # Gemma 4 E2B — 2B efficient multimodal
    "bench-gemma4-e4b": "vision",  # Gemma 4 E4B — 4B efficient multimodal
    "bench-gemma4-e4b-qat": "vision",  # Gemma 4 E4B QAT — near-BF16 quant
    "bench-gemma4-12b": "general",  # Gemma 4 12B — mid-size multimodal
    "bench-gemma4-26b-qat": "general",  # Gemma 4 26B QAT — auto-daily production model
    "bench-gemma4-31b-qat": "general",  # Gemma 4 31B QAT — upper-tier candidate
    # Phi-4 mini family
    "bench-phi4-mini": "reasoning",  # Phi-4-mini — dense 3.8B reasoning
    "bench-phi4-mini-reasoning": "reasoning",  # Phi-4-mini-reasoning — AIME/MATH-500 specialist (auto-math primary)
    # LFM2.5 creative/music lane
    "bench-lfm25-8b": "creative",  # LFM2.5-8B — liquid foundation model, creative/music
    "bench-lfm25-8b-uncensored": "creative",  # LFM2.5-8B uncensored — abliterated creative variant
    # Coding lane additions
    "bench-starcoder2": "coding",  # StarCoder2 — code completion
    "bench-devstral-small-2": "coding",  # Devstral-Small-2 — Mistral coding specialist
    "bench-qwen3-coder-next-abliterated": "coding",  # Qwen3-Coder-Next abliterated (auto-spl primary)
    # Reasoning/security additions
    "bench-mistral-small32": "reasoning",  # Mistral-Small-3.2-24B
    "bench-r1-0528-qwen3-8b": "reasoning",  # DeepSeek-R1-0528-Qwen3-8B (auto-reasoning primary)
    "bench-r1-0528-abliterated": "reasoning",  # R1-0528 abliterated — CoT without refusals
    # General additions
    "bench-nex-n2-mini": "coding",  # Nex-N2-Mini — compact agentic coding
    "bench-harness1": "general",  # Harness-1 eval model
    "bench-qwen36-hauhaucs": "creative",  # Qwen3.6-35B-A3B HauhauCS uncensored (auto-creative primary)
    # ── Security model bench workspaces ─────────────────────────────────────
    "bench-gemma4-31b-crack": "security",  # JANG-CRACK — auto-pentest primary (0.933 bench score)
    "bench-supergemma4": "security",       # SuperGemma4-26B uncensored (auto-redteam-deep primary)
    # ── 3B reasoning/uncensored bench workspaces (2026-06-17) ───────────────
    "bench-vibethinker-3b": "reasoning",   # VibeThinker-3B — Qwen2.5-3B, 0.938 avg, 39s (= phi4-mini at half latency)
    "bench-vibethinker-3b-ablated": "security",  # VibeThinker-3B-Ablated — 0.775 security avg
    # ── CAD/3D-print bench workspace ────────────────────────────────────────
    "bench-c3d-v0": "coding",              # 3D-print coding candidate (auto-cad evaluation)
    # ── Fast-context bench workspace ────────────────────────────────────────
    "bench-fastcontext": "coding",         # FastContext-1.0-4B-SFT (Microsoft long-context)
    # ── Generative image bench workspace ────────────────────────────────────
    # bench-diffusiongemma is a text→image diffusion model; the text harness produces
    # only the prompt text, not the image output, so TPS is not meaningful here.
    # Keep it in WORKSPACE_PROMPT_MAP so it doesn't fall through to "general" silently.
    "bench-diffusiongemma": "vision",      # DiffusionGemma-26B-A4B — image gen via token diffusion
    # ── Qwopus v2 MTP bench ─────────────────────────────────────────────────
    "bench-qwopus-coder-mtp-v2": "coding",  # Qwopus3.6-27B-v2-MTP (BLOCKED — widespread 500s)
    # Speech models — NOT in WORKSPACE_PROMPT_MAP by design:
    # - bench-voxtral-realtime (streaming ASR — text harness cannot exercise)
    # - bench-voxtral-tts (TTS — text harness cannot exercise)
    # - bench-granite-speech (ASR with keyword biasing — text harness cannot exercise)
    # These get probed by TASK_SPEECH_SHOOTOUT_V1 (deferred).
    # ── Drift backfill (pre-existing gap) ───────────────────────────────
    # tools-specialist (granite4.1:8b) — same tool-call issue as auto-agentic with
    # coding prompt; use general (OSI layers) which is pure knowledge recall, safe.
    "tools-specialist": "general",  # granite4.1:8b tool-calling specialist
}

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
