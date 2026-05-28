"""UAT catalog group: auto-compliance (compliance workspace)."""
from __future__ import annotations

from tests.uat_catalog._shared import REFUSAL_PHRASES, _CC01_ASSERTIONS, _CC01_ASSERTIONS_BENCH  # noqa: F401

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "WS-16",
        "name": "Compliance Analyst — CIP-003-9 R1.2.6",
        "section": "auto-compliance",
        "model_slug": "auto-compliance",
        "timeout": 360,
        "workspace_tier": "mlx_large",
        "prompt": (
            "We are a medium-sized Transmission Owner. We have never classified any assets under "
            "CIP-003 because we believed our distributed control systems were Low impact only. "
            "Our external auditor just told us CIP-003-9 R1.2.6 is now enforceable and may apply "
            "to some of our systems. What does CIP-003-9 R1.2.6 require, when is it enforceable, "
            "and what should we do immediately to assess our exposure?"
        ),
        "assertions": [
            {
                "type": "contains",
                "label": "Standard cited precisely",
                "keywords": ["cip-003-9", "r1", "1.2.6"],
                # word_boundary intentionally not set: the original review plan's
                # claim that 'r1' would substring-match 'router 1' was incorrect
                # (the space prevents that). And word_boundary regresses on
                # smashed forms like 'R1.2.6' (\b can't fire between word chars).
            },
            {
                "type": "any_of",
                "label": "Enforceability date",
                "keywords": [
                    "april 1, 2026",
                    "april 2026",
                    "2026",
                    "effective date",
                    "implementation date",
                    "deadline",
                    "enforcement date",
                    "now in effect",
                    "now enforceable",
                    "currently enforceable",
                ],
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Immediate actions given",
                "keywords": [
                    "assess",
                    "inventory",
                    "identif",
                    "review",
                    "determine",
                    "evaluate",
                    "audit",
                    "gap analysis",
                    "next step",
                    "action",
                ],
            },
            {
                "type": "any_of",
                "label": "Refers user to SME",
                "keywords": [
                    "sme",
                    "expert",
                    "attorney",
                    "legal",
                    "verify",
                    "professional",
                    "consult",
                    "qualified",
                    "specialist",
                    "counsel",
                ],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-C01",
        "name": "NERC CIP Analyst — CIP-003-9 Full Citation",
        "section": "auto-compliance",
        "model_slug": "nerccipcomplianceanalyst",
        "timeout": 360,
        "workspace_tier": "mlx_large",
        "prompt": (
            "We are a Distribution Provider with some assets that have routable external "
            "connectivity to a vendor cloud portal for remote monitoring. A colleague says "
            "CIP-003-9 R1 Part 1.2.6 applies to us now. Are they right? What does this "
            "require and what is the urgency?"
        ),
        "assertions": [
            {
                # any_of: models may cite the standard as "CIP-003" (without -9 suffix)
                # or "R1.2.6" without the full CIP prefix — accept any recognizable form.
                "type": "any_of",
                "label": "Precise citation",
                "keywords": [
                    "cip-003-9",
                    "cip 003-9",
                    "cip-003 r1.2.6",
                    "cip003-9",
                    "1.2.6",
                    "r1.2.6",
                    "part 1.2.6",
                    "requirement 1.2.6",
                ],
            },
            {
                "type": "any_of",
                "label": "Enforceability date",
                "keywords": [
                    "april 1, 2026",
                    "april 2026",
                    "2026",
                    "effective date",
                    "implementation date",
                    "deadline",
                    "enforcement date",
                ],
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Priority-1 flagged",
                "keywords": ["priority-1", "priority 1", "urgent", "immediate"],
            },
            {
                "type": "any_of",
                "label": "SME review recommended",
                "keywords": [
                    "sme",
                    "legal",
                    "expert",
                    "verify",
                    "counsel",
                    "consult",
                    "review",
                    "specialist",
                    "professional",
                    "qualified",
                ],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-C02",
        "name": "CIP Policy Writer — Aspirational Language Rejection",
        "section": "auto-compliance",
        "model_slug": "cippolicywriter",
        "timeout": 360,
        "workspace_tier": "mlx_large",
        "prompt": (
            "Review and fix this draft policy statement:\n\n"
            '"[ENTITY NAME] will strive to ensure that, as appropriate and where feasible, '
            'security patches are applied to BES Cyber Systems in a timely manner."\n\n'
            "Output format:\n"
            "1. Problems: list each issue with the original\n"
            "2. Rewrite: the corrected policy statement using mandatory language (shall/must) "
            "and a specific time window (e.g., 35 calendar days)\n"
            "3. Why: one sentence on why each change matters for audit"
        ),
        "assertions": [
            {
                "type": "contains",
                "label": "Aspirational language flagged",
                "keywords": ["strive", "as appropriate", "where feasible", "timely"],
            },
            {
                "type": "any_of",
                "label": "Rewrite uses mandatory language",
                "keywords": [
                    "shall",
                    "must",
                    "will patch",
                    "required to",
                    "are required",
                    "must be applied",
                    "shall be applied",
                ],
            },
            {"type": "contains", "label": "Placeholder preserved", "keywords": ["[entity name]"]},
            {
                "type": "any_of",
                "label": "Time window specified",
                "keywords": [
                    "35 calendar",
                    "days",
                    "patch window",
                    "calendar days",
                    "window",
                    "timeframe",
                    "time frame",
                    "period",
                    "deadline",
                    "within",
                ],
                "critical": False,
            },
        ],
    },]
