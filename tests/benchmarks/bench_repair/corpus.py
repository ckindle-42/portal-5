"""Corpus load + exam fingerprint (gsha changes iff corpus/prompts/Ollama version change)."""

from __future__ import annotations

import hashlib
import json

import httpx

from portal.platform.data_loader import load_data
from tests.benchmarks.bench_repair.config import (
    OLLAMA_URL,
    ONE_SHOT_TEMPLATE,
    REPAIR_TEMPLATE,
)


def load_corpus() -> list[dict]:
    return load_data("tests/data", "bench_capability_c2_problems")


def _ollama_version() -> str:
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/version", timeout=5)
        r.raise_for_status()
        return r.json().get("version", "unknown")
    except Exception as exc:  # noqa: BLE001
        return f"unreachable:{exc.__class__.__name__}"


def compute_gsha(corpus: list[dict]) -> tuple[str, dict]:
    """Return (gsha, breakdown) where breakdown records the inputs for auditability."""
    corpus_bytes = json.dumps(corpus, sort_keys=True, separators=(",", ":")).encode()
    corpus_sha = hashlib.sha256(corpus_bytes).hexdigest()[:16]
    prompts_sha = hashlib.sha256((ONE_SHOT_TEMPLATE + REPAIR_TEMPLATE).encode()).hexdigest()[:16]
    ollama_ver = _ollama_version()
    composite = hashlib.sha256((corpus_sha + prompts_sha + ollama_ver).encode()).hexdigest()[:12]
    return composite, {
        "corpus_sha": corpus_sha,
        "prompts_sha": prompts_sha,
        "ollama_version": ollama_ver,
        "gsha": composite,
    }
