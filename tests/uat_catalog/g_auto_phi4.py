"""UAT catalog group: auto-phi4 (STEM reasoning specialist).

phi4-reasoning:plus / plus-ctx32k are NOT used here — confirmed to crash
Ollama's llama-server on load (signal: abort trap, llama.cpp
common_fit_params device-memory-fit crash) on this host, reproduced even
after a full ollama rm + re-pull + rebuild of the ctx-tagged variants (so
NOT a corrupted-download issue, contra the earlier theory in
KNOWN_LIMITATIONS.md). Tests target auto-reasoning's actual pool default
(DeepSeek-R1-0528-Qwen3-8B) instead — matches phi4stemanalyst's
re-identified (Phi-4-lineage-dropped) persona.
"""

from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [  # -----------------------------------------------------------------------
    {
        "id": "WS-PHI4-01",
        "name": "STEM Reasoning — Eigenvalue Derivation",
        # BUILD_PROGRAM_ALIAS_RETIRE_V1.md Phase 3: "auto-phi4" retired
        # (model-tied). See module docstring — phi4-reasoning is confirmed
        # crash-prone on this host, so this exercises auto-reasoning's
        # actual served model rather than a ?model= override.
        "section": "auto-reasoning (STEM reasoning)",
        "model_slug": "auto-reasoning",
        "via_dispatcher": True,
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
        "name": "STEM Reasoning — Physics Derivation",
        # See WS-PHI4-01's comment / module docstring.
        "section": "auto-reasoning (STEM reasoning)",
        "model_slug": "auto-reasoning",
        "via_dispatcher": True,
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
