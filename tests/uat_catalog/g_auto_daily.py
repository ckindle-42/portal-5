"""UAT catalog group: auto-daily (daily-driver workspace)."""
from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "WS-DD-01",
        "name": "Daily Driver — Casual Chat Snap (no reasoning leak)",
        "section": "auto-daily",
        "model_slug": "auto-daily",
        "timeout": 60,
        "workspace_tier": "mlx_small",
        "mlx_model": "mlx-community/gemma-4-26b-a4b-it-4bit",
        "prompt": "What's a quick lunch I can make in 10 minutes if I have eggs, bread, and a tomato?",
        "assertions": [
            {"type": "min_length", "label": "Substantive response", "chars": 200},
            {"type": "not_contains", "label": "No refusal", "keywords": REFUSAL_PHRASES},
            {
                "type": "not_contains",
                "label": "No reasoning chain leak",
                "keywords": ["<think>", "</think>", "<thinking>", "</thinking>"],
            },
        ],
    },
    {
        "id": "WS-DD-02",
        "name": "Daily Driver — Persona Self-Description",
        "section": "auto-daily",
        "model_slug": "dailydriver",
        "timeout": 60,
        "workspace_tier": "mlx_small",
        "mlx_model": "mlx-community/gemma-4-26b-a4b-it-4bit",
        "prompt": "Hi! What can you help me with today?",
        "assertions": [
            {"type": "min_length", "label": "Substantive response", "chars": 200},
            {
                "type": "any_of",
                "label": "Describes daily-driver role",
                "keywords": [
                    "daily",
                    "everyday",
                    "general",
                    "writing",
                    "summari",
                    "planning",
                    "assistant",
                ],
            },
            {"type": "not_contains", "label": "No reasoning leak", "keywords": ["<think>"]},
        ],
    },
    {
        "id": "WS-DD-03",
        "name": "Daily Driver — Writing Rewrite Preserves Meaning",
        "section": "auto-daily",
        "model_slug": "dailydriver",
        "timeout": 60,
        "workspace_tier": "mlx_small",
        "mlx_model": "mlx-community/gemma-4-26b-a4b-it-4bit",
        "prompt": (
            "Rewrite this for clarity, keep my voice: 'so basically what we found "
            "is that the thing we thought was broken wasn't actually broken it was "
            "just configured wrong which honestly is kind of worse'"
        ),
        "assertions": [
            {"type": "min_length", "label": "Substantive response", "chars": 80},
            {
                "type": "any_of",
                "label": "Preserves core concepts",
                "keywords": ["broken", "configured", "misconfigured", "configuration"],
            },
            {"type": "not_contains", "label": "No reasoning leak", "keywords": ["<think>"]},
        ],
    },
    {
        "id": "WS-DD-04",
        "name": "Daily Driver — Summarization",
        "section": "auto-daily",
        "model_slug": "dailydriver",
        "timeout": 90,
        "workspace_tier": "mlx_small",
        "mlx_model": "mlx-community/gemma-4-26b-a4b-it-4bit",
        "prompt": (
            "Summarize this passage in 4 sentences:\n\n"
            "It is a truth universally acknowledged, that a single man in possession "
            "of a good fortune, must be in want of a wife. However little known the "
            "feelings or views of such a man may be on his first entering a "
            "neighbourhood, this truth is so well fixed in the minds of the "
            "surrounding families, that he is considered the rightful property of "
            "some one or other of their daughters. 'My dear Mr. Bennet,' said his "
            "lady to him one day, 'have you heard that Netherfield Park is let at "
            "last?' Mr. Bennet replied that he had not. 'But it is,' returned she; "
            "'for Mrs. Long has just been here, and she told me all about it.' Mr. "
            "Bennet made no answer. 'Do not you want to know who has taken it?' "
            "cried his wife impatiently. 'You want to tell me, and I have no "
            "objection to hearing it.' This was invitation enough. 'Why, my dear, "
            "you must know, Mrs. Long says that Netherfield is taken by a young man "
            "of large fortune from the north of England; that he came down on "
            "Monday in a chaise and four to see the place, and was so much "
            "delighted with it that he agreed with Mr. Morris immediately; that he "
            "is to take possession before Michaelmas, and some of his servants are "
            "to be in the house by the end of next week.' 'What is his name?' "
            "'Bingley.'"
        ),
        "assertions": [
            {"type": "min_length", "label": "Substantive summary", "chars": 150},
            {
                "type": "any_of",
                "label": "Key entities preserved",
                "keywords": ["Bennet", "Bingley", "Netherfield", "fortune", "wife"],
            },
            {"type": "not_contains", "label": "No reasoning leak", "keywords": ["<think>"]},
        ],
    },
    {
        "id": "WS-DD-05",
        "name": "Daily Driver — Planning Output",
        "section": "auto-daily",
        "model_slug": "dailydriver",
        "timeout": 90,
        "workspace_tier": "mlx_small",
        "mlx_model": "mlx-community/gemma-4-26b-a4b-it-4bit",
        "prompt": (
            "Help me plan a focused 90-minute work block for tomorrow: I need to "
            "reply to 4 emails, draft a one-page memo, and review a colleague's PR."
        ),
        "assertions": [
            {"type": "min_length", "label": "Substantive plan", "chars": 300},
            {
                "type": "any_of",
                "label": "Time-structured response",
                "keywords": [
                    "minutes",
                    "min",
                    "block",
                    "first",
                    "then",
                    "next",
                    "finally",
                    ":00",
                    ":15",
                    ":30",
                    ":45",
                ],
            },
            {
                "type": "any_of",
                "label": "Addresses all three tasks",
                "keywords": ["email", "memo", "PR", "pull request", "review"],
            },
            {"type": "not_contains", "label": "No reasoning leak", "keywords": ["<think>"]},
        ],
    },
    {
        "id": "WS-DD-06",
        "name": "Daily Driver — Light Technical (git safety)",
        "section": "auto-daily",
        "model_slug": "dailydriver",
        "timeout": 60,
        "workspace_tier": "mlx_small",
        "mlx_model": "mlx-community/gemma-4-26b-a4b-it-4bit",
        "prompt": "What does this git command do, and is it safe? git reset --hard origin/main",
        "assertions": [
            {"type": "min_length", "label": "Substantive answer", "chars": 200},
            {"type": "contains", "label": "Names the command", "keywords": ["reset"]},
            {
                "type": "any_of",
                "label": "Flags destructiveness",
                "keywords": [
                    "discard",
                    "lose",
                    "lost",
                    "overwrit",
                    "destructive",
                    "careful",
                    "irreversible",
                    "cannot be undone",
                    "uncommitted",
                    "permanent",
                ],
            },
            {"type": "not_contains", "label": "No refusal", "keywords": REFUSAL_PHRASES},
        ],
    },
    {
        "id": "WS-DD-07",
        "name": "Daily Driver — Escalation Honesty",
        "section": "auto-daily",
        "model_slug": "dailydriver",
        "timeout": 120,
        "workspace_tier": "mlx_small",
        "mlx_model": "mlx-community/gemma-4-26b-a4b-it-4bit",
        "prompt": (
            "Write a complete production-grade Python web server with JWT auth, "
            "rate limiting, OpenAPI docs, and pytest tests for every route."
        ),
        "assertions": [
            {"type": "min_length", "label": "Substantive response", "chars": 400},
            {
                "type": "any_of",
                "label": "Acknowledges scope / suggests proper workspace",
                "keywords": [
                    "auto-coding",
                    "Code Expert",
                    "larger",
                    "bigger",
                    "out of",
                    "beyond",
                    "specialist",
                    "workspace",
                    "starter",
                    "outline",
                    "skeleton",
                    "scaffold",
                ],
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Still attempts some content",
                "keywords": ["def ", "import ", "FastAPI", "Flask", "from ", "@app"],
            },
        ],
    },
    {
        "id": "WS-DD-08",
        "name": "Daily Driver — Memory-Augmented Variant (personalassistant)",
        "section": "auto-daily",
        "model_slug": "personalassistant",
        "timeout": 60,
        "workspace_tier": "mlx_small",
        "mlx_model": "mlx-community/gemma-4-26b-a4b-it-4bit",
        "prompt": "Hello, what's your role here?",
        "assertions": [
            {"type": "min_length", "label": "Substantive response", "chars": 150},
            {
                "type": "any_of",
                "label": "Mentions memory/continuity",
                "keywords": [
                    "remember",
                    "preference",
                    "recall",
                    "memory",
                    "continuity",
                    "context",
                    "across conversations",
                ],
            },
            {"type": "not_contains", "label": "No reasoning leak", "keywords": ["<think>"]},
        ],
    },]
