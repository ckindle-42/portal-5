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
import time
from pathlib import Path
from typing import Any

import httpx

from portal.platform.inference.router.metrics import _router_latency_seconds
from portal.platform.inference.router.workspaces import WORKSPACES


def _load_data(name: str) -> Any:
    """Load a data file that was a module-level literal before V1."""
    if env_dir := os.environ.get("ROUTING_CONFIG_DIR"):
        config_dir = Path(env_dir)
    else:
        docker_dir = Path("/app/config")
        config_dir = (
            docker_dir if docker_dir.is_dir() else Path(__file__).resolve().parents[4] / "config"
        )
    path = config_dir / "inference" / f"{name}.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


logger = logging.getLogger(__name__)

# Shared httpx client — set by lifespan in router_pipe after startup.
# None until lifespan runs; _route_with_llm checks and degrades gracefully.
_http_client: httpx.AsyncClient | None = None

# ── Content-aware routing: weighted keyword scoring ──────────────────────────
# Applied only when the user selects the 'auto' workspace.
# Each workspace defines weighted keywords and an activation threshold.
# Weights: 3 = strong/clear intent, 2 = medium signal, 1 = weak/broad term.
# The workspace with the highest score above its threshold wins.

# Redteam keywords — clearly offensive intent
_REDTEAM_KEYWORDS: dict[str, int] = _load_data("routing_redteam_keywords")

# Security keywords — broader (defensive + offensive analysis)
_SECURITY_KEYWORDS: dict[str, int] = _load_data("routing_security_keywords")

# SPL keywords — Splunk-specific vocabulary (low false positive rate)
_SPL_KEYWORDS: dict[str, int] = _load_data("routing_spl_keywords")

# Coding keywords — software development intent
_CODING_KEYWORDS: dict[str, int] = _load_data("routing_coding_keywords")

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
_COMPLIANCE_KEYWORDS: dict[str, int] = _load_data("routing_compliance_keywords")

# Harmful-intent keywords — genuinely harmful asks (targeting a private
# individual, deception/fraud, harassment) that a STANDARD-posture lane must
# handle so it refuses, never an abliterated lane. Distinct from
# redteam/security (authorized offensive work is legitimate). The `auto`
# router SHOULD default most traffic to abliterated lanes — this gate is the
# narrow exception. Adaptive UAT FINDINGS C1/C2/C3.
_HARMFUL_INTENT_KEYWORDS: dict[str, int] = _load_data("routing_harmful_intent_keywords")
_HARMFUL_INTENT_THRESHOLD: int = int(os.environ.get("HARMFUL_INTENT_THRESHOLD", "3"))
# Standard-posture lane harmful `auto` requests are routed to. Non-abliterated,
# tool-light, will refuse a genuinely harmful ask and offer a safe alternative.
_HARMFUL_INTENT_LANE: str = os.environ.get("HARMFUL_INTENT_LANE", "auto-daily")
_HARMFUL_INTENT_KW_CACHE: dict[str, int] = {
    kw.lower(): w for kw, w in _HARMFUL_INTENT_KEYWORDS.items()
}


def detect_harmful_intent(messages: list[dict]) -> bool:
    """True when the last user message trips the harmful-intent keyword gate.

    Weighted substring scoring over the lowercased last user message, same
    mechanism as ``_detect_workspace``. Conservative by design: a false
    positive only means the request is handled by the standard lane instead
    of an abliterated one, which is cheap; a false negative is the failure
    mode this gate exists to prevent.
    """
    text = _last_user_text(messages, 2000).lower()
    if not text:
        return False
    score = sum(w for kw, w in _HARMFUL_INTENT_KW_CACHE.items() if kw in text)
    return score >= _HARMFUL_INTENT_THRESHOLD


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

# Variant-signal keyword sets for the coding base workspace. Described as
# *variants* of a canonical base workspace; keyword content and weights are
# byte-for-byte unchanged from before alias retirement.
_CODING_LAGUNA_KEYWORDS: dict[str, int] = {  # variant of auto-coding
    "fix this bug": 3,
    "refactor": 2,
    "add feature": 2,
    "maintain": 2,
    "advance": 2,
    "iterate": 2,
    "run tests": 3,
    "make changes": 2,
    "update the code": 2,
    "edit the file": 3,
    "modify portal": 3,
    "agentic coding": 3,
    "devstral": 3,
}
_CODING_HEAVY_KEYWORDS: dict[str, int] = {  # variant of auto-coding
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
}

# Reused by both Layer 2 (below) and Layer 1's post-classification variant
# inference (_infer_variant in _route_with_llm) so the two layers agree on
# what each variant/role "sounds like" — one keyword source, two consumers.
_CODING_VARIANT_SIGNALS: dict[str, dict[str, int]] = {
    "laguna": _CODING_LAGUNA_KEYWORDS,
    "heavy": _CODING_HEAVY_KEYWORDS,
}

# Layer 2 (the keyword scorer) had a dedicated entry only for "redteam"; the
# other 6 security variants are extracted from the retiring Layer-1
# routing_descriptions.json entries and routing_examples.json, so the
# variant-inference signal is grounded in content the router already believed
# differentiated these intents. The LLM-layer accuracy check
# (scripts/routing_regression.py --layer=llm --labeled-corpus) against the
# live router model is the arbiter of whether this reconstruction holds.
_SECURITY_VARIANT_SIGNALS: dict[str, dict[str, int]] = {
    "redteam": _REDTEAM_KEYWORDS,
    "blueteam": {
        "incident response": 3,
        "threat hunting": 3,
        "soc operations": 3,
        "soc": 2,
        "siem": 3,
        "siem analysis": 3,
        "edr": 2,
        "xdr": 2,
        "security monitoring": 2,
        "log analysis": 2,
        "malware containment": 3,
        "blue team": 3,
        "blueteam": 3,
        "firewall rules": 2,
        "ids alert": 3,
        "ransomware": 2,
        "isolate": 2,
        "detection rule": 2,
    },
    "pentest": {  # live-execution intent (vs redteam: pure generation)
        "live tool execution": 3,
        "run a live": 3,
        "authorized pentest": 3,
        "authorized targets": 2,
        "ad attack chain": 3,
        "hash cracking": 3,
        "crack the hash": 3,
        "poc validation": 3,
        "kerberoastable": 3,
        "ad pivot": 3,
        "compromised workstation": 2,
    },
    "redteam-deep": {  # advanced red-team simulation
        "detailed att&ck": 3,
        "full kill-chain": 3,
        "kill chain walk-through": 3,
        "advanced red team": 3,
        "ad pivoting": 3,
    },
    "purpleteam": {  # red+blue analysis, 2-hop, no tool execution
        "purple team": 3,
        "purpleteam": 3,
        "attack chain": 2,
        "map the attack chain": 3,
        "detection rules for each stage": 3,
    },
    "purpleteam-deep": {  # four-hop simulation, no tool execution
        "full purple team analysis": 3,
        "four-hop": 3,
        "four hop": 3,
        "ttp generation": 2,
        "detection analysis": 2,
        "pure simulation": 3,
        "no tool execution": 2,
        "cobalt strike beacon": 2,
    },
    "purpleteam-exec": {  # four-hop chain with live execution, scoped env only
        "run an authorized scan": 3,
        "authorized scan": 2,
        "identify vulnerabilities": 2,
        "detection engineering": 3,
        "ir playbook synthesis": 3,
        "scoped lab": 2,
        "live execution": 2,
    },
}

# Maps an internal scorer key to the canonical (base, variant) it represents.
# Keys not present here (auto-coding, auto-security, auto-spl, auto-reasoning,
# auto-compliance) are already canonical base ids — no translation needed.
_SCORER_VARIANT_MAP: dict[str, tuple[str, str]] = {
    "_security_redteam": ("auto-security", "redteam"),
    "_coding_laguna": ("auto-coding", "laguna"),
    "_coding_heavy": ("auto-coding", "heavy"),
}

# Workspace routing configuration: keywords + activation threshold
# Thresholds tuned so a single strong signal (weight 3) triggers routing,
# or a combination of medium signals (2+2=4) reaches the bar.
#
# auto-mistral is retired as its own entry: its keywords/threshold are
# IDENTICAL to before, just unioned into auto-reasoning. _MISTRAL_KEYWORDS
# and _REASONING_KEYWORDS have zero key overlap (verified), so this is a
# lossless union — no weight collisions to resolve.
_WORKSPACE_ROUTING: dict[str, dict[str, Any]] = {
    "_security_redteam": {  # -> (auto-security, redteam)
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
    "_coding_laguna": {  # -> (auto-coding, laguna)
        "keywords": _CODING_LAGUNA_KEYWORDS,
        "threshold": 3,
    },
    "_coding_heavy": {  # -> (auto-coding, heavy)
        "keywords": _CODING_HEAVY_KEYWORDS,
        "threshold": 3,
    },
    "auto-reasoning": {
        "keywords": {**_REASONING_KEYWORDS, **_MISTRAL_KEYWORDS},
        "threshold": 3,
    },
    "auto-compliance": {
        "keywords": _COMPLIANCE_KEYWORDS,
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
# Falls back to keyword scoring (Layer 2) on low confidence or timeout.
# Default model: gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M (~82% acc, 840ms warm).
# Requires LLM_ROUTER_TIMEOUT_MS=1000 and OLLAMA_MAX_LOADED_MODELS=3.

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
        # Required posture of the request, independent of topic. "harmful"
        # diverts to the standard-posture lane regardless of the workspace
        # pick (the semantic counterpart to the keyword gate — adaptive UAT
        # FINDINGS C1/C2). "standard"/"permissive" are informational.
        "posture": {
            "type": "string",
            "enum": ["harmful", "standard", "permissive"],
        },
    },
    "required": ["workspace", "confidence", "posture"],
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
    for parent in this_file.parents:
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
        f'Message: "{ex["message"]}"\nWorkspace: {ex["workspace"]}\n'
        f"Confidence: {ex['confidence']}\nPosture: {ex.get('posture', 'standard')}"
        for ex in (examples or [])[:9]
    )

    return f"""You are an intent router for an AI platform. Classify the user message into exactly one workspace, and judge the posture the request requires.

WORKSPACES:
{desc_lines}

EXAMPLES:
{example_lines}

POSTURE — judge the request's intent, not its topic:
- "harmful": genuinely harmful intent — targeting or surveilling a specific private individual (doxxing, stalking, accessing someone's account/messages without consent), fraud or deception (fake reviews, forged documents, impersonation, phishing), harassment, blackmail, or covert cheating. Legitimate security research, authorized pentesting, fiction, and a user acting on their OWN accounts/devices are NOT harmful.
- "permissive": legitimate work that is sensitive or explicit — security/exploit research, authorized offensive testing, uncensored creative writing, adult content.
- "standard": everything else.

Now classify this message:
Message: "{user_message}"

Respond ONLY with a JSON object: {{"workspace": "<workspace_id>", "confidence": <0.0-1.0>, "posture": "<harmful|standard|permissive>"}}
The workspace must be one of the valid IDs listed above."""


# Per-base variant-signal table used by Layer 1's post-classification pass to
# recover the variant once the LLM has picked a base workspace id.
_VARIANT_INFERENCE_TABLE: dict[str, dict[str, dict[str, int]]] = {
    "auto-coding": _CODING_VARIANT_SIGNALS,
    "auto-security": _SECURITY_VARIANT_SIGNALS,
}
# Minimum score for a variant signal set to "win" and get attached — below
# this, the message just doesn't say enough to justify picking a specific
# variant over the base workspace's own generic behavior.
_VARIANT_INFERENCE_THRESHOLD = 3


def _infer_variant(base: str, message: str) -> str:
    """Score `message` against `base`'s variant-signal sets (if any) and
    return `"<base>::<variant>"` for the highest-scoring variant that clears
    `_VARIANT_INFERENCE_THRESHOLD`, else `base` unchanged.

    Used by Layer 1 (`_route_with_llm`) only — Layer 2 (`_detect_workspace`)
    achieves the same effect natively via its own per-variant scoring
    entries (`_coding_laguna`/`_coding_heavy`/`_security_redteam` in
    `_WORKSPACE_ROUTING`) and doesn't need this second pass.
    """
    signal_table = _VARIANT_INFERENCE_TABLE.get(base)
    if not signal_table:
        return base
    text = message.lower()
    scores = {
        variant: score
        for variant, keywords in signal_table.items()
        if (score := sum(w for kw, w in keywords.items() if kw in text))
        >= _VARIANT_INFERENCE_THRESHOLD
    }
    if not scores:
        return base
    winner = max(scores, key=lambda k: scores[k])
    return f"{base}::{winner}"


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
    * Hard timeout (default 1000ms, via ``LLM_ROUTER_TIMEOUT_MS``).
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
    _t0 = time.monotonic()
    if not _LLM_ROUTER_ENABLED:
        _router_latency_seconds.labels(outcome="disabled").observe(0.0)
        return None

    last_user_content = _last_user_text(messages, 500)
    if not last_user_content:
        _router_latency_seconds.labels(outcome="disabled").observe(0.0)
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
            _router_latency_seconds.labels(outcome="disabled").observe(0.0)
            return None
        payload = {
            "model": _LLM_ROUTER_MODEL,
            "prompt": prompt,
            "stream": False,
            "keep_alive": -1,  # Keep model warm — int not string (Ollama 0.30+ rejects "-1")
            "options": {
                "temperature": 0,
                "num_predict": 64,  # room for the added "posture" field
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
        posture = str(parsed.get("posture", "")).strip().lower()

        # Harmful-posture diversion — semantic counterpart to the keyword gate
        # in detect_harmful_intent (adaptive UAT FINDINGS C1/C2). Checked before
        # the workspace/confidence gates: a harmful request must go to the
        # standard-posture lane even when the model is unsure which topic
        # workspace it belongs to.
        if posture == "harmful":
            logger.warning(
                "LLM router: posture=harmful for %r — routing to standard-posture "
                "lane '%s' instead of '%s'.",
                last_user_content[:80],
                _HARMFUL_INTENT_LANE,
                workspace or "auto",
            )
            _router_latency_seconds.labels(outcome="harmful_posture").observe(
                time.monotonic() - _t0
            )
            return _HARMFUL_INTENT_LANE

        # Validate workspace ID against allowlist
        if workspace not in _VALID_WORKSPACE_IDS:
            logger.warning(
                "LLM router returned unknown workspace '%s' — falling back to keywords",
                workspace,
            )
            _router_latency_seconds.labels(outcome="invalid_workspace").observe(
                time.monotonic() - _t0
            )
            return None

        # Don't return 'auto' — it's the default, no routing gain
        if workspace == "auto":
            _router_latency_seconds.labels(outcome="invalid_workspace").observe(
                time.monotonic() - _t0
            )
            return None

        if confidence < _LLM_ROUTER_CONFIDENCE_THRESHOLD:
            logger.debug(
                "LLM router low confidence %.2f for '%s' — falling back to keywords",
                confidence,
                workspace,
            )
            _router_latency_seconds.labels(outcome="low_confidence").observe(time.monotonic() - _t0)
            return None

        resolved = _infer_variant(workspace, last_user_content)
        logger.info(
            "LLM router: '%s' → workspace='%s' confidence=%.2f",
            last_user_content[:60],
            resolved,
            confidence,
        )
        _router_latency_seconds.labels(outcome="confident").observe(time.monotonic() - _t0)
        return resolved

    except (TimeoutError, httpx.TimeoutException):
        logger.debug(
            "LLM router timed out after %dms — falling back to keywords",
            _LLM_ROUTER_TIMEOUT_MS,
        )
        _router_latency_seconds.labels(outcome="timeout").observe(time.monotonic() - _t0)
        return None
    except Exception as e:
        logger.debug("LLM router error (non-fatal): %s — falling back to keywords", e)
        _router_latency_seconds.labels(outcome="error").observe(time.monotonic() - _t0)
        return None


def _detect_workspace(messages: list[dict]) -> str | None:
    """Layer 2 of auto-routing — weighted keyword scoring fallback.

    Used when the LLM router (``_route_with_llm``) returns ``None``
    — either disabled, timed out, low confidence, or hallucinated an
    invalid workspace.

    Scoring: for each entry in ``_WORKSPACE_ROUTING``, sum the
    weights of matching keywords in the (lowercased, 2000-char-truncated)
    last user message. An entry qualifies if its score meets its
    declared threshold; the highest-scoring qualifier wins. Entries whose
    key is one of ``_SCORER_VARIANT_MAP``'s internal sentinels (e.g.
    ``"_coding_heavy"``) represent a *variant* of a canonical base
    workspace, not a workspace of their own — the winning key is translated
    to the canonical ``"<base>::<variant>"`` synthetic form before returning
    (a rename of the scorer's output *vocabulary*, not a change to its
    *decisions*).

    Two tiebreaks:

    1. **Redteam preempts security** when both qualify AND redteam's
       score ≥ 5. Same model family, but redteam routes to the more
       permissive abliterated variant; falling through to security
       would silently degrade quality for users explicitly asking for
       offensive work. Returns ``"auto-security::redteam"`` (not a bare
       "auto-redteam" alias id — retired).
    2. **Otherwise ties go to ``_WORKSPACE_ROUTING`` insertion
       order** via Python dict semantics under ``max(..., key=...)``
       — first-declared wins. Current declaration order is:
       redteam-variant, security, spl, coding, laguna-variant,
       heavy-variant, reasoning (mistral's keywords unioned in),
       compliance.

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
    if (
        "_security_redteam" in scores
        and "auto-security" in scores
        and scores["_security_redteam"] >= 5
    ):
        logger.info(
            "Auto-routing tiebreak: redteam=%d wins over security=%d "
            "(same model family; redteam variant is more permissive).",
            scores["_security_redteam"],
            scores["auto-security"],
        )
        return "auto-security::redteam"

    winner = max(scores, key=lambda k: scores[k])
    if winner in _SCORER_VARIANT_MAP:
        base, variant = _SCORER_VARIANT_MAP[winner]
        return f"{base}::{variant}"
    return winner
