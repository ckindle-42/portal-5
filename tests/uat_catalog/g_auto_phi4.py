"""UAT catalog group: auto-phi4 (Phi-4-reasoning-plus STEM specialist)."""

from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [  # -----------------------------------------------------------------------
    {
        "id": "WS-PHI4-01",
        "name": "Phi-4 STEM — Eigenvalue Derivation",
        "section": "auto-phi4",
        "model_slug": "auto-phi4",
        "timeout": 240,
        "workspace_tier": "ollama",
        "prompt": (
            "/nothink\n"
            "Find the eigenvalues and eigenvectors of the matrix A = [[4, 1], [2, 3]]. "
            "Show the characteristic polynomial derivation, then solve for eigenvalues, "
            "then find the eigenvectors. Express answers exactly (no floating-point)."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Characteristic polynomial",
                "keywords": [
                    "characteristic",
                    "det",
                    "lambda",
                    "determinant",
                    "(4-λ)",
                    "(4 - λ)",
                    "λ²",
                ],
            },
            {
                "type": "any_of",
                "label": "Correct eigenvalues (2 and 5)",
                "keywords": [
                    "λ = 5",
                    "λ = 2",
                    "λ=5",
                    "λ=2",
                    "eigenvalue.*5",
                    "eigenvalue.*2",
                    "= 5",
                    "= 2",
                ],
                "critical": True,
            },
            {
                "type": "any_of",
                "label": "Eigenvector computed",
                "keywords": ["eigenvector", "v =", "vector", "[1,", "[2,", "null space", "kernel"],
            },
            {"type": "min_length", "label": "Full derivation shown", "chars": 400},
        ],
    },
    {
        "id": "WS-PHI4-02",
        "name": "Phi-4 STEM — Physics Derivation",
        "section": "auto-phi4",
        "model_slug": "auto-phi4",
        "timeout": 240,
        "workspace_tier": "ollama",
        "prompt": (
            "/nothink\n"
            "Derive the escape velocity formula from energy conservation principles. "
            "Start from kinetic energy equals gravitational potential energy, define all variables, "
            "and show each algebraic step. State the final formula and evaluate it for Earth "
            "(M=5.97×10²⁴ kg, R=6.37×10⁶ m, G=6.67×10⁻¹¹)."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Energy conservation setup",
                "keywords": ["kinetic", "potential", "mv²", "½mv", "GMm/r", "energy conservation"],
                "critical": True,
            },
            {
                "type": "any_of",
                "label": "Final formula present",
                "keywords": ["v_e", "v =", "escape", "sqrt(2GM", "√(2GM", "2GM/R"],
                "critical": True,
            },
            {
                "type": "any_of",
                "label": "Numerical result ~11.2 km/s",
                "keywords": ["11.2", "11,200", "11.18", "11 km/s", "~11"],
            },
            {"type": "min_length", "label": "Step-by-step derivation", "chars": 400},
        ],
    },
]
