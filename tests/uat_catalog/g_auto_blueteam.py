"""UAT catalog group: auto-blueteam (blue-team workspace)."""
from __future__ import annotations

from tests.uat_catalog._shared import REFUSAL_PHRASES, _CC01_ASSERTIONS, _CC01_ASSERTIONS_BENCH  # noqa: F401

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "WS-07",
        "name": "Blue Team — Multi-Stage Incident Triage",
        "section": "auto-blueteam",
        "model_slug": "auto-blueteam",
        "timeout": 180,
        "workspace_tier": "mlx_small",
        "mlx_model": "foundation-ai/Foundation-Sec-8B-Reasoning-4bit-mlx",
        "prompt": (
            "We are mid-incident. Timeline: 14:03 — EDR alert: PowerShell download cradle on WS-42. "
            "14:11 — DNS logs show WS-42 querying a DGA-like domain 6x. "
            "14:19 — Firewall: WS-42 initiating outbound HTTPS to 91.109.x.x (known TOR exit). "
            "14:31 — Auth logs: admin account used from WS-42, destination: DC01. "
            "What do we do right now? Provide a triage and containment plan."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Isolation first",
                "keywords": ["isolat", "contain", "disconnect", "block"],
            },
            {
                "type": "any_of",
                "label": "Admin account action",
                "keywords": [
                    "credential",
                    "reset",
                    "password",
                    "rotate",
                    "revoke",
                    "lock",
                    "disable",
                    "admin account",
                    "administrator",
                    "account",
                    "access",
                    "compromised account",
                    "suspend",
                    "authenticate",
                    "domain controller",
                    "dc01",
                ],
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Action-oriented",
                "keywords": [
                    "immediately",
                    "now",
                    "step",
                    "first",
                    "priority",
                    "urgent",
                    "right now",
                ],
            },
            {"type": "min_length", "label": "Substantive response", "chars": 500},
        ],
    },
    {
        "id": "P-S03",
        "name": "Blue Team Defender — Asks for OT Context",
        "section": "auto-blueteam",
        "model_slug": "blueteamdefender",
        "timeout": 120,
        "workspace_tier": "mlx_small",
        "mlx_model": "foundation-ai/Foundation-Sec-8B-Reasoning-4bit-mlx",
        "prompt": "Anomaly detected. Respond.",
        "assertions": [
            {
                "type": "any_of",
                "label": "Asks for context",
                "keywords": [
                    "what type",
                    "what kind",
                    "which environment",
                    "more information",
                    "tell me more",
                    "clarify",
                    "need more",
                    "can you provide",
                    "could you share",
                    "describe",
                    "what system",
                    "what happened",
                    "what anomaly",
                    "more details",
                    "what do you mean",
                    "elaborate",
                    "context",
                    "specifics",
                    "nature of",
                    "what are you seeing",
                    "what triggered",
                ],
            },
            {
                "type": "not_contains",
                "label": "No immediate IR plan",
                "keywords": ["step 1: isolate", "immediately isolate", "first, isolate"],
                "critical": False,
            },
        ],
    },]
