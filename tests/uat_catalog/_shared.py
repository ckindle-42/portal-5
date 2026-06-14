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
# ══════════════════════════════════════════════════════════════════════════
# GAME-CHALLENGE TIER (TASK_CODING_GAMECHALLENGE_V1)
# Three difficulty bands; each is a single self-contained web package
# (one HTML file, inline CSS+JS, zero external deps). Assertions check
# behavioral mechanisms (collision, state machine, the hard-part logic),
# not just keywords. Play@k render-check is a separate post-run pass.
# ══════════════════════════════════════════════════════════════════════════

_GC_SINGLE_FILE_NOTE = (
    " Deliver as ONE complete self-contained HTML file: inline <style> and "
    "<script>, NO external <script src=>, NO CDN links, NO asset files, NO "
    "build step. It must run by opening the file in a browser. Don't ask "
    "clarifying questions — ship it."
)

_GC01_PROMPT = (
    "Create a fully playable Flappy Bird game in the browser. The bird falls "
    "under gravity and flaps upward on spacebar or click. Pipes scroll from "
    "the right with gaps to fly through. Colliding with a pipe or the ground "
    "ends the game. Score increases by 1 for each pipe passed. Show a "
    "game-over screen with the score and a way to restart." + _GC_SINGLE_FILE_NOTE
)

_GC02_PROMPT = (
    "Create a fully playable Tetris game in the browser. Tetrominoes (all 7 "
    "shapes) fall into a grid; arrow keys move and rotate them, down speeds "
    "the drop. Completed horizontal lines clear and award points. The fall "
    "speed increases as more lines are cleared. The game ends when a new "
    "piece can't spawn. Show the score and next piece." + _GC_SINGLE_FILE_NOTE
)

_GC03_PROMPT = (
    "Create a fully playable side-scrolling platformer in the browser. An "
    "arrow-key controlled character runs and jumps (gravity + ground "
    "collision) across a tile-based level. At least one patrolling enemy "
    "moves on its own; touching it costs a life. The camera scrolls to follow "
    "the player. Reaching the right end of the level wins. Show lives and a "
    "win/lose screen." + _GC_SINGLE_FILE_NOTE
)

# ── Shared structural checks for every game band ───────────────────────────
_GC_BASE_ASSERTIONS = [
    {"type": "has_code", "label": "HTML file delivered"},
    {
        "type": "code_pattern",
        "label": "Single-file constraint (no external script src)",
        # PASS = the forbidden pattern is ABSENT. The matrix analyzer treats a
        # code_pattern with "negate": True as passing when no regex matches.
        "negate": True,
        "patterns": [
            {"regex": r"<script[^>]+src\s*=", "label": "external <script src=>"},
            {"regex": r"https?://\S+\.js", "label": "remote .js URL"},
            {"regex": r"cdn\.\S+", "label": "CDN reference"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Game loop present",
        "patterns": [
            {"regex": r"requestAnimationFrame\s*\(", "label": "requestAnimationFrame()"},
            {"regex": r"setInterval\s*\(", "label": "setInterval()"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Collision detection present",
        "patterns": [
            {"regex": r"\bcollid", "label": "collide/collision identifier"},
            {"regex": r"getBoundingClientRect|intersect|overlap", "label": "intersection test"},
            {"regex": r"<=?.*&&.*<=?|x\s*<.*&&.*y\s*<", "label": "AABB bounds check"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Game-over / restart state",
        "patterns": [
            {
                "regex": r"gameOver|game_over|isGameOver|state\s*=\s*['\"]",
                "label": "game state flag",
            },
            {"regex": r"\brestart|\breset\s*\(|location\.reload", "label": "restart mechanism"},
        ],
        "critical": False,
    },
    {"type": "contains", "label": "Score system", "keywords": ["score"]},
]

# ── GC-01 Flappy Bird — gravity + single collision + score ─────────────────
_GC01_ASSERTIONS = [
    *_GC_BASE_ASSERTIONS,
    {
        "type": "code_pattern",
        "label": "Gravity physics (velocity accumulation)",
        "patterns": [
            {"regex": r"velocity\s*\+=|vy\s*\+=|dy\s*\+=", "label": "velocity += gravity"},
            {"regex": r"gravity", "label": "gravity identifier"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Flap/jump impulse on input",
        "patterns": [
            {
                "regex": r"velocity\s*=\s*-|vy\s*=\s*-|dy\s*=\s*-",
                "label": "negative velocity (flap)",
            },
            {
                "regex": r"(keydown|click|keyup).*space|space.*keydown|' '|'Space'|32",
                "label": "spacebar/click handler",
            },
        ],
        "critical": False,
    },
    {
        "type": "any_of",
        "label": "Pipe obstacle logic",
        "keywords": ["pipe", "obstacle", "gap", "barrier"],
    },
]

# ── GC-02 Tetris — grid + rotation matrix + line clear + speed curve ───────
_GC02_ASSERTIONS = [
    *_GC_BASE_ASSERTIONS,
    {
        "type": "code_pattern",
        "label": "2D grid / board state",
        "patterns": [
            {
                "regex": r"\[\s*\]\s*\.\s*fill|Array\s*\(.*\)\.fill|new Array",
                "label": "array board init",
            },
            {"regex": r"board\s*\[|grid\s*\[|field\s*\[", "label": "board[][] access"},
            {"regex": r"for\s*\(.*\)\s*\{?\s*.*\[.*\]\s*\[", "label": "2D iteration"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Rotation logic (the hard part)",
        "patterns": [
            {"regex": r"rotat", "label": "rotate identifier"},
            {
                "regex": r"\[\s*\w+\s*\]\s*\[\s*\w+\s*\]\s*=\s*\w+\s*\[",
                "label": "matrix transpose assign",
            },
            {"regex": r"map\s*\(.*=>.*\[", "label": "matrix map rotation"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Line clear logic",
        "patterns": [
            {"regex": r"every\s*\(.*=>|\.every\(", "label": "row .every() full check"},
            {"regex": r"splice\s*\(|filter\s*\(.*=>.*some", "label": "row removal"},
            {"regex": r"clearLine|clearRow|fullRow|completedLine", "label": "clear-line function"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Difficulty / speed curve",
        "patterns": [
            {
                "regex": r"speed\s*[-*]?=|dropInterval|fallSpeed|level\s*\+\+",
                "label": "speed adjustment",
            },
        ],
        "critical": False,
    },
    {
        "type": "any_of",
        "label": "Tetromino shapes",
        "keywords": ["tetromino", "piece", "shape", "block", "SHAPES", "PIECES"],
    },
]

# ── GC-03 Platformer — tiles + jump physics + enemy AI + camera ────────────
_GC03_ASSERTIONS = [
    *_GC_BASE_ASSERTIONS,
    {
        "type": "code_pattern",
        "label": "Jump physics (gravity + ground collision)",
        "patterns": [
            {"regex": r"gravity|velocityY\s*\+=|vy\s*\+=", "label": "gravity accumulation"},
            {"regex": r"onGround|grounded|canJump|isJumping", "label": "ground state flag"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Tile-based level rendering",
        "patterns": [
            {"regex": r"tile|level\s*\[|map\s*\[|levelData", "label": "tile/level map"},
            {"regex": r"for\s*\(.*\).*for\s*\(", "label": "nested tile loop"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Enemy patrol AI (the hard part)",
        "patterns": [
            {"regex": r"enemy|enemies|patrol", "label": "enemy identifier"},
            {
                "regex": r"direction\s*\*=\s*-1|dir\s*=\s*-dir|speed\s*=\s*-",
                "label": "patrol direction flip",
            },
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Scrolling camera",
        "patterns": [
            {"regex": r"camera|scrollX|offsetX|cameraX|viewport", "label": "camera offset"},
            {"regex": r"translate\s*\(|ctx\.translate", "label": "canvas translate (camera)"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Lives + win condition",
        "patterns": [
            {"regex": r"\blives\b", "label": "lives identifier"},
            {"regex": r"\bwin|youWin|levelComplete|reachEnd|victory", "label": "win condition"},
        ],
        "critical": False,
    },
]

# ── GC-04 Burning Letter — fire particles + smoke + scorching + lighting ───
_GC04_PROMPT = (
    "Create a single HTML file with a canvas animation of a handwritten letter "
    "burning. Show an aged, slightly yellowed sheet of paper with visible "
    "handwritten cursive text (procedurally drawn lines are fine) resting on a "
    "dark wooden desk. After 2 seconds, a flame ignites at the bottom-right "
    "corner and spreads organically across the page — the burn front should "
    "advance with an irregular, noisy edge, never a straight line. Just ahead "
    "of the flames, the paper should darken and brown (scorching), then char "
    "black, then disappear entirely, revealing the desk beneath. Render the "
    "fire with layered particles: a bright white-yellow core, orange mid-flame, "
    "and translucent red tips that flicker and lick upward. Glowing embers "
    "should detach from the burn edge and drift upward on turbulent air "
    "currents, fading from orange to gray. Add wisps of semi-transparent smoke "
    "rising and dispersing above the flames, and a warm flickering light that "
    "the fire casts onto the surrounding desk. The entire page should be "
    "consumed in roughly 15 seconds, leaving only a few glowing ash fragments "
    "that slowly dim. 60fps, no external libraries." + _GC_SINGLE_FILE_NOTE
)

# ── GC-04 base assertions (visual animation — no game mechanics) ──────────
_GC04_BASE_ASSERTIONS = [
    {"type": "has_code", "label": "HTML file delivered"},
    {
        "type": "code_pattern",
        "label": "Single-file constraint (no external script src)",
        "negate": True,
        "patterns": [
            {"regex": r"<script[^>]+src\s*=", "label": "external <script src=>"},
            {"regex": r"https?://\S+\.js", "label": "remote .js URL"},
            {"regex": r"cdn\.\S+", "label": "CDN reference"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Canvas + animation loop present",
        "patterns": [
            {"regex": r"<canvas", "label": "canvas element"},
            {"regex": r"requestAnimationFrame\s*\(|setInterval\s*\(", "label": "animation loop"},
            {"regex": r"getContext\s*\(\s*['\"]2d", "label": "2d context"},
        ],
        "critical": False,
    },
    {
        "type": "any_of",
        "label": "Visual atmosphere described",
        "keywords": ["paper", "letter", "cursive", "desk", "wooden", "yellow", "flame", "fire", "smoke", "particle"],
    },
]

_GC04_ASSERTIONS = [
    *_GC04_BASE_ASSERTIONS,
    {
        "type": "code_pattern",
        "label": "Fire particles (core/orange/tip layers)",
        "patterns": [
            {"regex": r"\bparticle|\bember|\bspark", "label": "particle/ember identifier"},
            {"regex": r"\bflame|\bfire|\bburn", "label": "flame/fire identifier"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Irregular burn front (noise-driven edge)",
        "patterns": [
            {"regex": r"\bnoise|\brandom|\bMath\.random", "label": "random/noise for edge"},
            {"regex": r"\bburn|\bscorch|\bchar", "label": "burn/scorch/char state"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Smoke wisps + lighting glow",
        "patterns": [
            {"regex": r"\bsmoke|\bwisp|\bopacity|\balpha", "label": "smoke/opacity"},
            {"regex": r"\bglow|\blight|\bradial", "label": "glow/light effect"},
        ],
        "critical": False,
    },
    {
        "type": "code_pattern",
        "label": "Paper consumption timeline (~15s)",
        "patterns": [
            {"regex": r"\btime|\belapsed|\bduration", "label": "time tracking"},
            {"regex": r"\bprogress|\bt\s*[*/]", "label": "progress/normalized time"},
        ],
        "critical": False,
    },
    {
        "type": "any_of",
        "label": "Visual atmosphere described",
        "keywords": ["paper", "letter", "cursive", "desk", "wooden", "yellow"],
    },
]

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
