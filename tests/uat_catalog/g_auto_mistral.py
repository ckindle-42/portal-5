"""UAT catalog group: auto-mistral (Mistral workspace)."""
from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "WS-17",
        "name": "Mistral Reasoner — Multi-Stakeholder OT Problem",
        "section": "auto-mistral",
        "model_slug": "auto-mistral",
        "mlx_model": "lmstudio-community/Magistral-Small-2509-MLX-8bit",
        "timeout": 240,
        "workspace_tier": "mlx_small",
        "prompt": (
            "A utility CISO wants full EDR on all OT workstations for security visibility. "
            "The OT engineering manager says any agent on OT hosts risks process instability "
            "and violates vendor support agreements. Legal says a recent ransomware near-miss "
            "means the board now requires 'demonstrable endpoint monitoring' or they face "
            "personal liability. Operations says downtime costs $180K/hour. "
            "Find a path through this that all three can accept."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "CISO/security perspective addressed",
                "keywords": [
                    "chief information security",
                    "ciso",
                    "security officer",
                    "security team",
                    "security perspective",
                    "security concern",
                    "edr",
                    "endpoint",
                ],
            },
            {
                "type": "contains",
                "label": "OT/Legal/Operations perspectives",
                "keywords": ["legal", "operat"],
            },
            {
                "type": "any_of",
                "label": "Network-based monitoring",
                "keywords": [
                    "passive",
                    "network monitor",
                    "claroty",
                    "dragos",
                    "nta",
                    "network-based",
                    "network visibility",
                    "ids",
                    "ips",
                    "intrusion detection",
                    "anomaly detection",
                    "tap",
                    "span",
                    "sensor",
                    "network traffic",
                    "network detection",
                    "agentless",
                    "agent-less",
                    "agent free",
                    "without agent",
                    "no agent",
                ],
            },
            {
                "type": "any_of",
                "label": "Specific recommendation",
                "keywords": [
                    "recommend",
                    "propose",
                    "suggest",
                    "solution",
                    "best approach",
                    "optimal",
                    "conclude",
                    "best option",
                    "approach",
                    "path",
                    "strategy",
                    "framework",
                ],
            },
            {"type": "min_length", "label": "Substantive response", "chars": 600},
        ],
    },
    {
        "id": "P-R01",
        "name": "Magistral Strategist — Reasoning Before Conclusion",
        "section": "auto-mistral",
        "model_slug": "magistralstrategist",
        "timeout": 240,
        "workspace_tier": "mlx_small",
        "prompt": (
            "A growing SaaS company (150 employees, $8M ARR) must decide between: "
            "(A) Building and managing their own data center for cost savings at scale, "
            "(B) Staying on AWS with reserved instances for cost optimization. "
            "The CFO pushed for (A) based on a back-of-napkin analysis. "
            "Reason through this carefully before recommending."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "TCO analysis",
                "keywords": ["tco", "total cost", "capex", "staffing"],
            },
            {
                "type": "contains",
                "label": "Both options analyzed",
                "keywords": ["data center", "aws"],
            },
            {
                "type": "any_of",
                "label": "Scale threshold discussed",
                "keywords": [
                    "scale",
                    "arr",
                    "size",
                    "threshold",
                    "break-even",
                    "breakeven",
                    "grows",
                    "growth",
                ],
            },
            {
                "type": "any_of",
                "label": "Clear recommendation",
                "keywords": [
                    "recommend",
                    "suggest",
                    "should",
                    "conclusion",
                    "better choice",
                    "best option",
                    "opt for",
                    "go with",
                ],
            },
        ],
    },]
