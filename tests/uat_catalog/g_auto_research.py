"""UAT catalog group: auto-research (research workspace)."""
from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "WS-13",
        "name": "Research Assistant — Post-Quantum Cryptography",
        "section": "auto-research",
        "model_slug": "auto-research",
        "timeout": 360,
        "workspace_tier": "mlx_large",
        "prompt": (
            "Post-quantum cryptography deployment status. Structure your response in exactly "
            "these four sections, no preamble:\n"
            "1. NIST-FINALIZED ALGORITHMS — name each finalized algorithm and production-readiness status\n"
            "2. TLS LIBRARY SUPPORT — which major TLS libraries have shipped PQC support and which version\n"
            "3. MIGRATION TIMELINE — realistic phased plan for an enterprise with 200+ internal services\n"
            "4. CONFIRMED VS EMERGING — one sentence distinguishing what is deployed today vs still in progress\n"
            "Limit: 700 words total. No preamble before section 1."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "NIST algorithms named",
                "keywords": ["ml-kem", "kyber", "ml-dsa", "dilithium", "slh-dsa"],
            },
            {
                "type": "any_of",
                "label": "TLS library mentioned",
                "keywords": ["openssl", "boringssl", "rustls", "tls"],
            },
            {
                "type": "any_of",
                "label": "Migration timeline",
                "keywords": [
                    "phase",
                    "migrat",
                    "timeline",
                    "roadmap",
                    "step",
                    "schedule",
                    "year 1",
                    "year 2",
                    "year one",
                    "year two",
                    "rollout",
                    "rolled out",
                    "phased",
                    "deployment plan",
                    "near-term",
                    "long-term",
                    "short-term",
                    "q1",
                    "q2",
                    "q3",
                    "q4",
                    "first quarter",
                    "wave 1",
                    "wave 2",
                    # Additions for transition language NIST and migration plans use:
                    "by 2030",
                    "by 2035",
                    "interim",
                    "hybrid",
                    "transition period",
                    "begin migration",
                    "prepare for",
                    "preparation",
                    "plan to migrate",
                    "incremental",
                ],
                "critical": False,
            },
            {"type": "min_length", "label": "Substantive response", "chars": 500},
        ],
    },
    {
        "id": "P-R05",
        "name": "Research Analyst — Evidence Quality Labeling",
        "section": "auto-research",
        "model_slug": "researchanalyst",
        "timeout": 360,
        "workspace_tier": "mlx_large",
        "prompt": (
            "Analyze this claim: 'Passwordless authentication is more secure than passwords + MFA "
            "for enterprise environments.'\n\n"
            "Structure your response as follows:\n"
            "1. METHODOLOGY — what framework you are applying\n"
            "2. KEY FINDINGS — for each finding, prefix the claim with exactly one of: "
            "[Established Fact], [Strong Evidence], [Inference], or [Speculation]\n"
            "3. COUNTERARGUMENTS — limitations, challenges, or cases where the claim does not hold\n"
            "4. CONCLUSION — confidence-weighted verdict (High/Medium/Low)\n"
            "No preamble. Start directly with section 1. Limit: 600 words."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Evidence labels present",
                "keywords": [
                    "established fact",
                    "strong evidence",
                    "inference",
                    "speculation",
                    "well established",
                    "widely accepted",
                    "evidence suggests",
                    "likely",
                    "inferred",
                    "speculative",
                    "uncertain",
                    "high confidence",
                    "medium confidence",
                    "low confidence",
                    "established:",
                    "evidence:",
                    "inference:",
                    "speculation:",
                    "[established",
                    "[strong",
                    "[inference",
                    "[speculation",
                    "fact:",
                    "based on evidence",
                    "limited evidence",
                ],
            },
            {
                "type": "any_of",
                "label": "Counterpoints included",
                "keywords": [
                    "however",
                    "but",
                    "challenge",
                    "limitation",
                    "concern",
                    "caveat",
                    "drawback",
                    "disadvantage",
                    "on the other hand",
                    "critics",
                    "some argue",
                    "others argue",
                    "debate",
                    "not without",
                    "it should be noted",
                    "worth noting",
                ],
            },
            {
                "type": "not_contains",
                "label": "No absolute claim",
                "keywords": ["passwordless is always", "always more secure"],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-R06",
        "name": "Gemma Research Analyst — AI Regulation with Evidence Framework",
        "section": "auto-research",
        "model_slug": "gemmaresearchanalyst",
        "timeout": 360,
        "workspace_tier": "mlx_large",
        "prompt": (
            "Analyze AI regulation globally. Structure your response as follows:\n"
            "- For EACH claim, prefix it with one of: [Established Fact], [Strong Evidence], "
            "[Inference], or [Speculation]\n"
            "- Cover: EU AI Act, US executive orders, China's approach\n"
            "- Surface at least one area of significant expert disagreement — "
            "do not smooth it over\n"
            "Keep the total response under 600 words."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Evidence labels present",
                "keywords": [
                    "established fact",
                    "strong evidence",
                    "inference",
                    "speculation",
                    "[established",
                    "[strong",
                    "[inference",
                    "[speculation",
                ],
            },
            {
                "type": "any_of",
                "label": "EU AI Act covered",
                "keywords": ["eu ai act", "european", "eu act", "artificial intelligence act"],
            },
            {
                "type": "any_of",
                "label": "Expert disagreement surfaced",
                "keywords": [
                    "disagreement",
                    "debate",
                    "some argue",
                    "others argue",
                    "conflicting",
                    "contend",
                    "dispute",
                    "differ",
                    "not all",
                    "critics",
                ],
            },
        ],
    },
    {
        "id": "P-R07",
        "name": "SuperGemma4 Uncensored — Adversarial ML Analysis",
        "section": "auto-research",
        "model_slug": "supergemma4researcher",
        "timeout": 360,
        "workspace_tier": "mlx_large",
        "prompt": (
            "Technical briefing on adversarial ML attacks against production LLMs. "
            "Use this exact structure — one paragraph each:\n"
            "1. Prompt Injection: mechanism + detection + mitigation\n"
            "2. Model Extraction via API: how attackers reconstruct models + defenses\n"
            "3. Training Data Extraction: what leaks + how to prevent\n"
            "4. Jailbreaking: common vectors + defender countermeasures\n"
            "Be direct and technical. No preamble."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Prompt injection covered",
                "keywords": [
                    "prompt injection",
                    "injecting",
                    "indirect injection",
                    "instruction injection",
                ],
            },
            {
                "type": "any_of",
                "label": "Model extraction covered",
                "keywords": [
                    "model extraction",
                    "api",
                    "reconstruct",
                    "stealing",
                    "extraction attack",
                    "query budget",
                ],
            },
            {
                "type": "any_of",
                "label": "Defenses included",
                "keywords": [
                    "detect",
                    "mitigat",
                    "defend",
                    "prevent",
                    "protect",
                    "filter",
                    "monitor",
                    "sanitiz",
                ],
            },
            {
                "type": "not_contains",
                "label": "No excessive refusal",
                "keywords": ["i cannot provide", "i'm unable to", "i won't"],
                "critical": True,
            },
        ],
    },]
