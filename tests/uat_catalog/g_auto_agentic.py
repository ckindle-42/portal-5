"""UAT catalog group: auto-agentic (agentic workspace)."""

from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [  # -----------------------------------------------------------------------
    {
        "id": "WS-03",
        "name": "Agentic Coder Heavy — Flask Migration Plan",
        # BUILD_PROGRAM_ALIAS_RETIRE_V1.md Phase 3: "auto-agentic" retired,
        # folded into auto-coding's "heavy" variant (_LEGACY_WORKSPACE_ALIASES).
        # OWUI mediates the browser test path and cannot carry ?variant=, so
        # this is routed via_dispatcher (direct-to-pipeline) instead.
        "section": "auto-coding (agentic/heavy)",
        "model_slug": "auto-coding",
        "route_params": {"variant": "heavy"},
        "via_dispatcher": True,
        "timeout": 360,
        "workspace_tier": "ollama",
        "prompt": (
            "I have a Flask monolith split across app.py (routes), models.py (SQLAlchemy ORM), "
            "and utils.py (helpers, 40+ functions). I want to refactor it into a proper Flask "
            "application factory pattern with Blueprints. Produce your answer as text with inline "
            "code snippets — do NOT execute bash or Python to create files. Include: "
            "(1) the target directory structure, (2) a file-by-file migration map showing what moves where, "
            "(3) the new __init__.py using create_app(), and (4) an example blueprint showing "
            "how one existing route group migrates."
        ),
        "assertions": [
            {
                "type": "contains",
                "label": "Directory structure shown",
                "keywords": ["__init__.py", "blueprint"],
            },
            {"type": "contains", "label": "create_app factory", "keywords": ["create_app"]},
            {
                "type": "any_of",
                "label": "Blueprint registration",
                "keywords": [
                    "register_blueprint",
                    "app.register_blueprint",
                    "blueprint(",
                    ".register(",
                    "register the blueprint",
                ],
                "critical": False,
            },
            {"type": "min_length", "label": "Substantive response", "chars": 1200},
        ],
    },
    {
        "id": "P-D17",
        "name": "Codebase WIKI — Inferred Sections Labeled",
        "section": "auto-agentic",
        "model_slug": "codebasewikidocumentationskill",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Generate WIKI documentation for this incomplete class signature. "
            "I have not provided the method bodies — apply your HARD CONSTRAINT: "
            "any section based on inference rather than direct code inspection MUST be "
            "labeled '[Inferred — verify with source]'. Document what you can determine "
            "from the interface alone:\n\n"
            "class EventBus:\n"
            "    def subscribe(self, event_type: str, handler: Callable) -> str: ...\n"
            "    def unsubscribe(self, subscription_id: str) -> bool: ...\n"
            "    def publish(self, event_type: str, payload: dict) -> int: ...\n"
            "    def _dispatch(self, event_type: str, payload: dict) -> None: ..."
        ),
        "assertions": [
            {
                "type": "contains",
                "label": "Public methods documented",
                "keywords": ["subscribe", "unsubscribe", "publish"],
            },
            {
                "type": "any_of",
                "label": "_dispatch marked internal",
                "keywords": ["internal", "private", "_dispatch"],
            },
            {
                "type": "any_of",
                "label": "Inferred label used",
                "keywords": [
                    "inferred",
                    "verify with source",
                    "[inferred",
                    "based on inference",
                    "not explicitly",
                    "unclear from",
                ],
                "critical": False,
            },
        ],
    },
]
