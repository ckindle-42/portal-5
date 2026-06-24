#!/usr/bin/env python3
"""Portal 5 — Security Model Benchmark (refactored package).

All implementation lives in the bench_security/ package.
This module is a thin re-export shim for backward compatibility.

Usage:
    python3 -m tests.benchmarks.bench_security [args...]
"""

# Re-export everything from the package for backward compat
# (any code doing 'from bench_security import ...' gets the same symbols)
from bench_security.__init__ import *  # noqa: F403
from bench_security.__init__ import main  # noqa: F401
