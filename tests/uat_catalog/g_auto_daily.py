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
        "workspace_tier": "ollama",
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
        "workspace_tier": "ollama",
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
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Rewrite this for clarity, keep my voice: 'so basically what we found "
            "is that the thing we thought was broken wasn't actually broken it was "
            "just configured wrong which honestly is kind of worse'"
        ),
        "assertions": [
            {"type": "min_length", "label": "Substantive response", "chars": 80, "critical": False},
            {
                "type": "any_of",
                "label": "Preserves core concepts",
                "keywords": ["broken", "configured", "misconfigured", "configuration"],
                "critical": False,
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
        "workspace_tier": "ollama",
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
        "workspace_tier": "ollama",
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
        "workspace_tier": "ollama",
        "prompt": "What does this git command do, and is it safe? git reset --hard origin/main",
        "assertions": [
            {"type": "min_length", "label": "Substantive answer", "chars": 200},
            {
                "type": "any_of",
                "label": "Names the command",
                "keywords": [
                    "reset", "--hard", "git reset", "hard reset", "overwrites", "resets your",
                    "reset --hard", "reset --soft", "HEAD~", "HEAD^",
                    "undo commit", "revert commit",
                ],
            },
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
        "workspace_tier": "ollama",
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
        "workspace_tier": "ollama",
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
    },
    # ── Tool-capability tests (new generative suite) ──────────────────────────
    # These tests verify that the daily driver's expanded tool set actually works.
    # Each uses a prompt that can only produce the correct answer if the tool ran.
    {
        "id": "DD-TV-01",
        "name": "Daily Driver — execute_python proof (Gemma 4 QAT)",
        "section": "auto-daily",
        "model_slug": "auto-daily",
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
                "label": "Correct computed output (56154) — proves execute_python ran",
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
        "id": "WS-DD-09",
        "name": "Daily Driver — Web Search (live URL proof)",
        "section": "auto-daily",
        "model_slug": "auto-daily",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Use web_search to search for 'Python programming language' and tell me "
            "the URL of the first result you find."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "URL in response — proves web_search ran",
                "keywords": [
                    "http://", "https://", "python.org", "wikipedia.org",
                    "docs.python", "pypi.org", "realpython.com",
                ],
            },
            {
                "type": "min_length",
                "label": "Substantive response",
                "chars": 80,
                "critical": False,
            },
            {
                "type": "not_contains",
                "label": "No refusal",
                "keywords": REFUSAL_PHRASES,
                "critical": False,
            },
        ],
    },
    {
        "id": "WS-DD-10",
        "name": "Daily Driver — Create Word Document",
        "section": "auto-daily",
        "model_slug": "auto-daily",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Create a Word document titled 'Portal 5 Test' with one paragraph:\n"
            "'This document was generated by Portal 5 Daily Driver.'\n"
            "Tell me the filename it was saved as."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": ".docx filename in response — proves create_word_document ran",
                "keywords": [".docx", "Portal_5_Test", "portal-5-test", "portal5test"],
            },
            {
                "type": "not_contains",
                "label": "No tool error",
                "keywords": ["error", "failed to create", "unable to create"],
                "critical": False,
            },
        ],
    },
    {
        "id": "WS-DD-11",
        "name": "Daily Driver — Create Excel Spreadsheet",
        "section": "auto-daily",
        "model_slug": "auto-daily",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Create an Excel spreadsheet with these 3 data rows:\n"
            "Name, Age, City\n"
            "Alice, 30, New York\n"
            "Bob, 25, Chicago\n"
            "Tell me the filename it was saved as."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": ".xlsx filename in response — proves create_excel ran",
                "keywords": [".xlsx", "spreadsheet", "excel", "download"],
            },
            {
                "type": "not_contains",
                "label": "No tool error",
                "keywords": ["error", "failed to create", "unable to create"],
                "critical": False,
            },
        ],
    },
    {
        "id": "WS-DD-12",
        "name": "Daily Driver — Create PowerPoint Presentation",
        "section": "auto-daily",
        "model_slug": "auto-daily",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Create a PowerPoint presentation with these 3 slides:\n"
            "1. Title: 'Q3 Review', Content: 'Quarter overview'\n"
            "2. Title: 'Results', Content: 'Revenue up 12%'\n"
            "3. Title: 'Next Steps', Content: 'Continue current strategy'\n"
            "Tell me the filename it was saved as."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": ".pptx filename in response — proves create_powerpoint ran",
                "keywords": [".pptx", "presentation", "powerpoint", "download"],
            },
            {
                "type": "not_contains",
                "label": "No tool error",
                "keywords": ["error", "failed to create", "unable to create"],
                "critical": False,
            },
        ],
    },
    {
        "id": "WS-DD-13",
        "name": "Daily Driver — Memory Store + Recall Chain",
        "section": "auto-daily",
        "model_slug": "auto-daily",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Do these two steps in order:\n"
            "1. Use the remember tool to store the value 'portal5-uat-marker-2026' "
            "under the key 'uat_test_key'\n"
            "2. Use the recall tool to retrieve 'uat_test_key' and tell me exactly "
            "what value came back from the tool."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Recalled marker value in response — proves both memory tools ran",
                "keywords": ["portal5-uat-marker-2026", "portal5-uat", "uat_test_key", "uat-marker"],
            },
            {
                "type": "not_contains",
                "label": "No tool failure",
                "keywords": ["cannot recall", "unable to remember", "tool error"],
                "critical": False,
            },
        ],
    },
    {
        "id": "WS-DD-14",
        "name": "Daily Driver — Multi-Tool: Code + Document (end-to-end)",
        "section": "auto-daily",
        "model_slug": "auto-daily",
        "timeout": 150,
        "workspace_tier": "ollama",
        "prompt": (
            "Do this in two steps:\n"
            "1. Use execute_python to compute: sum(range(1, 101)) — the sum of 1 to 100.\n"
            "2. Create a Word document titled 'Computation Result' that contains "
            "the answer from step 1.\n"
            "Tell me both the computed answer and the filename of the document."
        ),
        "assertions": [
            {
                "type": "contains",
                "label": "Correct sum (5050) — proves execute_python ran",
                "keywords": ["5050"],
            },
            {
                "type": "any_of",
                "label": ".docx created — proves create_word_document ran",
                "keywords": [".docx", "Computation_Result", "computation", "download"],
            },
        ],
    },]
