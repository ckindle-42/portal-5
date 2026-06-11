"""UAT catalog group: tools-specialist (ToolACE-2.5, purpose-trained tool-calling)."""
from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "WS-TOOLS-01",
        "name": "Tool Composer — Multi-Step Tool Plan",
        "section": "tools-specialist",
        "model_slug": "tools-specialist",
        "timeout": 180,
        "workspace_tier": "ollama",
        "prompt": (
            "I need to: (1) execute Python code that reads /workspace/data.csv and counts rows, "
            "(2) store the row count in memory under the key 'row_count', "
            "(3) recall 'row_count' and return it to me. "
            "Plan the tool calls in order. Available tools: execute_python, remember, recall."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "execute_python referenced",
                "keywords": [
                    "execute_python",
                    "execute python",
                    "run python",
                    "python code",
                    "python",
                    "execute code",
                    "run code",
                    "code execution",
                ],
            },
            {
                "type": "any_of",
                "label": "remember/store referenced",
                "keywords": ["remember", "store", "save", "key", "row_count", "memory"],
            },
            {
                "type": "any_of",
                "label": "Sequential plan present",
                "keywords": [
                    "step",
                    "first",
                    "then",
                    "next",
                    "order",
                    "sequence",
                    "1.",
                    "2.",
                    "3.",
                    "finally",
                    "afterward",
                    "followed by",
                    "after that",
                    "in order",
                    "call",
                    "invoke",
                ],
            },
            {"type": "min_length", "label": "Substantive response", "chars": 100},
        ],
    },
    {
        "id": "P-TOOLS-01",
        "name": "toolcomposer persona — File Count and Store",
        "section": "tools-specialist",
        "model_slug": "toolcomposer",
        "timeout": 180,
        "workspace_tier": "ollama",
        "prompt": (
            "I need to count the lines in /workspace/report.txt using execute_python, "
            "then store the count in memory as 'line_count'. "
            "What tool calls do you plan, and in what order?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "execute_python in plan",
                "keywords": ["execute_python", "execute python", "python", "run code"],
            },
            {
                "type": "any_of",
                "label": "memory store in plan",
                "keywords": ["remember", "store", "save", "line_count", "memory"],
            },
            {
                "type": "any_of",
                "label": "Ordered steps",
                "keywords": ["step", "first", "then", "next", "1.", "2.", "order"],
            },
        ],
    },]
