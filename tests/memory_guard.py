"""Re-export shim — monitoring primitives live in portal_pipeline.router.monitor.

All callers that imported from tests.memory_guard continue to work unchanged.
"""

from portal_pipeline.router.monitor import (  # noqa: F401
    DEFAULT_OLLAMA_URL,
    DEFAULT_POLL_S,
    DEFAULT_RETRIES,
    DEFAULT_THRESHOLD_PCT,
    DEFAULT_TIMEOUT_S,
    free_ram_gb,
    memory_pct,
    purge_memory,
    restart_ollama,
    wait_for_drain,
    wait_for_drain_async,
    wait_for_model_loaded,
)
