"""Workspace configuration — WORKSPACES dict, persona map, tool resolution helpers.

Extracted from router_pipe.py. Import via:
    from portal_pipeline.router.workspaces import WORKSPACES, _PERSONA_MAP, ...
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Persona map (for tool whitelist resolution) ─────────────────────────────
_PERSONA_MAP: dict[str, dict[str, Any]] = {}


def _load_persona_map() -> None:
    """Load persona YAML files into a slug -> data dict for tool resolution."""
    global _PERSONA_MAP
    personas_dir = Path(__file__).resolve().parent.parent.parent / "config" / "personas"
    if not personas_dir.is_dir():
        return
    try:
        import yaml  # noqa: F811 — pyyaml is a pipeline dependency

        for yf in sorted(personas_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(yf.read_text()) or {}
                slug = data.get("slug", yf.stem)
                _PERSONA_MAP[slug] = data
            except Exception as e:
                logger.debug("Failed to load persona %s: %s", yf, e)
    except Exception as e:
        logger.warning("Failed to load persona map: %s", e)


_load_persona_map()

# Canonical workspace definitions — must match backends.yaml workspace_routing keys
# model_hint: preferred Ollama model tag within the routed backend group
# mlx_model_hint: preferred MLX model tag (HF path) for workspaces that route through MLX
WORKSPACES: dict[str, dict[str, Any]] = {
    "auto": {
        "name": "🤖 Portal Auto Router",
        "description": (
            "Intelligently routes to the best specialist model based on your question. "
            "Security/redteam topics → BaronLLM. Coding → Qwen3-Coder. "
            "Reasoning/research → DeepSeek-R1. Other → general."
        ),
        # AUTO primary swapped from dolphin to qwen3.5-abliterated for tool-call
        # support and catalog consistency with ollama-general line 1. Uncensored
        # property preserved (huihui-ai abliteration). See
        # TASK_TOOL_SUPPORT_AUDIT_V1 §A7.
        "model_hint": "huihui_ai/qwen3.5-abliterated:9b",
        "mlx_model_hint": "huihui-ai/Huihui-Qwen3.5-9B-abliterated-mlx-4bit",
        "tools": [],
    },
    "auto-coding": {
        "name": "💻 Portal Code Expert",
        "description": "Code generation, debugging, architecture review",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/GLM-4.7-Flash-4bit",
        # Output budget — GLM-4.7-Flash is verbose-by-default and can spend an
        # entire short response on analysis before reaching the code block.
        # 8192 tokens (~6000 words / ~24K chars) is enough for analysis +
        # production-grade code with comments. Mirrors auto-research /
        # auto-reasoning tier (which use 16384 for longer prose responses).
        # See UAT 2026-04-28 §A — auto-coding "planning instead of code" failures.
        "predict_limit": 8192,
        "tools": [
            "execute_python",
            "execute_nodejs",
            "execute_bash",
            "sandbox_status",
            "read_word_document",
            "read_pdf",
            "remember",
            "recall",
        ],
    },
    "auto-agentic": {
        "name": "⚡ Portal Agentic Coder (Heavy)",
        "description": (
            "Full-power agentic coding via Qwen3-Coder-Next-4bit (80B MoE, 3B active, 256K ctx). "
            "Triggers big-model mode: unloads all Ollama + MLX models before loading. "
            "Use for long-horizon multi-file tasks, SWE-agent-style workflows, and complex refactors. "
            "Not for interactive chat — load time ~60s, context capped at 32K."
        ),
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-Next-4bit",
        "context_limit": 32768,
        "tools": [
            "execute_python",
            "execute_bash",
            "execute_nodejs",
            "sandbox_status",
            "create_word_document",
            "create_excel",
            "create_powerpoint",
            "read_word_document",
            "read_excel",
            "read_powerpoint",
            "read_pdf",
            "classify_vulnerability",
            "transcribe_audio",
            "speak",
            "generate_image",
            "web_search",
            "web_fetch",
            "remember",
            "recall",
            "kb_search",
            "kb_list",
        ],
    },
    "auto-spl": {
        "name": "🔍 Portal SPL Engineer",
        "description": "Splunk SPL queries, pipeline explanation, detection search authoring",
        "model_hint": "deepseek-coder-v2:16b-lite-instruct-q4_K_M",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
        "tools": ["classify_vulnerability", "kb_search", "kb_list"],
    },
    "auto-security": {
        "name": "🔒 Portal Security Analyst",
        "description": "Security analysis, hardening, vulnerability assessment",
        "model_hint": "baronllm:q6_k",
        "tools": [
            "classify_vulnerability",
            "execute_python",
            "execute_bash",
            "web_search",
            "web_fetch",
            "kb_search",
            "kb_list",
        ],
    },
    "auto-redteam": {
        "name": "🔴 Portal Red Team",
        "description": "Offensive security, penetration testing, exploit research",
        "model_hint": "baronllm:q6_k",
        "tools": ["execute_python", "execute_bash", "execute_nodejs", "classify_vulnerability"],
    },
    "auto-blueteam": {
        "name": "🔵 Portal Blue Team",
        "description": "Defensive security, incident response, threat hunting",
        "model_hint": "lily-cybersecurity:7b-q4_k_m",
        "tools": ["execute_python", "classify_vulnerability"],
    },
    "auto-creative": {
        "name": "✍️  Portal Creative Writer",
        "description": "Creative writing, storytelling, content generation",
        "model_hint": "dolphin-llama3:8b",
        "mlx_model_hint": "divinetribe/gemma-4-31b-it-abliterated-4bit-mlx",
        "tools": [],
    },
    "auto-reasoning": {
        "name": "🧠 Portal Deep Reasoner",
        "description": "Complex analysis, research synthesis, step-by-step reasoning",
        "model_hint": "deepseek-r1:32b-q4_k_m",
        "mlx_model_hint": "Jackrong/MLX-Qwopus3.5-27B-v3-8bit",
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": [],
    },
    "auto-documents": {
        "name": "📄 Portal Document Builder",
        "description": "Create Word, Excel, PowerPoint via MCP tools; diarized transcription",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "mlx-community/phi-4-8bit",
        "predict_limit": 8192,
        "tools": [
            "create_word_document",
            "create_excel",
            "create_powerpoint",
            "read_word_document",
            "read_excel",
            "read_powerpoint",
            "read_pdf",
            "transcribe_with_speakers",
        ],
    },
    "auto-video": {
        "name": "🎬 Portal Video Creator",
        "description": "Generate videos via ComfyUI / Wan2.2",
        "model_hint": "granite4.1:8b",
        "tools": ["generate_video", "generate_image", "list_video_models"],
    },
    "auto-music": {
        "name": "🎵 Portal Music Producer",
        "description": "Generate music and audio via AudioCraft/MusicGen",
        # auto-music dispatches via OWUI Path 2 (server:mcp:portal_music + portal_tts).
        # Hint swapped to qwen3.5-abliterated for catalog consistency with AUTO.
        "model_hint": "huihui_ai/qwen3.5-abliterated:9b",
        "tools": [],
    },
    "auto-research": {
        "name": "🔍 Portal Research Assistant",
        "description": "Web research, information synthesis, fact-checking",
        "model_hint": "huihui_ai/tongyi-deepresearch-abliterated",
        "mlx_model_hint": "mlx-community/gemma-4-31b-it-4bit",
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": [
            "web_search",
            "web_fetch",
            "news_search",
            "kb_search",
            "kb_search_all",
            "kb_list",
            "remember",
            "recall",
        ],
    },
    "auto-vision": {
        "name": "👁️  Portal Vision",
        "description": "Image understanding, visual analysis, multimodal tasks",
        "model_hint": "qwen3-vl:32b",
        "mlx_model_hint": "mlx-community/gemma-4-31b-it-4bit",
        "tools": ["transcribe_audio"],
    },
    "auto-data": {
        "name": "📊 Portal Data Analyst",
        "description": "Data analysis, statistics, visualization guidance",
        "model_hint": "deepseek-r1:32b-q4_k_m",
        "mlx_model_hint": "mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit",
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": ["execute_python", "create_excel", "kb_search"],
    },
    "auto-compliance": {
        "name": "⚖️  Portal Compliance Analyst",
        "description": (
            "Multi-framework compliance analysis: NERC CIP, HIPAA, GDPR, "
            "SOC 2, PCI-DSS, NIST CSF/800-53, ISO 27001, FedRAMP, NIS2, "
            "CMMC, FFIEC, and state privacy laws (CCPA/CPRA, Texas TDPSA, "
            "Connecticut CTDPA, etc.). Gap analysis, policy drafting, "
            "evidence review, cross-framework control mapping, audit prep."
        ),
        "model_hint": "deepseek-r1:32b-q4_k_m",
        "mlx_model_hint": "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit",
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": [
            "create_word_document",
            "read_pdf",
            "kb_search",
            "kb_list",
            "web_search",
        ],
    },
    "auto-mistral": {
        "name": "🧪 Portal Mistral Reasoner",
        "description": (
            "Structured reasoning via Magistral-Small-2509 — Mistral training lineage, "
            "[THINK] mode, distinct failure profile from Qwen/DeepSeek reasoning models."
        ),
        "model_hint": "deepseek-r1:32b-q4_k_m",
        "mlx_model_hint": "lmstudio-community/Magistral-Small-2509-MLX-8bit",
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": ["execute_python", "execute_bash"],
    },
    "auto-math": {
        "name": "🧮 Portal Math Reasoner",
        "description": "Mathematical problem solving, proofs, calculus, algebra, statistics",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "mlx-community/Qwen2.5-Math-7B-Instruct-4bit",
        "predict_limit": 8192,
        "tools": ["execute_python"],
    },
    # ── Coding Capability Benchmark Workspaces ───────────────────────────────
    "bench-devstral": {
        "name": "🔬 Bench · Devstral-Small-2507",
        "description": "Benchmark: Devstral-Small-2507 (MLX, Mistral/Codestral lineage, ~15GB, 53.6% SWE-bench)",
        "model_hint": "devstral:24b",
        "mlx_model_hint": "lmstudio-community/Devstral-Small-2507-MLX-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-qwen3-coder-next": {
        "name": "🔬 Bench · Qwen3-Coder-Next (80B MoE)",
        "description": "Benchmark: Qwen3-Coder-Next-4bit (MLX, Alibaba, 80B MoE 3B active, ~46GB, 256K ctx — cold load ~60s)",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-Next-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-qwen3-coder-30b": {
        "name": "🔬 Bench · Qwen3-Coder-30B",
        "description": "Benchmark: Qwen3-Coder-30B-A3B-8bit (MLX, Alibaba, 30B MoE 3B active, ~22GB)",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-llama33-70b": {
        "name": "🔬 Bench · Llama-3.3-70B",
        "description": "Benchmark: Llama-3.3-70B-Instruct-4bit (MLX, Meta, ~40GB — cold load ~60s, plan for sequential runs)",
        "model_hint": "llama3.3:70b-q4_k_m",
        "mlx_model_hint": "mlx-community/Llama-3.3-70B-Instruct-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-phi4": {
        "name": "🔬 Bench · Phi-4",
        "description": "Benchmark: phi-4-8bit (MLX, Microsoft, 14B, synthetic training data — distinct methodology)",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "mlx-community/phi-4-8bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-phi4-reasoning": {
        "name": "🔬 Bench · Phi-4-reasoning-plus",
        "description": "Benchmark: Phi-4-reasoning-plus (MLX, Microsoft, RL-trained, ~7GB — produces reasoning traces before code)",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "lmstudio-community/Phi-4-reasoning-plus-MLX-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-dolphin8b": {
        "name": "🔬 Bench · Dolphin-Llama3-8B",
        "description": "Benchmark: Dolphin3.0-Llama3.1-8B-8bit (MLX, Cognitive Computations, ~9GB — fast baseline, uncensored)",
        "model_hint": "dolphin-llama3:8b",
        "mlx_model_hint": "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-glm": {
        "name": "🔬 Bench · GLM-4.7-Flash",
        "description": "Benchmark: glm-4.7-flash:q4_k_m (Ollama, Zhipu AI — distinct Chinese research lineage, ~6GB)",
        "model_hint": "glm-4.7-flash:q4_k_m",
        "max_concurrent": 1,
        "tools": [],
    },
    "bench-gptoss": {
        "name": "🔬 Bench · GPT-OSS-20B",
        "description": "Benchmark: gpt-oss:20b (Ollama, OpenAI open-weight MoE, ~12GB, o3-mini level — configurable thinking depth)",
        "model_hint": "gpt-oss:20b",
        "max_concurrent": 1,
        "tools": [],
    },
    "bench-laguna": {
        "name": "🔬 Bench · Laguna-XS.2 (Poolside)",
        "description": "Benchmark: Laguna-XS.2-4bit (MLX, Poolside AI, 33B-A3B MoE, ~18.8GB, 68.2% SWE-bench Verified, interleaved reasoning)",
        "model_hint": "glm-4.7-flash:q4_k_m",
        "mlx_model_hint": "mlx-community/Laguna-XS.2-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-granite41-8b": {
        "name": "🔬 Bench · Granite-4.1 8B (IBM)",
        "description": (
            "Benchmark: granite4.1:8b (Ollama, IBM Research, dense 8B no-think, "
            "~5.3GB Q4_K_M — Apache 2.0, ISO-certified. BFCL V3 68.3, IFEval 87.1, "
            "GSM8K 92.5. Predictable-latency tool calling without reasoning chains.)"
        ),
        "model_hint": "granite4.1:8b",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-granite41-30b": {
        "name": "🔬 Bench · Granite-4.1 30B (IBM)",
        "description": (
            "Benchmark: granite4.1:30b (Ollama, IBM Research, dense 30B no-think, "
            "~17GB Q4_K_M — Apache 2.0, ISO-certified, cryptographic signatures. "
            "BFCL V3 73.7 (#1 on IBM chart), IFEval 89.7, GSM8K 94.2, EvalPlus 82.7. "
            "Trained with GRC data curation — fits compliance/audit workflows.)"
        ),
        "model_hint": "granite4.1:30b",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-qwen35-abliterated": {
        "name": "🧪 Bench — Qwen3.5-9B Abliterated (huihui-ai)",
        "description": "Direct routing to huihui_ai/qwen3.5-abliterated:9b — uncensored, tool-capable AUTO primary baseline",
        "model_hint": "huihui_ai/qwen3.5-abliterated:9b",
        "mlx_model_hint": "huihui-ai/Huihui-Qwen3.5-9B-abliterated-mlx-4bit",
        "tools": [],
    },
}

# ── Tool-call helpers (M2) ──────────────────────────────────────────────────

MAX_TOOL_HOPS = int(os.environ.get("MAX_TOOL_HOPS", "10"))


def _workspace_tools(workspace_id: str) -> list[str]:
    """Get the tool whitelist for a workspace."""
    return WORKSPACES.get(workspace_id, {}).get("tools", [])


def _resolve_persona_tools(persona: dict, workspace_id: str) -> list[str]:
    """Resolve the effective tool list for a persona within a workspace.

    Order of precedence:
        1. persona.tools_deny — always strips these tools
        2. persona.tools_allow — if present, uses this list (then applies deny)
        3. workspace.tools — default fallback
    """
    workspace_tools = set(_workspace_tools(workspace_id))
    persona_allow = set(persona.get("tools_allow", []) or [])
    persona_deny = set(persona.get("tools_deny", []) or [])

    effective = persona_allow or workspace_tools
    effective = effective - persona_deny
    return sorted(effective)


def _resolve_persona_browser_policy(persona: dict) -> dict:
    """Return the persona's browser policy. Defaults applied for missing fields."""
    bp = persona.get("browser_policy", {}) or {}
    return {
        "allowed_domains": bp.get("allowed_domains") or [],
        "blocked_domains": bp.get("blocked_domains") or [],
        "default_profile": bp.get("default_profile", "_isolated"),
        "force_credential_fill": bp.get("force_credential_fill", False),
        "max_navigations_per_session": bp.get("max_navigations_per_session", 50),
    }
