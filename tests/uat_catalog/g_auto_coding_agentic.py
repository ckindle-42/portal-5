"""UAT catalog group: auto-coding-agentic (Devstral 24B agentic coding workspace)."""

from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [  # -----------------------------------------------------------------------
    {
        "id": "WS-02A",
        "name": "Agentic Coder — Bug Fix Plan",
        # BUILD_PROGRAM_ALIAS_RETIRE_V1.md Phase 3: "auto-coding-agentic"
        # retired, folded into auto-coding's "laguna" variant.
        "section": "auto-coding (agentic/laguna)",
        "model_slug": "auto-coding",
        "route_params": {"variant": "laguna"},
        "via_dispatcher": True,
        "timeout": 300,
        "workspace_tier": "ollama",
        "prompt": (
            "I have a Python function that's supposed to calculate a running average but "
            "returns None instead of the computed value. Explain how you would diagnose "
            "and fix this bug — describe the likely cause, the fix, and how you would verify "
            "the fix works. Include example code. Do NOT use any tools or execute code — "
            "respond with text and inline code only."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Diagnoses missing return",
                "keywords": ["return", "missing", "None", "forgot", "implicit", "no return"],
            },
            {
                "type": "any_of",
                "label": "Shows fix with code",
                "keywords": ["def ", "return ", "average", "fix", "corrected"],
            },
            {"type": "min_length", "label": "Substantive response", "chars": 400},
        ],
    },
    {
        "id": "P-D-CA01",
        "name": "Agentic Coder — Refactor Plan with Targeted Edits",
        # BUILD_PROGRAM_ALIAS_RETIRE_V1.md Phase 3: "auto-coding-agentic"
        # retired, folded into auto-coding's "laguna" variant.
        "section": "auto-coding (agentic/laguna)",
        "model_slug": "auto-coding",
        "route_params": {"variant": "laguna"},
        "via_dispatcher": True,
        "timeout": 300,
        "workspace_tier": "ollama",
        "prompt": (
            "I need to add input validation to an existing Flask route. The route currently "
            "accepts POST JSON with 'username' and 'email' fields but does no validation. "
            "Describe your approach: (1) what to check before any code changes, "
            "(2) the minimal targeted edit to add validation, (3) how to verify the change. "
            "Respond as text with inline code — do NOT execute code or use tools."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Identifies validation requirements",
                "keywords": ["validate", "check", "empty", "required", "email", "format"],
            },
            {
                "type": "any_of",
                "label": "Shows code edit",
                "keywords": ["request.json", "400", "abort", "jsonify", "if not", "raise"],
            },
            {
                "type": "any_of",
                "label": "Mentions testing/verification",
                "keywords": ["test", "verify", "curl", "assert", "confirm", "pytest"],
            },
            {"type": "min_length", "label": "Substantive response", "chars": 500},
        ],
    },
    # ── Workspace smoke tests (uncovered auto-* coverage) ─────────────────────
    {
        "id": "WS-26",
        "name": "Uncensored Agentic Coder — Refactor Plan",
        # BUILD_PROGRAM_ALIAS_RETIRE_V1.md Phase 3: "auto-coding-uncensored-agentic"
        # retired, folded into auto-coding's "uncensored-agentic" variant.
        "section": "auto-coding (uncensored-agentic)",
        "model_slug": "auto-coding",
        "route_params": {"variant": "uncensored-agentic"},
        "via_dispatcher": True,
        "timeout": 180,
        "workspace_tier": "ollama",
        "prompt": (
            "I have a 500-line Python module with 8 functions, no tests, and globals used "
            "as state. Describe a step-by-step refactor plan to make it testable: "
            "eliminate globals, extract a class, and add a pytest fixture. "
            "Be specific about what to do in each step."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Step-by-step structure",
                "keywords": ["step", "first", "1.", "1)", "phase", "then"],
            },
            {
                "type": "any_of",
                "label": "Class extraction mentioned",
                "keywords": ["class", "encapsulate", "object", "__init__"],
            },
            {
                "type": "any_of",
                "label": "Testing addressed",
                "keywords": ["pytest", "fixture", "test", "mock", "assert"],
            },
            {"type": "min_length", "label": "Substantive plan", "chars": 400},
        ],
    },
    {
        "id": "WS-27",
        "name": "Agentic Lite — SWE Task Decomposition",
        # BUILD_PROGRAM_ALIAS_RETIRE_V1.md Phase 3: "auto-agentic-lite"
        # retired, folded into auto-coding's "lite" variant.
        "section": "auto-coding (agentic/lite)",
        "model_slug": "auto-coding",
        "route_params": {"variant": "lite"},
        "via_dispatcher": True,
        "timeout": 180,
        "workspace_tier": "ollama",
        "prompt": (
            "Break down this task into actionable subtasks: "
            "Add rate limiting to a FastAPI endpoint using Redis. "
            "List what files to create or modify, what dependencies to add, "
            "and what tests to write."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Files mentioned",
                "keywords": ["requirements", "pyproject", "main.py", ".py", "redis", "middleware"],
            },
            {
                "type": "any_of",
                "label": "Dependencies addressed",
                "keywords": ["redis", "slowapi", "limits", "aioredis", "install", "pip", "uv"],
            },
            {
                "type": "any_of",
                "label": "Testing mentioned",
                "keywords": ["test", "pytest", "assert", "mock", "rate limit"],
            },
            {"type": "min_length", "label": "Substantive decomposition", "chars": 300},
        ],
    },
]
