"""UAT catalog group: auto-reasoning (reasoning workspace)."""

from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [  # -----------------------------------------------------------------------
    {
        "id": "WS-09",
        "name": "Deep Reasoner — Secrets Management Trade-off",
        "section": "auto-reasoning",
        "model_slug": "auto-reasoning",
        "timeout": 360,
        "workspace_tier": "ollama",
        "prompt": (
            "A platform team must choose a secrets management approach for 40 microservices. "
            "Options: (A) HashiCorp Vault self-hosted, (B) AWS Secrets Manager, "
            "(C) Kubernetes Secrets with external-secrets-operator and KMS encryption. "
            "The team is AWS-native, has 2 platform engineers, no budget for Vault Enterprise, "
            "and must meet SOC 2 Type II audit requirements. Reason through the trade-offs "
            "and give a recommendation."
        ),
        "assertions": [
            {
                "type": "contains",
                "label": "All three options covered",
                "keywords": ["vault", "aws secrets", "external-secrets"],
            },
            {"type": "contains", "label": "SOC 2 addressed", "keywords": ["soc 2"]},
            {
                "type": "contains",
                "label": "Team size factored",
                "keywords": ["engineer", "team", "operational"],
            },
            {
                "type": "any_of",
                "label": "Clear recommendation",
                "keywords": ["recommend", "suggest", "should", "opt for", "go with", "best option"],
            },
        ],
    },
    {
        "id": "P-D08",
        "name": "DevOps Engineer — Consults Before Designing",
        "section": "auto-reasoning",
        "model_slug": "devopsengineer",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": "We need a CI/CD pipeline. Can you set one up for us?",
        "assertions": [
            {
                "type": "any_of",
                "label": "Asks clarifying questions",
                "keywords": [
                    "which cloud",
                    "what cloud",
                    "provider",
                    "stack",
                    "team size",
                    "what language",
                    "existing",
                ],
            },
            {
                "type": "not_contains",
                "label": "No pipeline YAML",
                "keywords": ["name: ci/cd", "on: push", "runs-on:"],
                "critical": True,
            },
        ],
    },
    {
        "id": "P-R02",
        "name": "IT Architect — Requirements Before Architecture",
        "section": "auto-reasoning",
        "model_slug": "itarchitect",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": "Design an integration architecture for our systems.",
        "assertions": [
            {
                "type": "any_of",
                "label": "Asks for requirements",
                "keywords": [
                    "which systems",
                    "what systems",
                    "requirements",
                    "constraints",
                    "tell me more",
                    "before i can",
                    "before designing",
                    "need to know",
                    "help me understand",
                    "tell me about",
                    "more context",
                    "what are",
                    "clarify",
                    "could you",
                    "please share",
                    "existing",
                    "insufficient context",
                ],
            },
            {
                "type": "not_contains",
                "label": "No architecture output",
                "keywords": ["api gateway", "event bus", "message queue", "kafka", "rabbitmq"],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-R03",
        "name": "Senior Software Engineer/Architect — Rate Limiting Trade-offs",
        "section": "auto-reasoning",
        "model_slug": "seniorsoftwareengineersoftwarearchitectrules",
        "timeout": 360,
        "workspace_tier": "ollama",
        "prompt": (
            "We need to implement distributed rate limiting for our API gateway. "
            "Expected load: 50,000 req/s across 8 nodes. Requirement: sub-5ms overhead. "
            "Evaluate at least two approaches and recommend one with trade-off justification."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "At least two approaches",
                "keywords": ["approach", "option", "method", "strategy", "algorithm", "pattern"],
            },
            {
                "type": "any_of",
                "label": "Rate-limiting algorithm or store",
                "keywords": [
                    "redis",
                    "token bucket",
                    "sliding window",
                    "fixed window",
                    "leaky bucket",
                    "rate limiter",
                    "rate-limiter",
                    "in-memory",
                    "distributed cache",
                    "memcached",
                    "hazelcast",
                    "lua",
                    "atomic",
                    "counter",
                    "bucket",
                ],
            },
            {
                "type": "any_of",
                "label": "Latency budget addressed",
                "keywords": ["5ms", "latency", "overhead"],
            },
            {
                "type": "any_of",
                "label": "Recommendation given",
                "keywords": [
                    "recommend",
                    "suggest",
                    "should choose",
                    "opt for",
                    "go with",
                    "best choice",
                    "preferred",
                    "winner",
                ],
            },
        ],
    },
    {
        "id": "P-R04",
        "name": "GPT-OSS Analyst — Independent Second Opinion",
        "section": "auto-reasoning",
        "model_slug": "gptossanalyst",
        "timeout": 240,
        "workspace_tier": "ollama",
        "prompt": (
            "Another AI in this system recommended using a microservices architecture for "
            "a 3-person startup building an internal HR tool with ~50 users. "
            "Do you agree? Apply your own reasoning independently."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Monolith argued",
                "keywords": ["monolith", "simpler", "start with", "complexity"],
            },
            {
                "type": "any_of",
                "label": "Team size factored",
                "keywords": [
                    "3 person",
                    "3-person",
                    "team size",
                    "small team",
                    "three-person",
                    "three person",
                ],
            },
            {
                "type": "any_of",
                "label": "Second opinion framing",
                "keywords": ["second opinion", "independent", "disagree", "however", "actually"],
            },
        ],
    },
]
