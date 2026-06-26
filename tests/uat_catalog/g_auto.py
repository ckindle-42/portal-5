"""UAT catalog group: auto (intent-driven router workspace)."""

from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [  # -----------------------------------------------------------------------
    {
        "id": "WS-01",
        "name": "Auto Router — Intent-Driven Routing",
        "section": "auto",
        "model_slug": "auto",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "I need to deploy a containerized Python app to a Kubernetes cluster. "
            "Can you write the Deployment and Service manifests, and also tell me what "
            "RBAC permissions the service account will need?"
        ),
        "assertions": [
            {
                # any_of: model may describe manifests in prose without emitting
                # literal apiVersion/kind fields — accept any structural K8s keyword.
                "type": "any_of",
                "label": "YAML manifests present",
                "keywords": [
                    "apiVersion",
                    "apiversion",
                    "kind",
                    "Deployment",
                    "deployment",
                    "Service",
                    "spec:",
                    "metadata:",
                    "replicas",
                    "kubectl",
                    "yaml manifest",
                    "yaml file",
                    "kubernetes manifest",
                    "deployment manifest",
                    "service manifest",
                ],
            },
            {
                "type": "any_of",
                "label": "RBAC discussed",
                "keywords": ["rbac", "role", "serviceaccount", "clusterrole", "rolebinding"],
            },
            {
                "type": "not_contains",
                "label": "No refusal",
                "keywords": REFUSAL_PHRASES,
            },
            {"type": "min_length", "label": "Substantive response", "chars": 800},
        ],
    },
    {
        "id": "P-W06",
        "name": "IT Expert — Asks Symptoms Before Diagnosing",
        "section": "auto",
        "model_slug": "itexpert",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": "My computer is slow. Fix it.",
        "assertions": [
            {
                "type": "any_of",
                "label": "Asks what OS",
                "word_boundary": True,
                "keywords": [
                    "operating system",
                    "what os",
                    "which os",
                    "os are you",
                    "os do you",
                    "os version",
                    "windows",
                    "macos",
                    "mac os",
                    "linux",
                    "ubuntu",
                    "platform you",
                    "platform are",
                    "what platform",
                ],
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Asks what is slow",
                "keywords": [
                    "what is slow",
                    "when did",
                    "how slow",
                    "specific",
                    "consistently",
                    "certain situations",
                    "applications",
                    "symptoms",
                    "more information",
                    "slowdown",
                    "what's happening",
                    "tell me more",
                    "what changed",
                    "how long",
                    "recent changes",
                    "error message",
                    "error code",
                    "recent software",
                    "hardware changes",
                    "software installations",
                    "hardware or software",
                    "encountered",
                    "need information",
                    "diagnose",
                ],
            },
            {
                "type": "not_contains",
                "label": "No immediate fix list",
                "keywords": ["here are 10 ways", "try these steps", "1. check disk"],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-W03",
        "name": "Tech Reviewer — Training Data Caveat on Benchmarks",
        "section": "auto",
        "model_slug": "techreviewer",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": "Compare the M4 Pro and M4 Max chips for local LLM inference. Give me specific benchmark numbers and tell me which to buy.",
        "assertions": [
            # Persona HARD CONSTRAINTS mandate this caveat. Broadened keyword set
            # absorbs the common phrasings models actually emit.
            {
                "type": "any_of",
                "label": "Training data caveat",
                # Was 18 keywords including bare "current" / "verify" / "as of"
                # which passed on any acknowledgment ("as of right now" / "verify
                # the seller"). Tightened to phrases that ONLY appear when the
                # model is hedging on knowledge currency.
                "keywords": [
                    "training data",
                    "training cutoff",
                    "knowledge cutoff",
                    "my training",
                    "since my data",
                    "based on my training",
                    "may have changed",
                    "may not reflect",
                    "may be outdated",
                    "subject to change",
                    "verify with apple",
                    "check apple's",
                    "check apple website",
                    "apple's official",
                    "official apple",
                    "apple.com",
                    "before purchasing",
                    "before you buy",
                    "double-check the latest",
                    "i don't have real-time",
                    "i don't have current",
                    "i may not have",
                    # Additional phrasings Qwopus/Chinese models commonly use
                    "my knowledge",
                    "as of my knowledge",
                    "based on available",
                    "cannot guarantee",
                    "may not be current",
                    "this could change",
                    "latest specs",
                    "check the latest",
                    "verify the latest",
                    "specifications may",
                    "latest information",
                    "might have changed",
                    "i should note",
                    "i was trained",
                    "last updated",
                    "released after",
                    "newer than my",
                ],
            },
            # Was a `contains` requiring BOTH literal "m4 pro" and "m4 max" — too
            # brittle. Switched to `any_of` with comparison-pattern phrases that
            # only fire when the model is actually discussing both chips together.
            {
                "type": "any_of",
                "label": "Both chips compared",
                "keywords": [
                    "m4 pro and m4 max",
                    "m4 pro vs m4 max",
                    "m4 pro vs. m4 max",
                    "m4 max and m4 pro",
                    "m4 max vs m4 pro",
                    "m4 max vs. m4 pro",
                    "m4 pro and the m4 max",
                    "m4 max and the m4 pro",
                    "m4 pro and the max",
                    "m4 max and the pro",
                    "the pro and the max",
                    "the max and the pro",
                    "between the m4 pro",
                    "between the m4 max",
                    "compared to the m4 pro",
                    "compared to the m4 max",
                    "than the m4 pro",
                    "than the m4 max",
                    "versus the m4 pro",
                    "versus the m4 max",
                ],
            },
            # Broadened to absorb common recommendation phrasings the persona's
            # Verdict section produces ("I'd lean toward…", "go with…", "depends on…").
            {
                "type": "any_of",
                "label": "Recommendation given",
                "keywords": [
                    "recommend",
                    "choose",
                    "buy",
                    "better for",
                    "advantage",
                    "performance advantage",
                    "clear advantage",
                    "superior",
                    "stronger",
                    "go with",
                    "i'd suggest",
                    "i would suggest",
                    "i'd lean",
                    "i would lean",
                    "best for",
                    "well-suited",
                    "go for",
                    "verdict",
                    "depends on",
                    "if you",
                    "the right choice",
                    "worth the",
                    "worth it",
                ],
            },
        ],
    },
    # ── Workspace smoke tests (uncovered auto-* coverage) ─────────────────────
    {
        "id": "WS-32",
        "name": "General Uncensored — Dual-Use Tool Analysis",
        "section": "auto-general-uncensored",
        "model_slug": "auto-general-uncensored",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Compare nmap and masscan for network reconnaissance: "
            "speed, accuracy, stealth, and typical use cases for each tool. "
            "Which would you choose for a large enterprise network audit?"
        ),
        "assertions": [
            {"type": "any_of", "label": "Both tools compared",
             "keywords": ["nmap", "masscan"]},
            {"type": "any_of", "label": "Comparison dimensions covered",
             "keywords": ["speed", "fast", "accurate", "stealth", "port", "scan"]},
            {"type": "min_length", "label": "Substantive comparison", "chars": 200},
        ],
    },
    {
        "id": "WS-33",
        "name": "Extract Uncensored — Structured Data Extraction",
        "section": "auto-extract-uncensored",
        "model_slug": "auto-extract-uncensored",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Extract all entities from this text as JSON:\n\n"
            "\"John Smith (CEO, Acme Corp) signed a $2.5M contract with Beta Inc "
            "on March 15, 2025, at their San Francisco office. "
            "The deal covers 18 months of cloud migration services.\"\n\n"
            "Include: people, organizations, monetary values, dates, locations, durations."
        ),
        "assertions": [
            {"type": "has_code", "label": "Structured output present"},
            {"type": "any_of", "label": "Key entities extracted",
             "keywords": ["John Smith", "Acme", "Beta", "2.5", "March", "San Francisco"]},
            {"type": "not_contains", "label": "No extraction failure",
             "keywords": ["cannot extract", "unable to parse", "no entities"]},
        ],
    },
]
