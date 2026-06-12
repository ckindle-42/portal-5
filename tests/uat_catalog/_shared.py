"""Shared symbols referenced by catalog entry dicts.

REFUSAL_PHRASES is the canonical refusal keyword list (also imported by the
driver from ``common``); the _CC01 assertion specs are reused across coding
entries. Defined once here so catalog data modules import from one place.
"""

from __future__ import annotations

from tests.common import REFUSAL_PHRASES  # noqa: F401  (re-exported for catalog modules)

_CC01_PROMPT = (
    "Create, in a single HTML file, a fully playable Asteroids game in the browser "
    "that keeps score with levels of increasing difficulty like the original arcade game. "
    "The ship should rotate and thrust, bullets should fire on spacebar, asteroids should "
    "split when shot, and a new level should start when all asteroids are cleared. "
    "Include a lives system: the player starts with 3 lives, loses one on collision with "
    "an asteroid, and the game ends when all lives are lost. "
    "Include a high score that persists within the session."
)
_CC01_ASSERTIONS = [
    {"type": "has_code", "label": "HTML file delivered"},
    # ── Behavioral checks (code patterns, not variable names) ──────────────
    {
        "type": "code_pattern",
        "label": "Game loop (behavioral)",
        "patterns": [
            {"regex": r"requestAnimationFrame\s*\(", "label": "requestAnimationFrame() call"},
            {"regex": r"setInterval\s*\(", "label": "setInterval() call"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Lives manipulation (behavioral)",
        "patterns": [
            {"regex": r"\blives\s*--", "label": "lives-- decrement"},
            {"regex": r"\blives\s*-=\s*1", "label": "lives -= 1"},
            {"regex": r"\blives\s*=\s*\blives\s*-\s*1", "label": "lives = lives - 1"},
            {"regex": r"\bthis\.lives\s*--", "label": "this.lives--"},
            {"regex": r"\bplayer\.lives\s*--", "label": "player.lives--"},
            {"regex": r"\blose\s+a?\s*life", "label": "lose a life message"},
            {"regex": r"\blives\s*[<>!=]=\s*0", "label": "lives <=/>=/==/!= 0 check"},
            {"regex": r"\blives\s*<\s*1", "label": "lives < 1 (zero check)"},
            {"regex": r"\blives\s*==\s*0", "label": "lives == 0 check"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Score increment (behavioral)",
        "patterns": [
            {"regex": r"\bscore\s*\+=\s*", "label": "score += (increment)"},
            {"regex": r"\bscore\s*=\s*\bscore\s*\+", "label": "score = score +"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Asteroid split/push (behavioral)",
        "patterns": [
            {"regex": r"asteroid.*\.push\(", "label": "asteroid push"},
            {"regex": r"\.push\(.*asteroid", "label": "push asteroid"},
            {"regex": r"\.split\s*\(", "label": "split() method"},
            {"regex": r"asteroids\.push\(", "label": "asteroids.push()"},
        ],
        "critical": False,
    },
    # ── Keyword checks (defense-in-depth, survives code-block extraction failure) ──
    {
        "type": "any_of",
        "label": "Canvas game loop (keyword)",
        "keywords": [
            "requestanimationframe",
            "requestAnimationFrame",
            "setinterval",
            "setInterval",
            "game loop",
            "gameloop",
            "game_loop",
        ],
        "critical": False,
    },
    {
        "type": "any_of",
        "label": "Asteroids split logic",
        "keywords": ["split", "asteroid", "fragment", "smaller"],
    },
    {
        "type": "any_of",
        "label": "Lives system (keyword)",
        "word_boundary": True,
        "keywords": [
            "lives",
            "life",
            "lives_remaining",
            "numlives",
            "playerlives",
            "player.lives",
            "this.lives",
            "this.life",
            "playerlife",
            "livescount",
            "livesleft",
            "lifecount",
            "remaininglives",
            "player_lives",
            "lose a life",
            "lost a life",
            "starting lives",
            "3 lives",
        ],
        "critical": False,
    },
    {"type": "contains", "label": "Score system", "keywords": ["score"]},
]

# Variant for RL/STEM-tuned models (P5-BENCH-001) that don't reliably emit
# HTML code blocks — has_code demoted to critical: False so the benchmark
# scores the game-logic understanding without gating on code delivery.
_CC01_ASSERTIONS_BENCH = [
    {"type": "has_code", "label": "HTML file delivered", "critical": False},
    *_CC01_ASSERTIONS[1:],
]
