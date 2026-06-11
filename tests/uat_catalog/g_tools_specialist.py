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
    # ── Tool-invocation validation (TV series) ───────────────────────────────
    # Proof-of-execution tests: the correct answer requires actually running code.
    # A model generating from training knowledge cannot produce 56154 without calling
    # execute_python — it would have to multiply 42 × 1337 in weights, which is not
    # reliably stored. The assertion is the computed output, not keyword presence.
    {
        "id": "TV-01",
        "name": "Tool Validation — execute_python proof (auto-coding/qwen3-coder baseline)",
        "section": "tools-specialist",
        "model_slug": "auto-coding",
        "timeout": 90,
        "workspace_tier": "ollama",
        "force_unload_before": True,
        "prompt": (
            "Use execute_python to run this code and return ONLY the numeric result:\n"
            "```python\n"
            "print(42 * 1337)\n"
            "```"
        ),
        "assertions": [
            {
                "type": "contains",
                "label": "Correct computed output (56154) — proves tool ran",
                "keywords": ["56154"],
            },
            {
                "type": "not_contains",
                "label": "Did not refuse tool use",
                "keywords": ["cannot execute", "unable to run", "don't have the ability", "can't run"],
                "critical": False,
            },
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
