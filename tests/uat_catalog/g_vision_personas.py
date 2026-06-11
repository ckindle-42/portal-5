"""UAT catalog group: vision personas (M6-T08)."""
from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "P-V10",
        "name": "Code Screenshot Reader — Protocol",
        "section": "auto-vision",
        "model_slug": "codescreenshotreader",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "How would you transcribe a code screenshot from a VS Code dark theme? "
            "What steps do you take to ensure accuracy?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Language identification",
                "keywords": [
                    "language",
                    "syntax",
                    "identify",
                    "extension",
                    "highlighting",
                    "programming language",
                    "code language",
                    "file type",
                    "language detection",
                ],
            },
            {
                "type": "any_of",
                "label": "Indentation preservation",
                "keywords": [
                    "indent",
                    "spaces",
                    "tabs",
                    "formatting",
                    "preserv",
                    "whitespace",
                    "alignment",
                    "structure",
                    "line by line",
                ],
            },
            {
                "type": "any_of",
                "label": "Ambiguous character handling",
                "keywords": [
                    "ambiguous",
                    "l vs 1",
                    "O vs 0",
                    "resolution",
                    "[?]",
                    "visually similar",
                    "similar character",
                    "hard to distinguish",
                    "hard to tell",
                    "similar-looking",
                    "look alike",
                    "easily confused",
                    "0 and o",
                    "1 and l",
                    "similar letters",
                    "might be",
                    "could be",
                    "double-check",
                    "verify",
                    "unclear",
                ],
            },
            {"type": "min_length", "label": "Substantive response", "chars": 200},
        ],
    },
    {
        "id": "P-V11",
        "name": "Chart Analyst — Analysis Framework",
        "section": "auto-vision",
        "model_slug": "chartanalyst",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "I'm about to send you a bar chart comparing quarterly revenue across regions. "
            "What information will you extract from it?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Chart type identification",
                "keywords": [
                    "chart type",
                    "bar chart",
                    "type of chart",
                    "axes",
                    "bar graph",
                    "bar diagram",
                    "column chart",
                    "x-axis",
                    "y-axis",
                    "horizontal axis",
                    "vertical axis",
                    "legend",
                    "categories",
                    "labeled",
                ],
            },
            {
                "type": "any_of",
                "label": "Data extraction mentioned",
                "keywords": [
                    "data",
                    "extract",
                    "values",
                    "points",
                    "numbers",
                    "figures",
                    "revenue",
                    "quantities",
                ],
            },
            {
                "type": "any_of",
                "label": "Design critique mentioned",
                "keywords": [
                    "design",
                    "tufte",
                    "misleading",
                    "truncated",
                    "data-ink",
                    "visual",
                    "clarity",
                    "readability",
                    "color",
                    "presentation",
                    "effective",
                    "best practice",
                    "data visualization",
                    "scale",
                    "label",
                    "proportion",
                    "clear",
                ],
            },
        ],
    },]
