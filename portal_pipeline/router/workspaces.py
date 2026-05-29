"""Routing policy — workspace catalog, persona map, and tool whitelist resolution.

The pipeline's "what should I do?" decisions live here:

* ``WORKSPACES`` — the canonical workspace catalog. One entry per
  user-selectable workspace; each entry pins a preferred Ollama model
  (``model_hint``), an MLX model (``mlx_model_hint``), per-workspace
  tuning knobs (``predict_limit``, ``context_limit``, ``max_concurrent``,
  ``mlx_only``, ``mlx_chat_template_kwargs``, ``emits_reasoning``,
  ``system_prompt_append``), and the default tool whitelist
  (``tools``). The keys here are the contract — they must match
  ``workspace_routing`` in ``config/backends.yaml`` exactly (the
  consistency check in CLAUDE.md §6 enforces this). Workspaces
  prefixed ``bench-`` are user-pickable but excluded from auto-routing.

* ``_PERSONA_MAP`` — slug → persona YAML dict for every file under
  ``config/personas/``. Populated **at import time** by
  ``_load_persona_map()``. The pipeline indexes this by the persona
  slug taken from the chat-completion request.

* ``_resolve_persona_tools`` — combines a persona's optional
  ``tools_allow``/``tools_deny`` with the workspace default to produce
  the effective tool list for one request. This is the policy gate
  before ``tool_registry.get_openai_tools`` is asked to advertise
  anything to the model.

* ``_resolve_persona_browser_policy`` — defined but **currently has no
  callers in the active codebase**. Documented here for completeness;
  see its own docstring for the intended consumer.

Import-time side effect: ``_load_persona_map()`` runs at module load
and reads every ``*.yaml`` under ``<repo>/config/personas/``. This is
fine in production (one-time cost) but tests that mock the filesystem
must do so before importing this module.

History note: this file is the first extracted sub-module of the
``router_pipe.py`` decomposition (CLAUDE.md alludes to "additional
sub-modules"). The public surface — ``WORKSPACES``, ``_PERSONA_MAP``,
``MAX_TOOL_HOPS``, ``_resolve_persona_tools``, ``_workspace_tools`` —
is re-exported from ``router_pipe.py`` so external callers and tests
see no API change.
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
    """Populate ``_PERSONA_MAP`` from every ``*.yaml`` under ``config/personas/``.

    Called exactly once, at module import time (line 40). The pipeline
    has no hot-reload path for personas — operator workflow is to edit
    YAML and restart the pipeline container.

    Each file is keyed in ``_PERSONA_MAP`` by its ``slug:`` field if
    present, otherwise by the filename stem. The fallback exists so a
    persona YAML missing a ``slug:`` line still loads instead of
    failing silently.

    Failure modes — all logged, never raised:

    * ``config/personas/`` directory missing → silent return; the
      registry stays empty.
    * Top-level YAML error → logged warning; no personas load.
    * One file invalid → debug log for that file; surrounding files
      still load.

    The pipeline must reach a serving state even with a broken
    persona catalog so operators can fix YAML without a manual
    process bounce. Same "graceful empty" pattern as
    ``cluster_backends._load_config``.
    """
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

# ─── Canonical workspace catalog ─────────────────────────────────────────────
# Keys here MUST match `workspace_routing` in config/backends.yaml exactly.
# (Consistency check in CLAUDE.md §6 enforces this on startup.)
#
# Per-entry fields (all optional except `name` and `description`):
#   name                       Display name shown in Open WebUI.
#   description                Open WebUI tooltip / model description.
#   model_hint                 Preferred Ollama tag in the routed backend group.
#   mlx_model_hint             Preferred MLX model (HuggingFace path).
#   mlx_only                   True → never fall through to Ollama, even on MLX failure.
#   tools                      Default tool-name whitelist (overridable per-persona).
#   predict_limit              Max output tokens (Ollama: num_predict; MLX: max_tokens).
#   context_limit              Max context window for this workspace.
#   max_concurrent             Per-workspace concurrency cap (router_pipe semaphore).
#   system_prompt_append       String appended after the persona system prompt.
#   mlx_chat_template_kwargs   Kwargs forwarded to the MLX chat template
#                              (e.g. enable_thinking=False to suppress <think>).
#   emits_reasoning            True → model emits reasoning chains (DeepSeek-R1 family);
#                              affects how the streaming layer parses delta fields.
#
# Workspace ID prefixes:
#   auto       — auto-routable (the LLM intent classifier may route here).
#   auto-*     — user-selectable AND auto-route targets.
#   bench-*    — user-selectable only; excluded from auto-routing (see
#                router_pipe.py:1046).
# ─────────────────────────────────────────────────────────────────────────────
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
        # MLX path: huihui-ai/Huihui-Qwen3.5-9B-abliterated-mlx-4bit. Healthy as
        # of 2026-05-12 UAT (WS-01 / P-W06 / P-W03 / P-B03 PASS via pipeline,
        # routed model confirmed). Earlier "V5 warmup FAIL" condition was
        # resolved by V6 refresh; previous comment block was stale.
        # Constraint: auto workspace must remain uncensored — any future MLX
        # repin candidate must be abliterated or otherwise uncensored.
        # For snappier daily-driver flows that bypass the LLM intent
        # classifier, users should pick the `auto-daily` workspace
        # (pinned to mlx-community/gemma-4-26b-a4b-it-4bit, 57.8 TPS).
        "model_hint": "huihui_ai/qwen3.5-abliterated:9b",
        "mlx_model_hint": "huihui-ai/Huihui-Qwen3.5-9B-abliterated-mlx-4bit",
        "tools": [],
    },
    "auto-daily": {
        "name": "🪶 Portal Daily Driver",
        "description": (
            "Fast everyday assistant: chat, writing, editing, summarization, "
            "planning, light technical help. MLX gemma-4-26b-a4b primary "
            "(57.8 TPS, MoE 4B active, VLM, Apache 2.0); Ollama dolphin-"
            "llama3:8b fallback (non-thinking). Daily-driver lane — escalates "
            "to specialist workspaces (auto-coding, auto-reasoning, etc.) when "
            "the persona detects out-of-lane requests. No reasoning chain, "
            "no <think> emission — predict_limit capped and thinking mode "
            "explicitly disabled to keep responses snappy."
        ),
        "model_hint": "dolphin-llama3:8b",
        "mlx_model_hint": "mlx-community/gemma-4-26b-a4b-it-4bit",
        "predict_limit": 4096,
        # Suppress thinking mode on Gemma 4 (chat-template kwarg honored by
        # mlx_lm.server / mlx_vlm.server). Same pattern as auto-security /
        # auto-redteam in WORKSPACES (commit 7462c1b) — keeps content in
        # delta.content rather than delta.reasoning under streaming. Consumed
        # by _inject_mlx_options() in router_pipe.py.
        "mlx_chat_template_kwargs": {"enable_thinking": False},
        "tools": [
            "web_search",
            "web_fetch",
            "kb_search",
            "kb_list",
            "read_pdf",
            "read_word_document",
            "remember",
            "recall",
        ],
    },
    "auto-coding": {
        "name": "💻 Portal Code Expert",
        "description": "Code generation, debugging, architecture review",
        "model_hint": "qwen3-coder:30b",
        # V5 bench: GLM-4.7-Flash-4bit FAIL (0 tokens, P5-MLX-006 chat template defect).
        # Promoted to Laguna-XS.2-4bit (Poolside AI, 40.3 t/s, 19GB, smoke PASS).
        # V9 REVERTED (TASK_REVERT_AUTOCODING_PROMOTION_V1): the OptiQ auto-promotion
        # violated the 20 TPS floor (14.4) and lowered quality (0.67 vs Laguna 1.0).
        # The quant A/B (OptiQ vs plain-27B) was valid but does not justify
        # displacing the faster/higher-quality Laguna MoE incumbent. OptiQ-27B
        # remains available as bench-qwen36-27b-optiq.
        "mlx_model_hint": "mlx-community/Laguna-XS.2-4bit",
        # Output budget raised to 16384 — full-game HTML (Asteroids, particle
        # systems, etc.) sits at 6-10K tokens; the prior 8192 cap cut responses
        # while still in the analysis phase for complex deliverables.
        # See UAT 2026-04-28 §A and run-21 streaming-cutoff analysis.
        "predict_limit": 16384,
        # Injected after the persona system prompt to override agentic "plan then stop"
        # behavior in Laguna-XS.2-4bit. The model otherwise plans in <think>, writes
        # one intro sentence, and stops — expecting a tool call loop that doesn't exist
        # in single-turn chat. This directive forces immediate complete output.
        "system_prompt_append": (
            "\n\nCRITICAL OUTPUT RULE: This is a SINGLE-TURN response — deliver everything now. "
            "Do NOT promise, plan, or say 'I will'. IMMEDIATELY produce your complete output. "
            "For code: wrap in fenced code blocks (```language). "
            "For terminal output: emit the exact shell output, nothing else. "
            "Your response must be complete and self-contained — the user cannot follow up."
        ),
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
            "read_word_document",
            "read_excel",
            "read_powerpoint",
            "read_pdf",
            "classify_vulnerability",
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
        # V5 bench: glm-4.7-flash-abliterated-8bit FAIL (0 tokens, P5-MLX-008).
        # Promoted to AEON-4Bit (Qwen3.6 27B uncensored, 7.9 t/s, 14GB, smoke PASS).
        # Thinking disabled (enable_thinking=False): AEON outputs directly to
        # delta.content, avoiding the mlx_lm regression where all output routes
        # to delta.reasoning leaving content="" in OWUI. Direct answers are
        # sufficient — security analysis quality held at Q=0.50 baseline.
        # web_search/web_fetch removed (UAT5): AEON issues parallel tool-call bursts
        # (5+ simultaneous searches) that exhaust KV cache and trigger mid-stream
        # eviction. AEON's training covers CVEs/ATT&CK well enough without live search.
        "mlx_model_hint": "mlx-community/Qwen3.6-27B-AEON-Ultimate-Uncensored-BF16-mlx-4Bit",
        "mlx_chat_template_kwargs": {"enable_thinking": False},
        "tools": [
            "classify_vulnerability",
            "execute_python",
            "execute_bash",
            "kb_search",
            "kb_list",
        ],
    },
    "auto-redteam": {
        "name": "🔴 Portal Red Team",
        "description": "Offensive security, penetration testing, exploit research",
        "model_hint": "baronllm:q6_k",
        # V5 bench: same GLM defect as auto-security. Promoted to AEON-4Bit.
        # Thinking disabled (same reason as auto-security — direct content output).
        # web_search intentionally excluded — same parallel-burst eviction risk as
        # auto-security. Redteam work is reasoning-heavy, not search-heavy.
        "mlx_model_hint": "mlx-community/Qwen3.6-27B-AEON-Ultimate-Uncensored-BF16-mlx-4Bit",
        "mlx_chat_template_kwargs": {"enable_thinking": False},
        "tools": ["execute_python", "execute_bash", "execute_nodejs", "classify_vulnerability"],
    },
    "auto-blueteam": {
        "name": "🔵 Portal Blue Team",
        "description": "Defensive security, incident response, threat hunting",
        "model_hint": "lily-cybersecurity:7b-q4_k_m",
        # Foundation-Sec-8B-Reasoning is the MLX primary for blue-team work:
        # purpose-trained on cybersec corpus + RLVR, native <think> reasoning,
        # strong on CVE→CWE, MITRE ATT&CK, SOC triage, compliance evidence.
        # lily-cybersecurity remains the Ollama fallback when MLX is occupied.
        # NOTE: <think> is multi-token text in Llama-3.1 vocab (not a single token),
        # so mlx_lm.server's has_thinking=False — reasoning output goes into content,
        # not reasoning_content. This is intentional: the reasoning chain IS the
        # analytical value for defenders. No mlx_chat_template_kwargs suppress needed.
        "mlx_model_hint": "foundation-ai/Foundation-Sec-8B-Reasoning-4bit-mlx",
        "emits_reasoning": True,
        "tools": ["execute_python", "classify_vulnerability"],
    },
    "tools-specialist": {
        "name": "🔧 Portal Tool Composer",
        "description": "Structured function/API calling via ToolACE-2.5 (purpose-trained, BFCL-topping). Use for tasks that require composing multiple tool calls in sequence.",
        "model_hint": None,
        "mlx_model_hint": "team-ace/ToolACE-2.5-Llama-3.1-8B-4bit-mlx",
        "mlx_only": True,
        "max_concurrent": 1,
        # Tool names must match registered MCP function names (not MCP server IDs).
        # memory MCP exposes: remember, recall. execution MCP exposes: execute_python.
        "tools": ["execute_python", "remember", "recall"],
    },
    "auto-creative": {
        "name": "✍️  Portal Creative Writer",
        "description": "Creative writing, storytelling, content generation",
        # Ollama dolphin-llama3:8b primary — fast, uncensored, creative-tuned.
        # MLX removed from cascade (backends.yaml): Gemma 4 VLM is a thinking model
        # (10-15 min reasoning phase) — wrong tool for proofreading and creative writing.
        "model_hint": "dolphin-llama3:8b",
        "tools": [],
    },
    "auto-reasoning": {
        "name": "🧠 Portal Deep Reasoner",
        "description": "Complex analysis, research synthesis, step-by-step reasoning",
        "model_hint": "deepseek-r1:32b-q4_k_m",
        "mlx_model_hint": "Jackrong/MLX-Qwopus3.5-27B-v3-8bit",
        # Thinking model: Qwopus3.5 spends 8-12K tok on reasoning before content.
        # 16384 was insufficient — truncated mid-answer. Raised to 32768.
        "predict_limit": 32768,
        "emits_reasoning": True,
        "tools": [],
    },
    "auto-documents": {
        "name": "📄 Portal Document Builder",
        "description": "Create Word, Excel, PowerPoint via MCP tools; diarized transcription",
        "model_hint": "huihui_ai/qwen3.5-abliterated:9b",
        "mlx_model_hint": "huihui-ai/Huihui-Qwen3.5-9B-abliterated-mlx-4bit",
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
        # Previous hint (Qwen3.5-9B) was a 9B general routing model — mismatched
        # for a workspace with emits_reasoning+predict_limit (those apply to the
        # Ollama tongyi fallback). Promoted to gemma-4-26b-a4b-it-4bit (VLM,
        # thinking, 256K ctx, ~23 TPS) — same model as auto-vision primary,
        # confirmed working on Apple Silicon.
        "mlx_model_hint": "mlx-community/gemma-4-26b-a4b-it-4bit",
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
        # V5 bench: gemma-4-31b-it-4bit at 3.5 t/s → gemma-4-26b-a4b-it-4bit at
        # 23.4 t/s (6.7× speedup, 13GB vs 18GB, Apache 2.0, smoke PASS). Same
        # Gemma 4 family, MoE architecture serves vision + audio identically.
        "mlx_model_hint": "mlx-community/gemma-4-26b-a4b-it-4bit",
        # Gemma-4 is a thinking model; vision description tasks don't need reasoning traces.
        "mlx_chat_template_kwargs": {"enable_thinking": False},
        "tools": ["transcribe_audio"],
    },
    "auto-data": {
        "name": "📊 Portal Data Analyst",
        "description": "Data analysis, statistics, visualization guidance",
        "model_hint": "deepseek-r1:32b-q4_k_m",
        # Switched from 8-bit (34GB, needs 44GB) to 4-bit (18GB, needs 28GB).
        # The 8-bit version was rejected by admission control when Ollama models
        # occupied memory (~18-20GB), leaving only 37-38GB available (6GB short).
        # The 4-bit abliterated version fits in 28GB — always clears on this host.
        "mlx_model_hint": "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit",
        # Thinking model: DeepSeek-R1 spends 10-16K tok on reasoning before
        # content. 16384 was insufficient — truncated mid-answer (P-DA05 UAT).
        # Raised to 32768 so reasoning + full derivation both fit.
        "predict_limit": 32768,
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
        # V5 bench: Jackrong 35B-A3B unbenched. Promoted to granite-4.1-30b-mxfp4
        # (IBM, 7.8 t/s, 15GB, smoke PASS) — purpose-built for GRC compliance
        # workflows, Apache 2.0, ISO-certified training data, BFCL V3 73.7.
        "mlx_model_hint": "mlx-community/granite-4.1-30b-mxfp4",
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
        # qwen3.5-abliterated:9b is in the general group (auto-mistral routing
        # was [mlx, reasoning, general] but reasoning was removed because deepseek-r1
        # exhausts its thinking budget on strategy tasks → empty responses).
        "model_hint": "huihui_ai/qwen3.5-abliterated:9b",
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
        # Raised from 16384: RL reasoning traces consume 8-12K tokens before code begins;
        # 16384 left insufficient budget for a complete 6-8K token game implementation.
        "predict_limit": 32768,
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
        "description": "Benchmark: GLM-4.7-Flash-4bit (MLX, Zhiyu AI — distinct Chinese research lineage, ~15GB, 59.2% SWE-bench)",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/GLM-4.7-Flash-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-gptoss": {
        "name": "🔬 Bench · GPT-OSS-20B",
        "description": "Benchmark: gpt-oss:20b (Ollama, OpenAI open-weight MoE, ~12GB, o3-mini level — configurable thinking depth)",
        "model_hint": "gpt-oss:20b",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-laguna": {
        "name": "🔬 Bench · Laguna-XS.2 (Poolside)",
        "description": "Benchmark: Laguna-XS.2-4bit (MLX, Poolside AI, 33B-A3B MoE, ~18.8GB, 68.2% SWE-bench Verified, interleaved reasoning)",
        "model_hint": "qwen3-coder:30b",
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
        "predict_limit": 8192,
        "tools": [],
        "max_concurrent": 1,
    },
    # ── V6 candidate benches (TASK_MODEL_REFRESH_V6) ────────────────────────
    "bench-qwen36-27b": {
        "name": "🔬 Bench · Qwen3.6-27B (Alibaba)",
        "description": (
            "Benchmark: mlx-community/Qwen3.6-27B-4bit (MLX, Alibaba Apr 2026, dense 27B + "
            "vision encoder, ~16GB, 262K ctx, Apache 2.0). Official mlx-community convert. "
            "SWE-bench Verified 73.4%. Fallback: froggeric/Qwen3.6-27B-MLX-4bit "
            "(pre-release, still in backends.yaml catalog, chat templates fixed)."
        ),
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/Qwen3.6-27B-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-qwen36-27b-mtp": {
        "name": "🔬 Bench · Qwen3.6-27B MTP (Alibaba + MTPLX)",
        "description": (
            "Benchmark: Youssofal/Qwen3.6-27B-MTPLX-Optimized-Speed (MLX-native MTP "
            "speculative decoding, ~18GB, ~2.24x vendor claim, lossless at temp 0). "
            "BENCH-ONLY — MTP candidate for TASK_MODEL_REFRESH_V8 A/B. "
            "No-MTP baseline: mlx-community/Qwen3.6-27B-4bit measured 12.4 TPS; "
            "MTP target ~27-32 TPS. Requires MTPLX runtime."
        ),
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "Youssofal/Qwen3.6-27B-MTPLX-Optimized-Speed",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-qwen36-35b-a3b": {
        "name": "🔬 Bench · Qwen3.6-35B-A3B (Alibaba MoE)",
        "description": (
            "Benchmark: mlx-community/Qwen3.6-35B-A3B-4bit (MLX, Alibaba Apr 2026, "
            "35B total / 3B active MoE, ~20GB, 262K ctx). Alibaba positioning: "
            "'Agentic Coding Power, Now Open to All.' Self-reported SWE-bench "
            "Verified 73.4%, AIME26 92.7%, Terminal-Bench 2.0 51.5%."
        ),
        "model_hint": "huihui_ai/Qwen3.6-abliterated:27b",
        "mlx_model_hint": "mlx-community/Qwen3.6-35B-A3B-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-omnicoder2": {
        "name": "🔬 Bench · OmniCoder-2-9B",
        "description": (
            "Benchmark: omnicoder2:9b-q4_k_m (Ollama, Qwen3.5-9B "
            "base SFT on 425K agentic trajectories from Claude Opus 4.6 / GPT-5.4 / "
            "Codex / Gemini 3.1 Pro). Apache 2.0, ~5.7GB. v2 fixes v1's repetition "
            "loops + bloated thinking + agentic-loop instability. Ollama only — MLX "
            "path deferred until mlx-community/OmniCoder-2-9B-* is published or "
            "self-converted from safetensors."
        ),
        "model_hint": "omnicoder2:9b-q4_k_m",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-negentropy": {
        "name": "🔬 Bench · Negentropy-9B (Jackrong)",
        "description": (
            "Benchmark: Jackrong/Negentropy-claude-opus-4.7-9B-6bit (MLX, Qwen3.5-9B "
            "base, trace-inversion methodology — Trace-Inverter-4B reconstructs full "
            "CoT from Claude Opus compressed reasoning bubbles, then SFT on reconstructed "
            "traces). Apache 2.0, ~7GB. Lineage overlap with existing auto-reasoning "
            "primary (MLX-Qwopus3.5-27B-v3-8bit, same author). Card-acknowledged: "
            "'logic-style hallucinations' possible — unsuited for compliance/NERC CIP work."
        ),
        "model_hint": "deepseek-r1:32b-q4_k_m",
        "mlx_model_hint": "Jackrong/Negentropy-claude-opus-4.7-9B-6bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": [],
    },
    "bench-olmo3-32b": {
        "name": "🔬 Bench · Olmo-3-32B (Allen AI)",
        "description": (
            "Benchmark: mlx-community/Olmo-3-1125-32B-4bit (MLX, Allen AI dense 32B, "
            "~17GB, Apache 2.0, NOT Qwen lineage). V5 Pareto winner for auto-reasoning "
            "candidates (8.6 TPS, smoke PASS). supports_tools=false per V5 catalog."
        ),
        "model_hint": "huihui_ai/tongyi-deepresearch-abliterated",
        "mlx_model_hint": "mlx-community/Olmo-3-1125-32B-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 16384,
        "tools": [],
    },
    # ── May 2026 additions (TASK_BENCH_COVERAGE_V1) ──────────────────────────
    "bench-nemotron-omni": {
        "name": "🔬 Bench · Nemotron-3-Nano-Omni (NVIDIA MoE)",
        "description": (
            "Benchmark: mlx-community/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-mxfp4 "
            "(MLX, NVIDIA Apr 2026, 30B MoE / 3B active, ~15GB, is_vlm=True via mlx-vlm 0.4.5). "
            "Omni-modal: text + image + video + audio. MMLongBench-Doc 57.5, OCRBenchV2 65.8, "
            "VoiceBench 89.4. NVIDIA Open Model Agreement (commercial use permitted). "
            "BENCH-ONLY — promotion gated on TASK_NEMOTRON_OMNI_PROMOTE_V1."
        ),
        "model_hint": "llama3.3:70b-q4_k_m",
        "mlx_model_hint": "mlx-community/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-mxfp4",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    # ── V7 adds (PHASE_PLAN_MODEL_REFRESH_V7_V2) ─────────────────────────────
    "bench-olmocr2": {
        "name": "🔬 Bench · olmOCR-2 (Allen AI)",
        "description": "Benchmark: olmOCR-2-7B-1025-5bit (MLX, Allen AI, 7B Qwen2.5-VL base, RLVR document OCR, ~5GB). Strengths: math formulas, tables, multi-column layouts, markdown-clean output.",
        "model_hint": None,
        "mlx_model_hint": "mlx-community/olmOCR-2-7B-1025-5bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
        "emits_reasoning": False,
    },
    "bench-nanonets-ocr2": {
        "name": "🔬 Bench · Nanonets-OCR2 (Nanonets)",
        "description": "Benchmark: Nanonets-OCR2-3B-4bit (MLX, Nanonets, Qwen2.5-VL-3B base, ~2GB). Strengths: pdf2markdown structure, LaTeX equations, semantic image tags, tables (HTML/markdown), signatures/watermarks/checkboxes. Pairs with bench-olmocr2.",
        "model_hint": None,
        "mlx_model_hint": "mlx-community/Nanonets-OCR2-3B-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
        "emits_reasoning": False,
    },
    "bench-lfm2-moe": {
        "name": "🔬 Bench · LFM2-8B-A1B (Liquid AI)",
        "description": "Benchmark: LFM2-8B-A1B-8bit (MLX, Liquid AI, 8.3B/1.5B-active MoE, hybrid Liquid arch — NON-TRANSFORMER, ~8GB). Scope per Liquid AI: agentic / data-extraction / RAG / creative / multi-turn. NOT for code or knowledge. Lineage diversification value.",
        "model_hint": None,
        "mlx_model_hint": "mlx-community/LFM2-8B-A1B-8bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
        "emits_reasoning": False,
    },
    "bench-foundation-sec": {
        "name": "🔬 Bench · Foundation-Sec (Cisco)",
        "description": "Benchmark: Foundation-Sec-8B-Reasoning-4bit-mlx (locally converted, Cisco, Llama-3.1-8B base + cybersec corpus + RLVR, ~4.5GB). Native <think> reasoning. Defender-side: CVE→CWE, MITRE ATT&CK, SOC triage, compliance.",
        "model_hint": None,
        "mlx_model_hint": "foundation-ai/Foundation-Sec-8B-Reasoning-4bit-mlx",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
        "emits_reasoning": True,
    },
    "bench-toolace25": {
        "name": "🔬 Bench · ToolACE-2.5 (Team-ACE)",
        "description": "Benchmark: ToolACE-2.5-Llama-3.1-8B-4bit-mlx (locally converted, Team-ACE, LLaMA-3.1-8B + ToolACE synthetic data, ~4.5GB, BFCL-topping). Purpose-trained for tool-calling accuracy. Expects ToolACE-style system prompt with [func(arg=val)] format.",
        "model_hint": None,
        "mlx_model_hint": "team-ace/ToolACE-2.5-Llama-3.1-8B-4bit-mlx",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": ["filesystem", "memory", "time"],
        "emits_reasoning": False,
    },
    # ── V7 catalog refresh (TASK_MODEL_REFRESH_V7) ────────────────────────────
    "bench-apriel-nemotron": {
        "name": "🔬 Bench · Apriel-Nemotron-15B-Thinker",
        "description": "Benchmark: Apriel-Nemotron-15B-Thinker-8bit (MLX, ServiceNow+NVIDIA, dense 15B reasoning, native <think>, MIT, ~16GB)",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "mlx-community/Apriel-Nemotron-15B-Thinker-8bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
    },
    "bench-voxtral-realtime": {
        "name": "🔬 Bench · Voxtral Realtime ASR",
        "description": "Benchmark: Voxtral-Mini-4B-Realtime-2602-4bit (MLX, Mistral, streaming ASR ~570ms TTFT, 13 languages, ~3GB)",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "mlx-community/Voxtral-Mini-4B-Realtime-2602-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
    },
    "bench-voxtral-tts": {
        "name": "🔬 Bench · Voxtral TTS (4B)",
        "description": "Benchmark: Voxtral-4B-TTS-2603-mlx-6bit (MLX, Mistral, 20 voices x 9 languages, ~4GB)",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "mlx-community/Voxtral-4B-TTS-2603-mlx-6bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
    },
    "bench-granite-speech": {
        "name": "🔬 Bench · Granite Speech 4.1 2B",
        "description": "Benchmark: granite-speech-4.1-2b (MLX, IBM, #1 OpenASR, native keyword biasing, EN/FR/DE/ES/PT/JA, ~4GB)",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "mlx-community/granite-speech-4.1-2b",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
    },
    "bench-qwen36-27b-ud": {
        "name": "🔬 Bench · Qwen3.6-27B (Unsloth UD)",
        "description": "Benchmark: unsloth/Qwen3.6-27B-UD-MLX-4bit (Alibaba+Unsloth Dynamic 2.0, dense 27B, ~16GB, head-to-head vs stock 4-bit)",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "unsloth/Qwen3.6-27B-UD-MLX-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
    },
    "bench-qwen36-35b-a3b-ud": {
        "name": "🔬 Bench · Qwen3.6-35B-A3B (Unsloth UD)",
        "description": "Benchmark: unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit (Alibaba+Unsloth Dynamic 2.0, MoE 3B active, ~20GB)",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "unsloth/Qwen3.6-35B-A3B-UD-MLX-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "tools": [],
    },
    # ── TASK_QUANT_TRUEUP_V1: optimized-quant + uncensored-refresh bench candidates ──
    "bench-qwen36-35b-a3b-dwq": {
        "name": "🔬 Bench · Qwen3.6-35B-A3B (DWQ)",
        "description": "Benchmark: mlx-community/Qwen3.6-35B-A3B-4bit-DWQ (distillation-aware 4-bit MoE, ~20GB), pairs against plain RTN 4-bit",
        "model_hint": "huihui_ai/Qwen3.6-abliterated:27b",
        "mlx_model_hint": "mlx-community/Qwen3.6-35B-A3B-4bit-DWQ",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-qwen36-27b-optiq": {
        "name": "🔬 Bench · Qwen3.6-27B (OptiQ)",
        "description": "Benchmark: mlx-community/Qwen3.6-27B-OptiQ-4bit (sensitivity-aware mixed 4-bit, ~16GB), pairs against plain 4-bit",
        "model_hint": "qwen3-coder:30b",
        "mlx_model_hint": "mlx-community/Qwen3.6-27B-OptiQ-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-gemma4-26b-optiq": {
        "name": "🔬 Bench · Gemma-4-26B-A4B (OptiQ)",
        "description": "Benchmark: mlx-community/gemma-4-26B-A4B-it-OptiQ-4bit (sensitivity-aware mixed 4-bit MoE, ~13GB), pairs against auto-daily plain. fp16 KV only (A4).",
        "model_hint": "dolphin-llama3:8b",
        "mlx_model_hint": "mlx-community/gemma-4-26B-A4B-it-OptiQ-4bit",
        "mlx_only": True,
        "max_concurrent": 1,
        "mlx_chat_template_kwargs": {"enable_thinking": False},
        "tools": [],
    },
    "bench-huihui-qwen36-27b": {
        "name": "🔬 Bench · Huihui-Qwen3.6-27B (Abliterated)",
        "description": "Benchmark: nabi-chan/Huihui-Qwen3.6-27B-abliterated-MLX-4bit (dense 27B abliterated, ~16GB), uncensored refresh candidate vs Qwen3.5-9B",
        "model_hint": "huihui_ai/qwen3.5-abliterated:9b",
        "mlx_model_hint": "nabi-chan/Huihui-Qwen3.6-27B-abliterated-MLX-4bit",
        "predict_limit": 8192,
        "tools": [],
        "max_concurrent": 1,
    },
    "bench-huihui-qwen36-35b-a3b": {
        "name": "🔬 Bench · Huihui-Qwen3.6-35B-A3B (Abliterated)",
        "description": "Benchmark: vanch007/Huihui-Qwen3.6-35B-A3B-abliterated-mlx-4bit (MoE 3B active abliterated, ~20GB), uncensored speed-play vs Qwen3.5-9B",
        "model_hint": "huihui_ai/qwen3.5-abliterated:9b",
        "mlx_model_hint": "vanch007/Huihui-Qwen3.6-35B-A3B-abliterated-mlx-4bit",
        "predict_limit": 8192,
        "tools": [],
        "max_concurrent": 1,
    },
}

# ── Tool-call helpers (M2) ──────────────────────────────────────────────────

# Max iterations of the streaming tool-call loop before the pipeline gives up
# and returns whatever the model has so far. Env-overridable. Consumed in
# router_pipe._stream_with_tool_loop_impl.
MAX_TOOL_HOPS = int(os.environ.get("MAX_TOOL_HOPS", "10"))


def _workspace_tools(workspace_id: str) -> list[str]:
    """Return the default tool whitelist for ``workspace_id``.

    The unknown-workspace path returns ``[]`` rather than raising, so a
    request referencing a since-removed workspace still serves — just
    without any tools advertised to the model.

    Used directly by ``router_pipe.py`` (re-exported there for tests
    and external callers; see the ``noqa: F401`` at line 529) and
    indirectly via ``_resolve_persona_tools``.

    Args:
        workspace_id: A ``WORKSPACES`` key. Unknown ids return ``[]``.

    Returns:
        Tool names from the workspace's ``tools`` field, or ``[]``.
    """
    return WORKSPACES.get(workspace_id, {}).get("tools", [])


def _resolve_persona_tools(persona: dict, workspace_id: str) -> list[str]:
    """Resolve the effective tool list for one persona × workspace pair.

    This is the **least-privilege policy gate** for tool calling. The
    workspace declares a default "what tools are reasonable here"; the
    persona refines it per the YAML's ``tools_allow``/``tools_deny``
    fields. Resolution rules:

    1. If ``persona.tools_allow`` is **non-empty**, it **replaces** the
       workspace default entirely (not "adds to"). This is intentional:
       a persona can declare a strict subset of the workspace's tools.
    2. ``persona.tools_deny`` then strips anything from the result.
    3. If both are absent or empty, the workspace's ``tools`` field is
       used unchanged.

    Edge case worth knowing: ``tools_allow: []`` in YAML evaluates to
    an empty set, which is falsy, so ``persona_allow or workspace_tools``
    falls through to the workspace default. A persona that wants
    **no tools at all** cannot express it via empty ``tools_allow:`` —
    it must list every workspace-default tool in ``tools_deny:``.
    (This is a known footgun; not addressed in this PR.)

    Args:
        persona: The persona YAML dict from ``_PERSONA_MAP``. An empty
            dict (the standard fallback for unknown personas) yields
            the workspace default unchanged.
        workspace_id: Workspace key for the default fallback; unknown
            ids contribute ``[]`` as the base.

    Returns:
        Sorted, deduplicated tool names. Sorted alphabetically for
        determinism in caching, tests, and logs; downstream
        ``tool_registry.get_openai_tools`` preserves whatever order it
        receives.
    """
    workspace_tools = set(_workspace_tools(workspace_id))
    persona_allow = set(persona.get("tools_allow", []) or [])
    persona_deny = set(persona.get("tools_deny", []) or [])

    effective = persona_allow or workspace_tools
    effective = effective - persona_deny
    return sorted(effective)


def _resolve_persona_browser_policy(persona: dict) -> dict:
    """Return the persona's browser policy dict with defaults applied.

    **Currently has no callers in the active codebase.** The intended
    consumer is the Playwright-backed browser MCP at port 8923, which
    expects allowlist / blocklist / profile / credential-fill policy
    on a per-persona basis (see ``portal_mcp/browser/browser_mcp.py``
    for the corresponding enforcement side). The wiring that would
    pass this through the pipeline to that MCP is not present at
    HEAD. Persona YAMLs do declare ``browser_policy:`` blocks, so the
    persona-side data shape is in place; only the request-time
    plumbing is missing.

    Treat as documentation of the intended shape until the wiring
    lands. Do not delete: removing it would also remove the canonical
    record of what fields a persona's ``browser_policy`` may declare.

    Field defaults applied for missing keys:

    * ``allowed_domains``                — ``[]`` (open by default;
      browser MCP's own ``PLAYWRIGHT_MCP_BLOCKED_ORIGINS`` env still
      applies).
    * ``blocked_domains``                — ``[]``.
    * ``default_profile``                — ``"_isolated"``
      (ephemeral, cookies discarded).
    * ``force_credential_fill``          — ``False``.
    * ``max_navigations_per_session``    — ``50``.

    Args:
        persona: Persona YAML dict; ``persona.browser_policy`` (if
            present) is consulted, otherwise defaults are returned.

    Returns:
        A fully-populated policy dict with the five fields above.
    """
    bp = persona.get("browser_policy", {}) or {}
    return {
        "allowed_domains": bp.get("allowed_domains") or [],
        "blocked_domains": bp.get("blocked_domains") or [],
        "default_profile": bp.get("default_profile", "_isolated"),
        "force_credential_fill": bp.get("force_credential_fill", False),
        "max_navigations_per_session": bp.get("max_navigations_per_session", 50),
    }
