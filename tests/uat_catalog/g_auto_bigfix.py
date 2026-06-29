"""UAT catalog group: auto-bigfix (HCL BigFix endpoint management specialist)."""

from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [  # -----------------------------------------------------------------------
    {
        "id": "WS-BF-01",
        "name": "BigFix — Relevance Language Expression",
        "section": "auto-bigfix",
        "model_slug": "auto-bigfix",
        "timeout": 180,
        "workspace_tier": "ollama",
        "prompt": (
            "Write a BigFix Relevance Language expression that returns a list of "
            "Windows endpoints where the operating system is Windows 10 or Windows 11 "
            "AND the last login was more than 30 days ago. "
            "Use proper Relevance syntax with 'whose' clauses."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Relevance syntax present",
                "keywords": [
                    "whose",
                    "of it",
                    "exists",
                    "computer name",
                    "name of operating system",
                ],
                "critical": True,
            },
            {
                "type": "any_of",
                "label": "Windows OS filter",
                "keywords": ["Windows 10", "Windows 11", "windows", "operating system"],
            },
            {
                "type": "any_of",
                "label": "Time-based filter",
                "keywords": ["30 day", "last logged", "login", "day", "now - 30"],
            },
            {"type": "min_length", "label": "Substantive response", "chars": 200},
        ],
    },
    {
        "id": "WS-BF-02",
        "name": "BigFix — REST API Patch Compliance Query",
        "section": "auto-bigfix",
        "model_slug": "auto-bigfix",
        "timeout": 180,
        "workspace_tier": "ollama",
        "prompt": (
            "Write a BigFix REST API call using Python requests to query the "
            "NERC CIP compliance dashboard for all endpoints where critical patches "
            "are missing (relevance: patch count > 0). Include authentication headers, "
            "the endpoint URL structure, and how to parse the JSON response."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "REST API endpoint structure",
                "keywords": ["api/v1", "/api/", "bigfix", "port 52311", ":52311", "https://"],
            },
            {
                "type": "any_of",
                "label": "Python requests usage",
                "keywords": [
                    "requests.get",
                    "requests.post",
                    "import requests",
                    "session",
                    "auth=",
                ],
            },
            {
                "type": "any_of",
                "label": "Response parsing",
                "keywords": ["json()", ".json", "response", "parse", "data", "result"],
            },
            {"type": "min_length", "label": "Substantive response", "chars": 300},
        ],
    },
]
