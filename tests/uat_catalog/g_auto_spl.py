"""UAT catalog group: auto-spl (SPL workspace)."""
from __future__ import annotations

from tests.uat_catalog._shared import REFUSAL_PHRASES, _CC01_ASSERTIONS, _CC01_ASSERTIONS_BENCH  # noqa: F401

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "WS-04",
        "name": "SPL Engineer — Refactor Slow Search",
        "section": "auto-spl",
        "model_slug": "auto-spl",
        "timeout": 160,
        "workspace_tier": "mlx_small",
        "prompt": (
            "Refactor this slow SPL search to use tstats for performance:\n"
            "index=windows EventCode=4624 LogonType=3 | stats count by src_ip, dest_host, user, _time | where count > 10\n"
            "Also explain why the original is slow and what tstats gains us."
        ),
        "assertions": [
            {"type": "contains", "label": "tstats used", "keywords": ["tstats"]},
            {"type": "contains", "label": "count filter preserved", "keywords": ["count", "> 10"]},
            {
                "type": "any_of",
                "label": "Performance explanation",
                "keywords": [
                    "tsidx",
                    "faster",
                    "performance",
                    "index",
                    "raw event",
                    "accelerat",
                    "tsmaps",
                    "bloom",
                ],
            },
            {
                "type": "not_contains",
                "label": "No threat intel detour",
                "keywords": ["threat intelligence", "attacker", "mitre att&ck"],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-S06",
        "name": "SPL Engineer — Redirects Non-SPL Request",
        "section": "auto-spl",
        "model_slug": "splunksplgineer",
        "timeout": 60,
        "workspace_tier": "mlx_small",
        "prompt": (
            "We just had a security incident. What frameworks should we use for our incident "
            "response and what tools do you recommend for threat hunting?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Redirects to SPL scope",
                "keywords": ["spl", "splunk", "redirect", "only", "scope", "my function"],
            },
            {
                "type": "not_contains",
                "label": "No IR framework answer",
                "keywords": ["nist 800-61", "sans ir", "mitre att&ck for ir", "step 1: identify"],
                "critical": True,
            },
        ],
    },]
