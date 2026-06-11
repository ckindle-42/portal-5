"""UAT catalog group: browser automation (M5 personas)."""
from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "P-B01",
        "name": "E2E Test Author — Test Strategy",
        "section": "auto-coding",
        "model_slug": "e2etestauthor",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Write a Playwright test for a login page: POST /login accepts email+password, "
            "redirects to /dashboard on success, shows error toast on failure. "
            "Include both happy-path and error-path tests."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Playwright selectors",
                "keywords": ["getbyrole", "getbylabel", "getbytext", "locator", "page.goto"],
            },
            {
                "type": "any_of",
                "label": "Happy path present",
                "keywords": ["success", "dashboard", "redirect", "expect", "visible"],
            },
            {
                "type": "any_of",
                "label": "Error path present",
                "keywords": ["error", "invalid", "wrong password", "fail", "toast"],
            },
            {"type": "has_code", "label": "Code block present"},
        ],
    },
    {
        "id": "P-B02",
        "name": "Form Filler — Verification Protocol",
        "section": "auto-coding",
        "model_slug": "formfiller",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "I need you to fill out a job application form at careers.example.com. "
            "It has: name, email, resume upload, cover letter textarea, and salary expectations. "
            "What's your approach?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Field mapping mentioned",
                "keywords": ["map", "field", "identify", "label", "structure"],
            },
            {
                "type": "any_of",
                "label": "Verification before submit",
                "keywords": ["verify", "review", "confirm", "before submit", "check each"],
            },
            {
                "type": "any_of",
                "label": "No auto-submit",
                "keywords": [
                    "never auto-submit",
                    "without confirmation",
                    "ask",
                    "operator",
                    "your approval",
                    "confirm first",
                    "before submitting",
                    "before submission",
                    "would you like",
                    "please provide",
                    "need from you",
                    "wait",
                    "pause",
                    "hold",
                    "permission",
                ],
                "critical": False,
            },
        ],
    },
    # -----------------------------------------------------------------------
    # Missing browser personas (M5)
    # -----------------------------------------------------------------------
    {
        "id": "P-B03",
        "name": "Web Navigator — Task Decomposition",
        "section": "auto",
        "model_slug": "webnavigator",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "Go to the AWS console and check my current monthly bill. "
            "How would you approach this task?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Task decomposition",
                "keywords": ["navigate", "login", "billing", "step", "first", "then", "click"],
            },
            {
                "type": "any_of",
                "label": "Safety awareness",
                "keywords": [
                    "confirm",
                    "purchase",
                    "delete",
                    "never",
                    "without",
                    "ask",
                    "security",
                    "privacy",
                    "i can't directly",
                    "cannot directly",
                    "you'd need",
                    "you'll need",
                    "you need to",
                    "on your behalf",
                    "access your",
                    "your account",
                ],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-B04",
        "name": "E2E Debugger — Root Cause Analysis",
        "section": "auto-coding",
        "model_slug": "e2edebugger",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "My Playwright test `test_login_redirect` fails intermittently. "
            "The error is: 'TimeoutError: locator.click: Timeout 30000ms exceeded.' "
            "The test clicks a 'Sign In' button that should redirect to /dashboard. "
            "It works locally but fails in CI. What's your diagnosis approach?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Timing issue suspected",
                "keywords": [
                    "timing",
                    "race",
                    "animation",
                    "network",
                    "slow",
                    "wait",
                    "timeout",
                    "flaky",
                ],
            },
            {
                "type": "any_of",
                "label": "Browser inspection suggested",
                "keywords": [
                    "snapshot",
                    "browser",
                    "inspect",
                    "navigate",
                    "reproduce",
                    "accessibility",
                ],
            },
        ],
    },
    {
        "id": "P-B05",
        "name": "Data Extractor — Extraction Strategy",
        "section": "auto-data",
        "model_slug": "dataextractor",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "I need to extract all product names and prices from a paginated "
            "e-commerce category page (20 products per page, ~50 pages). "
            "What's your approach using browser tools?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Pagination handling",
                "keywords": ["page", "pagination", "next", "click", "scroll", "iterate", "loop"],
            },
            {
                "type": "any_of",
                "label": "Structured output",
                "keywords": ["csv", "json", "table", "extract", "format", "structured"],
            },
        ],
    },
    {
        "id": "P-B06",
        "name": "Paywalled Researcher — Source Strategy",
        "section": "auto-research",
        "model_slug": "paywalledresearcher",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "I need to find recent papers on 'local LLM inference optimization' "
            "from ACM Digital Library and IEEE Xplore. I have institutional access "
            "to both. What's your approach?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Authenticated sources mentioned",
                "keywords": [
                    "acm",
                    "ieee",
                    "login",
                    "profile",
                    "session",
                    "access",
                    "institutional",
                ],
            },
            {
                "type": "any_of",
                "label": "Fallback to open access",
                "keywords": ["arxiv", "semantic scholar", "open access", "alternative", "free"],
                "critical": False,
            },
        ],
    },
    # -----------------------------------------------------------------------
    # Missing vision persona (M6)
    # -----------------------------------------------------------------------
    {
        "id": "P-V12",
        "name": "Whiteboard Converter — Diagram Recognition",
        "section": "auto-vision",
        "model_slug": "whiteboardconverter",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "If I send you a whiteboard photo of a system architecture sketch "
            "with boxes labeled 'API Gateway', 'Auth Service', 'User DB', and "
            "arrows between them, how would you convert it to a digital format?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Diagram type identification",
                "keywords": [
                    "architecture",
                    "flowchart",
                    "diagram",
                    "type",
                    "identify",
                    "classify",
                ],
            },
            {
                "type": "any_of",
                "label": "Mermaid or structured output",
                "keywords": ["mermaid", "markdown", "structured", "format", "convert", "digital"],
            },
            {
                "type": "any_of",
                "label": "Ambiguity handling or context-awareness",
                "keywords": [
                    "ambiguit",
                    "unclear",
                    "not sure",
                    "confidence",
                    "best guess",
                    "hard to distinguish",
                    "hard to identify",
                    "hard to read",
                    "potentially misread",
                    "manual check",
                    "need to verify",
                    "verify",
                    "i'll note",
                    "i'll flag",
                    "flag any",
                    "note any",
                    "where unclear",
                    "might be unclear",
                    "could be",
                    "might be",
                    "uncertain",
                    "indicate where",
                    "assuming",
                    "based on",
                    "depending",
                    "as described",
                    "from the description",
                    "you've described",
                    "you described",
                    "as you mentioned",
                    "given the",
                    "interpret",
                    "note that",
                ],
                "critical": False,
            },
        ],
    },
    # -----------------------------------------------------------------------
    # Missing persona smoke tests (M7)
    # -----------------------------------------------------------------------
    {
        "id": "P-N01",
        "name": "Goal Decomposition — Research & Deliver Plan",
        "section": "advanced",
        "model_slug": "auto-daily",  # gemma-4-26b — fast, non-thinking; agentic execution test is A-09
        "timeout": 90,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 600,
        "prompt": (
            "I want to research the 5 most recent CVEs affecting Apache HTTP Server "
            "and write up a summary report. "
            "List 4-5 concrete steps to accomplish this goal, "
            "and for each step identify what tool or resource you would use."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Step decomposition",
                "keywords": ["step", "1.", "2.", "3.", "first", "then", "next"],
            },
            {
                "type": "any_of",
                "label": "Tool identification",
                "keywords": ["search", "web", "tool", "create", "document", "word"],
            },
            {
                "type": "min_length",
                "label": "Substantive plan",
                "chars": 150,
            },
        ],
    },
    {
        "id": "P-N02",
        "name": "Business Analyst — Requirements Decomposition",
        "section": "advanced",
        "model_slug": "businessanalyst",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "The VP of Sales wants 'a better CRM.' "
            "Help me translate this into structured business requirements."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Distinguishes objective from feature",
                "keywords": ["objective", "goal", "problem", "requirement", "outcome"],
            },
            {
                "type": "any_of",
                "label": "Asks clarifying questions or lists open questions",
                "keywords": [
                    "what do you mean",
                    "clarif",
                    "more specific",
                    "which",
                    "who",
                    "stakeholder",
                    "open question",
                    "understand",
                ],
            },
        ],
    },
    {
        "id": "P-N03",
        "name": "Compliance Analyst — Multi-Framework Gap Analysis",
        "section": "auto-compliance",
        "model_slug": "complianceanalyst",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "We're a SaaS company storing health data for US clients and EU clients. "
            "Which compliance frameworks apply and where do we have potential gaps?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "HIPAA identified",
                "keywords": ["hipaa", "health insurance", "phi", "health data"],
            },
            {
                "type": "any_of",
                "label": "GDPR identified",
                "keywords": ["gdpr", "general data protection", "eu", "european"],
            },
            {
                "type": "any_of",
                "label": "Gap analysis framing",
                "keywords": ["gap", "risk", "requirement", "control", "framework"],
            },
        ],
    },
    {
        "id": "P-N04",
        "name": "Dashboard Architect — Executive Dashboard Design",
        "section": "auto-data",
        "model_slug": "dashboardarchitect",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Design an executive dashboard for a B2B SaaS company. "
            "The CEO cares most about MRR growth and churn. What should be above the fold?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Primary metrics identified",
                "keywords": ["mrr", "churn", "revenue", "trend", "growth"],
            },
            {
                "type": "any_of",
                "label": "Design principle applied",
                "keywords": [
                    "above the fold",
                    "headline",
                    "primary",
                    "key metric",
                    "data-ink",
                    "few",
                    "tufte",
                    "single",
                    "focus",
                ],
            },
        ],
    },
    {
        "id": "P-N05",
        "name": "Database Architect — Multi-Tenant Schema",
        "section": "auto-data",
        "model_slug": "databasearchitect",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Design a database schema for a multi-tenant SaaS application "
            "with organizations, users, projects, and audit logs. "
            "Recommend a tenancy model and explain the trade-offs."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Tenancy model discussed",
                "keywords": [
                    "row-level",
                    "schema-per",
                    "database-per",
                    "shared schema",
                    "tenant_id",
                    "tenancy",
                    "isolation",
                    "separate schema",
                ],
            },
            {
                "type": "any_of",
                "label": "Trade-offs acknowledged",
                "keywords": [
                    "trade-off",
                    "cost",
                    "isolation",
                    "complexity",
                    "performance",
                    "easier",
                    "harder",
                    "pros",
                    "cons",
                ],
            },
            {"type": "has_code", "label": "Schema DDL or pseudo-code present"},
        ],
    },
    {
        "id": "P-N06",
        "name": "Diagram Reader — Architecture Interpretation",
        "section": "auto-vision",
        "model_slug": "diagramreader",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "I'm about to send you a C4 container diagram of a microservices system. "
            "What information will you extract and how will you represent it in text?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Diagram type identified",
                "keywords": ["c4", "container", "diagram type", "architecture", "component"],
            },
            {
                "type": "any_of",
                "label": "Output format mentioned",
                "keywords": [
                    "mermaid",
                    "markdown",
                    "text",
                    "structured",
                    "format",
                    "describe",
                    "represent",
                    "list",
                ],
            },
        ],
    },
    {
        "id": "P-N07",
        "name": "Documentation Architect — Diátaxis Framework",
        "section": "auto-docs",
        "model_slug": "documentationarchitect",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "We have a REST API and want to document it properly. "
            "We currently only have an OpenAPI spec. "
            "What documentation types do we need and why?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Diátaxis modes or equivalents",
                "keywords": [
                    "tutorial",
                    "how-to",
                    "reference",
                    "explanation",
                    "guide",
                    "conceptual",
                    "diataxis",
                ],
            },
            {
                "type": "any_of",
                "label": "OpenAPI limitation acknowledged",
                "keywords": [
                    "spec",
                    "reference only",
                    "not enough",
                    "also need",
                    "beyond the spec",
                    "openapi alone",
                    "just a spec",
                ],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-N08",
        "name": "Fact Checker — Claim Verification Protocol",
        "section": "auto-research",
        "model_slug": "factchecker",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "Claim: 'Python is the most popular programming language in the world.' "
            "Walk me through how you'd fact-check this."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Authoritative source identified",
                "keywords": [
                    "tiobe",
                    "stackoverflow",
                    "github",
                    "source",
                    "survey",
                    "index",
                    "primary",
                    "authoritative",
                    "redmonk",
                ],
            },
            {
                "type": "any_of",
                "label": "Nuance or context noted",
                "keywords": [
                    "depends",
                    "definition",
                    "metric",
                    "measure",
                    "context",
                    "how you define",
                    "varies",
                    "depends on",
                ],
            },
        ],
    },
    {
        "id": "P-N09",
        "name": "GDPR DPO Advisor — Lawful Basis Assessment",
        "section": "auto-compliance",
        "model_slug": "gdprdpoadvisor",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Our app sends marketing emails to EU users. "
            "We currently rely on 'legitimate interests' as the lawful basis. "
            "Is this appropriate, and what are the risks?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Article 6 or lawful basis identified",
                "keywords": [
                    "article 6",
                    "art. 6",
                    "lawful basis",
                    "legitimate interest",
                    "balancing test",
                    "lia",
                    "legitimate interests assessment",
                ],
            },
            {
                "type": "any_of",
                "label": "Right to object mentioned",
                "keywords": [
                    "opt-out",
                    "right to object",
                    "article 21",
                    "unsubscribe",
                    "object",
                    "oppose",
                ],
            },
            {
                "type": "any_of",
                "label": "Risk or alternative noted",
                "keywords": ["consent", "risk", "emarketing", "pecr", "alternative", "reconsider"],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-N10",
        "name": "Go Engineer — Idiomatic Error Handling",
        "section": "auto-coding",
        "model_slug": "goengineer",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Write a Go function that reads a JSON config file, "
            "unmarshals it into a Config struct, and returns it with proper error handling. "
            "Show idiomatic Go error wrapping."
        ),
        "assertions": [
            {"type": "has_code", "label": "Code block present"},
            {
                "type": "any_of",
                "label": "Idiomatic error return",
                "keywords": ["error", "fmt.errorf", "return nil", "return err", "%w"],
            },
            {
                "type": "any_of",
                "label": "JSON unmarshal used",
                "keywords": ["unmarshal", "json.unmarshal", "os.readfile", "os.open"],
            },
        ],
    },
    {
        "id": "P-N11",
        "name": "HIPAA Privacy Officer — Breach Notification",
        "section": "auto-compliance",
        "model_slug": "hipaaprivacyofficer",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "A laptop containing unencrypted PHI for 450 patients was stolen. "
            "Walk me through HIPAA breach notification requirements and deadlines."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Breach assessment step",
                "keywords": [
                    "risk assessment",
                    "assess",
                    "determine",
                    "evaluate",
                    "whether",
                    "reportable",
                    "notification required",
                ],
            },
            {
                "type": "any_of",
                "label": "60-day deadline or HHS notification",
                "keywords": ["60 day", "60-day", "hhs", "secretary", "notification deadline"],
            },
            {
                "type": "any_of",
                "label": "Affected individuals notified",
                "keywords": ["notify", "individual", "patient", "affected", "letter"],
            },
        ],
    },
    {
        "id": "P-N12",
        "name": "Interview Coach — Technical Screening Prep",
        "section": "advanced",
        "model_slug": "interviewcoach",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "I'm preparing for a senior software engineer interview at a FAANG company. "
            "Give me 3 realistic system design questions I should practice, "
            "and what aspects of my answer will interviewers evaluate?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "System design questions provided",
                "keywords": ["design", "system", "scale", "how would you", "build a"],
            },
            {
                "type": "any_of",
                "label": "Evaluation criteria mentioned",
                "keywords": [
                    "clarif",
                    "requirement",
                    "trade-off",
                    "scale",
                    "bottleneck",
                    "evaluate",
                    "looking for",
                    "interviewers",
                ],
            },
        ],
    },
    {
        "id": "P-N13",
        "name": "Knowledge Base Navigator — KB Retrieval Protocol",
        "section": "auto-research",
        "model_slug": "kbnavigator",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "What knowledge bases do you have access to, "
            "and how would you find information about our product's API rate limits?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "KB listing step described",
                "keywords": [
                    "kb_list",
                    "list",
                    "available",
                    "check",
                    "first",
                    "which kb",
                    "what kbs",
                    "knowledge base",
                    "collections",
                ],
            },
            {
                "type": "any_of",
                "label": "Search strategy described",
                "keywords": [
                    "search",
                    "query",
                    "look for",
                    "retrieve",
                    "kb_search",
                    "find",
                    "locate",
                ],
            },
        ],
    },
    {
        "id": "P-N14",
        "name": "Market Analyst — Competitive Analysis",
        "section": "auto-research",
        "model_slug": "marketanalyst",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Give me a competitive analysis of the top 3 players in the local LLM inference market. "
            "What's driving adoption?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Market players or segments mentioned",
                "keywords": [
                    "ollama",
                    "llm",
                    "local",
                    "inference",
                    "open source",
                    "model",
                    "deployment",
                    "on-premise",
                    "self-hosted",
                ],
            },
            {"type": "min_length", "label": "Substantive analysis", "chars": 200},
        ],
    },
    {
        "id": "P-N15",
        "name": "Math Reasoner — Calculus Proof from First Principles",
        "section": "auto-math",
        "model_slug": "mathreasoner",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Prove that the derivative of sin(x) is cos(x) from first principles "
            "(limit definition of the derivative). Show every step."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Limit definition stated",
                "keywords": [
                    "lim",
                    "h→0",
                    "h -> 0",
                    "limit",
                    "definition of derivative",
                    "difference quotient",
                ],
            },
            {
                "type": "any_of",
                "label": "Sine addition formula used",
                "keywords": [
                    "sin(x+h)",
                    "sin(a+b)",
                    "addition formula",
                    "sum formula",
                    "trig identity",
                    "sin x cos h",
                ],
            },
            {
                "type": "any_of",
                "label": "Result stated",
                "keywords": ["cos(x)", "cos x", "= cos"],
            },
        ],
    },
    {
        "id": "P-N16",
        "name": "OCR Specialist — Two-Column Table Extraction",
        "section": "auto-vision",
        "model_slug": "ocrspecialist",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "I have a scanned two-column academic paper with a table in the results section. "
            "How would you extract the table data accurately?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Layout detection mentioned",
                "keywords": [
                    "column",
                    "layout",
                    "two-column",
                    "region",
                    "detect",
                    "identify",
                    "structure",
                ],
            },
            {
                "type": "any_of",
                "label": "Table extraction strategy",
                "keywords": [
                    "row",
                    "header",
                    "cell",
                    "table",
                    "csv",
                    "json",
                    "structured",
                    "delimit",
                ],
            },
        ],
    },
    {
        "id": "P-N17",
        "name": "PCI-DSS Assessor — Stripe Elements Scope",
        "section": "auto-compliance",
        "model_slug": "pcidssassessor",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "We use Stripe Elements for payment collection. "
            "Does this reduce our PCI-DSS scope, and if so, to which SAQ?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Scope reduction confirmed",
                "keywords": ["scope", "reduce", "cardholder data", "cde", "out of scope"],
            },
            {
                "type": "any_of",
                "label": "SAQ type identified",
                "keywords": ["saq a", "saq a-ep", "saq", "self-assessment"],
            },
        ],
    },
    {
        "id": "P-N18",
        "name": "Product Manager — PRD Structure",
        "section": "advanced",
        "model_slug": "productmanager",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "We want to add AI-powered search to our B2B SaaS platform. "
            "Outline the key sections of a PRD for this feature."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Problem or user need section",
                "keywords": [
                    "problem",
                    "user need",
                    "pain point",
                    "opportunity",
                    "why",
                    "objective",
                ],
            },
            {
                "type": "any_of",
                "label": "Success metrics included",
                "keywords": [
                    "metric",
                    "kpi",
                    "success",
                    "measure",
                    "adoption",
                    "engagement",
                    "target",
                ],
            },
            {
                "type": "any_of",
                "label": "Out of scope or assumptions",
                "keywords": [
                    "out of scope",
                    "assumption",
                    "constraint",
                    "non-goal",
                    "not in scope",
                ],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-N19",
        "name": "Proofreader — Copy Editing Pass",
        "section": "auto-creative",
        "model_slug": "proofreader",
        "timeout": 60,
        "workspace_tier": "ollama",  # auto-creative → dolphin-llama3:8b via Ollama (Gemma 4 VLM thinking model is wrong for text tasks)
        "prompt": (
            "Proofread this sentence and explain all corrections: "
            "'The team have agreed, that they will meet on tuesday at 3pm "
            "to dicuss the projects progress and it's impact.'"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Subject-verb agreement noted",
                "keywords": [
                    "team has",
                    "subject-verb",
                    "collective noun",
                    "singular",
                    "have → has",
                    "has agreed",
                ],
            },
            {
                "type": "any_of",
                "label": "Spelling error found",
                "keywords": ["discuss", "dicuss", "spelling", "typo"],
            },
            {
                "type": "any_of",
                "label": "Apostrophe error found",
                "keywords": ["it's", "its", "possessive", "apostrophe", "contraction"],
            },
        ],
    },
    {
        "id": "P-N20",
        "name": "Rust Engineer — Result Propagation",
        "section": "auto-coding",
        "model_slug": "rustengineer",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Write a Rust function that reads a file path from args, "
            "reads the file contents, and returns a word count. "
            "Use proper Result propagation and no unwrap() in non-main code."
        ),
        "assertions": [
            {"type": "has_code", "label": "Code block present"},
            {
                "type": "any_of",
                "label": "Result propagation",
                "keywords": ["result", "?", "err", "io::error", "std::io"],
            },
            {
                "type": "any_of",
                "label": "File reading idiom",
                "keywords": [
                    "fs::read_to_string",
                    "file::open",
                    "read_to_string",
                    "buf_reader",
                ],
            },
        ],
    },
    {
        "id": "P-N21",
        "name": "SOC 2 Auditor — Control Gap Assessment",
        "section": "auto-compliance",
        "model_slug": "soc2auditor",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Our SaaS company is preparing for a SOC 2 Type II audit. "
            "We have no formal access review process and no MFA enforcement. "
            "Which Trust Services Criteria are at risk?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Security criteria identified",
                "keywords": [
                    "cc6",
                    "cc5",
                    "common criteria",
                    "security",
                    "access control",
                    "logical access",
                    "cc6.1",
                    "cc6.2",
                ],
            },
            {
                "type": "any_of",
                "label": "MFA or access review gap",
                "keywords": [
                    "mfa",
                    "multi-factor",
                    "access review",
                    "periodic review",
                    "user access",
                    "logical access",
                ],
            },
        ],
    },
    {
        "id": "P-N22",
        "name": "Splunk Detection Author — Impossible Travel Rule",
        "section": "auto-spl",
        "model_slug": "splunkdetectionauthor",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Write a Splunk detection for T1078 (Valid Accounts) — specifically, "
            "a user account authenticating from two geographically distant IPs "
            "within 60 minutes. Include MITRE mapping and risk score."
        ),
        "assertions": [
            {"type": "has_code", "label": "SPL detection present"},
            {
                "type": "any_of",
                "label": "MITRE ATT&CK mapping",
                "keywords": ["t1078", "valid accounts", "mitre", "att&ck", "technique"],
            },
            {
                "type": "any_of",
                "label": "Geographic or timing logic",
                "keywords": [
                    "geo",
                    "location",
                    "distance",
                    "ip",
                    "60 minute",
                    "time window",
                    "span",
                    "earliest",
                    "latest",
                ],
            },
        ],
    },
    {
        "id": "P-N23",
        "name": "Terraform Writer — S3 Module",
        "section": "auto-coding",
        "model_slug": "terraformwriter",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Write a Terraform module for an AWS S3 bucket with versioning, "
            "server-side encryption, and public access blocked. "
            "Use proper module structure with variables and outputs."
        ),
        "assertions": [
            {"type": "has_code", "label": "Terraform code present"},
            {
                "type": "any_of",
                "label": "S3 bucket resource",
                "keywords": ["aws_s3_bucket", "resource", "bucket"],
            },
            {
                "type": "any_of",
                "label": "Security controls present",
                "keywords": [
                    "versioning",
                    "encryption",
                    "server_side_encryption",
                    "block_public",
                    "public_access",
                ],
            },
        ],
    },
    {
        "id": "P-N24",
        "name": "Transcript Analyst — Meeting Summary Protocol",
        "section": "auto-docs",
        "model_slug": "transcriptanalyst",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "Before I upload my audio, can you describe what output you produce "
            "and in what format for a 45-minute engineering all-hands meeting recording?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Transcript or summary output described",
                "keywords": [
                    "transcript",
                    "summary",
                    "action item",
                    "speaker",
                    "key point",
                    "decision",
                    "formatted",
                ],
            },
            {
                "type": "any_of",
                "label": "Document export mentioned",
                "keywords": ["word", "docx", "document", "export", "download", "file"],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-N25",
        "name": "TypeScript Engineer — Generic Pick Utility",
        "section": "auto-coding",
        "model_slug": "typescriptengineer",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "Write a TypeScript generic function "
            "`pick<T, K extends keyof T>(obj: T, keys: K[]): Pick<T, K>` "
            "that returns an object with only the specified keys. "
            "Show how TypeScript infers the return type correctly with an example."
        ),
        "assertions": [
            {"type": "has_code", "label": "Code block present"},
            {
                "type": "any_of",
                "label": "Generic signature correct",
                "keywords": ["<T", "keyof", "extends", "pick<", "K[]"],
            },
            {
                "type": "any_of",
                "label": "Type inference demonstrated",
                "keywords": ["infer", "typeof", "const", "type", "Pick<"],
            },
        ],
    },
    {
        "id": "P-N26",
        "name": "Web Researcher — Multi-Source Research Protocol",
        "section": "auto-research",
        "model_slug": "webresearcher",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "Research the current state of Mixture-of-Experts (MoE) models for local inference. "
            "Describe your research protocol: what sources will you consult and how will you "
            "verify the findings?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Multi-source or verification strategy",
                "keywords": [
                    "multiple source",
                    "cross-reference",
                    "verify",
                    "source",
                    "arxiv",
                    "papers",
                    "different",
                    "cross-check",
                ],
            },
            {
                "type": "any_of",
                "label": "Research process described",
                "keywords": [
                    "web_search",
                    "search",
                    "first",
                    "then",
                    "step",
                    "protocol",
                    "approach",
                    "fetch",
                ],
            },
        ],
    },
    # -----------------------------------------------------------------------
    # Missing bench workspace tests (M7)
    # -----------------------------------------------------------------------
]
