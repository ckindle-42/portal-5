"""UAT catalog group: benchmark (benchmark workspace)."""
from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "WS-MATH-01",
        "name": "Math Reasoner — Calculus Problem",
        "section": "auto-math",
        "model_slug": "auto-math",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Find the area enclosed by the curves y = x^2 and y = 2x. "
            "Show your work step by step: find intersection points, set up the integral, "
            "and evaluate it."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Intersection points found",
                "keywords": [
                    "x=0",
                    "x=2",
                    "x = 0",
                    "x = 2",
                    "x=0 and x=2",
                    "x = 0 and x = 2",
                    "(0, 0)",
                    "(2, 4)",
                    "(0,0)",
                    "(2,4)",
                    "0 and 2",
                ],
            },
            {
                "type": "any_of",
                "label": "Integral set up",
                "keywords": ["integral", "∫", "dx", "integrate", "2x - x^2", "x^2 - 2x"],
            },
            {
                "type": "any_of",
                "label": "Final answer 4/3",
                "keywords": [
                    "4/3",
                    "1.333",
                    "1.33",
                    "4 / 3",
                    "\\frac{4}{3}",
                    "frac{4}{3}",
                    "frac{4}",
                ],
            },
            {
                "type": "any_of",
                "label": "Math notation present",
                "critical": False,
                "keywords": ["```", "$$", "\\frac", "\\int", "\\["],
            },
        ],
    },
    {
        "id": "WS-MATH-02",
        "name": "Math Reasoner — Statistics Proof",
        "section": "auto-math",
        "model_slug": "auto-math",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Prove that for any dataset, the sample variance s^2 = (1/(n-1)) * sum((xi - xbar)^2) "
            "is an unbiased estimator of the population variance sigma^2. Show each step."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Expected value concept",
                "keywords": ["expected value", "E[", "expectation", "unbiased", "E(s"],
            },
            {
                "type": "any_of",
                "label": "Variance formula shown",
                "keywords": ["sigma^2", "σ²", "variance", "n-1", "degrees of freedom"],
            },
            {"type": "min_length", "label": "Substantive proof", "chars": 500},
        ],
    },]
