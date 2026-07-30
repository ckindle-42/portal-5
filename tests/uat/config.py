"""Portal 5 UAT — environment constants, timeouts, thresholds, result paths.

Extracted verbatim from tests/portal5_uat_driver.py (TASK_UAT_MODULARIZE_V1
phase A). RESULTS_FILE is monkeypatch-sensitive: always access it as
``config.RESULTS_FILE`` (attribute form), never ``from ... import RESULTS_FILE``.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

# Hermetic-test guard — same class of bug as bench/config.py's _load_env:
# this ran unconditionally at import time, leaking every real .env key into
# whichever test session transitively imported this module.
if os.environ.get("UNIT_TEST_MODE") != "1":
    load_dotenv()

# Compose-internal hostnames are unresolvable from the host, and this driver runs
# host-side. `.env` ships PIPELINE_URL=http://portal-pipeline:9099 (see
# .env.example:197) for the containerized bots; load_dotenv() puts that value in
# os.environ, so `os.environ.get("PIPELINE_URL", "http://localhost:9099")` never
# reaches its localhost default and every via_dispatcher test died with
# "ConnectError: nodename nor servname provided" — 31 cases reported as SKIP and
# therefore never actually executed. Same class of bug, same fix as
# tests/benchmarks/bench_lab_exec.py's _ENV_KEYS_SKIP_FROM_DOTENV.
_COMPOSE_ONLY_HOSTS = frozenset(
    {
        "portal-pipeline",
        "portal5-pipeline",
        "portal-5-pipeline",
        "host.docker.internal",
    }
)


def _host_side_url(raw: str, fallback: str) -> str:
    """Rewrite a compose-internal hostname to localhost, preserving port and path.

    Anything else — real hostnames, IPs, an already-correct localhost URL — is
    returned untouched, so an operator who deliberately points the driver at a
    remote pipeline keeps that behavior.
    """
    if not raw:
        return fallback
    parts = urlsplit(raw)
    if not parts.hostname or parts.hostname not in _COMPOSE_ONLY_HOSTS:
        return raw
    netloc = "localhost" if parts.port is None else f"localhost:{parts.port}"
    return urlunsplit((parts.scheme or "http", netloc, parts.path, parts.query, parts.fragment))


# Config
# ---------------------------------------------------------------------------

OPENWEBUI_URL = os.environ.get("OPENWEBUI_URL", "http://localhost:8080")
PIPELINE_URL = _host_side_url(os.environ.get("PIPELINE_URL", ""), "http://localhost:9099")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "portal-pipeline")
ADMIN_EMAIL = os.environ.get("OPENWEBUI_ADMIN_EMAIL", "admin@portal.local")
ADMIN_PASS = os.environ.get("OPENWEBUI_ADMIN_PASSWORD", "")

SEND_TIMEOUT = 300_000  # initial window for stop-button to appear (cold load)
PROGRESS_POLL_S = 30  # legacy heartbeat interval (kept for compatibility)
MAX_WAIT_NO_PROGRESS = 900  # 15 min hard cap if zero progress detected
NO_STREAM_TIMEOUT = 450  # exit for retry if stop never appeared after this many seconds (cold 30B loads can take 3-4 min)
PROGRESS_LOG_INTERVAL = 120  # log a heartbeat every 2 min

# Tiered polling intervals — replace the single 30s PROGRESS_POLL_S at the
# decision points in _wait_for_completion. The 30s value remains in use as
# a heartbeat reference but is no longer the polling resolution.
PHASE1_FAST_S = 0.5  # poll every 0.5s while waiting for stream to start
PHASE1_FAST_DURATION_S = 10  # for the first 10 seconds
PHASE1_MID_S = 2.0  # then poll every 2s
PHASE1_MID_DURATION_S = 30  # for the next 30 seconds (10s..40s elapsed)
PHASE1_SLOW_S = 5.0  # then poll every 5s for very cold loads (40s+)

PHASE2_STREAMING_POLL_S = 1.5  # poll every 1.5s while model is actively streaming
PHASE2_DOM_STABLE_NEEDED = 3  # consecutive identical samples to declare DOM stable

POST_STREAM_API_WAIT_S = 15.0  # bounded API poll after stream ends (replaces fixed sleep(5))
BACKEND_SETTLE_WAIT_S = 15.0  # bounded backend-alive poll after retry (replaces sleep(15))
RESULTS_FILE = Path("tests/UAT_RESULTS.md")
SCREENSHOT_DIR = Path("/tmp/uat_screenshots")
ARTIFACT_DIR = Path("/tmp/uat_artifacts")

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# Sections that require all models unloaded before running for max memory headroom.
SECTIONS_REQUIRE_UNLOAD = True  # Always unload Ollama before sections

# Memory pressure thresholds
MEMORY_WARN_PCT = 80.0  # Log warning
MEMORY_CRITICAL_PCT = 90.0  # Force eviction before next test
MEMORY_ABORT_PCT = 95.0  # Stop — system is about to OOM
# Same-model eviction: even when the next test uses the same model, evict if
# memory exceeds this after the previous test. KV cache from long inference
# compounds into the next test's KV cache allocation.
# (Observed: gemma-4-26b at 82% post-P-V02 crashed at 92%
# during P-R06. Same model, no eviction, compounding KV cache = crash.)
MEMORY_SAME_MODEL_EVICT_PCT = 78.0
# After this many consecutive "DOM stable but API empty" cycles, assume OWUI 0.9.5+
# is not going to commit the response via API (thinking-model commit delay) and let
# the caller's DOM fallback extract the response directly from the page.
DOM_STABLE_API_EMPTY_MAX = 3
