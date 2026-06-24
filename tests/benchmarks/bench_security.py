#!/usr/bin/env python3
"""Portal 5 — Security Model Benchmark (refactored package).

All implementation lives in the bench_security/ package.
This module is a thin re-export shim for backward compatibility.

Usage:
    python3 -m tests.benchmarks.bench_security [args...]
"""

from bench_security import (  # noqa: F401
    CHAIN_INHERITANCE,
    DEFAULT_WORKSPACES,
    DISCLAIMER_PATTERNS,
    EXEC_SEQUENCES,
    EXECUTION_WORKSPACES,
    MITRE_PATTERN,
    PIPELINE_API_KEY,
    PIPELINE_URL,
    PROMPT_MAX_TOKENS,
    PROMPTS,
    REQUEST_TIMEOUT,
    RESULTS_DIR,
    BenchConfig,
    call_pipeline,
    call_pipeline_exec,
    main,
    score_execution,
    score_handoff_quality,
    score_response,
)
