"""Portal 5.2.1 Pipeline entry point."""

from __future__ import annotations

import logging
import multiprocessing
import os

import uvicorn


def main() -> None:
    log_level = os.environ.get("LOG_LEVEL", "INFO").lower()
    port = int(os.environ.get("PIPELINE_PORT", "9099"))

    # Workers: default to CPU count, capped at 4 for memory-bounded workloads.
    # Pipeline is mostly I/O bound (proxying to Ollama) so workers > 1 helps.
    default_workers = min(multiprocessing.cpu_count(), 4)
    workers = int(os.environ.get("PIPELINE_WORKERS", default_workers))

    # ── Prometheus multiprocess mode ─────────────────────────────────────────
    # When workers > 1, each process needs a shared directory to write metrics.
    # Must be set BEFORE prometheus_client is imported (happens in router_pipe).
    # With workers=1, this is harmless overhead.
    if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        import tempfile

        _mp_dir = tempfile.mkdtemp(prefix="portal_metrics_")
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = _mp_dir
        logging.debug("Prometheus multiprocess dir: %s", _mp_dir)

    logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))
    logging.info("Starting Portal Pipeline on :%d with %d worker(s)", port, workers)

    uvicorn.run(
        "portal_pipeline.router_pipe:app",
        host="0.0.0.0",
        port=port,
        workers=workers,
        log_level=log_level,
        access_log=True,
    )


if __name__ == "__main__":
    main()
