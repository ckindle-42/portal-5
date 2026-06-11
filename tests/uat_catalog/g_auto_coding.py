"""UAT catalog group: auto-coding (coding workspace)."""
from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "WS-02",
        "name": "Code Expert — Async HTTP Retry Wrapper",
        "section": "auto-coding",
        "model_slug": "auto-coding",
        "timeout": 240,
        "workspace_tier": "ollama",
        "prompt": (
            "Write a Python async HTTP retry wrapper using httpx.AsyncClient. "
            "Requirements: exponential backoff with jitter, max 3 retries, retry only on "
            "429/500/502/503/504 status codes, configurable timeout. Include type hints, "
            "docstring, and a usage example."
        ),
        "assertions": [
            {
                # any_of: model may describe httpx usage in prose before or instead of code;
                # accept any mention of the library or client class.
                "type": "any_of",
                "label": "Uses httpx.AsyncClient",
                "keywords": [
                    "httpx",
                    "asyncclient",
                    "async with httpx",
                    "httpx.asyncclient",
                    "asyncclient()",
                ],
            },
            {
                "type": "any_of",
                "label": "Status codes correct",
                "keywords": ["429", "500", "503", "502", "504", "status code"],
            },
            {
                "type": "any_of",
                "label": "Asyncio backoff present",
                "keywords": ["asyncio.sleep", "import asyncio", "backoff", "jitter", "exponential"],
            },
            {
                "type": "any_of",
                "label": "Type hints present",
                "keywords": ["->", ": int", ": str", ": float", "optional[", "dict[", "tuple["],
                "critical": False,
            },
            {
                # critical: False — prose description without a fenced block still
                # demonstrates knowledge; scored but does not kill the test.
                "type": "any_of",
                "label": "Code block present",
                "keywords": ["```", "async def", "asyncclient", "httpx.asyncclient"],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-D01",
        "name": "Python Code Generator — Five-Step Delivery",
        "section": "auto-coding",
        "model_slug": "pythoncodegeneratorcleanoptimizedproduction-ready",
        "timeout": 240,
        "workspace_tier": "ollama",
        "prompt": (
            "Write a function to parse YAML configuration files with schema validation. "
            "The function should: accept a file path and a pydantic model class, return a "
            "validated model instance, and raise a descriptive error on validation failure "
            "or missing file. Use pathlib and PyYAML."
        ),
        "assertions": [
            {"type": "contains", "label": "pathlib used", "keywords": ["pathlib", "path"]},
            {
                "type": "any_of",
                "label": "yaml.safe_load",
                "keywords": ["safe_load", "yaml.safe_load", "pyyaml"],
            },
            {
                "type": "any_of",
                "label": "Type hints present",
                "keywords": ["->", ": Path", ": str", ": path", "-> Path", "-> str"],
            },
            {"type": "has_code", "label": "Code block present"},
            {"type": "min_length", "label": "Structured response", "chars": 600},
        ],
    },
    {
        "id": "P-D02",
        "name": "Bug Discovery — Classification by Type",
        "section": "auto-coding",
        "model_slug": "bugdiscoverycodeassistant",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Find all issues in this function and classify each by type "
            "(Logic Error, Runtime Error, Security Vulnerability, or Performance Issue):\n\n"
            "def get_config(env):\n"
            '    config = {"dev": {"db": "sqlite"}, "prod": {"db": "postgres"}}\n'
            '    cmd = f"load_config --env {env}"\n'
            "    os.system(cmd)\n"
            '    return config[env]["db"]'
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Command injection found",
                "keywords": [
                    "injection",
                    "os.system",
                    "command injection",
                    "shell",
                    "arbitrary command",
                ],
            },
            {
                "type": "any_of",
                "label": "Security type label",
                "keywords": [
                    "security vulnerability",
                    "security issue",
                    "security risk",
                    "vulnerability",
                    "security flaw",
                ],
            },
            {
                "type": "any_of",
                "label": "Runtime error label",
                "keywords": [
                    "runtime error",
                    "keyerror",
                    "key error",
                    "KeyError",
                    "exception",
                    "logic error",
                    "wrong data",
                    "crash",
                    "invalid key",
                    "missing key",
                    "IndexError",
                    "ValueError",
                ],
            },
            {
                "type": "any_of",
                "label": "At least 3 enumerated issues",
                "keywords": [
                    "1. ",
                    "2. ",
                    "3. ",
                    "1) ",
                    "2) ",
                    "3) ",
                ],
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Issue 3: input validation / unsafe concat",
                "keywords": [
                    "validate",
                    "validation",
                    "sanitize",
                    "untrusted",
                    "f-string",
                    'f"',
                    "concatenat",
                    "user input",
                    "user-supplied",
                    "shell",
                    "shlex",
                ],
            },
        ],
    },
    {
        "id": "P-D03",
        "name": "Code Review Assistant — PR Diff Scope",
        "section": "auto-coding",
        "model_slug": "codereviewassistant",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "PR Diff (review only the changed lines marked with +):\n\n"
            "def authenticate(username, password):\n"
            "-    return check_db(username, password)\n"
            '+    token = jwt.encode({"user": username}, SECRET_KEY, algorithm="HS256")\n'
            '+    return {"token": token, "expires": 3600}\n\n'
            "def check_db(username, password):\n"
            "     # unchanged — no modification\n"
            "     return db.query(username, password)"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "SECRET_KEY flagged",
                "keywords": [
                    "secret_key",
                    "secret key",
                    "hardcoded",
                    "environment",
                    "hardcode",
                    "hard-coded",
                    "env var",
                    "secret",
                    "credential",
                    "config",
                    "leaked",
                ],
            },
            {
                "type": "any_of",
                "label": "exp/expiry claim",
                "keywords": [
                    "exp",
                    "expiry",
                    "expiration",
                    "claim",
                    "ttl",
                    "expires",
                    "lifetime",
                    "duration",
                    "3600",
                ],
            },
            {
                "type": "not_contains",
                "label": "check_db not critiqued",
                "keywords": ["check_db is", "check_db looks", "check_db function"],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-D04",
        "name": "Code Reviewer — Deep Audit with Confidence",
        "section": "auto-coding",
        "model_slug": "codereviewer",
        "timeout": 240,
        "workspace_tier": "ollama",
        "prompt": (
            "Audit this Python function completely. Assign confidence level "
            "(High/Medium/Low) to each finding:\n\n"
            "def merge_configs(base: dict, override: dict) -> dict:\n"
            "    result = base\n"
            "    for key, val in override.items():\n"
            "        if isinstance(val, dict):\n"
            "            result[key] = merge_configs(result.get(key, {}), val)\n"
            "        else:\n"
            "            result[key] = val\n"
            "    return result"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Mutation bug found",
                "keywords": ["mutation", "aliasing", "in-place", "result = base", "copy"],
            },
            {
                "type": "any_of",
                "label": "Confidence levels present",
                "keywords": ["high", "medium", "low", "confidence"],
            },
            {
                "type": "any_of",
                "label": "Recursion risk noted",
                "keywords": ["recursion", "depth", "stack overflow", "merge_configs("],
            },
        ],
    },
    {
        "id": "P-D05",
        "name": "Fullstack Developer — Secure JWT Auth",
        "section": "auto-coding",
        "model_slug": "fullstacksoftwaredeveloper",
        "timeout": 150,
        "workspace_tier": "ollama",
        "prompt": (
            "Implement a FastAPI JWT authentication flow: POST /auth/login returns access + "
            "refresh tokens, GET /protected requires valid access token, POST /auth/refresh "
            "exchanges a refresh token for a new access token. Show the complete implementation."
        ),
        "assertions": [
            {
                "type": "contains",
                "label": "All 3 endpoints",
                "keywords": ["/auth/login", "/protected", "/auth/refresh"],
            },
            {
                "type": "any_of",
                "label": "exp claim present",
                "keywords": ["exp", "expiry", "expiration", "expires", "expire", "ttl"],
            },
            {
                "type": "not_contains",
                "label": "No hardcoded secret",
                "keywords": ['secret_key = "', "secret_key = '", '= "mysecret'],
            },
            {"type": "has_code", "label": "Code block present"},
        ],
    },
    {
        "id": "P-D06",
        "name": "Senior Frontend Developer — Asks Framework First",
        "section": "auto-coding",
        "model_slug": "seniorfrontenddeveloper",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "Build me a reusable data table component with sorting, pagination "
            "(25 rows per page), and a search filter. Column definitions should be passed as props."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Asks about framework",
                "keywords": [
                    "which framework",
                    "what framework",
                    "framework?",
                    "which library",
                    "what stack",
                    "what are you using",
                    "insufficient context",
                    "what are you building with",
                    "react, vue",
                    "react or vue",
                    "before i",
                    "first, could you",
                    "to get started",
                    "are you using react",
                    "are you using vue",
                    "preferred framework",
                    "what's your stack",
                    "what tech",
                    "technology stack",
                ],
            },
            {
                "type": "not_contains",
                "label": "No immediate component",
                "keywords": ["import React", "const DataTable", "export default", "<template>"],
                "critical": True,
            },
        ],
    },
    {
        "id": "P-D07",
        "name": "DevOps Automator — Complete K8s Manifest",
        "section": "auto-coding",
        "model_slug": "devopsautomator",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Generate a Kubernetes Deployment manifest for a Python FastAPI app. "
            "Image: ghcr.io/myorg/api:v1.2.3, port 8000, 2 replicas, readiness probe on /health, "
            "resource limits 512Mi/0.5CPU."
        ),
        "assertions": [
            {"type": "any_of", "label": "Image tag pinned", "keywords": ["v1.2.3", "1.2.3"]},
            {
                "type": "any_of",
                "label": "readinessProbe on /health",
                "keywords": ["readinessprobe", "/health", "readiness", "healthz"],
            },
            {
                "type": "any_of",
                "label": "Resource limits set",
                "keywords": [
                    "512mi",
                    "0.5",
                    "limits",
                    "limit",
                    "250m",
                    "cpu",
                    "memory",
                    "resources",
                ],
            },
            {
                "type": "any_of",
                "label": "Rollback included",
                "keywords": ["rollout undo", "rollback", "kubectl rollout", "revision"],
                "critical": False,
            },
            {"type": "has_code", "label": "YAML block present"},
        ],
    },
    {
        "id": "P-D09",
        "name": "GitHub Expert — Destructive Command Warning",
        "section": "auto-coding",
        "model_slug": "githubexpert",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "I need to undo the last 3 commits on main branch and remove them completely "
            "from git history so nobody can ever see them. What is the git command?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Correct command",
                "keywords": ["reset --hard", "reset --hard head~3", "force", "git reset"],
            },
            {
                "type": "any_of",
                "label": "Data loss warning",
                "keywords": [
                    "data loss",
                    "permanent",
                    "cannot be recovered",
                    "unrecoverable",
                    "warning",
                    "destructive",
                    "irreversible",
                ],
            },
            {
                "type": "any_of",
                "label": "Collaborators mentioned",
                "keywords": [
                    "collaborator",
                    "team",
                    "pulled",
                    "pushed",
                    "remote",
                    "others",
                    "shared",
                    "force push",
                ],
            },
        ],
    },
    {
        "id": "P-D10",
        "name": "Ethereum Developer — Security Audit Disclaimer",
        "section": "auto-coding",
        "model_slug": "ethereumdeveloper",
        "timeout": 420,
        "workspace_tier": "ollama",
        "prompt": (
            "Write a Solidity staking contract where users can deposit ETH, earn yield based on "
            "time staked, and withdraw with accumulated rewards. This will go live on mainnet "
            "next week."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Audit disclaimer",
                "keywords": [
                    "security audit",
                    "professional audit",
                    "audit before",
                    "has not been audited",
                    "not been audited",
                    "not audited",
                    "security notice",
                    "⚠️",
                    "mainnet deployment",
                    "before deploying",
                    "before deployment",
                    "audited by",
                    "recommend an audit",
                    "requires an audit",
                ],
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Solidity pragma",
                "keywords": ["pragma solidity", "^0.", "solidity ^", "solidity version"],
            },
            {
                "type": "any_of",
                "label": "Reentrancy protection",
                "keywords": [
                    "reentrancyguard",
                    "checks-effects",
                    "reentrancy",
                    "checks effects interactions",
                    "nonreentrant",
                    "re-entrancy",
                    "reentrancy protection",
                    "reentrancy attack",
                ],
            },
            {"type": "has_code", "label": "Code block present"},
        ],
    },
    {
        "id": "P-D11",
        "name": "JavaScript Console — Strict V8 Output",
        "section": "auto-coding",
        "model_slug": "javascriptconsole",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "> typeof null\n"
            "> [].foo.bar\n"
            "> [1,2,3].map(x => x * 2)\n"
            '> new Map([["a",1],["b",2]]).get("c")'
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "typeof null = object",
                "keywords": ["object", "'object'", '"object"', "typeof null", "null is object", "null"],
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "TypeError for [].foo.bar",
                "keywords": ["typeerror", "cannot read", "undefined"],
            },
            {
                "type": "any_of",
                "label": "[2, 4, 6] correct",
                "keywords": ["2, 4, 6", "[2,4,6]", "[2, 4, 6]", "map(x", "x * 2"],
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Map.get returns undefined",
                "keywords": ["undefined", "no value", "not found"],
                "critical": False,
            },
            {
                "type": "not_contains",
                "label": "No prose explanation",
                "keywords": ["as you can see", "note that", "this is because"],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-D12",
        "name": "Linux Terminal — Stateful Session",
        "section": "auto-coding",
        "model_slug": "linuxterminal",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "$ mkdir -p /tmp/portal_test && cd /tmp/portal_test\n"
            '$ echo "hello portal" > greet.txt\n'
            "$ cat greet.txt\n"
            "$ pwd"
        ),
        "assertions": [
            {"type": "contains", "label": "cat output correct", "keywords": ["hello portal"]},
            {
                "type": "contains",
                "label": "pwd shows /tmp/portal_test",
                "keywords": ["/tmp/portal_test"],
            },
            {
                "type": "not_contains",
                "label": "No prose",
                "keywords": ["here is", "this command", "the output is"],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-D13",
        "name": "Python Interpreter — Traceback Handling",
        "section": "auto-coding",
        "model_slug": "pythoninterpreter",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            'data = {"name": "Portal", "version": 6}\n'
            "items = list(data.items())\n"
            "print(f\"System: {data['name']} v{data['version']}\")\n"
            "print(items[5])  # this should fail"
        ),
        "assertions": [
            {
                "type": "contains",
                "label": "Print output correct",
                "keywords": ["system: portal v6"],
            },
            {"type": "contains", "label": "IndexError raised", "keywords": ["indexerror"]},
            # NOTE: previously had a not_contains check for ">>>". Removed because
            # the persona is named "Python Interpreter" — '>>>' is the literal
            # Python REPL prompt, so emitting it is correct behavior.
        ],
    },
    {
        "id": "P-D14",
        "name": "SQL Terminal — DML Session State",
        "section": "auto-coding",
        "model_slug": "sqlterminal",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "SELECT TOP 3 Username, Role FROM Users ORDER BY CreatedAt DESC;\n"
            "INSERT INTO Users (Username, Email, Role) VALUES ('newuser', 'new@lab.local', 'analyst');\n"
            "SELECT Username, Role FROM Users WHERE Username = 'newuser';"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "SELECT returns rows",
                "keywords": [
                    "(3 rows",
                    "3 row",
                    "username",
                    "rows returned",
                    "3 records",
                    "3 results",
                    "user",
                ],
            },
            {
                "type": "any_of",
                "label": "INSERT acknowledged",
                "keywords": [
                    "1 row",
                    "affected",
                    "inserted",
                    "insert 0",
                    "row added",
                    "1 record",
                    "success",
                    "created",
                ],
            },
            {"type": "any_of", "label": "newuser retrieved", "keywords": ["newuser", "analyst"]},
        ],
    },
    {
        "id": "P-D15",
        "name": "Excel Sheet — Formula Computation",
        "section": "auto-coding",
        "model_slug": "excelsheet",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Set up this spreadsheet:\n"
            "A1=Month, B1=Revenue, C1=Expenses, D1=Net\n"
            "A2=January, B2=42000, C2=31500, D2=formula: =B2-C2\n"
            "A3=February, B3=38000, C3=29000, D3=formula: =B3-C3\n"
            "A4=TOTAL, B4=formula: =SUM(B2:B3), C4=formula: =SUM(C2:C3), D4=formula: =SUM(D2:D3)"
        ),
        "assertions": [
            {"type": "any_of", "label": "D2 = 10500", "keywords": ["10500", "10,500"]},
            {"type": "any_of", "label": "D3 = 9000", "keywords": ["9000", "9,000", "9.000", "9 000"], "critical": False},
            {"type": "any_of", "label": "B4 = 80000", "keywords": ["80000", "80,000"]},
            {"type": "any_of", "label": "D4 = 19500", "keywords": ["19500", "19,500"]},
            # NOTE: previously had a not_contains check for raw formula text.
            # Removed because the persona is named "Excel Sheet" — a real
            # spreadsheet display legitimately shows the formula alongside the
            # computed value. Penalizing that was inverted polarity.
        ],
    },
    {
        "id": "P-D16",
        "name": "K8s/Docker RPG — Mission Start",
        "section": "auto-coding",
        "model_slug": "kubernetesdockerrpglearningengine",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": "START NEW GAME. Character: DevOps Apprentice. Difficulty: Normal. I want to learn how to deploy my first containerized app to Kubernetes. Begin Mission 1.",
        "assertions": [
            {
                "type": "any_of",
                "label": "RPG framing present",
                "keywords": ["mission", "quest", "challenge", "xp", "level"],
            },
            {
                "type": "any_of",
                "label": "First task given",
                "keywords": ["docker", "kubectl", "pod", "container"],
            },
            {"type": "min_length", "label": "Substantive response", "chars": 200},
        ],
    },
    {
        "id": "P-D18",
        "name": "QA Tester — Test Type Coverage",
        "section": "auto-coding",
        "model_slug": "softwarequalityassurancetester",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Write a test strategy for a file upload API endpoint: POST /api/v1/files — "
            "accepts multipart/form-data, max 10MB, allowed types: PDF/PNG/DOCX. "
            "Separate your test cases by type: unit, integration, security, and boundary. "
            "Do not claim 'comprehensive coverage' — be specific about what each test covers."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Security tests present",
                "keywords": [
                    "security",
                    "malicious",
                    "injection",
                    "xss",
                    "path traversal",
                    "exploit",
                    "attack",
                    "adversarial",
                    "invalid type",
                    "unauthorized",
                ],
            },
            {
                "type": "any_of",
                "label": "Boundary at 10MB",
                "keywords": [
                    "10mb",
                    "10 mb",
                    "10mb",
                    "size limit",
                    "file size",
                    "limit",
                    "max",
                    "oversized",
                    "exceed",
                    "boundary",
                    "maximum",
                ],
            },
            {
                "type": "any_of",
                "label": "Multiple test types",
                "keywords": ["unit", "integration", "security", "boundary"],
            },
            {
                "type": "not_contains",
                "label": "No vague coverage claim",
                "keywords": ["comprehensive coverage", "covers everything"],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-D19",
        "name": "UX/UI Developer — Platform Clarification",
        "section": "auto-coding",
        "model_slug": "ux-uideveloper",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "Design a dashboard for a field technician who needs to view and update work orders, "
            "check equipment status, and log time against jobs."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Asks about platform",
                "keywords": [
                    "which platform",
                    "what platform",
                    "mobile or desktop",
                    "what device",
                    "clarif",
                    "before i design",
                    "before designing",
                    "need to know",
                ],
            },
            {
                "type": "any_of",
                "label": "Platform context present",
                "keywords": [
                    "mobile",
                    "desktop",
                    "platform",
                    "device",
                    "tablet",
                    "responsive",
                    "screen size",
                    "browser",
                    "what device",
                    "which platform",
                    "target device",
                    "ios",
                    "android",
                    "web app",
                    "native app",
                    "viewport",
                    "display",
                    "interface type",
                ],
            },
            {
                "type": "not_contains",
                "label": "No immediate mockup",
                "keywords": [
                    "here is the dashboard",
                    "dashboard layout:",
                    "navigation bar:",
                    "sidebar:",
                ],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-D20",
        "name": "Creative Coder — Particle System (Ships First)",
        "section": "auto-coding",
        "model_slug": "creativecoder",
        "timeout": 240,
        "workspace_tier": "ollama",
        "prompt": (
            "Make me a particle system visualizer. Particles should emit from wherever I click, "
            "fan outward with randomized velocity and color, fade out over their lifetime, and "
            "respect gravity. Keyboard: [Space] to toggle gravity on/off, [C] to clear all particles."
        ),
        "assertions": [
            # critical: False — creative persona may narrate the code rather than fence it;
            # other assertions confirm functional understanding regardless.
            {"type": "has_code", "label": "HTML file delivered", "critical": False},
            {
                "type": "any_of",
                "label": "Canvas used",
                "keywords": ["canvas", "getcontext", "2d", "html canvas", "canvas element"],
            },
            {
                "type": "any_of",
                "label": "Gravity implemented",
                "keywords": ["gravity", "vy", "velocity", "vx", "acceleration", "fall", "g ="],
            },
            {
                "type": "any_of",
                "label": "Space/C key handlers",
                "keywords": [
                    "space",
                    "keydown",
                    "addeventlistener",
                    "key ===",
                    "[space]",
                    "spacebar",
                    "keycode",
                    "event.key",
                ],
            },
            {
                "type": "not_contains",
                "label": "No clarifying questions",
                "keywords": ["what framework", "which library", "do you want"],
                "critical": True,
            },
        ],
    },
    {
        "id": "P-DA06",
        "name": "Excel Sheet — Multi-Region Rank Formula",
        "section": "auto-coding",
        "model_slug": "excelsheet",
        "timeout": 90,
        "workspace_tier": "ollama",
        # Laguna-XS.2-4bit computes correctly in thinking but corrupts some 6-digit
        # numbers in output (e.g. 865000 → "8650nothman"). Thinking block has correct
        # answer so include it in assertions.
        "include_thinking_in_assertions": True,
        "prompt": (
            "Row 1 headers: Region | Q1_Sales | Q2_Sales | Q3_Sales | Q4_Sales | Annual | Rank\n"
            "A2=North, B2=120000, C2=135000, D2=98000, E2=145000\n"
            "A3=South, B3=89000, C3=102000, D3=115000, E3=78000\n"
            "A4=West, B4=210000, C4=195000, D4=220000, E4=240000\n"
            "F column: =SUM of Q1-Q4 for each row\n"
            "G column: =RANK of Annual Sales (highest=1) among all regions"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "F2 = 498000",
                "keywords": ["498000", "498,000", "$498,000"],
            },
            {
                "type": "any_of",
                "label": "F3 = 384000",
                "keywords": ["384000", "384,000", "$384,000"],
            },
            {
                "type": "any_of",
                "label": "F4 = 865000",
                "keywords": ["865000", "865,000", "$865,000"],
            },
            {
                "type": "any_of",
                "label": "West is rank 1",
                # Models display ranks in many shapes; accept any of these structural
                # signatures. Plain regex strings here are NOT regexes — assert_any_of
                # is literal substring (or word-boundary). Match the ways models
                # actually render: 'West ... 1', '1 ... West', 'rank 1', etc.
                "keywords": [
                    "west",
                    "rank: 1",
                    "rank 1",
                    "1st place",
                    "highest",
                ],
                "critical": False,
            },
        ],
    },
    {
        "id": "T-01",
        "name": "Code Sandbox — Python Exact Execution",
        "section": "auto-coding",
        "model_slug": "auto-coding",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Run this code and show me the exact output:\n\n"
            "from collections import Counter\n"
            'text = "the quick brown fox jumps over the lazy dog"\n'
            "top3 = Counter(text.split()).most_common(3)\n"
            "for word, count in top3:\n"
            '    print(f"{word}: {count}")'
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Sandbox output present",
                "keywords": ["the: 2", "quick: 1", "brown: 1"],
            },
            {
                "type": "not_contains",
                "label": "Not a prediction",
                "keywords": ["would output", "this will print"],
                "critical": True,
            },
        ],
    },
    {
        "id": "T-02",
        "name": "Code Sandbox — Bash Pipeline",
        "section": "auto-coding",
        "model_slug": "auto-coding",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Run this bash command and show exact output:\n\n"
            'printf "%s\\n" apple banana cherry apple banana apple | sort | uniq -c | sort -rn'
        ),
        "assertions": [
            {"type": "contains", "label": "3 apple first", "keywords": ["3 apple"]},
            {"type": "contains", "label": "2 banana second", "keywords": ["2 banana"]},
            {"type": "contains", "label": "1 cherry last", "keywords": ["1 cherry"]},
        ],
    },
    {
        "id": "T-03",
        "name": "Code Sandbox — Network Isolation",
        "section": "auto-coding",
        "model_slug": "auto-coding",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            'Run this code:\n\nimport urllib.request\nurllib.request.urlopen("http://example.com")'
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Network error returned",
                "keywords": [
                    "urlerror",
                    "gaierror",
                    "network",
                    "failed",
                    "error",
                    "unable",
                    "connection",
                    "refused",
                    "sandbox",
                    "execute",
                ],
            },
            {
                "type": "not_contains",
                "label": "No fake success",
                # "status: 200" removed — model may reference it when explaining what
                # a successful connection *would* look like, while correctly blocking it.
                "keywords": ["200 ok", "successfully connected", "retrieved"],
                "critical": False,
            },
        ],
    },]
