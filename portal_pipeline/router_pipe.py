"""Portal 5.2.1 — Intelligent Router Pipeline.

Exposes OpenAI-compatible /v1/models and /v1/chat/completions.
Open WebUI connects here as its sole model source.
Routes by workspace to the appropriate backend + model.
"""

from __future__ import annotations

import asyncio
import hmac
import importlib.metadata
import json
import logging
import os
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from portal_pipeline.notifications import NotificationDispatcher, NotificationScheduler

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from portal_pipeline.cluster_backends import BackendRegistry

logger = logging.getLogger(__name__)
# Ensure the logger has its own stderr handler — survives uvicorn multi-worker fork().
# Without this, logger.info() output is silently dropped when workers > 1 because
# logging.basicConfig() from __main__.py doesn't propagate to forked child processes.
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger.addHandler(_handler)
_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, _log_level, logging.INFO))

# Persistent state file — survives pipeline restarts.
# Mounted as a Docker volume so it persists across container lifecycle.
_STATE_FILE = Path(os.environ.get("METRICS_STATE_FILE", "/app/data/metrics_state.json"))

# Basic Prometheus-compatible metrics counter
_request_count: dict[str, int] = {}
_startup_time = time.time()

# Maximum request body size (default 4MB)
_MAX_REQUEST_BYTES: int = int(os.environ.get("MAX_REQUEST_BYTES", str(4 * 1024 * 1024)))

# Extended stats tracked for daily summary (aggregated from Prometheus metrics)
# These are updated on every request and read by the notification scheduler.
_total_response_time_ms: float = 0.0
_total_tps: float = 0.0
_request_tps_count: int = 0
_total_input_tokens: int = 0
_total_output_tokens: int = 0
_req_count_by_model: dict[str, int] = {}  # model_name -> count (plain dict for summary)
_req_count_by_error: dict[str, int] = {}  # error_type -> count (plain dict for summary)
_peak_concurrent: int = 0
_persona_usage_raw: dict[str, dict[str, int]] = {}  # persona -> {model -> count}

# Background task that periodically persists state to disk
_state_save_task: asyncio.Task | None = None


def _record_error(workspace: str, error_type: str) -> None:
    """Record an error in both the Prometheus Counter and the plain dict for summaries."""
    _errors_total.labels(workspace=workspace, error_type=error_type).inc()
    global _req_count_by_error
    _req_count_by_error[error_type] = _req_count_by_error.get(error_type, 0) + 1


def _record_persona(persona: str, model: str) -> None:
    """Record persona usage in both the Prometheus Counter and the raw dict for persistence."""
    _persona_usage.labels(persona=persona, model=model).inc()
    global _persona_usage_raw
    if persona not in _persona_usage_raw:
        _persona_usage_raw[persona] = {}
    _persona_usage_raw[persona][model] = _persona_usage_raw[persona].get(model, 0) + 1


def _load_state() -> None:
    """Restore persisted metrics state from disk (survives restarts)."""
    global \
        _request_count, \
        _total_response_time_ms, \
        _total_tps, \
        _request_tps_count, \
        _total_input_tokens, \
        _total_output_tokens, \
        _req_count_by_model, \
        _req_count_by_error, \
        _peak_concurrent, \
        _persona_usage_raw

    if not _STATE_FILE.exists():
        logger.info("No persisted metrics state found at %s — starting fresh", _STATE_FILE)
        return

    try:
        state = json.loads(_STATE_FILE.read_text())
        _request_count = state.get("request_count", {})
        _total_response_time_ms = float(state.get("total_response_time_ms", 0.0))
        _total_tps = float(state.get("total_tps", 0.0))
        _request_tps_count = int(state.get("request_tps_count", 0))
        _total_input_tokens = int(state.get("total_input_tokens", 0))
        _total_output_tokens = int(state.get("total_output_tokens", 0))
        _req_count_by_model = state.get("req_count_by_model", {})
        _req_count_by_error = state.get("req_count_by_error", {})
        _peak_concurrent = int(state.get("peak_concurrent", 0))
        _persona_usage_raw = state.get("persona_usage_raw", {})
        logger.info(
            "Loaded persisted metrics state: %d requests, %d output tokens, peak concurrent=%d",
            sum(_request_count.values()),
            _total_output_tokens,
            _peak_concurrent,
        )
    except Exception as e:
        logger.warning("Failed to load persisted metrics state: %s — starting fresh", e)


def _save_state() -> None:
    """Persist current metrics state to disk.

    With multiple workers, each process has its own in-memory counters.
    On save we read the existing file, merge our counters into it (sum for
    accumulators, max for peak), and write back atomically.
    """
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Read existing state (may have been written by another worker)
        existing: dict = {}
        if _STATE_FILE.exists():
            with suppress(json.JSONDecodeError, OSError):
                existing = json.loads(_STATE_FILE.read_text())

        # Merge: sum accumulators, max for peak
        merged = {
            "request_count": dict(existing.get("request_count", {})),
            "total_response_time_ms": float(existing.get("total_response_time_ms", 0.0))
            + _total_response_time_ms,
            "total_tps": float(existing.get("total_tps", 0.0)) + _total_tps,
            "request_tps_count": int(existing.get("request_tps_count", 0)) + _request_tps_count,
            "total_input_tokens": int(existing.get("total_input_tokens", 0)) + _total_input_tokens,
            "total_output_tokens": int(existing.get("total_output_tokens", 0))
            + _total_output_tokens,
            "req_count_by_model": dict(existing.get("req_count_by_model", {})),
            "req_count_by_error": dict(existing.get("req_count_by_error", {})),
            "peak_concurrent": max(int(existing.get("peak_concurrent", 0)), _peak_concurrent),
            "persona_usage_raw": dict(existing.get("persona_usage_raw", {})),
        }

        # Merge nested dicts
        for ws, count in _request_count.items():
            merged["request_count"][ws] = merged["request_count"].get(ws, 0) + count
        for model, count in _req_count_by_model.items():
            merged["req_count_by_model"][model] = merged["req_count_by_model"].get(model, 0) + count
        for err_type, count in _req_count_by_error.items():
            merged["req_count_by_error"][err_type] = (
                merged["req_count_by_error"].get(err_type, 0) + count
            )
        for persona, models in _persona_usage_raw.items():
            if persona not in merged["persona_usage_raw"]:
                merged["persona_usage_raw"][persona] = {}
            for model, count in models.items():
                merged["persona_usage_raw"][persona][model] = (
                    merged["persona_usage_raw"][persona].get(model, 0) + count
                )

        # Atomic write
        tmp = _STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(merged))
        tmp.rename(_STATE_FILE)
    except Exception as e:
        logger.debug("Failed to persist metrics state: %s", e)


async def _state_save_loop(interval: int = 60) -> None:
    """Background task: save state to disk every N seconds."""
    while True:
        await asyncio.sleep(interval)
        _save_state()


# Notification subsystem handles operational alerts and daily summaries
_notification_dispatcher: NotificationDispatcher | None = None
_notification_scheduler: NotificationScheduler | None = None

# Cached multiprocess collector registry — rebuilt only when the process
# directory changes, not on every /metrics scrape.
_mp_registry_cache: CollectorRegistry | None = None
_mp_registry_dir_cache: str | None = None

# ── Prometheus metrics (per-model granularity) ────────────────────────────
# Use a separate registry to avoid conflicts with default prometheus_client
# global state when running with multiple uvicorn workers.
_REGISTRY = CollectorRegistry(auto_describe=True)

_tokens_per_second = Histogram(
    "portal_tokens_per_second",
    "Tokens generated per second by model and workspace",
    ["model", "workspace"],
    buckets=[5, 10, 20, 30, 40, 50, 60, 80, 100, 150, 200],
    registry=_REGISTRY,
)

_output_tokens = Counter(
    "portal_output_tokens_total",
    "Total output tokens generated by model and workspace",
    ["model", "workspace"],
    registry=_REGISTRY,
)

_input_tokens = Counter(
    "portal_input_tokens_total",
    "Total input tokens processed by model and workspace",
    ["model", "workspace"],
    registry=_REGISTRY,
)

_requests_by_model = Counter(
    "portal_requests_by_model_total",
    "Total requests routed to each model",
    ["model", "workspace"],
    registry=_REGISTRY,
)

_response_time_seconds = Histogram(
    "portal_response_time_seconds",
    "End-to-end response time (request received to last byte) per model and workspace",
    ["model", "workspace"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
    registry=_REGISTRY,
)

_requests_total = Counter(
    "portal_requests_total",
    "Total requests by workspace (aggregated across workers)",
    ["workspace"],
    registry=_REGISTRY,
)

_errors_total = Counter(
    "portal_errors_total",
    "Total failed requests by workspace and error type",
    ["workspace", "error_type"],
    registry=_REGISTRY,
)

_concurrent_requests = Gauge(
    "portal_concurrent_requests",
    "Number of requests currently being processed",
    registry=_REGISTRY,
)

_persona_usage = Counter(
    "persona_usage_total",
    "Total requests by persona/model preset as selected by user",
    ["persona", "model"],
    registry=_REGISTRY,
)


def _record_usage(
    model: str, workspace: str, data: dict, elapsed_seconds: float | None = None
) -> None:
    """Extract usage fields from an Ollama or OpenAI-format response dict and record metrics.

    Safe to call with incomplete dicts — missing fields are skipped.
    Supports both Ollama native format (eval_count, eval_duration, prompt_eval_count)
    and OpenAI compatibility format (completion_tokens, prompt_tokens).
    TPS computation (fastest available method):
      1. eval_duration_ns  — Ollama native model compute time (preferred)
      2. elapsed_seconds    — wall-clock time from stream start (streaming fallback)
    Updates both Prometheus histograms/counters and module-level aggregates
    used by the daily summary scheduler.
    """
    try:
        global \
            _total_output_tokens, \
            _total_input_tokens, \
            _total_tps, \
            _request_tps_count, \
            _req_count_by_model
        # Prefer OpenAI format fields (completion_tokens / prompt_tokens)
        # Fall back to Ollama native (eval_count / prompt_eval_count)
        # MLX server nests tokens inside "usage" dict — check both levels.
        usage = data.get("usage") or {}
        completion_tokens = int(
            data.get("completion_tokens")
            or usage.get("completion_tokens")
            or data.get("eval_count")
            or usage.get("eval_count")
            or 0
        )
        prompt_tokens = int(
            data.get("prompt_tokens")
            or usage.get("prompt_tokens")
            or data.get("prompt_eval_count")
            or usage.get("prompt_eval_count")
            or 0
        )
        eval_duration_ns = int(data.get("eval_duration") or usage.get("eval_duration") or 0)

        _requests_by_model.labels(model=model, workspace=workspace).inc()

        if completion_tokens > 0:
            _output_tokens.labels(model=model, workspace=workspace).inc(completion_tokens)
            _total_output_tokens += completion_tokens

        if prompt_tokens > 0:
            _input_tokens.labels(model=model, workspace=workspace).inc(prompt_tokens)
            _total_input_tokens += prompt_tokens

        # TPS: prefer Ollama's eval_duration; fall back to wall-clock elapsed time (streaming)
        if completion_tokens > 0 and eval_duration_ns > 0:
            tps = completion_tokens / (eval_duration_ns / 1_000_000_000)
            _tokens_per_second.labels(model=model, workspace=workspace).observe(tps)
            # Update running totals for daily summary
            _total_tps += tps
            _request_tps_count += 1
            logger.debug(
                "Usage: workspace=%s model=%s tokens=%d tps=%.1f (model time)",
                workspace,
                model,
                completion_tokens,
                tps,
            )
        elif completion_tokens > 0 and elapsed_seconds and elapsed_seconds > 0:
            tps = completion_tokens / elapsed_seconds
            _tokens_per_second.labels(model=model, workspace=workspace).observe(tps)
            # Update running totals for daily summary
            _total_tps += tps
            _request_tps_count += 1
            logger.debug(
                "Usage: workspace=%s model=%s tokens=%d tps=%.1f (wall clock)",
                workspace,
                model,
                completion_tokens,
                tps,
            )
        elif elapsed_seconds and elapsed_seconds > 0:
            # OpenAI-format streaming with no usage data (data: [DONE] path).
            # We still know the request completed — record with 0 tokens but
            # track the elapsed time for response time visibility.
            logger.debug(
                "Usage: workspace=%s model=%s no token data (OpenAI stream), elapsed=%.2fs",
                workspace,
                model,
                elapsed_seconds,
            )

        # Track per-model request count for summary (plain dict, not the Counter)
        _req_count_by_model[model] = _req_count_by_model.get(model, 0) + 1

    except Exception as e:
        logger.debug("Failed to record usage metrics: %s", e)


def _record_response_time(model: str, workspace: str, duration_seconds: float) -> None:
    """Record end-to-end response time for a request.

    Updates both Prometheus histogram and module-level aggregate for the daily summary.
    """
    try:
        _response_time_seconds.labels(model=model, workspace=workspace).observe(duration_seconds)
        global _total_response_time_ms
        _total_response_time_ms += duration_seconds * 1000
    except Exception as e:
        logger.debug("Failed to record response time: %s", e)


# Canonical workspace definitions — must match backends.yaml workspace_routing keys
# model_hint: preferred Ollama model tag within the routed backend group
# mlx_model_hint: preferred MLX model tag (HF path) for workspaces that route through MLX
WORKSPACES: dict[str, dict[str, str]] = {
    "auto": {
        "name": "🤖 Portal Auto Router",
        "description": (
            "Intelligently routes to the best specialist model based on your question. "
            "Security/redteam topics → BaronLLM. Coding → Qwen3-Coder. "
            "Reasoning/research → DeepSeek-R1. Other → general."
        ),
        "model_hint": "dolphin-llama3:8b",
    },
    "auto-coding": {
        "name": "💻 Portal Code Expert",
        "description": "Code generation, debugging, architecture review",
        "model_hint": "qwen3-coder-next:30b-q5",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-Next-4bit",
    },
    "auto-spl": {
        "name": "🔍 Portal SPL Engineer",
        "description": "Splunk SPL queries, pipeline explanation, detection search authoring",
        "model_hint": "deepseek-coder-v2:16b-lite-instruct-q4_K_M",
        "mlx_model_hint": "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",  # FIX: DeepSeek-Coder-V2-Lite-8bit causes consistent 120s timeouts; Qwen3-Coder-30B handles SPL reliably
    },
    "auto-security": {
        "name": "🔒 Portal Security Analyst",
        "description": "Security analysis, hardening, vulnerability assessment",
        "model_hint": "baronllm:q6_k",
    },
    "auto-redteam": {
        "name": "🔴 Portal Red Team",
        "description": "Offensive security, penetration testing, exploit research",
        "model_hint": "baronllm:q6_k",
    },
    "auto-blueteam": {
        "name": "🔵 Portal Blue Team",
        "description": "Defensive security, incident response, threat hunting",
        "model_hint": "lily-cybersecurity:7b-q4_k_m",
    },
    "auto-creative": {
        "name": "✍️  Portal Creative Writer",
        "description": "Creative writing, storytelling, content generation",
        "model_hint": "dolphin-llama3:8b",
        "mlx_model_hint": "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",
    },
    "auto-reasoning": {
        "name": "🧠 Portal Deep Reasoner",
        "description": "Complex analysis, research synthesis, step-by-step reasoning",
        "model_hint": "deepseek-r1:32b-q4_k_m",
        "mlx_model_hint": "Jackrong/MLX-Qwopus3.5-27B-v3-8bit",
    },
    "auto-documents": {
        "name": "📄 Portal Document Builder",
        "description": "Create Word, Excel, PowerPoint via MCP tools",
        "model_hint": "qwen3.5:9b",
        "mlx_model_hint": "Jackrong/MLX-Qwopus3.5-9B-v3-8bit",
    },
    "auto-video": {
        "name": "🎬 Portal Video Creator",
        "description": "Generate videos via ComfyUI / Wan2.2",
        "model_hint": "dolphin-llama3:8b",
    },
    "auto-music": {
        "name": "🎵 Portal Music Producer",
        "description": "Generate music and audio via AudioCraft/MusicGen",
        "model_hint": "dolphin-llama3:8b",
    },
    "auto-research": {
        "name": "🔍 Portal Research Assistant",
        "description": "Web research, information synthesis, fact-checking",
        "model_hint": "huihui_ai/tongyi-deepresearch-abliterated",
        "mlx_model_hint": "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit",
    },
    "auto-vision": {
        "name": "👁️  Portal Vision",
        "description": "Image understanding, visual analysis, multimodal tasks",
        "model_hint": "qwen3-vl:32b",
        "mlx_model_hint": "mlx-community/gemma-4-26b-a4b-4bit",  # Updated: Gemma 4 replaces Qwen3-VL as primary MLX VLM (Google family, #6 open LMArena)
    },
    "auto-data": {
        "name": "📊 Portal Data Analyst",
        "description": "Data analysis, statistics, visualization guidance",
        "model_hint": "deepseek-r1:32b-q4_k_m",
        "mlx_model_hint": "mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit",
    },
    "auto-compliance": {
        "name": "⚖️  Portal Compliance Analyst",
        "description": "NERC CIP compliance, policy analysis, regulatory guidance",
        "model_hint": "deepseek-r1:32b-q4_k_m",
        "mlx_model_hint": "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit",
    },
    "auto-mistral": {
        "name": "🧪 Portal Mistral Reasoner",
        "description": (
            "Structured reasoning via Magistral-Small-2509 — Mistral training lineage, "
            "[THINK] mode, distinct failure profile from Qwen/DeepSeek reasoning models."
        ),
        "model_hint": "deepseek-r1:32b-q4_k_m",
        "mlx_model_hint": "lmstudio-community/Magistral-Small-2509-MLX-8bit",
    },
}

# ── Content-aware routing keyword sets ───────────────────────────────────────
# Applied only when the user selects the 'auto' workspace.
# Each set maps to a workspace. Order matters — security before coding
# so "write an exploit in Python" routes to security, not coding.

_SECURITY_KEYWORDS: frozenset[str] = frozenset(
    {
        # Offensive / redteam
        "exploit",
        "payload",
        "shellcode",
        "privilege escalation",
        "privesc",
        "reverse shell",
        "bind shell",
        "command injection",
        "sql injection",
        "sqli",
        "xss",
        "csrf",
        "buffer overflow",
        "rop chain",
        "heap spray",
        "use after free",
        "uaf",
        "zero day",
        "0day",
        "cve-",
        "metasploit",
        "msfvenom",
        "meterpreter",
        "cobalt strike",
        "c2 server",
        "c&c",
        "lateral movement",
        "persistence mechanism",
        "evasion",
        "obfuscation",
        "antivirus bypass",
        "edr bypass",
        "av evasion",
        "defense evasion",
        "exfiltration",
        "data exfiltration",
        "lolbas",
        "living off the land",
        "pentesting",
        "pentest",
        "penetration test",
        "red team",
        "redteam",
        "offensive security",
        "bug bounty",
        "ctf",
        "capture the flag",
        "nmap",
        "masscan",
        "gobuster",
        "nikto",
        "burp suite",
        "sqlmap",
        "hydra",
        "hashcat",
        "mimikatz",
        "bloodhound",
        "crackmapexec",
        "pass the hash",
        "pass the ticket",
        "kerberoasting",
        "asreproasting",
        "golden ticket",
        "silver ticket",
        "dcsync",
        # Defensive / blue team
        "incident response",
        "threat hunting",
        "threat intelligence",
        "ioc",
        "indicator of compromise",
        "malware analysis",
        "reverse engineering",
        "yara rule",
        "sigma rule",
        "siem alert",
        "splunk detection",
        "ids rule",
        "snort rule",
        "suricata",
        "network forensics",
        "memory forensics",
        "volatility",
        "malware",
        "ransomware",
        "trojan",
        "rootkit",
        "backdoor",
        "botnet",
        "threat actor",
        "vulnerability assessment",
        "vulnerability scan",
        "nessus",
        "openvas",
        "security audit",
        "hardening",
        "cis benchmark",
        "mitre att&ck",
        "attack framework",
        "kill chain",
        "diamond model",
    }
)

_REDTEAM_KEYWORDS: frozenset[str] = frozenset(
    {
        # Clearly offensive intent — route to redteam (more permissive model)
        "exploit",
        "payload",
        "shellcode",
        "bypass",
        "evasion",
        "obfuscate",
        "reverse shell",
        "bind shell",
        "privilege escalation",
        "privesc",
        "c2",
        "c2 server",
        "command and control",
        "metasploit",
        "msfvenom",
        "cobalt strike",
        "offensive",
        "red team",
        "redteam",
        "pentest",
        "penetration test",
        "hack",
        "hacking",
        "ctf",
        "lolbas",
        "living off",
        "lateral movement",
        "mimikatz",
        "bloodhound",
        "dcsync",
        "kerberoast",
        "pass the hash",
        "golden ticket",
        "edr bypass",
        "av evasion",
        "antivirus bypass",
    }
)

_CODING_KEYWORDS: frozenset[str] = frozenset(
    {
        "write a function",
        "write a script",
        "write a program",
        "write code",
        "debug this",
        "fix this code",
        "fix the bug",
        "code review",
        "refactor",
        "implement",
        "class definition",
        "api endpoint",
        "unit test",
        "pytest",
        "unittest",
        "docker",
        "kubernetes",
        "ci/cd",
        "sql query",
        "regex",
        "algorithm",
        "data structure",
        "python",
        "javascript",
        "typescript",
        "rust",
        "golang",
        "bash script",
        "powershell",
        "ansible",
        "terraform",
        "bigfix",
        "bes xml",
        "relevance",
        # Persona-specific: pythoninterpreter, sqlterminal
        "sql",
        "interpreter",
        "simulator",
        "execute",
        "run this code",
    }
)

_SPL_KEYWORDS: frozenset[str] = frozenset(
    {
        # Direct SPL / Splunk language references
        "splunk",
        "spl",
        "spl query",
        "search processing language",
        # SPL commands (common ones users type in natural language)
        "tstats",
        "eval field",
        "rex field",
        "lookup command",
        "inputlookup",
        "outputlookup",
        "makeresults",
        "mvexpand",
        "streamstats",
        "eventstats",
        "transaction command",
        "| stats",
        "| timechart",
        "| table",
        "| eval",
        "| rex",
        "| dedup",
        "| sort",
        "| rename",
        # SPL-specific diagnostic language
        "correlation search",
        "notable event",
        "splunk es",
        "splunk enterprise security",
        "datamodel",
        "data model acceleration",
        "summary index",
        "saved search",
        "dashboard panel spl",
        "detection search",
        "splunk query",
        "write me a splunk",
        "write a splunk",
        "build a splunk",
    }
)

_REASONING_KEYWORDS: frozenset[str] = frozenset(
    {
        "analyze",
        "compare",
        "evaluate",
        "pros and cons",
        "trade-off",
        "research",
        "summarize",
        "explain in depth",
        "step by step",
        "break down",
        "how does",
        "why does",
        "what is the difference",
        "deep dive",
        "comprehensive",
        "thorough",
        "detailed analysis",
    }
)


# P9: Pre-compiled regex for security and coding keyword sets.
# Replaces 80+/35+ substring scans with a single regex match pass.
# Pattern: \b(word1|word2|...)\b — word boundary prevents partial matches.
def _make_word_boundary_regex(keywords: frozenset[str]) -> re.Pattern:
    escaped = [re.escape(kw) for kw in keywords]
    pattern = r"\b(" + "|".join(escaped) + r")\b"
    return re.compile(pattern, re.IGNORECASE)


_SECURITY_REGEX = _make_word_boundary_regex(_SECURITY_KEYWORDS)
_CODING_REGEX = _make_word_boundary_regex(_CODING_KEYWORDS)
_SPL_REGEX = _make_word_boundary_regex(_SPL_KEYWORDS)


def _detect_workspace(messages: list[dict]) -> str | None:
    """Detect the most appropriate workspace from the last user message.

    Returns a workspace ID string, or None if no strong signal found
    (caller should use the default 'auto' routing in that case).

    Routing priority (highest to lowest):
    1. Redteam keywords → auto-redteam (most permissive security model)
    2. Security keywords → auto-security (defensive + offensive analysis)
    3. SPL keywords → auto-spl (Splunk SPL queries, DeepSeek-Coder-V2-Lite)
    4. Coding keywords → auto-coding (Qwen3-Coder-Next-4bit via MLX)
    5. Reasoning keywords → auto-reasoning (DeepSeek-R1)
    """
    # Find the last user message — reversed() stops at first hit (O(1) for recent msgs)
    last_user_content = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_content = str(msg.get("content", ""))[:2000].lower()
            break

    if not last_user_content:
        return None

    # Redteam check first — more specific than security (needs 2 hits).
    # Early-exit loop: stop scanning as soon as threshold is met.
    redteam_hits = 0
    for kw in _REDTEAM_KEYWORDS:
        if kw in last_user_content:
            redteam_hits += 1
            if redteam_hits >= 2:
                return "auto-redteam"

    # Security check (broader — includes defensive topics). 1 hit is enough.
    # Pre-compiled regex (P9): single pass instead of 100+ substring scans.
    if _SECURITY_REGEX.search(last_user_content):
        return "auto-security"

    # SPL check — must come before coding (SPL is a strict subset, needs dedicated routing).
    # Single hit is sufficient — SPL vocabulary is specific enough that false positives
    # are rare. Splunk-related terms are no longer in _CODING_KEYWORDS.
    if _SPL_REGEX.search(last_user_content):
        return "auto-spl"

    # Coding check — same single-pass regex (P9).
    if _CODING_REGEX.search(last_user_content):
        return "auto-coding"

    # Reasoning check (requires 2+ signals to avoid false positives).
    reasoning_hits = 0
    for kw in _REASONING_KEYWORDS:
        if kw in last_user_content:
            reasoning_hits += 1
            if reasoning_hits >= 2:
                return "auto-reasoning"

    return None


_raw_api_key = os.environ.get("PIPELINE_API_KEY", "")
if not _raw_api_key:
    import warnings

    warnings.warn(
        "PIPELINE_API_KEY is not set — using insecure default 'portal-pipeline'. "
        "Set PIPELINE_API_KEY in .env before deploying.",
        stacklevel=1,
    )
    _raw_api_key = "portal-pipeline"
PIPELINE_API_KEY: str = _raw_api_key

# Concurrency limiter — prevents Ollama overload when all workers are busy
_MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT_REQUESTS", "20"))

# Semaphore acquisition timeout in milliseconds. Default 50ms survives normal
# scheduling jitter. Set to 0 to restore original 1ms non-blocking behavior.
try:
    _SEMAPHORE_TIMEOUT = float(os.environ.get("SEMAPHORE_TIMEOUT_MS", "50")) / 1000.0
except ValueError:
    _SEMAPHORE_TIMEOUT = 0.050
    logger.warning("Invalid SEMAPHORE_TIMEOUT_MS value — must be a number. Using default: 50ms")
_request_semaphore: asyncio.Semaphore | None = None

# ── Ollama per-request TTFT tuning ────────────────────────────────────────────
# keep_alive: how long Ollama keeps the model loaded after a request completes.
#   "-1" = never unload. Eliminates the 10-30s cold-start on the next request.
#   Native Ollama default is ~5 min; docker-ollama sets OLLAMA_KEEP_ALIVE=24h
#   server-wide, but native installs don't get that. Injecting it per-request
#   covers both cases reliably.
# num_batch: tokens processed per prompt-evaluation pass (Ollama default: 512).
#   2048 = 4× throughput during prefill — cuts TTFT on long conversation histories.
#   Safe upper bound: match your model's training context / 8. 2048 fits all
#   models in the catalog without exceeding their attention window.
_OLLAMA_KEEP_ALIVE: str = os.environ.get("OLLAMA_KEEP_ALIVE_REQUEST", "-1")
try:
    _OLLAMA_NUM_BATCH: int = int(os.environ.get("OLLAMA_NUM_BATCH", "2048"))
except ValueError:
    _OLLAMA_NUM_BATCH = 2048
    logger.warning(
        "Invalid OLLAMA_NUM_BATCH value — must be an integer. Using default: %d", _OLLAMA_NUM_BATCH
    )

# ── Routing visibility ─────────────────────────────────────────────────────────
# When true, the first line of every streaming response shows which workspace and
# model was selected. Set SHOW_ROUTING_STATUS=true in .env to enable.
# Default false — clean output. Useful for debugging auto-routing decisions.
_SHOW_ROUTING_STATUS: bool = os.environ.get("SHOW_ROUTING_STATUS", "false").lower() in (
    "1",
    "true",
    "yes",
)

registry: BackendRegistry | None = None
_health_task: asyncio.Task | None = None

# Shared httpx client for backend inference — P1: connection pool reused across
# all streaming and completion requests, avoiding TCP/TLS handshake overhead.
_http_client: httpx.AsyncClient | None = None


def _inject_ollama_options(body: dict) -> dict:
    """Inject Ollama-specific TTFT performance defaults not already in the request.

    Only called for backends with type='ollama'. Skipped for MLX and vLLM which
    do not recognise these fields.

    - keep_alive: top-level Ollama field. Prevents model unloading between
      requests, eliminating the 10-30s cold-start on the next request.
    - num_batch: inside 'options'. Larger batch = faster prompt evaluation = lower
      TTFT on multi-turn conversations with long histories.

    Uses setdefault() throughout — never overrides an explicit value from the
    caller (e.g. Open WebUI passing its own keep_alive).
    """
    body = dict(body)
    body.setdefault("keep_alive", _OLLAMA_KEEP_ALIVE)
    opts: dict = dict(body.get("options") or {})
    opts.setdefault("num_batch", _OLLAMA_NUM_BATCH)
    body["options"] = opts
    return body


def _init_notifications(registry: BackendRegistry) -> None:
    """Initialize the notification dispatcher and scheduler."""
    global _notification_dispatcher, _notification_scheduler
    # Late import to avoid circular dependency — notifications imports cluster_backends
    from portal_pipeline.notifications import NotificationDispatcher, NotificationScheduler
    from portal_pipeline.notifications.channels import (
        EmailChannel,
        PushoverChannel,
        SlackChannel,
        TelegramChannel,
        WebhookChannel,
    )

    _notification_dispatcher = NotificationDispatcher()

    # Register configured channels — share the pipeline's HTTP connection pool
    _notification_dispatcher.add_channel(SlackChannel(_http_client))
    _notification_dispatcher.add_channel(TelegramChannel(_http_client))
    _notification_dispatcher.add_channel(EmailChannel(_http_client))
    _notification_dispatcher.add_channel(PushoverChannel(_http_client))
    _notification_dispatcher.add_channel(WebhookChannel(_http_client))

    # Run threshold check on first health cycle to catch any immediate issues
    _notification_dispatcher.check_thresholds_and_alert(registry)

    # Schedule daily summary
    _notification_scheduler = NotificationScheduler(_notification_dispatcher)
    _notification_scheduler.start()

    # Attach scheduler to pipeline metrics for summary building
    from portal_pipeline.notifications import scheduler as notif_scheduler

    notif_scheduler._attach_to_pipeline(
        _notification_dispatcher,
        _request_count,
        _startup_time,
        registry,
    )


async def _warmup_auto_model(registry: BackendRegistry) -> None:
    """Pre-load the auto workspace's default model on startup.

    Ollama lazily loads models on first request. A cold load of an 8B model
    takes 10-30s on HDD, 1-5s on SSD/NFS. By making a minimal generation call
    during startup, subsequent user requests skip this penalty entirely.

    Runs in the background — startup is not blocked. Errors are logged but
    swallowed so a failed warmup does not crash the pipeline.
    """
    if _http_client is None:
        logger.debug("Warmup skipped: HTTP client not ready")
        return
    try:
        backend = registry.get_backend_for_workspace("auto")
        if backend is None:
            logger.debug("Warmup skipped: no healthy auto backend")
            return

        # Minimal prompt: one token of output, fastest model already in memory
        warmup_payload = {
            "model": backend.models[0] if backend.models else "dolphin-llama3:8b",
            "prompt": "ok",
            "stream": False,
            "options": {"num_predict": 1},
        }

        resp = await _http_client.post(backend.chat_url, json=warmup_payload)
        if resp.status_code == 200:
            logger.info(
                "Warmup complete: %s model '%s' pre-loaded",
                backend.type,
                warmup_payload["model"],
            )
        else:
            logger.debug(
                "Warmup backend %s returned HTTP %d — will load on first use",
                backend.id,
                resp.status_code,
            )
    except Exception as e:
        # Never let warmup failure affect pipeline startup
        logger.debug("Model warmup failed (non-fatal): %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global registry, _health_task, _request_semaphore, _http_client
    global _notification_dispatcher, _notification_scheduler, _state_save_task
    _request_semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    # P1: create shared client with a connection pool sized for concurrent inference
    # Timeout raised to 300s: cold-loading 32B models under memory pressure takes
    # 2-4 min before the first token. 120s was causing S3-18 streaming timeouts.
    # connect stays 5s — local backends should bind immediately.
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(300.0, connect=5.0),
        limits=httpx.Limits(
            max_keepalive_connections=20,
            max_connections=100,
        ),
    )
    registry = BackendRegistry()
    await registry.health_check_all()
    # Load persisted metrics state from disk (survives restarts)
    _load_state()
    # Pre-warm: load the auto workspace's default model so the first user request
    # is not penalized by Ollama's model-loading cold-start (10-60s for 8-32B).
    asyncio.create_task(_warmup_auto_model(registry))
    healthy = registry.list_healthy_backends()
    logger.info("Portal Pipeline started. Healthy backends: %d", len(healthy))
    if not healthy:
        logger.warning(
            "No healthy backends on startup — check Ollama is running and "
            "config/backends.yaml URLs are reachable from this container"
        )

    # ── Notifications: alerts + daily summaries ──────────────────────────────
    if os.environ.get("NOTIFICATIONS_ENABLED", "false").lower() in ("true", "1", "yes"):
        _init_notifications(registry)

    _health_task = asyncio.create_task(
        registry.start_health_loop(
            on_health_check=(
                lambda r: (
                    _notification_dispatcher.check_thresholds_and_alert(r)
                    if _notification_dispatcher
                    else None
                )
            )
        )
    )

    # Background task: persist metrics state to disk every 60s
    _state_save_task = asyncio.create_task(_state_save_loop(interval=60))

    yield

    # Final state save on shutdown
    _save_state()
    if _state_save_task:
        _state_save_task.cancel()
    if _health_task:
        _health_task.cancel()
    if _http_client:
        await _http_client.aclose()
    if _notification_scheduler:
        _notification_scheduler.stop()
    await BackendRegistry.close_health_client()


try:
    _PKG_VERSION = importlib.metadata.version("portal-5")
except importlib.metadata.PackageNotFoundError:
    _PKG_VERSION = "dev"
app = FastAPI(title="Portal Pipeline", version=_PKG_VERSION, lifespan=lifespan)


def _verify_key(authorization: str | None) -> None:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token.encode(), PIPELINE_API_KEY.encode()):
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/health")
async def health() -> dict:
    if registry is None:
        raise HTTPException(status_code=503, detail="Backend registry not initialised")
    healthy = registry.list_healthy_backends()
    return {
        "status": "ok" if healthy else "degraded",
        "version": _PKG_VERSION,
        "backends_healthy": len(healthy),
        "backends_total": len(registry.list_backends()),
        "workspaces": len(WORKSPACES),
    }


@app.post("/notifications/test")
async def test_notifications(authorization: str | None = Header(None)) -> dict:
    """Fire a test alert and summary to verify notification channel configuration.

    Returns the status of each configured channel (sent / skipped / error).
    Requires NOTIFICATIONS_ENABLED=true and at least one channel configured.
    """
    _verify_key(authorization)

    if _notification_dispatcher is None:
        raise HTTPException(
            status_code=503,
            detail="Notification dispatcher not initialized (NOTIFICATIONS_ENABLED=false?)",
        )

    from portal_pipeline.notifications.events import AlertEvent, EventType, SummaryEvent

    results: dict[str, str] = {}

    # Fire a test alert
    alert = AlertEvent(
        type=EventType.BACKEND_DOWN,
        message="This is a test alert — Portal 5 notification test successful!",
        backend_id="test-backend",
    )
    try:
        await _notification_dispatcher.dispatch(alert)
        results["alert"] = "dispatched"
    except Exception as e:
        results["alert"] = f"error: {e}"

    # Fire a test summary (stats will be zeros/minimal for a test)
    summary = SummaryEvent(
        timestamp=datetime.now(timezone.utc),
        report_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        total_requests=sum(_request_count.values()),
        requests_by_workspace=dict(_request_count),
        healthy_backends=len(registry.list_healthy_backends()) if registry else 0,
        total_backends=len(registry.list_backends()) if registry else 0,
        uptime_seconds=time.time() - _startup_time if _startup_time else 0.0,
        requests_by_model=dict(_req_count_by_model),
        avg_tokens_per_second=0.0,
        total_input_tokens=0,
        total_output_tokens=0,
        avg_response_time_ms=0.0,
    )
    try:
        await _notification_dispatcher.dispatch(summary)
        results["summary"] = "dispatched"
    except Exception as e:
        results["summary"] = f"error: {e}"

    # Report per-channel configuration status
    results["channels"] = {
        "slack": "configured" if os.environ.get("SLACK_ALERT_WEBHOOK_URL") else "not configured",
        "telegram": "configured"
        if os.environ.get("TELEGRAM_ALERT_BOT_TOKEN")
        else "not configured",
        "email": "configured" if os.environ.get("SMTP_HOST") else "not configured",
        "pushover": "configured"
        if (os.environ.get("PUSHOVER_API_TOKEN") and os.environ.get("PUSHOVER_USER_KEY"))
        else "not configured",
        "webhook": "configured" if os.environ.get("WEBHOOK_URL") else "not configured",
    }

    # Report scheduler settings
    results["scheduler"] = {
        "enabled": os.environ.get("ALERT_SUMMARY_ENABLED", "true").lower() in ("true", "1", "yes"),
        "hour": int(os.environ.get("ALERT_SUMMARY_HOUR", "9")),
        "timezone": os.environ.get("ALERT_SUMMARY_TIMEZONE", "UTC"),
    }

    return {"status": "ok", "results": results}


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    """Prometheus-compatible metrics endpoint.

    Intentionally unauthenticated — Prometheus scrapes without credentials.
    """
    uptime = time.time() - _startup_time
    if registry is None:
        raise HTTPException(status_code=503, detail="Backend registry not initialised")
    healthy = len(registry.list_healthy_backends())
    total = len(registry.list_backends())

    lines = [
        "# HELP portal_backends_healthy Number of healthy backends",
        "# TYPE portal_backends_healthy gauge",
        f"portal_backends_healthy {healthy}",
        "# HELP portal_backends_total Total registered backends",
        "# TYPE portal_backends_total gauge",
        f"portal_backends_total {total}",
        "# HELP portal_uptime_seconds Process uptime in seconds",
        "# TYPE portal_uptime_seconds gauge",
        f"portal_uptime_seconds {uptime:.1f}",
        "# HELP portal_workspaces_total Number of configured workspaces",
        "# TYPE portal_workspaces_total gauge",
        f"portal_workspaces_total {len(WORKSPACES)}",
    ]
    # Combine hand-rolled metrics with prometheus_client metrics.
    # Use multiprocess collector when PROMETHEUS_MULTIPROC_DIR is set
    # (aggregates metrics across all uvicorn workers).
    # Cache the registry object — MultiProcessCollector reads from disk files,
    # so there's no need to reconstruct it on every scrape.
    global _mp_registry_cache, _mp_registry_dir_cache
    mp_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if mp_dir:
        if _mp_registry_cache is None or _mp_registry_dir_cache != mp_dir:
            from prometheus_client import multiprocess

            _mp_registry_cache = CollectorRegistry()
            multiprocess.MultiProcessCollector(_mp_registry_cache)
            _mp_registry_dir_cache = mp_dir
        prometheus_output = generate_latest(_mp_registry_cache).decode("utf-8")
    else:
        prometheus_output = generate_latest(_REGISTRY).decode("utf-8")
    return PlainTextResponse("\n".join(lines) + "\n" + prometheus_output)


@app.get("/v1/models")
async def list_models(authorization: str | None = Header(None)) -> dict:
    _verify_key(authorization)
    ts = int(time.time())
    models = [
        {
            "id": ws_id,
            "object": "model",
            "created": ts,
            "owned_by": "portal-5",
            "name": ws_cfg["name"],
            "description": ws_cfg["description"],
        }
        for ws_id, ws_cfg in WORKSPACES.items()
    ]
    return {"object": "list", "data": models}


async def _try_non_streaming(
    backend: Any,
    body: dict,
    workspace_id: str,
    start_time: float,
    *,
    enforce_hint: bool = True,
) -> JSONResponse | None:
    """Try non-streaming completion from a single backend.

    Returns JSONResponse on success, None on failure (caller tries next backend).
    When enforce_hint=True and the workspace has a model_hint, backends that
    don't carry the hinted model are skipped (returns None) so the loop tries
    the next backend. Set enforce_hint=False on the last candidate to accept
    any model as fallback.
    """
    if _http_client is None:
        return None
    ws_cfg = WORKSPACES.get(workspace_id, {})
    model_hint = ws_cfg.get("model_hint", "")
    mlx_hint = ws_cfg.get("mlx_model_hint", "")

    # Pick the right hint for the backend type
    if backend.type == "mlx" and mlx_hint:
        target_model = mlx_hint if mlx_hint in backend.models else ""
        if not target_model and enforce_hint:
            logger.debug(
                "MLX backend %s lacks hinted model %s for workspace=%s — skipping",
                backend.id,
                mlx_hint,
                workspace_id,
            )
            return None
        if not target_model:
            target_model = backend.models[0] if backend.models else "dolphin-llama3:8b"
    elif model_hint and model_hint in backend.models:
        target_model = model_hint
    elif model_hint and enforce_hint and backend.type != "mlx":
        logger.debug(
            "Backend %s lacks hinted model %s for workspace=%s — skipping",
            backend.id,
            model_hint,
            workspace_id,
        )
        return None
    else:
        target_model = backend.models[0] if backend.models else "dolphin-llama3:8b"
    req_body = {**body, "model": target_model, "stream": False}
    if backend.type == "ollama":
        req_body = _inject_ollama_options(req_body)

    try:
        resp = await _http_client.post(backend.chat_url, json=req_body)
        resp.raise_for_status()
        data = resp.json()

        # Reasoning model normalisation: DeepSeek-R1, Qwen3 thinking mode, and Magistral
        # populate message.reasoning instead of message.content when the thinking chain
        # exhausts max_tokens. Promote reasoning→content so Open WebUI and all callers
        # always find the response in the standard OpenAI content field.
        try:
            for choice in data.get("choices") or []:
                msg = choice.get("message") or {}
                if not msg.get("content") and msg.get("reasoning"):
                    logger.debug(
                        "Backend %s: reasoning→content promotion for workspace=%s "
                        "(thinking chain consumed all tokens)",
                        backend.id,
                        workspace_id,
                    )
                    msg["content"] = msg["reasoning"]
        except Exception:
            pass  # Never let normalisation break a valid response

        _record_usage(
            model=target_model,
            workspace=workspace_id,
            data=data,
            elapsed_seconds=time.monotonic() - start_time,
        )
        logger.info(
            "Backend %s succeeded for workspace=%s model=%s",
            backend.id,
            workspace_id,
            target_model,
        )
        return JSONResponse(content=data)
    except Exception as e:
        logger.warning(
            "Backend %s failed for workspace=%s: %s — trying next candidate",
            backend.id,
            workspace_id,
            e,
        )
        return None


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    authorization: str | None = Header(None),
) -> Any:
    _verify_key(authorization)

    content_length = int(request.headers.get("content-length", 0))
    if content_length > _MAX_REQUEST_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Request body too large (max {_MAX_REQUEST_BYTES // 1024 // 1024}MB)",
        )

    if _request_semaphore is None:
        raise HTTPException(status_code=503, detail="Request semaphore not initialised")
    try:
        await asyncio.wait_for(_request_semaphore.acquire(), timeout=_SEMAPHORE_TIMEOUT)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Server busy — too many concurrent requests. Please retry.",
            headers={"Retry-After": "5"},
        ) from None

    _is_streaming = False
    workspace_id: str = "unknown"
    start_time = time.monotonic()  # Track request start for response time measurement
    try:
        if registry is None:
            raise HTTPException(status_code=503, detail="Backend registry not initialised")

        body = await request.json()
        workspace_id = body.get("model") or "auto"
        stream = body.get("stream", True)

        # Content-aware routing for 'auto' workspace
        # Inspect message content to pick the most specialized backend.
        # This lets users ask security/coding/reasoning questions through 'auto'
        # and get the right specialist model without manually switching workspaces.
        if workspace_id == "auto":
            messages = body.get("messages", [])
            detected = _detect_workspace(messages)
            if detected:
                logger.info("Auto-routing: detected workspace '%s' from message content", detected)
                workspace_id = detected

        # auto-vision text-only fallback: vision-language models (qwen3-vl:32b, Gemma 4)
        # return empty content when no image is provided. Detect absence of image_url
        # content parts and reroute to auto-reasoning for text-only queries, so users
        # always receive a meaningful response from the auto-vision workspace.
        if workspace_id == "auto-vision":
            messages = body.get("messages", [])
            has_image = any(
                isinstance(part, dict) and part.get("type") == "image_url"
                for msg in messages
                for part in (msg.get("content", []) if isinstance(msg.get("content"), list) else [])
            )
            if not has_image:
                logger.info(
                    "auto-vision: no image_url in request — rerouting to auto-reasoning "
                    "with vision system context injected"
                )
                workspace_id = "auto-reasoning"
                # Inject a system message so the reasoning model responds with
                # vision-domain vocabulary (image, visual, diagram, detect, etc.)
                # This ensures auto-vision text-only queries return domain-relevant
                # responses describing visual analysis capabilities rather than
                # generic reasoning answers.
                messages = body.get("messages", [])
                has_system = any(m.get("role") == "system" for m in messages)
                if not has_system:
                    vision_system = {
                        "role": "system",
                        "content": (
                            "You are a vision AI assistant. When answering questions about "
                            "your capabilities, focus on visual analysis tasks: image "
                            "understanding, diagram interpretation, visual element detection, "
                            "object recognition, scene description, chart reading, and "
                            "multimodal reasoning from images and diagrams."
                        ),
                    }
                    body = {**body, "messages": [vision_system] + messages}

        _request_count[workspace_id] = _request_count.get(workspace_id, 0) + 1
        _requests_total.labels(workspace=workspace_id).inc()
        _concurrent_requests.inc()
        global _peak_concurrent
        _peak_concurrent = max(_peak_concurrent, int(_concurrent_requests._value.get()))

        # Track persona usage — the "model" field in the request is the persona
        # (workspace ID) the user selected in Open WebUI.
        persona = body.get("model") or "auto"
        if persona in WORKSPACES:
            _record_persona(persona, "unknown")

        candidates = registry.get_backend_candidates(workspace_id)
        if not candidates:
            raise HTTPException(
                status_code=503,
                detail=(
                    "No healthy backends available. "
                    "Ensure Ollama is running and a model is pulled. "
                    "Check config/backends.yaml."
                ),
            )

        if not stream:
            # Non-streaming: try each backend in priority order until one succeeds.
            # Model hint is enforced (skip backends without the hinted model) for
            # all but the last candidate, where we accept any model as fallback.
            # Log the routing decision here — mirrors the streaming-path log at line ~1443
            # so that S3-19 log validation and operational log parsing work regardless
            # of whether the client requested streaming or non-streaming mode.
            logger.info(
                "Routing workspace=%s → %d candidate(s) stream=%s",
                workspace_id,
                len(candidates),
                stream,
            )
            for i, backend in enumerate(candidates):
                is_last = i == len(candidates) - 1
                result = await _try_non_streaming(
                    backend, body, workspace_id, start_time, enforce_hint=not is_last
                )
                if result is not None:
                    resolved_model = backend.models[0] if backend.models else "unknown"
                    _record_response_time(
                        resolved_model,
                        workspace_id,
                        time.monotonic() - start_time,
                    )
                    _record_persona(persona, resolved_model)
                    _concurrent_requests.dec()
                    return result
            # All backends failed
            _record_error(workspace_id, "all_backends_failed")
            _concurrent_requests.dec()
            raise HTTPException(
                status_code=502,
                detail="All backends failed — check server logs",
            )

        # Streaming: try first backend. If the stream yields an error chunk early,
        # fall back to non-streaming with remaining candidates.
        backend = candidates[0]
        ws_cfg = WORKSPACES.get(workspace_id, {})
        model_hint = ws_cfg.get("model_hint", "")
        mlx_hint = ws_cfg.get("mlx_model_hint", "")

        # Pick the right hint for the backend type
        if backend.type == "mlx" and mlx_hint:
            target_model = mlx_hint if mlx_hint in backend.models else ""
            if not target_model:
                target_model = backend.models[0] if backend.models else "dolphin-llama3:8b"
        elif model_hint and model_hint in backend.models:
            target_model = model_hint
        else:
            target_model = backend.models[0] if backend.models else "dolphin-llama3:8b"

        backend_body = {**body, "model": target_model}

        # Inject keep_alive + num_batch for Ollama backends.
        # Skipped for MLX (doesn't accept these fields) and vLLM (uses its own config).
        if backend.type == "ollama":
            backend_body = _inject_ollama_options(backend_body)

        logger.info(
            "Routing workspace=%s → backend=%s model=%s stream=%s (1/%d candidates)",
            workspace_id,
            backend.id,
            target_model,
            stream,
            len(candidates),
        )

        if len(candidates) == 1:
            # Single candidate — no fallback possible, return streaming directly
            _record_persona(persona, target_model)
            _streaming_response = StreamingResponse(
                _stream_with_preamble(
                    backend.chat_url,
                    backend_body,
                    _request_semaphore,
                    workspace_id=workspace_id,
                    model=target_model,
                    start_time=start_time,
                ),
                media_type="text/event-stream",
            )
            _is_streaming = True
            return _streaming_response

        # Multiple candidates — streaming with non-streaming fallback.
        # Try streaming from first backend; if it fails, fall back to non-streaming
        # from the remaining candidates.
        remaining = candidates[1:]

        async def _stream_or_fallback() -> AsyncIterator[bytes]:
            stream_failed = False
            try:
                async for chunk in _stream_with_preamble(
                    backend.chat_url,
                    backend_body,
                    _request_semaphore,
                    workspace_id=workspace_id,
                    model=target_model,
                    start_time=start_time,
                ):
                    if b'"error"' in chunk:
                        stream_failed = True
                    yield chunk
            except Exception:
                stream_failed = True

            if stream_failed and remaining:
                logger.info(
                    "Stream from %s failed, falling back to non-streaming for workspace=%s",
                    backend.id,
                    workspace_id,
                )
                fallback_body = {**body, "stream": False}
                for j, fb in enumerate(remaining):
                    fb_last = j == len(remaining) - 1
                    result = await _try_non_streaming(
                        fb, fallback_body, workspace_id, start_time, enforce_hint=not fb_last
                    )
                    if result is not None:
                        # Wrap non-streaming response as SSE for Open WebUI
                        import json as _json

                        data = _json.loads(result.body)
                        ts = int(time.time())
                        rid = f"chatcmpl-p5-{ts}"
                        # Emit role chunk
                        role_payload = {
                            "id": rid,
                            "object": "chat.completion.chunk",
                            "created": ts,
                            "model": workspace_id,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"role": "assistant", "content": ""},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield f"data: {_json.dumps(role_payload)}\n\n".encode()
                        # Emit content chunk
                        content = ""
                        if "choices" in data and data["choices"]:
                            msg = data["choices"][0].get("message", {})
                            # Reasoning model fallback: promote reasoning→content
                            content = msg.get("content", "") or msg.get("reasoning", "")
                        if content:
                            content_payload = {
                                "id": rid,
                                "object": "chat.completion.chunk",
                                "created": ts,
                                "model": workspace_id,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"content": content},
                                        "finish_reason": None,
                                    }
                                ],
                            }
                            yield f"data: {_json.dumps(content_payload)}\n\n".encode()
                        # Emit done
                        done_payload = {
                            "id": rid,
                            "object": "chat.completion.chunk",
                            "created": ts,
                            "model": workspace_id,
                            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                        }
                        yield f"data: {_json.dumps(done_payload)}\n\n".encode()
                        yield b"data: [DONE]\n\n"
                        return

        _streaming_response = StreamingResponse(
            _stream_or_fallback(),
            media_type="text/event-stream",
        )
        _record_persona(persona, target_model)
        _is_streaming = True
        return _streaming_response
    except HTTPException:
        _concurrent_requests.dec()
        raise
    except Exception:
        _record_error(workspace_id, "unexpected_error")
        _concurrent_requests.dec()
        raise
    finally:
        if not _is_streaming:
            # Non-streaming: response fully awaited above, safe to release here
            # Streaming: generator releases after stream completes
            _request_semaphore.release()


async def _stream_with_preamble(
    url: str,
    body: dict,
    sem: asyncio.Semaphore,
    workspace_id: str = "unknown",
    model: str = "unknown",
    start_time: float | None = None,
) -> AsyncIterator[bytes]:
    """Emit an immediate OpenAI role chunk before connecting to the backend.

    Problem: without this, Open WebUI shows nothing (frozen input, no typing
    indicator) until Ollama returns its first token. That wait includes model
    load time (10-30s cold start) plus prompt prefill — entirely silent from
    the user's perspective.

    Fix: yield a valid OpenAI streaming chunk immediately. FastAPI flushes this
    to the client before the backend connection is even opened, causing Open WebUI
    to show the typing indicator and mark the response as started. The actual
    backend response follows as normal.

    The preamble chunk carries an empty delta content — it adds no visible text to
    the chat. If SHOW_ROUTING_STATUS=true, a second chunk annotates the response
    with the selected workspace and model name.
    """
    ts = int(time.time())
    request_id = f"chatcmpl-p5-{ts}"

    def _make_chunk(delta: dict) -> bytes:
        """Serialise a single OpenAI-compatible SSE chunk."""
        payload = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": ts,
            "model": workspace_id,
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        }
        return f"data: {json.dumps(payload)}\n\n".encode()

    # Empty role chunk — starts Open WebUI typing indicator with zero latency.
    yield _make_chunk({"role": "assistant", "content": ""})

    # Optional routing annotation — shows workspace + model at top of response.
    if _SHOW_ROUTING_STATUS:
        ws_name = WORKSPACES.get(workspace_id, {}).get("name", workspace_id)
        yield _make_chunk({"content": f"`⚡ {ws_name} → {model}`\n\n"})

    # Stream from backend.
    # Semaphore ownership: _stream_with_preamble owns sem and releases it in its
    # own finally block (below). _stream_from_backend_guarded is called with
    # sem=None so its finally does NOT also release — preventing double-release.
    # This closes the window where a client disconnect after the preamble yield but
    # before the backend stream starts would leave sem permanently acquired.
    try:
        async for chunk in _stream_from_backend_guarded(
            url, body, sem=None, workspace_id=workspace_id, model=model, start_time=start_time
        ):
            yield chunk
    finally:
        sem.release()


async def _stream_from_backend_guarded(
    url: str,
    body: dict,
    sem: asyncio.Semaphore | None,
    workspace_id: str = "unknown",
    model: str = "unknown",
    start_time: float | None = None,
) -> AsyncIterator[bytes]:
    """Stream from backend and optionally release semaphore when stream is complete.

    sem=None: caller (e.g. _stream_with_preamble) owns semaphore release.
    sem=Semaphore: this function releases it in its finally block.

    The sem=None path exists so _stream_with_preamble can own the full semaphore
    lifecycle via its own try/finally, closing the early-disconnect leak window.
    """
    if _http_client is None:
        logger.error("HTTP client not initialised — yielding error chunk")
        yield ("data: " + json.dumps({"error": "Pipeline not ready"}) + "\n\n").encode()
        if sem is not None:
            sem.release()
        return
    try:
        async with _http_client.stream("POST", url, json=body) as resp:
            if resp.status_code != 200:
                err = await resp.aread()
                logger.error(
                    "Backend %s returned HTTP %d: %s",
                    url,
                    resp.status_code,
                    err[:200].decode(errors="replace"),
                )
                _record_error(
                    workspace_id,
                    f"backend_http_{resp.status_code}",
                )
                yield (
                    "data: "
                    + json.dumps({"error": f"Backend returned HTTP {resp.status_code}"})
                    + "\n\n"
                ).encode()
                return
            # Detect Ollama native NDJSON format (bare JSON lines, no "data:" prefix)
            _is_ollama_native = "/api/chat" in url and "/v1/" not in url
            rid = f"chatcmpl-p5-{int(time.time())}"
            ts = int(time.time())
            async for chunk in resp.aiter_bytes():
                if chunk:
                    if _is_ollama_native:
                        # Ollama native NDJSON: translate to SSE for Open WebUI
                        chunk_text = chunk.decode("utf-8", errors="replace")
                        for line in chunk_text.splitlines():
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                obj = json.loads(line)
                            except Exception:
                                continue
                            msg = obj.get("message") or {}
                            content_delta = msg.get("content", "") or msg.get("reasoning", "")
                            if content_delta:
                                sse_chunk = {
                                    "id": rid,
                                    "object": "chat.completion.chunk",
                                    "created": ts,
                                    "model": workspace_id,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {"content": content_delta},
                                            "finish_reason": None,
                                        }
                                    ],
                                }
                                yield f"data: {json.dumps(sse_chunk)}\n\n".encode()
                            if obj.get("done") is True:
                                elapsed = (
                                    (time.monotonic() - start_time)
                                    if start_time is not None
                                    else None
                                )
                                _record_usage(
                                    model=obj.get("model", model),
                                    workspace=workspace_id,
                                    data=obj,
                                    elapsed_seconds=elapsed,
                                )
                                done_chunk = {
                                    "id": rid,
                                    "object": "chat.completion.chunk",
                                    "created": ts,
                                    "model": workspace_id,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {},
                                            "finish_reason": "stop",
                                        }
                                    ],
                                }
                                yield f"data: {json.dumps(done_chunk)}\n\n".encode()
                                yield b"data: [DONE]\n\n"
                    else:
                        # Non-native path (MLX, vLLM, /v1/ Ollama compat): keep existing logic
                        # P6: Check raw bytes for '"done"' before decode — skip 99% of chunks.
                        if b'"done"' in chunk:
                            chunk_text = chunk.decode("utf-8", errors="replace")
                            for line in chunk_text.splitlines():
                                line = line.strip()
                                if line.startswith("data:") and "done" in line:
                                    payload = line[5:].strip()
                                    if payload and payload != "[DONE]":
                                        try:
                                            usage_data = json.loads(payload)
                                            elapsed = (
                                                (time.monotonic() - start_time)
                                                if start_time is not None
                                                else None
                                            )
                                            _record_usage(
                                                model=usage_data.get("model", model),
                                                workspace=workspace_id,
                                                data=usage_data,
                                                elapsed_seconds=elapsed,
                                            )
                                        except Exception:
                                            logger.debug(
                                                "Could not parse usage payload from stream"
                                            )
                                        break
                        # OpenAI SSE: "data: [DONE]" terminator — no usage data, but record with elapsed time.
                        if b"data: [DONE]" in chunk:
                            elapsed = (
                                (time.monotonic() - start_time) if start_time is not None else None
                            )
                            _record_usage(
                                model=model,
                                workspace=workspace_id,
                                data={},
                                elapsed_seconds=elapsed,
                            )
                        yield chunk
    except Exception as e:
        logger.error("Stream error from %s: %s", url, e)
        _record_error(workspace_id, "stream_error")
        yield (
            "data: "
            + json.dumps({"error": "Backend connection error — check server logs"})
            + "\n\n"
        ).encode()
    finally:
        if start_time is not None:
            _record_response_time(model, workspace_id, time.monotonic() - start_time)
        if sem is not None:
            sem.release()  # Release AFTER generator is fully exhausted


async def _complete_from_backend(
    url: str, body: dict, workspace_id: str = "unknown", model: str = "unknown"
) -> JSONResponse:
    if _http_client is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready")
    try:
        resp = await _http_client.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()
        _record_usage(model=model, workspace=workspace_id, data=data)
        return JSONResponse(content=data)
    except Exception as e:
        logger.error("Completion error from %s: %s", url, e)
        raise HTTPException(status_code=502, detail="Backend error — check server logs") from e
