"""Routing policy — workspace catalog, persona map, and tool whitelist resolution.

The pipeline's "what should I do?" decisions live here:

* ``WORKSPACES`` — the canonical workspace catalog. One entry per
  user-selectable workspace; each entry pins a preferred Ollama model
  (``model_hint``), per-workspace tuning knobs (``predict_limit``,
  ``context_limit``, ``max_concurrent``, ``emits_reasoning``,
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
#   tools                      Default tool-name whitelist (overridable per-persona).
#   predict_limit              Max output tokens (Ollama: num_predict).
#   context_limit              Max context window for this workspace.
#   max_concurrent             Per-workspace concurrency cap (router_pipe semaphore).
#   system_prompt_append       String appended after the persona system prompt.
#   think                      False → disable Qwen3/thinking-mode extended thinking
#                              (prevents token-budget exhaustion in <think> blocks).
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
        "model_hint": "huihui_ai/qwen3.5-abliterated:9b",
        "tools": [],
    },
    "auto-daily": {
        "name": "🪶 Portal Daily Driver",
        "description": (
            "Fast everyday assistant: chat, writing, editing, summarization, "
            "planning, light technical help. gemma4:26b-a4b-it-qat primary "
            "(Ollama, MoE 4B active, VLM, Apache 2.0, QAT near-BF16). "
            "Upgraded from q4_K_M → QAT (V8: +23% TPS, same ~15GB footprint). "
            "Daily-driver lane — escalates to specialist workspaces when needed."
        ),
        "model_hint": "gemma4:26b-a4b-it-qat",
        "predict_limit": 4096,
        "tools": [
            # Search + retrieval
            "web_search",
            "web_fetch",
            "kb_search",
            "kb_list",
            # Document read/write
            "read_pdf",
            "read_word_document",
            "read_excel",
            "create_word_document",
            "create_excel",
            "create_powerpoint",
            # Code execution
            "execute_python",
            # Memory
            "remember",
            "recall",
            # Media generation (conversational context may naturally request these)
            "generate_music",
            "transcribe_audio",
        ],
    },
    "auto-coding": {
        "name": "💻 Portal Code Expert",
        "description": "Code generation, debugging, architecture review (Qwen3-Coder-30B MoE, Ollama, 0.22s TTFT)",
        "model_hint": "qwen3-coder:30b-a3b-q4_K_M",
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
            "Agentic coding workspace for long-horizon multi-file tasks, SWE-agent-style "
            "workflows, and complex refactors. Qwen3-Coder-Next 80B/3B MoE (V8: agentic RL "
            "training on 800K executable tasks, 256K ctx, ~46GB, 20 t/s pipeline)."
        ),
        "model_hint": "qwen3-coder-next",
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
        "description": "Splunk SPL queries, YARA rules, detection search authoring, security scripting. Qwen3-Coder-Next abliterated (V8: 80B/3B MoE, 19 t/s, no refusals on offensive/security code, same quality as non-abliterated, ~46GB).",
        "model_hint": "hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M",
        "keep_alive": "10m",
        "tools": ["classify_vulnerability", "kb_search", "kb_list"],
    },
    "auto-security": {
        "name": "🔒 Portal Security Analyst",
        "description": "Security analysis, hardening, vulnerability assessment",
        "model_hint": "baronllm:q6_k",
        "keep_alive": "10m",
        "tools": [
            "web_search",
            "web_fetch",
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
        "keep_alive": "10m",
        "tools": ["execute_python", "execute_bash", "execute_nodejs", "classify_vulnerability"],
    },
    "auto-blueteam": {
        "name": "🔵 Portal Blue Team",
        "description": "Defensive security, incident response, threat hunting. Served by Foundation-Sec-8B-Reasoning (Cisco fdtn-ai, Llama-3.1-8B + cybersec corpus, native <think>). Purpose-trained defender model restored after the MLX retirement (P5-FUT-PARITY-001).",
        "model_hint": "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0",
        "emits_reasoning": True,
        "tools": ["execute_python", "classify_vulnerability"],
    },
    "auto-bigfix": {
        "name": "🩹 Portal BigFix Analyst",
        "description": (
            "HCL BigFix endpoint management and patch compliance workspace. "
            "Handles: BigFix REST API queries and response parsing, Relevance Language "
            "expressions for targeting endpoints, RQL fixlet applicability queries, "
            "patch deployment status reporting, computer property retrieval, and "
            "compliance gap analysis across managed endpoints. "
            "Model_hint pending D10 sec10-bigfix-parse probe results — "
            "will be set to the top D10 scorer from TASK_MODEL_EVAL_V9_CANDIDATES."
        ),
        "model_hint": "qwen3-coder:30b-a3b-q4_K_M",
        "tools": ["execute_python", "execute_bash", "web_search"],
    },
    "tools-specialist": {
        "name": "🔧 Portal Tool Composer",
        "description": "Structured function/API calling via Granite-4.1 8B (tool-tagged, BFCL V3 68.27). Substitutes for ToolACE-2.5 (no GGUF after MLX retirement; re-sourcing tracked in P5-FUT-PARITY-001). Use for tasks composing multiple tool calls in sequence.",
        "model_hint": "granite4.1:8b",
        "max_concurrent": 1,
        # Tool names must match registered MCP function names (not MCP server IDs).
        # memory MCP exposes: remember, recall. execution MCP exposes: execute_python.
        "tools": ["execute_python", "remember", "recall"],
    },
    "auto-creative": {
        "name": "✍️  Portal Creative Writer",
        "description": (
            "Creative writing, storytelling, content generation. "
            "Qwen3.6-35B-A3B HauhauCS uncensored (V8: 0/465 refusals, MoE 3B active, "
            "tool-capable + vision, ~22GB. Upgraded from gemma-4-heretic Q4)."
        ),
        "model_hint": "fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4",
        "tools": [],
    },
    "auto-reasoning": {
        "name": "🧠 Portal Deep Reasoner",
        "description": (
            "Complex analysis, research synthesis, step-by-step reasoning. "
            "DeepSeek R1-0528-Qwen3-8B (V8: 31 t/s pipeline, AIME 2024 = Qwen3-235B at 8B, "
            "~5GB. Replaces Qwopus primary which had pull failures). "
            "deepseek-r1:32b remains reasoning group fallback for heavy tasks."
        ),
        "model_hint": "hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL",
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": [],
    },
    "auto-documents": {
        "name": "📄 Portal Document Builder",
        "description": "Create Word, Excel, PowerPoint via MCP tools; diarized transcription",
        "model_hint": "granite4.1:8b",
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
        "description": "Generate music and audio via AudioCraft/MusicGen. LFM2.5-8B-A1B hybrid (V8: fastest structured-output model in fleet, 89 t/s, unique non-transformer architecture, tool-capable, Apache 2.0).",
        # auto-music dispatches via OWUI Path 2 (server:mcp:portal_music + portal_tts).
        "model_hint": "lfm2.5:8b",
        "tools": ["transcribe_audio"],
    },
    "auto-research": {
        "name": "🔍 Portal Research Assistant",
        "description": "Web research, information synthesis, fact-checking",
        "model_hint": "huihui_ai/tongyi-deepresearch-abliterated",
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
        "description": "Image understanding, visual analysis, multimodal tasks (Qwen3-VL, Ollama)",
        "model_hint": "qwen3-vl:32b",
        "tools": ["transcribe_audio"],
    },
    "auto-data": {
        "name": "📊 Portal Data Analyst",
        "description": "Data analysis, statistics, visualization guidance",
        "model_hint": "deepseek-r1:32b-q8_0",
        "predict_limit": 32768,
        "emits_reasoning": True,
        # 35 GB q8 — keep warm for back-to-back queries but don't pin forever
        "keep_alive": "10m",
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
        "model_hint": "granite4.1:8b",
        "predict_limit": 16384,
        "emits_reasoning": False,
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
        "description": "Magistral-Small-2509 (GGUF q8_0) — Mistral training lineage, [THINK] mode, distinct failure profile from Qwen/DeepSeek reasoning models.",
        "model_hint": "hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0",
        "predict_limit": 16384,
        "emits_reasoning": True,
        # 25 GB q8 — keep warm for back-to-back queries but don't pin forever
        "keep_alive": "10m",
        # Magistral's [AVAILABLE_TOOLS] template does not trigger Ollama tool dispatch
        # (verified TV-04 + direct API test). No tools exposed — model can't call them.
        "tools": [],
    },
    "auto-math": {
        "name": "🧮 Portal Math Reasoner",
        "description": "Mathematical problem solving, proofs, calculus, algebra, statistics. Phi-4-Mini-Reasoning (V8: RL-trained math specialist, beats 7B models on AIME/MATH-500 at 3.8B, ~2.5GB, MIT).",
        "model_hint": "phi4-mini-reasoning",
        "predict_limit": 8192,
        "emits_reasoning": True,
        "tools": ["execute_python"],
    },
    "auto-phi4": {
        "name": "🧮 Portal STEM Analyst",
        "description": (
            "STEM analysis, scientific reasoning, mathematical derivations, structured "
            "problem-solving. Phi-4-reasoning-plus (V8: RL-trained 14B, ~11GB, MIT — "
            "produces chain-of-thought traces before answers; ideal for stepwise STEM work)."
        ),
        "model_hint": "phi4-reasoning:plus",
        "predict_limit": 32768,
        "emits_reasoning": True,
        "keep_alive": "10m",
        "tools": ["execute_python", "create_excel", "kb_search"],
    },
    "auto-audio": {
        "name": "🎙️  Portal Audio Analyst",
        "description": "Audio transcription, speech analysis, audio understanding. Gemma 4 12B QAT (V8: first encoder-free audio model in fleet, native audio+image+text, 256K ctx, function calling, ~7GB, Google, Apache 2.0).",
        "model_hint": "gemma4:12b-it-qat",
        "tools": ["transcribe_audio"],
    },
    # ── Coding Capability Benchmark Workspaces ───────────────────────────────
    "bench-qwen3-coder-30b": {
        "name": "🔬 Bench · Qwen3-Coder-30B",
        "description": "Benchmark: Qwen3-Coder-30B (GGUF, Ollama, Alibaba, 30B MoE 3B active)",
        "model_hint": "qwen3-coder:30b-a3b-q4_K_M",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "emits_reasoning": True,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-llama33-70b": {
        "name": "🔬 Bench · Llama-3.3-70B",
        "description": "Benchmark: Llama-3.3-70B-Instruct (GGUF, Ollama, Meta)",
        "model_hint": "llama3.3:70b-q4_k_m",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-phi4": {
        "name": "🔬 Bench · Phi-4",
        "description": "Benchmark: phi-4 (GGUF, Ollama, Microsoft, 14B, synthetic training data — distinct methodology)",
        "model_hint": "phi4:14b-q8_0",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-phi4-reasoning": {
        "name": "🔬 Bench · Phi-4-reasoning-plus",
        "description": "Benchmark: Phi-4-reasoning-plus (GGUF, Ollama, Microsoft, RL-trained — produces reasoning traces before code)",
        "model_hint": "phi4-reasoning:plus",
        "max_concurrent": 1,
        # Raised from 16384: RL reasoning traces consume 8-12K tokens before code begins;
        # 16384 left insufficient budget for a complete 6-8K token game implementation.
        "predict_limit": 32768,
        "emits_reasoning": True,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-dolphin8b": {
        "name": "🔬 Bench · Dolphin-Llama3-8B",
        "description": "Benchmark: Dolphin3.0-Llama3.1-8B (GGUF, Ollama, Cognitive Computations — fast baseline, uncensored)",
        "model_hint": "dolphin-llama3:8b",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-glm": {
        "name": "🔬 Bench · GLM-4.7-Flash",
        "description": "Benchmark: GLM-4.7-Flash (GGUF, Ollama, Zhiyu AI — distinct Chinese research lineage, 59.2% SWE-bench)",
        "model_hint": "glm-4.7-flash:Q4_K_M",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "emits_reasoning": True,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-gptoss": {
        "name": "🔬 Bench · GPT-OSS-20B",
        "description": "Benchmark: gpt-oss:20b (Ollama, OpenAI open-weight MoE, ~12GB, o3-mini level — configurable thinking depth)",
        "model_hint": "gpt-oss:20b",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "emits_reasoning": True,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-laguna": {
        "name": "🔬 Bench · Laguna-XS.2 (Poolside)",
        "description": "Benchmark: Laguna-XS.2 (GGUF, Ollama, Poolside AI, 33B-A3B MoE, 68.2% SWE-bench Verified, interleaved reasoning)",
        "model_hint": "laguna-xs.2:Q4_K_M",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "keep_alive": "5m",
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
        "keep_alive": "5m",
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
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-qwen35-abliterated": {
        "name": "🧪 Bench — Qwen3.5-9B Abliterated (huihui-ai)",
        "description": "Direct routing to huihui_ai/qwen3.5-abliterated:9b — uncensored, tool-capable AUTO primary baseline",
        "model_hint": "huihui_ai/qwen3.5-abliterated:9b",
        "predict_limit": 8192,
        "emits_reasoning": True,
        "keep_alive": "5m",
        "tools": [],
        "max_concurrent": 1,
    },
    # ── V6 candidate benches (TASK_MODEL_REFRESH_V6) ────────────────────────
    "bench-qwen36-27b": {
        "name": "🔬 Bench · Qwen3.6-27B Q8 (Alibaba)",
        "description": (
            "Benchmark: qwen3.6:27b-q8_0 (Ollama, Alibaba, dense 27B, 262K ctx, Apache 2.0, "
            "SWE-bench Verified 73.4%). High-precision quality-lane candidate + Phase-5 MTP A/B base."
        ),
        "model_hint": "qwen3.6:27b-q4_K_M",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "emits_reasoning": True,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-qwen36-27b-mtp": {
        "name": "🔬 Bench · Qwen3.6-27B MTP (Ollama speculative)",
        "description": (
            "Benchmark: portal5/qwen3.6-27b-mtp:q8_0-drafted — Qwen3.6-27B q8_0 base with "
            "mtp-q4_K_M draft (speculative decoding via DRAFT directive). "
            "Phase-5 MTP A/B vs bench-qwen36-27b (plain q8_0). "
            "Run: ./launch.sh apply-mtp-drafts to create the tag before use."
        ),
        "model_hint": "portal5/qwen3.6-27b-mtp:q8_0-drafted",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "emits_reasoning": True,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-qwen36-35b-a3b": {
        "name": "🔬 Bench · Qwen3.6-35B-A3B (Alibaba MoE)",
        "description": (
            "Benchmark: Qwen3.6-35B-A3B (GGUF, Ollama, Alibaba Apr 2026, "
            "35B total / 3B active MoE, 262K ctx). SWE-bench Verified 73.4%, AIME26 92.7%."
        ),
        "model_hint": "qwen3.6:35b-a3b-q4_K_M",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "emits_reasoning": True,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-omnicoder2": {
        "name": "🔬 Bench · OmniCoder-2-9B",
        "description": (
            "Benchmark: omnicoder2:9b-q4_k_m (Ollama, Qwen3.5-9B "
            "base SFT on 425K agentic trajectories from Claude Opus 4.6 / GPT-5.4 / "
            "Codex / Gemini 3.1 Pro). Apache 2.0, ~5.7GB. v2 fixes v1's repetition "
            "loops + bloated thinking + agentic-loop instability. Ollama-only "
            "stack (MLX inference tier retired 3a0c58e); served as "
            "omnicoder2:9b-q4_k_m."
        ),
        "model_hint": "omnicoder2:9b-q4_k_m",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-negentropy": {
        "name": "🔬 Bench · Negentropy-9B (Jackrong)",
        "description": (
            "Benchmark: Jackrong/Negentropy-claude-opus-4.7-9B (GGUF, Ollama, Qwen3.5-9B "
            "base, trace-inversion methodology). Card-acknowledged: "
            "'logic-style hallucinations' possible — unsuited for compliance/NERC CIP work."
        ),
        "model_hint": "deepseek-r1:32b-q4_k_m",
        "max_concurrent": 1,
        "predict_limit": 16384,
        "emits_reasoning": True,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-olmo3-32b": {
        "name": "🔬 Bench · Olmo-3-32B (Allen AI)",
        "description": (
            "Benchmark: Olmo-3-32B (GGUF, Ollama, Allen AI dense 32B, "
            "Apache 2.0, NOT Qwen lineage). supports_tools=false per V5 catalog."
        ),
        "model_hint": "olmo-3.1:32b-think",
        "max_concurrent": 1,
        "predict_limit": 16384,
        "keep_alive": "5m",
        "emits_reasoning": True,
        "tools": [],
    },
    # ── V7 adds (PHASE_PLAN_MODEL_REFRESH_V7_V2) ─────────────────────────────
    "bench-olmocr2": {
        "name": "🔬 Bench · olmOCR-2 (Allen AI)",
        "description": "Benchmark: olmOCR-2-7B (Allen AI, 7B Qwen2.5-VL base, RLVR document OCR). Strengths: math formulas, tables, multi-column layouts, markdown-clean output.",
        "model_hint": "qwen3-vl:32b",
        "max_concurrent": 1,
        "keep_alive": "5m",
        "tools": [],
        "emits_reasoning": False,
    },
    "bench-nanonets-ocr2": {
        "name": "🔬 Bench · Nanonets-OCR2 (Nanonets)",
        "description": "Benchmark: Nanonets-OCR2-3B (Nanonets, Qwen2.5-VL-3B base). Strengths: pdf2markdown structure, LaTeX equations, semantic image tags, tables (HTML/markdown), signatures/watermarks/checkboxes. Pairs with bench-olmocr2.",
        "model_hint": "qwen3-vl:32b",
        "max_concurrent": 1,
        "keep_alive": "5m",
        "tools": [],
        "emits_reasoning": False,
    },
    "bench-foundation-sec": {
        "name": "🔬 Bench · Foundation-Sec (Cisco)",
        "description": "Benchmark: Foundation-Sec-8B-Reasoning (Cisco fdtn-ai, first-party Q8_0 GGUF ~8.5GB, 128K ctx). Native <think>. Defender-side: CVE→CWE, MITRE ATT&CK, SOC triage, compliance. Now the auto-blueteam primary (P5-FUT-PARITY-001).",
        "model_hint": "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0",
        "max_concurrent": 1,
        "keep_alive": "5m",
        "tools": [],
        "emits_reasoning": True,
    },
    # ── V7 catalog refresh (TASK_MODEL_REFRESH_V7) ────────────────────────────
    "bench-qwen36-27b-ud": {
        "name": "🔬 Bench · Qwen3.6-27B Q4 (Unsloth UD proxy)",
        "description": (
            "Benchmark: qwen3.6:27b-q4_K_M (Ollama, dense 27B Q4). Proxy for Unsloth Dynamic "
            "2.0 UD-Q4_K_XL (not yet pulled) — establishes baseline for quant comparison "
            "when UD variant becomes available. TASK_QUANT_TRUEUP_V1."
        ),
        "model_hint": "qwen3.6:27b-q4_K_M",
        "max_concurrent": 1,
        "emits_reasoning": True,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-gemma4-26b-optiq": {
        "name": "🔬 Bench · Gemma-4-26B-A4B (OptiQ)",
        "description": "Benchmark: gemma4:26b-a4b-it-q4_K_M (GGUF, Ollama, MoE 4B active), pairs against auto-daily.",
        "model_hint": "gemma4:26b-a4b-it-q4_K_M",
        "max_concurrent": 1,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-huihui-qwen36-27b": {
        "name": "🔬 Bench · Huihui-Qwen3.6-27B (Abliterated)",
        "description": (
            "Benchmark: huihui_ai/Qwen3.6-abliterated:27b (Ollama, dense 27B abliterated, "
            "~16GB Q4). Uncensored Qwen3.6-27B — head-to-head vs stock qwen3.6:27b-q4_K_M. "
            "PROMOTE_POLICY=confirm."
        ),
        "model_hint": "huihui_ai/Qwen3.6-abliterated:27b",
        "predict_limit": 8192,
        "emits_reasoning": True,
        "keep_alive": "5m",
        "tools": [],
        "max_concurrent": 1,
    },
    # ── TASK_MODEL_FLEET_REFRESH_V2 Phase 4 adds ─────────────────────────────
    "bench-qwen36-35b-a3b-ud": {
        "name": "🔬 Bench · Qwen3.6-35B-A3B UD (Unsloth)",
        "description": (
            "Benchmark: hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL (Alibaba MoE, "
            "35B total / 3B active, ~22GB). Unsloth Dynamic 2.0 sensitivity-aware quant "
            "vs stock Q4_K_M — agentic lane candidate C1, TASK_MODEL_FLEET_REFRESH_V2."
        ),
        "model_hint": "hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "emits_reasoning": True,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-qwen36-hauhaucs": {
        "name": "🔬 Bench · Qwen3.6-35B-A3B HauhauCS (uncensored)",
        "description": (
            "Benchmark: fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4 "
            "(Ollama, MoE 3B active, ~22GB, 0/465 refusals). HauhauCS abliteration method — "
            "lowest KL-divergence vs base; vision patched; robust tool-calling at low quant."
        ),
        "model_hint": "fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "emits_reasoning": True,
        "keep_alive": "5m",
        "tools": [],
    },
    # ── Daily-driver candidate bench (gemma4:12b + phi4-mini) ──────────────
    "bench-gemma4-12b": {
        "name": "🔬 Bench · Gemma 4 12B QAT (Google)",
        "description": (
            "Benchmark: gemma4:12b-it-qat (Ollama, Google DeepMind, June 2026, Apache 2.0). "
            "12B Unified QAT — ~7GB, encoder-free audio+image+text, 256K ctx, native "
            "function calling. QAT: near-BF16 at 4-bit. PROMOTE_POLICY=confirm."
        ),
        "model_hint": "gemma4:12b-it-qat",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-phi4-mini": {
        "name": "🔬 Bench · Phi-4-Mini (Microsoft)",
        "description": (
            "Benchmark: phi4-mini (Ollama, Microsoft, Feb 2025, MIT, 3.8B, ~2.5GB Q4, 128K ctx). "
            "Synthetic-data reasoning: function calling, multilingual, math. "
            "Outperforms Llama 3.2 3B and Qwen 2.5 3B on reasoning at 3.8B. "
            "Ultra-fast daily tier candidate. PROMOTE_POLICY=confirm."
        ),
        "model_hint": "phi4-mini",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-gemma4-e4b": {
        "name": "🔬 Bench · Gemma 4 E4B (MoE 4B active)",
        "description": "Benchmark: gemma4:e4b-it-q4_K_M (~9.6GB, Google MoE, 4B active, 128K ctx, vision+thinking+tools). Daily-driver candidate.",
        "model_hint": "gemma4:e4b-it-q4_K_M",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "keep_alive": "5m",
        "tools": [],
    },
    # ── June 2026 additions (TASK_MODEL_REFRESH_V8) ──────────────────────────
    "bench-gemma4-e2b": {
        "name": "🔬 Bench · Gemma 4 E2B QAT (Google)",
        "description": (
            "Benchmark: gemma4:e2b-it-qat (Ollama, Google DeepMind, Apache 2.0). "
            "Effective 2B QAT — ~3GB, audio+image+video+text, thinking, 128K ctx. "
            "Fastest TPS candidate in fleet. QAT: near-BF16 at 4-bit. PROMOTE_POLICY=confirm."
        ),
        "model_hint": "gemma4:e2b-it-qat",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-gemma4-e4b-qat": {
        "name": "🔬 Bench · Gemma 4 E4B QAT (Google)",
        "description": (
            "Benchmark: gemma4:e4b-it-qat (Ollama, Google DeepMind, Apache 2.0). "
            "Effective 4B QAT — ~5GB, audio+image+video+text, thinking, 128K ctx. "
            "QAT quality upgrade vs production gemma4:e4b-it-q4_K_M. PROMOTE_POLICY=confirm."
        ),
        "model_hint": "gemma4:e4b-it-qat",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-gemma4-26b-qat": {
        "name": "🔬 Bench · Gemma 4 26B-A4B QAT (Google)",
        "description": (
            "Benchmark: gemma4:26b-a4b-it-qat (Ollama, Google DeepMind, June 2026, Apache 2.0). "
            "26B-A4B MoE QAT — ~15GB, vision+text, 256K ctx. "
            "QAT quality comparison vs production gemma4:26b-a4b-it-q4_K_M at same memory. "
            "If bench shows quality gain at ≥20 TPS, promotion task can swap the primary. "
            "PROMOTE_POLICY=confirm."
        ),
        "model_hint": "gemma4:26b-a4b-it-qat",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-gemma4-31b-qat": {
        "name": "🔬 Bench · Gemma 4 31B Dense QAT (Google)",
        "description": (
            "Benchmark: gemma4:31b-it-qat (Ollama, Google DeepMind, June 2026, Apache 2.0). "
            "31B Dense QAT — ~18GB, vision+text, 256K ctx. "
            "QAT quality comparison vs production gemma4:31b-it-q4_K_M. PROMOTE_POLICY=confirm."
        ),
        "model_hint": "gemma4:31b-it-qat",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-gemma4-31b-crack": {
        "name": "🔬 Bench · Gemma 4 31B JANG-4M-CRACK (dealignai)",
        "description": (
            "Benchmark: hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:"
            "gemma-4-31b-jang-crack-Q4_K_M.gguf "
            "(douyamv quant of dealignai/Gemma-4-31B-JANG_4M-CRACK, Gemma license, "
            "31B dense, ~20GB Q4_K_M). "
            "JANG_4M-CRACK: abliterated + uncensored Gemma 4 31B fine-tune with 4M context. "
            "Vision+text. Head-to-head vs bench-gemma4-31b-qat (refusals baseline) "
            "and bench-huihui-qwen36-27b (abliterated comparison). "
            "PROBE RESULT (2026-06-16): 20/23 — D8 5/5 (matches laguna/qwen36-27b), "
            "D10 9/10 (matches qwen3-coder-30b). Strong promotion candidate for "
            "security/PowerShell workspaces. 2 unexplained 500s (D6, D9 py4) likely "
            "empty-content on refusal-adjacent prompts. "
            "supports_tools=false until --audit-tools verification. PROMOTE_POLICY=confirm."
        ),
        "model_hint": (
            "hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:"
            "gemma-4-31b-jang-crack-Q4_K_M.gguf"
        ),
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-phi4-mini-reasoning": {
        "name": "🔬 Bench · Phi-4-Mini-Reasoning (Microsoft)",
        "description": (
            "Benchmark: phi4-mini-reasoning (Ollama, Microsoft, MIT, 3.8B, ~2.5GB Q4, 128K ctx). "
            "RL-trained math/logic specialist. Beats 7B models on AIME/MATH-500/GPQA. "
            "PROMOTE_POLICY=confirm."
        ),
        "model_hint": "phi4-mini-reasoning",
        "max_concurrent": 1,
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": [],
    },
    "bench-lfm25-8b": {
        "name": "🔬 Bench · LFM2.5-8B-A1B (Liquid AI)",
        "description": (
            "Benchmark: lfm2.5:8b (Ollama, Liquid AI, June 2026, Apache 2.0, ~5GB Q4, 128K ctx). "
            "Hybrid gated-convolution + attention MoE — ONLY non-transformer model in fleet. "
            "8.3B total / 1.5B active. Fastest in class on CPU. "
            "Strengths: agentic workflows, tool use, structured outputs, multilingual. "
            "Weaknesses: heavy code generation, knowledge-only tasks. PROMOTE_POLICY=confirm."
        ),
        "model_hint": "lfm2.5:8b",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-devstral-small-2": {
        "name": "🔬 Bench · Devstral Small 2 (Mistral)",
        "description": (
            "Benchmark: devstral-small-2 (Ollama, Mistral AI + All Hands AI, Dec 2025, "
            "Apache 2.0, 24B, ~14GB Q4). Devstral V2: 256K ctx, vision added, improved "
            "SWE-bench vs devstral:24b (V1). PROMOTE_POLICY=confirm."
        ),
        "model_hint": "devstral-small-2",
        "max_concurrent": 1,
        "predict_limit": 16384,
        "tools": [],
    },
    "bench-mistral-small32": {
        "name": "🔬 Bench · Mistral Small 3.2 (Mistral)",
        "description": (
            "Benchmark: mistral-small3.2:24b (Ollama, Mistral AI, June 2025, Apache 2.0, "
            "24B, ~14GB Q4). Improved function calling and instruction following over Small 3.1. "
            "auto-mistral lane candidate. PROMOTE_POLICY=confirm."
        ),
        "model_hint": "mistral-small3.2:24b",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-r1-0528-qwen3-8b": {
        "name": "🔬 Bench · DeepSeek R1-0528-Qwen3-8B (DeepSeek)",
        "description": (
            "Benchmark: hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL "
            "(Unsloth/DeepSeek, MIT, 8B Qwen3 base, ~5GB Q4_K_XL, May 2026). "
            "R1-0528 chain-of-thought distilled into Qwen3-8B. "
            "Matches Qwen3-235B on AIME 2024 at 8B parameters. "
            "Complements existing deepseek-r1:32b — smaller/faster reasoning tier. "
            "PROMOTE_POLICY=confirm."
        ),
        "model_hint": "hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL",
        "max_concurrent": 1,
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": [],
    },
    "bench-harness1": {
        "name": "🔬 Bench · Harness-1 (search agent, gpt-oss-20B base)",
        "description": (
            "Benchmark: hf.co/ijohn07/harness-1-Q4_K_M-GGUF:Q4_K_M "
            "(June 2026, Apache 2.0, 20B gpt-oss fine-tune, ~12GB Q4_K_M). "
            "RL-trained search agent with state-externalizing harness methodology. "
            "NOTE: Full harness capability (Chroma vector DB + external state) not available "
            "in Portal 5 pipeline. Standalone bench measures search-tuned gpt-oss-20B quality. "
            "auto-research lane candidate. PROMOTE_POLICY=confirm."
        ),
        "model_hint": "hf.co/ijohn07/harness-1-Q4_K_M-GGUF:Q4_K_M",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-nex-n2-mini": {
        "name": "🔬 Bench · Nex-N2-mini (Nex AGI)",
        "description": (
            "Benchmark: hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M "
            "(June 2026, Apache 2.0, 35B total / 3B active MoE, ~22GB UD-Q4_K_M). "
            "Post-trained on Qwen3.5-35B-A3B-Base for agentic coding, tool use, reasoning. "
            "Multimodal (image+text). imatrix community GGUF by sjakek. "
            "Terminal-Bench 2.1 score: 60.7. PROMOTE_POLICY=confirm."
        ),
        "model_hint": "hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M",
        "max_concurrent": 1,
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": [],
    },
    "bench-qwen3-coder-next": {
        "name": "🔬 Bench · Qwen3-Coder-Next 80B (Alibaba)",
        "description": (
            "Benchmark: qwen3-coder-next (Ollama, Alibaba Feb 2026, Apache 2.0). "
            "80B total / 3B active MoE. Hybrid architecture (Gated DeltaNet + MoE). "
            "Non-reasoning for fast code responses. 256K ctx. ~46GB Q4, fits 64GB. "
            "Agentic training: 800K executable tasks + RL. "
            "PROMOTE_POLICY=confirm."
        ),
        "model_hint": "qwen3-coder-next",
        "max_concurrent": 1,
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": [],
    },
    # ── V8 uncensored candidates (TASK_MODEL_REFRESH_V8_UNCENSORED) ───────────
    "bench-lfm25-8b-uncensored": {
        "name": "🔬 Bench · LFM2.5-8B Uncensored (Gaston)",
        "description": (
            "Benchmark: hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M "
            "(gaston-parravicini, imatrix Q4_K_M, ~5GB, abliterated LiquidAI/LFM2.5-8B-A1B base). "
            "Head-to-head vs production lfm2.5:8b — quality delta for creative/music/agentic lanes. "
            "PROMOTE_POLICY=confirm."
        ),
        "model_hint": "hf.co/gaston-parravicini/LFM2.5-8B-A1B-Uncensored-Gaston-GGUF:Q4_K_M",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-r1-0528-abliterated": {
        "name": "🔬 Bench · R1-0528-Qwen3-8B Abliterated (Josiefied)",
        "description": (
            "Benchmark: hf.co/mradermacher/Josiefied-DeepSeek-R1-0528-Qwen3-8B-abliterated-v1-GGUF:Q4_K_M "
            "(mradermacher packaging of Goekdeniz-Guelmez Josiefied abliteration, ~5GB Q4_K_M). "
            "Abliterated R1-0528-Qwen3-8B — chain-of-thought reasoning without refusals. "
            "Candidate for auto-redteam / security reasoning lane. "
            "Head-to-head vs non-abliterated bench-r1-0528-qwen3-8b. PROMOTE_POLICY=confirm."
        ),
        "model_hint": "hf.co/mradermacher/Josiefied-DeepSeek-R1-0528-Qwen3-8B-abliterated-v1-GGUF:Q4_K_M",
        "max_concurrent": 1,
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": [],
    },
    "bench-qwen3-coder-next-abliterated": {
        "name": "🔬 Bench · Qwen3-Coder-Next Abliterated (huihui-ai/bartowski)",
        "description": (
            "Benchmark: hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M "
            "(bartowski, 74k downloads, huihui-ai abliteration of Qwen/Qwen3-Coder-Next, ~46GB Q4_K_M). "
            "Abliterated Qwen3-Coder-Next — 80B/3B MoE agentic coder without refusals. "
            "Candidate for auto-agentic / auto-redteam coding lane. "
            "Head-to-head vs non-abliterated bench-qwen3-coder-next. PROMOTE_POLICY=confirm."
        ),
        "model_hint": "hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M",
        "max_concurrent": 1,
        "predict_limit": 16384,
        "emits_reasoning": True,
        "tools": [],
    },
    "bench-qwopus-coder-mtp": {
        "name": "🔬 Bench · Qwopus3.6-27B-Coder-MTP (Jackrong)",
        "description": (
            "Benchmark: hf.co/Jackrong/Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf "
            "(Jackrong, Apache 2.0, June 2026, 27B dense, ~19GB Q5_K_M). "
            "Coder SFT on Qwopus3.6-27B-v2 (Qwen3.6-27B + Trace Inversion). "
            "Agentic coding, tool-use, multi-turn orchestration. "
            "SWE-bench Verified 67.0% (thinking-off). MTP embedded draft heads. "
            "Candidate for auto-coding / auto-agentic fallback if TPS >= 20 and code quality competitive. "
            "Head-to-head vs qwen3.6:27b-q4_K_M (77.2% SWE, 27B dense) and laguna-xs.2 (68.2% SWE, 33B MoE). "
            "PROMOTE_POLICY=confirm."
        ),
        "model_hint": "hf.co/Jackrong/Qwopus3.6-27B-Coder-MTP-GGUF:Qwopus3.6-27B-Coder-MTP-Q5_K_M.gguf",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "emits_reasoning": True,
        "tools": [],
    },
    "bench-gemma4-12b-coder": {
        "name": "🔬 Bench · Gemma4-12B-Coder Fable5 (yuxinlu1)",
        "description": (
            "Benchmark: hf.co/yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M "
            "(yuxinlu1, Gemma license, June 2026, 12B dense, ~6.87GB Q4_K_M). "
            "Fine-tune of Gemma 4 12B on verifiable Python CoT: "
            "Composer 2.5 real reasoning + Fable 5 synthetic second-attempt traces, "
            "both gated on test execution. Coding + reasoning specialist. 131K ctx. "
            "Candidate for auto-coding fast-path or auto-agentic secondary if TPS >= 20. "
            "Head-to-head vs portal5/gemma4-12b:q4_K_M-ctx8k (general) and omnicoder2:9b-q4_k_m. "
            "PROMOTE_POLICY=confirm."
        ),
        "model_hint": "hf.co/yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "emits_reasoning": True,
        "tools": [],
    },
    "bench-fastcontext": {
        "name": "🔬 Bench · FastContext-1.0-4B-SFT (Microsoft)",
        "description": (
            "Benchmark: hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M "
            "(Microsoft github.com/microsoft/fastcontext, mitkox GGUF quant). "
            "4B SFT model purpose-trained for long-context retrieval and reasoning: "
            "needle-in-haystack, multi-hop QA, instruction following at 32K–128K ctx. "
            "NOT a coding or tool-use model. NOT suitable as router (standard model; refusals). "
            "PROBE RESULT (2026-06-15): returns empty content for most standard chat prompts "
            "via Ollama — only activates on long-context retrieval patterns (document+question). "
            "D4 PASS (1/1), D7 2/3; all D9/D10 returned 500 (pipeline choked on empty response). "
            "NOT viable as a pipeline workspace until a correct Modelfile/prompt template is "
            "written. PROMOTE_POLICY=blocked. Revisit if Microsoft publishes a chat-tuned "
            "variant or a community Modelfile with the right system prompt format."
        ),
        "model_hint": "hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M",
        "max_concurrent": 1,
        "predict_limit": 4096,
        "tools": [],
    },
    "bench-devstral": {
        "name": "🔬 Bench · Devstral 24B (Mistral)",
        "description": (
            "Benchmark: devstral:24b (Ollama, Mistral, Apache 2.0, 24B MoE 22B active, ~14GB). "
            "State-of-the-art open-source agent model for software engineering tasks. "
            "46.8% SWE-bench Verified, #1 open-source at release (May 2025). "
            "Designed for agentic coding: multi-step tool use, file editing, repo navigation. "
            "Head-to-head vs bench-devstral-small-2 (7B MoE) and bench-qwopus-coder-mtp (27B). "
            "Candidate for auto-agentic primary if TPS competitive and quality > small variant. "
            "PROMOTE_POLICY=confirm."
        ),
        "model_hint": "devstral:24b",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "bench-magistral": {
        "name": "🔬 Bench · Magistral-Small 24B Reasoning (Mistral)",
        "description": (
            "Benchmark: hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0 "
            "(Mistral, unsloth quant, Apache 2.0, 24B MoE, ~26GB Q8_0). "
            "Mistral's reasoning-specialized variant of Mistral-Small-3. "
            "Extended chain-of-thought, competitive on MATH and coding-with-reasoning benchmarks. "
            "Head-to-head vs bench-r1-0528-abliterated (32B) and bench-qwen36-27b (27B). "
            "Candidate for auto-reasoning or auto-coding if thinking quality >= R1. "
            "PROMOTE_POLICY=confirm."
        ),
        "model_hint": "hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "emits_reasoning": True,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-apriel-nemotron": {
        "name": "🔬 Bench · Apriel-Nemotron-15B Thinker (ServiceNow/NVIDIA)",
        "description": (
            "Benchmark: hf.co/bartowski/ServiceNow-AI_Apriel-Nemotron-15b-Thinker-GGUF:"
            "ServiceNow-AI_Apriel-Nemotron-15b-Thinker-Q5_K_M.gguf "
            "(ServiceNow AI + NVIDIA, Apache 2.0, 15B dense, ~10GB Q5_K_M). "
            "Enterprise reasoning model: extended thinking via chain-of-thought, "
            "strong on code, math, and multi-step problem-solving. "
            "Smaller footprint than 27B class — candidate for auto-reasoning fast-path. "
            "Head-to-head vs bench-r1-0528-qwen3-8b (8B) and bench-granite41-30b (32B). "
            "PROMOTE_POLICY=confirm."
        ),
        "model_hint": (
            "hf.co/bartowski/ServiceNow-AI_Apriel-Nemotron-15b-Thinker-GGUF:"
            "ServiceNow-AI_Apriel-Nemotron-15b-Thinker-Q5_K_M.gguf"
        ),
        "max_concurrent": 1,
        "predict_limit": 8192,
        "emits_reasoning": True,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-qwopus-coder-mtp-v2": {
        "name": "🔬 Bench · Qwopus3.6-27B-v2-MTP (Jackrong)",
        "description": (
            "Benchmark: hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf "
            "(Jackrong, Apache 2.0, June 2026, 27B dense, ~19GB Q5_K_M). "
            "v2 of Qwopus3.6-27B-Coder-MTP — direct head-to-head vs bench-qwopus-coder-mtp (v1). "
            "Updated SFT mix: additional agentic + multi-turn traces. MTP embedded draft heads. "
            "PROBE RESULT (2026-06-16): 10/23 — widespread 500 Internal Server Errors on complex "
            "prompts (same empty-content pattern as bench-fastcontext and bench-qwopus-coder-mtp-v1 "
            "at longer context). v2 regresses vs v1 on probe coverage. PROMOTE_POLICY=blocked."
        ),
        "model_hint": "hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "keep_alive": "5m",
        "tools": [],
    },
    "bench-deepseek-coder-v2": {
        "name": "🔬 Bench · DeepSeek-Coder-V2-Lite 16B (DeepSeek)",
        "description": (
            "Benchmark: deepseek-coder-v2:16b-lite-instruct-q4_K_M "
            "(DeepSeek, MIT-style license, 16B/2.4B MoE, ~9GB Q4_K_M). "
            "FIM-trained dedicated coder, 338 programming languages, 128K ctx. "
            "12.7% SWE-bench, 73.7% Aider, 90.2% HumanEval. Older (mid-2024) but "
            "a genuine code-specialist lineage absent elsewhere in fleet. "
            "Wired for game-challenge evaluation (TASK_CODING_GAMECHALLENGE_V1 A5). "
            "PROMOTE_POLICY=confirm."
        ),
        "model_hint": "deepseek-coder-v2:16b-lite-instruct-q4_K_M",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "tools": [],
    },
    "auto-cad": {
        "name": "📐 Portal CAD / 3D-Print Designer",
        "description": (
            "Parametric 3D-model generation via code-CAD (OpenSCAD primary; Python+trimesh "
            "for procedural geometry). Produces STL/3MF for FDM/SLA printing. "
            "Qwen3-Coder 30B-A3B MoE (Ollama, tool-capable, >20 t/s). "
            "Use render_openscad tool to convert SCAD code → STL + preview PNG. "
            "Note: CadQuery/build123d require OCP which has no arm64 wheels — use OpenSCAD."
        ),
        "model_hint": "qwen3-coder:30b-a3b-q4_K_M",
        "predict_limit": 16384,
        "think": False,
        "system_prompt_append": (
            "\n\nCAD OUTPUT RULE: When asked for a 3D model or printable part, write COMPLETE "
            "OpenSCAD source code in a fenced ```openscad block. State all dimensions as named "
            "variables at the top (units=mm, wall thickness, tolerances) so the part is "
            "parametric. End by calling the render_openscad tool with your code to produce the "
            "STL + preview PNG. For procedural geometry (arrays, math-driven surfaces), use "
            "Python with trimesh in execute_python — trimesh is available. Do not leave stubs."
        ),
        "tools": [
            "execute_python",
            "execute_bash",
            "sandbox_status",
            "read_pdf",
            "read_word_document",
            "web_search",
            "web_fetch",
            "remember",
            "recall",
            "kb_search",
            "render_mesh",
            "render_openscad",
            "convert_cad",
        ],
    },
    "bench-c3d-v0": {
        "name": "🔬 Bench · C3D-v0 (CADQuery specialist)",
        "description": (
            "Benchmark: C3Dv0:latest (joshuaokolo/C3Dv0, Ollama, Gemma-3n-E4B 4B base, "
            "LoRA on Text-to-CadQuery ~48K/50%/1-epoch, ~7.3GB, 32K ctx). TEXT-ONLY, "
            "NO TOOLS. Simple-to-moderate parametric geometry only. Own-hardware CAD eval "
            "vs incumbent coders. NEVER auto-routed/auto-promoted (PROMOTE_POLICY). "
            "Verified live 2026-06."
        ),
        "model_hint": "C3Dv0:latest",
        "max_concurrent": 1,
        "predict_limit": 8192,
        "keep_alive": "5m",
        "tools": [],
    },
}

# ── Tool-call helpers (M2) ──────────────────────────────────────────────────

# Max iterations of the streaming tool-call loop before the pipeline gives up
# and returns whatever the model has so far. Env-overridable. Consumed in
# router_pipe._stream_with_tool_loop_impl.
MAX_TOOL_HOPS = int(os.environ.get("MAX_TOOL_HOPS", "20"))


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

    1. ``tools_allow`` **absent** from the persona dict (or ``None``)
       → use the workspace default tools unchanged.
    2. ``tools_allow`` **present with an explicit list** (even ``[]``)
       → that exact set **replaces** the workspace default.
       ``tools_allow: []`` means *no tools at all*.
    3. ``tools_deny`` then strips anything from the result.

    Args:
        persona: The persona YAML dict from ``_PERSONA_MAP``. An empty
            dict (the standard fallback for unknown personas) yields
            the workspace default unchanged because ``get("tools_allow", None)``
            returns ``None``.
        workspace_id: Workspace key for the default fallback; unknown
            ids contribute ``[]`` as the base.

    Returns:
        Sorted, deduplicated tool names. Sorted alphabetically for
        determinism in caching, tests, and logs; downstream
        ``tool_registry.get_openai_tools`` preserves whatever order it
        receives.
    """
    raw_allow = persona.get("tools_allow")
    persona_deny = set(persona.get("tools_deny", []) or [])
    effective = set(_workspace_tools(workspace_id)) if raw_allow is None else set(raw_allow)
    return sorted(effective - persona_deny)


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
