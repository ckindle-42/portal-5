"""Probe modules. Importing this package registers every probe with the
framework registry. Reference probes are implemented here; the remaining ledger
consumers are implemented by the executor in Phase 3 against the spec cards in
the task file, each as its own module added to ``_MODULES``."""

from __future__ import annotations

import importlib

_MODULES = (
    "router",
    "tool_preselect",
    "wiki_search",
    "attack_mapping",
    "harmful_intent",
    "memory",
    "refusal_classifier",
    "security_text",
    "hygiene",
    "compliance",
    "bully",
    "seccode",
    "rag",
    "media",
)

for _m in _MODULES:
    importlib.import_module(f"{__name__}.{_m}")
