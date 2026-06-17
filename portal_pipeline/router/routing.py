"""Workspace routing: keyword heuristics + LLM-router fallback.

Loads routing descriptions/examples, builds the router prompt, calls the
router model, and resolves a workspace id from a message list. Depends on
metrics and router.workspaces; never imports router_pipe.

``_http_client`` is set by ``lifespan`` in ``router_pipe`` after the shared
``httpx.AsyncClient`` is created. It is ``None`` until then; ``_route_with_llm``
degrades gracefully when it is not yet initialised.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from portal_pipeline.router.workspaces import WORKSPACES

logger = logging.getLogger(__name__)

# Shared httpx client — set by lifespan in router_pipe after startup.
# None until lifespan runs; _route_with_llm checks and degrades gracefully.
_http_client: httpx.AsyncClient | None = None

# ── Content-aware routing: weighted keyword scoring ──────────────────────────
# Applied only when the user selects the 'auto' workspace.
# Each workspace defines weighted keywords and an activation threshold.
# Weights: 3 = strong/clear intent, 2 = medium signal, 1 = weak/broad term.
# The workspace with the highest score above its threshold wins.
# This replaces the old regex-based approach — same O(n) complexity but
# handles overlapping signals naturally (highest score wins, not arbitrary order).

# Redteam keywords — clearly offensive intent
_REDTEAM_KEYWORDS: dict[str, int] = {
    # Strong (3) — unambiguous offensive intent
    "exploit": 3,
    "payload": 3,
    "shellcode": 3,
    "reverse shell": 3,
    "bind shell": 3,
    "privilege escalation": 3,
    "privesc": 3,
    "metasploit": 3,
    "msfvenom": 3,
    "cobalt strike": 3,
    "mimikatz": 3,
    "golden ticket": 3,
    "dcsync": 3,
    "pass the hash": 3,
    "antivirus bypass": 3,
    "edr bypass": 3,
    "av evasion": 3,
    # Medium (2) — offensive context
    "bypass": 2,
    "evasion": 2,
    "obfuscate": 2,
    "c2": 2,
    "c2 server": 2,
    "command and control": 2,
    "offensive": 2,
    "red team": 2,
    "redteam": 2,
    "pentest": 2,
    "penetration test": 2,
    "hack": 2,
    "hacking": 2,
    "ctf": 2,
    "lolbas": 2,
    "living off": 2,
    "lateral movement": 2,
    "bloodhound": 2,
    "kerberoast": 2,
}

# Security keywords — broader (defensive + offensive analysis)
_SECURITY_KEYWORDS: dict[str, int] = {
    # Strong (3) — unambiguous security intent
    "exploit": 3,
    "payload": 3,
    "shellcode": 3,
    "privilege escalation": 3,
    "privesc": 3,
    "reverse shell": 3,
    "bind shell": 3,
    "command injection": 3,
    "sql injection": 3,
    "sqli": 3,
    "xss": 3,
    "csrf": 3,
    "buffer overflow": 3,
    "rop chain": 3,
    "heap spray": 3,
    "use after free": 3,
    "uaf": 3,
    "zero day": 3,
    "0day": 3,
    "cve-": 3,
    "metasploit": 3,
    "msfvenom": 3,
    "meterpreter": 3,
    "cobalt strike": 3,
    "c2 server": 3,
    "c&c": 3,
    "lateral movement": 3,
    "persistence mechanism": 3,
    "antivirus bypass": 3,
    "edr bypass": 3,
    "av evasion": 3,
    "defense evasion": 3,
    "exfiltration": 3,
    "data exfiltration": 3,
    "pentesting": 3,
    "pentest": 3,
    "penetration test": 3,
    "red team": 3,
    "redteam": 3,
    "offensive security": 3,
    "mimikatz": 3,
    "crackmapexec": 3,
    "pass the hash": 3,
    "pass the ticket": 3,
    "kerberoasting": 3,
    "asreproasting": 3,
    "golden ticket": 3,
    "silver ticket": 3,
    "dcsync": 3,
    "ransomware": 3,
    "rootkit": 3,
    "backdoor": 3,
    "botnet": 3,
    "incident response": 3,
    "threat hunting": 3,
    "malware analysis": 3,
    "network forensics": 3,
    "memory forensics": 3,
    "mitre att&ck": 3,
    # Medium (2) — clear security context
    "evasion": 2,
    "obfuscation": 2,
    "lolbas": 2,
    "living off the land": 2,
    "bug bounty": 2,
    "ctf": 2,
    "capture the flag": 2,
    "nmap": 3,
    "masscan": 2,
    "gobuster": 2,
    "nikto": 2,
    "burp suite": 2,
    "sqlmap": 2,
    "hydra": 2,
    "hashcat": 2,
    "bloodhound": 2,
    "threat intelligence": 2,
    "ioc": 2,
    "indicator of compromise": 2,
    "reverse engineering": 2,
    "yara rule": 2,
    "sigma rule": 2,
    "siem alert": 2,
    "splunk detection": 2,
    "ids rule": 2,
    "snort rule": 2,
    "suricata": 2,
    "volatility": 2,
    "malware": 3,
    "trojan": 2,
    "threat actor": 2,
    "vulnerability assessment": 2,
    "vulnerability scan": 2,
    "nessus": 2,
    "openvas": 2,
    "hardening": 2,
    "cis benchmark": 2,
    "attack framework": 2,
    "kill chain": 2,
    "diamond model": 2,
    # Weak (1) — broad terms that need corroboration
    "security audit": 1,
    "vulnerability": 1,
    "security": 1,
    "implications": 1,
}

# SPL keywords — Splunk-specific vocabulary (low false positive rate)
_SPL_KEYWORDS: dict[str, int] = {
    # Strong (3) — unambiguous SPL intent
    "splunk": 3,
    "spl query": 3,
    "search processing language": 3,
    "tstats": 3,
    "inputlookup": 3,
    "outputlookup": 3,
    "makeresults": 3,
    "mvexpand": 3,
    "streamstats": 3,
    "eventstats": 3,
    "correlation search": 3,
    "notable event": 3,
    "splunk es": 3,
    "splunk enterprise security": 3,
    "data model acceleration": 3,
    "summary index": 3,
    "detection search": 3,
    "splunk query": 3,
    "write me a splunk": 3,
    "write a splunk": 3,
    "build a splunk": 3,
    # Medium (2) — SPL commands in natural language
    "eval field": 2,
    "rex field": 2,
    "lookup command": 2,
    "transaction command": 2,
    "| stats": 2,
    "| timechart": 2,
    "| eval": 2,
    "| rex": 2,
    "datamodel": 2,
    "saved search": 2,
    "dashboard panel spl": 2,
    # Weak (1) — short terms that need corroboration
    "spl": 1,
    "| table": 1,
    "| dedup": 1,
    "| sort": 1,
    "| rename": 1,
}

# Coding keywords — software development intent
_CODING_KEYWORDS: dict[str, int] = {
    # Strong (3) — clear coding intent
    "write a function": 3,
    "write a script": 3,
    "write a program": 3,
    "write code": 3,
    "debug this": 3,
    "fix this code": 3,
    "fix the bug": 3,
    "code review": 3,
    "run this code": 3,
    # Medium (2) — development activities
    "refactor": 2,
    "implement": 2,
    "class definition": 2,
    "api endpoint": 2,
    "unit test": 2,
    "pytest": 2,
    "unittest": 2,
    "sql query": 2,
    "algorithm": 2,
    "data structure": 2,
    "bash script": 2,
    "powershell": 2,
    "ansible": 2,
    "terraform": 2,
    "bigfix": 2,
    "bes xml": 2,
    "relevance": 2,
    "interpreter": 2,
    "simulator": 2,
    "execute": 2,
    # Weak (1) — broad terms that need corroboration
    "docker": 1,
    "kubernetes": 1,
    "ci/cd": 1,
    "regex": 1,
    "python": 1,
    "javascript": 1,
    "typescript": 1,
    "rust": 1,
    "golang": 1,
    "sql": 1,
    "function": 1,
    "script": 1,
    "review": 2,
    "bug": 2,
    "bash": 2,
    "networking": 2,
    "write function": 2,
    "write script": 2,
    "write a python": 2,
    "write a javascript": 2,
    "write a typescript": 2,
    "write a rust": 2,
    "write a golang": 2,
    "write a sql": 2,
    "write a bash": 2,
    "write a docker": 2,
    "write a kubernetes": 2,
    "docker compose": 2,
    "dockerfile": 2,
    "pipeline": 1,
}

# Reasoning keywords — analytical/deep thinking intent
_REASONING_KEYWORDS: dict[str, int] = {
    # Strong (3) — clear analytical intent
    "pros and cons": 3,
    "trade-off": 3,
    "explain in depth": 3,
    "step by step": 3,
    "break down": 3,
    "what is the difference": 3,
    "deep dive": 3,
    "detailed analysis": 3,
    # Medium (2) — analytical activities
    "analyze": 2,
    "compare": 2,
    "evaluate": 2,
    "research": 2,
    # Weak (1) — broad terms that need corroboration
    "summarize": 1,
    "how does": 1,
    "why does": 1,
    "comprehensive": 1,
    "thorough": 1,
}

# Compliance keywords — NERC CIP and regulatory intent
_COMPLIANCE_KEYWORDS: dict[str, int] = {
    # Strong (3) — unambiguous compliance intent
    "nerc cip": 3,
    "cip-002": 3,
    "cip-003": 3,
    "cip-004": 3,
    "cip-005": 3,
    "cip-006": 3,
    "cip-007": 3,
    "cip-008": 3,
    "cip-009": 3,
    "cip-010": 3,
    "cip-011": 3,
    "cip-013": 3,
    "cip-014": 3,
    "compliance gap": 3,
    "gap analysis": 3,
    "regulatory compliance": 3,
    "audit preparation": 3,
    "policy mapping": 3,
    "policy-to-standard": 3,
    "control evidence": 3,
    "compliance status": 3,
    # Medium (2) — regulatory context
    "nerc": 2,
    "bulk electric": 2,
    "bes cyber": 2,
    "critical asset": 2,
    "low impact": 2,
    "medium impact": 2,
    "high impact": 2,
    "electronic security": 2,
    "physical security": 2,
    "access management": 2,
    "security management": 2,
    "incident response plan": 2,
    "recovery plan": 2,
    "configuration change": 2,
    "patch management": 2,
    # Weak (1) — broad regulatory terms
    "compliance": 1,
    "regulation": 1,
    "audit": 1,
    "standard": 1,
    "policy review": 1,
}

# Mistral/Magistral keywords — structured reasoning with Mistral lineage
_MISTRAL_KEYWORDS: dict[str, int] = {
    # Strong (3) — explicit Mistral/Magistral requests
    "magistral": 3,
    "mistral reasoning": 3,
    "mistral model": 3,
    "think mode": 3,
    "[think]": 3,
    "strategic reasoning": 3,
    "structured reasoning": 3,
    # Medium (2) — strategic/planning context
    "strategic analysis": 2,
    "strategic planning": 2,
    "business reasoning": 2,
    "decision framework": 2,
    "decision analysis": 2,
    "trade-off analysis": 2,
    "risk assessment": 2,
    # Weak (1) — broad planning terms
    "strategy": 1,
    "planning": 1,
}

# Workspace routing configuration: keywords + activation threshold
# Thresholds tuned so a single strong signal (weight 3) triggers routing,
# or a combination of medium signals (2+2=4) reaches the bar.
_WORKSPACE_ROUTING: dict[str, dict[str, Any]] = {
    "auto-redteam": {
        "keywords": _REDTEAM_KEYWORDS,
        "threshold": 4,
    },
    "auto-security": {
        "keywords": _SECURITY_KEYWORDS,
        "threshold": 3,
    },
    "auto-spl": {
        "keywords": _SPL_KEYWORDS,
        "threshold": 3,
    },
    "auto-coding": {
        "keywords": _CODING_KEYWORDS,
        "threshold": 3,
    },
    "auto-agentic": {
        "keywords": {
            "agentic": 3,
            "swe-agent": 3,
            "openhands": 3,
            "multi-file": 3,
            "long-horizon": 3,
            "codebase refactor": 3,
            "full codebase": 3,
            "repository-wide": 3,
            "heavy coder": 2,
            "big model": 2,
            "qwen3 coder next": 2,
        },
        "threshold": 3,
    },
    "auto-reasoning": {
        "keywords": _REASONING_KEYWORDS,
        "threshold": 3,
    },
    "auto-compliance": {
        "keywords": _COMPLIANCE_KEYWORDS,
        "threshold": 3,
    },
    "auto-mistral": {
        "keywords": _MISTRAL_KEYWORDS,
        "threshold": 3,
    },
}

# Pre-lowered keyword cache for O(len(keywords)) scoring in _detect_workspace().
_KEYWORD_CACHE: dict[str, dict[str, int]] = {}
for _ws_id, _ws_cfg in _WORKSPACE_ROUTING.items():
    _KEYWORD_CACHE[_ws_id] = {kw.lower(): weight for kw, weight in _ws_cfg["keywords"].items()}


def _last_user_text(messages: list[dict[str, Any]], limit: int) -> str:
    """Extract the text content of the last user message, truncated to ``limit`` chars.

    Handles both string-content messages (the common case) and
    list-content messages (OpenAI-style content arrays with text parts).
    Non-string, non-list content is coerced via ``str()``.
    """
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            return content[:limit]
        if isinstance(content, list):
            parts = [
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            return " ".join(parts)[:limit]
        return str(content)[:limit]
    return ""


# ── LLM-Based Intent Router (P5-FUT-006) ─────────────────────────────────────
# Router bench results (73 tests, 29 workspaces, 17 candidates — 2026-06-17):
#
#   PRIMARY:  hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M
#             82.2% acc / 77.8% sec / p50=840ms warm — best quality overall
#             Requires LLM_ROUTER_TIMEOUT_MS=1000 (set below)
#
#   STANDBY:  llama3.2:3b
#             75.3% acc / 66.7% sec / p50=433ms warm — best within 500ms budget
#             Switch to this if routing latency becomes a UX concern:
#             LLM_ROUTER_MODEL=llama3.2:3b LLM_ROUTER_TIMEOUT_MS=500
#
# Non-abliterated models score zero security refusals (routing = classification,
# not generation) — abliteration offers no benefit for this use case.
# Falls back to keyword scoring (Layer 2) on low confidence or timeout.

_LLM_ROUTER_ENABLED: bool = os.environ.get("LLM_ROUTER_ENABLED", "true").lower() == "true"
_LLM_ROUTER_MODEL: str = os.environ.get(
    "LLM_ROUTER_MODEL", "hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M"
)
_LLM_ROUTER_CONFIDENCE_THRESHOLD: float = float(
    os.environ.get("LLM_ROUTER_CONFIDENCE_THRESHOLD", "0.5")
)
_LLM_ROUTER_TIMEOUT_MS: int = int(os.environ.get("LLM_ROUTER_TIMEOUT_MS", "1000"))
_LLM_ROUTER_OLLAMA_URL: str = os.environ.get(
    "LLM_ROUTER_OLLAMA_URL", "http://host.docker.internal:11434"
)

# Valid workspace IDs the LLM router may return
# Valid workspace IDs the LLM router may return.
# Derived from WORKSPACES, excluding bench-* (those are user-selected only,
# never auto-routed to). Updates automatically when WORKSPACES changes.
_VALID_WORKSPACE_IDS: frozenset[str] = frozenset(
    k for k in WORKSPACES if not k.startswith("bench-")
)

# JSON schema enforced by Ollama grammar decoding — derived from WORKSPACES.
# One source of truth: adding a workspace to WORKSPACES automatically
# makes it available to the LLM router. No parallel list to maintain.
_ROUTER_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "workspace": {
            "type": "string",
            "enum": sorted(_VALID_WORKSPACE_IDS),
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["workspace", "confidence"],
}

_routing_descriptions: dict[str, str] | None = None
_routing_examples: list[dict] | None = None


def _resolve_routing_config_dir() -> Path:
    """Resolve the routing-config directory across container, local-dev, and CI.

    Priority order:

    1. ``ROUTING_CONFIG_DIR`` environment variable (explicit override).
    2. ``/app/config/`` — the Docker container mount.
    3. Walk up from this file to find ``config/`` in the repo root.
    4. Fall back to ``/app/config/`` so downstream logs point at the
       path operators expect.

    Returns:
        A ``Path`` to the directory containing ``routing_descriptions.json``
        and ``routing_examples.json``.
    """
    if env_dir := os.environ.get("ROUTING_CONFIG_DIR"):
        return Path(env_dir)

    docker_dir = Path("/app/config")
    if docker_dir.is_dir():
        return docker_dir

    this_file = Path(__file__).resolve()
    for parent in [this_file.parent, this_file.parent.parent, this_file.parent.parent.parent]:
        candidate = parent / "config"
        if candidate.is_dir():
            return candidate

    return docker_dir


def _load_routing_config() -> tuple[dict[str, str], list[dict]]:
    """Load LLM-router descriptions and few-shot examples (cached after first call).

    Resolves ``config/routing_descriptions.json`` and
    ``config/routing_examples.json`` via ``_resolve_routing_config_dir``
    (env-var → Docker → walk-up-from-``__file__``). These files are
    operator-editable: adding a new workspace means appending one
    description and a few example messages, no code changes. The LLM
    router picks up additions on the next pipeline restart — no hot
    reload.

    Two graceful-fallback paths, both logged at warning level:

    * Either file missing → WARNING log, returns empty dict / list.
      The LLM router still functions but with no in-context guidance.
    * JSON parse error → same as missing; the file is treated as
      empty for this process lifetime.

    Filters out keys whose names start with ``_`` in the descriptions
    file. This is the convention for operator notes (e.g.
    ``"_comment": "..."``) so they don't end up in the model's
    classification prompt.

    Returns:
        ``(descriptions, examples)`` tuple. ``descriptions`` is a
        workspace-id → text dict; ``examples`` is a list of
        ``{message, workspace, confidence}`` dicts. Both are cached
        as module-level globals after the first call — the cache is
        per-process, so each uvicorn worker pays the file-read cost
        once.
    """
    global _routing_descriptions, _routing_examples
    if _routing_descriptions is not None and _routing_examples is not None:
        return _routing_descriptions, _routing_examples

    config_dir = _resolve_routing_config_dir()
    desc_path = config_dir / "routing_descriptions.json"
    ex_path = config_dir / "routing_examples.json"

    try:
        if desc_path.exists():
            raw = json.loads(desc_path.read_text())
            _routing_descriptions = {k: v for k, v in raw.items() if not k.startswith("_")}
        else:
            logger.warning(
                "LLM router: routing_descriptions.json not found at %s — router will use empty descriptions",
                desc_path,
            )
            _routing_descriptions = {}
    except Exception as e:
        logger.warning("LLM router: failed to load routing_descriptions.json: %s", e)
        _routing_descriptions = {}

    try:
        if ex_path.exists():
            raw = json.loads(ex_path.read_text())
            _routing_examples = raw.get("examples", [])
        else:
            logger.warning(
                "LLM router: routing_examples.json not found at %s — router will use empty examples",
                ex_path,
            )
            _routing_examples = []
    except Exception as e:
        logger.warning("LLM router: failed to load routing_examples.json: %s", e)
        _routing_examples = []

    return _routing_descriptions, _routing_examples


def _build_router_prompt(user_message: str) -> str:
    """Build the classification prompt sent to the LLM router model.

    Composes four sections: workspace descriptions, few-shot examples
    (capped at 9), the user message, and a JSON-format instruction.
    Reads descriptions and examples from ``_load_routing_config`` —
    operator-editable config files, no code changes needed when a new
    workspace is added.

    Token budget: the router model runs with ``num_ctx: 2048``
    (configured in ``_route_with_llm``). The 9-example cap plus 17
    workspace descriptions plus instructions leave ~300 tokens of
    headroom for the user message. Raising the example cap risks
    silent prompt truncation.

    The trailing "Respond ONLY with a JSON object..." instruction is
    belt-and-suspenders. The actual JSON shape is enforced by Ollama
    grammar decoding (``format: _ROUTER_JSON_SCHEMA`` in
    ``_route_with_llm``). The instruction alone yields ~70%
    parseable output; grammar enforcement raises that to ~100%. Both
    are kept so the prompt remains readable in logs and degrades
    sanely if grammar decoding is ever disabled.

    Args:
        user_message: The user's most recent message, pre-truncated
            to 500 chars by the caller to avoid prompt bloat.

    Returns:
        Multi-line prompt string, ready to send to ``/api/generate``.
    """
    descriptions, examples = _load_routing_config()

    # Workspace descriptions block
    desc_lines = "\n".join(f"- {ws_id}: {desc}" for ws_id, desc in descriptions.items())

    # Few-shot examples block (cap at 9 examples)
    example_lines = "\n".join(
        f'Message: "{ex["message"]}"\nWorkspace: {ex["workspace"]}\nConfidence: {ex["confidence"]}'
        for ex in (examples or [])[:9]
    )

    return f"""You are an intent router for an AI platform. Classify the user message into exactly one workspace.

WORKSPACES:
{desc_lines}

EXAMPLES:
{example_lines}

Now classify this message:
Message: "{user_message}"

Respond ONLY with a JSON object: {{"workspace": "<workspace_id>", "confidence": <0.0-1.0>}}
The workspace must be one of the valid IDs listed above."""


async def _route_with_llm(messages: list[dict]) -> str | None:
    """Layer 1 of auto-routing — LLM intent classifier with grammar-enforced JSON.

    Sends the user's last message to the router model via Ollama
    ``/api/generate`` with ``format: _ROUTER_JSON_SCHEMA``, parses the
    grammar-constrained JSON response, validates the workspace id
    against ``_VALID_WORKSPACE_IDS``, returns the workspace if
    confidence ≥ ``_LLM_ROUTER_CONFIDENCE_THRESHOLD``, otherwise
    ``None``. The caller (``chat_completions``) then falls back to
    ``_detect_workspace``'s keyword scoring on ``None``.

    **Never raises.** Every error path returns ``None``:

    * ``LLM_ROUTER_ENABLED=false`` — feature disabled outright.
    * HTTP client not yet initialised (request arrived before
      ``lifespan`` finished).
    * Hard timeout (default 500ms, via ``LLM_ROUTER_TIMEOUT_MS``).
    * HTTP failure, JSON parse failure, missing fields.
    * Workspace returned is not in ``_VALID_WORKSPACE_IDS`` (logged
      at WARNING — usually means a model hallucination or schema
      drift).
    * Workspace returned is ``"auto"`` (logged at DEBUG — the model
      sometimes returns the default; treat as "no opinion").
    * Confidence below threshold (logged at DEBUG — expected on
      ambiguous queries).

    Two non-obvious design choices:

    1. **Hard timeout via ``asyncio.wait_for``, not the HTTP client**.
       The shared ``_http_client`` has a 300s body timeout (cold-loading
       big inference models). The router needs 500ms not 300s. Wrapping
       in ``asyncio.wait_for`` enforces fast-fail without giving up
       the shared connection pool.
    2. **``bench-*`` workspaces are filtered out of ``_VALID_WORKSPACE_IDS``**.
       The grammar decoder cannot emit them. User-selectable only — the
       LLM router will never auto-route to a benchmark workspace.

    Sends ``keep_alive: -1`` on every request to keep the router
    model pinned in memory (paired with ``_warmup_llm_router`` at
    startup, which pre-loads it).

    Args:
        messages: The full ``messages[]`` array from the incoming
            chat-completion request. Only the last user message is
            inspected; truncated to 500 chars to bound prompt size.

    Returns:
        Workspace id (e.g. ``"auto-coding"``) on confident
        classification, ``None`` on any failure or low confidence.
    """
    if not _LLM_ROUTER_ENABLED:
        return None

    last_user_content = _last_user_text(messages, 500)
    if not last_user_content:
        return None

    prompt = _build_router_prompt(last_user_content)
    timeout_s = _LLM_ROUTER_TIMEOUT_MS / 1000.0

    try:
        # P7-PERF: Reuse shared httpx client instead of per-request client creation.
        # The shared _http_client has connection pooling configured (20 keepalive, 100 max).
        # Use asyncio.wait_for for timeout instead of client-level timeout to avoid
        # creating a new client just for the shorter LLM router timeout.
        if _http_client is None:
            logger.debug("LLM router skipped: HTTP client not ready")
            return None
        payload = {
            "model": _LLM_ROUTER_MODEL,
            "prompt": prompt,
            "stream": False,
            "keep_alive": -1,  # Keep model warm — int not string (Ollama 0.30+ rejects "-1")
            "options": {
                "temperature": 0,
                "num_predict": 40,
                "num_ctx": 2048,
            },
            "format": _ROUTER_JSON_SCHEMA,  # Ollama grammar-enforced JSON
        }
        resp = await asyncio.wait_for(
            _http_client.post(
                f"{_LLM_ROUTER_OLLAMA_URL}/api/generate",
                json=payload,
            ),
            timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_response = data.get("response", "").strip()

        # Parse and validate
        parsed = json.loads(raw_response)
        workspace = str(parsed.get("workspace", "")).strip()
        confidence = float(parsed.get("confidence", 0.0))

        # Validate workspace ID against allowlist
        if workspace not in _VALID_WORKSPACE_IDS:
            logger.warning(
                "LLM router returned unknown workspace '%s' — falling back to keywords",
                workspace,
            )
            return None

        # Don't return 'auto' — it's the default, no routing gain
        if workspace == "auto":
            return None

        if confidence < _LLM_ROUTER_CONFIDENCE_THRESHOLD:
            logger.debug(
                "LLM router low confidence %.2f for '%s' — falling back to keywords",
                confidence,
                workspace,
            )
            return None

        logger.info(
            "LLM router: '%s' → workspace='%s' confidence=%.2f",
            last_user_content[:60],
            workspace,
            confidence,
        )
        return workspace

    except (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException):
        logger.debug(
            "LLM router timed out after %dms — falling back to keywords",
            _LLM_ROUTER_TIMEOUT_MS,
        )
        return None
    except Exception as e:
        logger.debug("LLM router error (non-fatal): %s — falling back to keywords", e)
        return None


def _detect_workspace(messages: list[dict]) -> str | None:
    """Layer 2 of auto-routing — weighted keyword scoring fallback.

    Used when the LLM router (``_route_with_llm``) returns ``None``
    — either disabled, timed out, low confidence, or hallucinated an
    invalid workspace.

    Scoring: for each workspace in ``_WORKSPACE_ROUTING``, sum the
    weights of matching keywords in the (lowercased, 2000-char-truncated)
    last user message. A workspace qualifies if its score meets its
    declared threshold; the highest-scoring qualifier wins.

    Worked examples illustrating "score, not position":

    * ``"write an exploit in Python"`` → security wins
      (``exploit=3`` + ``python=1`` = 4) over coding (``code=3``).
    * ``"analyze this malware"`` → security wins
      (``malware=2`` + ``analyze=2`` = 4) over reasoning (``analyze=2``).
    * ``"step by step comparison of frameworks"`` → reasoning wins
      (``step by step=3`` + ``compare=2`` = 5).

    Two tiebreaks:

    1. **Redteam preempts security** when both qualify AND redteam's
       score ≥ 5 (line 1275). Same model family, but redteam routes
       to the more permissive abliterated variant; falling through
       to security would silently degrade quality for users
       explicitly asking for offensive work.
    2. **Otherwise ties go to ``_WORKSPACE_ROUTING`` insertion
       order** via Python dict semantics under ``max(..., key=...)``
       — first-declared wins. Current declaration order is:
       redteam, security, spl, coding, agentic, reasoning,
       compliance, mistral.

    Performance: keywords are pre-lowercased once at module load
    into ``_KEYWORD_CACHE``, so each request pays one ``.lower()``
    on the user message and ~120 string-in-string checks total.
    O(n) over keyword count, no regex.

    Args:
        messages: Full ``messages[]`` array. Only the last user
            message is scored.

    Returns:
        Workspace id of the highest-scoring qualifier, or ``None``
        if no workspace clears its threshold. Caller falls back to
        the default ``"auto"`` model on ``None``.
    """
    last_user_content = _last_user_text(messages, 2000).lower()
    if not last_user_content:
        return None

    # P7-PERF: Use pre-compiled keyword cache for faster scoring
    scores: dict[str, int] = {}
    for workspace_id, keywords in _KEYWORD_CACHE.items():
        score = sum(weight for kw, weight in keywords.items() if kw in last_user_content)
        threshold = _WORKSPACE_ROUTING[workspace_id]["threshold"]
        if score >= threshold:
            scores[workspace_id] = score

    if not scores:
        return None

    # Redteam takes priority over security when both exceed threshold
    # (same model family, but redteam is more permissive)
    if "auto-redteam" in scores and "auto-security" in scores and scores["auto-redteam"] >= 5:
        return "auto-redteam"

    return max(scores, key=lambda k: scores[k])
