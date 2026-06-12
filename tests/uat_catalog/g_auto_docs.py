"""UAT catalog group: auto-docs (documents workspace)."""
from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "WS-10",
        "name": "Document Builder — Change Management DOCX",
        "section": "auto-docs",
        "model_slug": "auto-documents",
        "timeout": 180,
        "workspace_tier": "ollama",
        "artifact_ext": "docx",
        "prompt": (
            'Create a Word document: "Change Management Procedure for OT Environments". '
            "Include: Purpose, Scope, Definitions (table: Term | Definition, at least 4 rows), "
            "Change Request Process (numbered steps), Risk Assessment Matrix "
            "(table: Risk | Likelihood | Impact | Mitigation), and Approvals section. "
            "Save as a .docx file."
        ),
        "assertions": [
            {
                "type": "not_contains",
                "label": "No error message",
                "keywords": ["error", "failed", "unable to create"],
                "critical": True,
            },
            {"type": "docx_valid", "label": "DOCX file opens without error"},
        ],
    },
    {
        "id": "P-W04",
        "name": "Tech Writer — Audience-Appropriate Docs",
        "section": "auto-docs",
        "model_slug": "techwriter",
        "timeout": 360,
        "workspace_tier": "ollama",
        "prompt": (
            "Write a 'Getting Started' guide for a junior developer joining our team. "
            "They need to set up a local development environment for a Python FastAPI project. "
            "The project uses Docker Compose, PostgreSQL, and Redis. "
            "They have Python experience but have never used Docker."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Prerequisites section",
                "keywords": [
                    "prerequisite",
                    "before you begin",
                    "requirements",
                    "what you need",
                    "setup",
                    "getting started",
                    "install",
                    "you'll need",
                    "make sure",
                ],
            },
            {
                "type": "any_of",
                "label": "Verification steps",
                "keywords": [
                    "verify",
                    "confirm",
                    "you should see",
                    "check",
                    "test",
                    "validate",
                    "ensure",
                    "make sure",
                    "should be able",
                ],
            },
            {
                "type": "not_contains",
                "label": "Not condescending",
                "keywords": ["simply", "just run", "easily", "trivially"],
                "critical": False,
            },
            {"type": "min_length", "label": "Comprehensive guide", "chars": 800},
        ],
    },
    {
        "id": "P-W05",
        "name": "Phi-4 Technical Analyst — Conclusion First",
        "section": "auto-docs",
        "model_slug": "phi4specialist",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": "Analyze this system: A FastAPI app uses a synchronous SQLAlchemy session inside async route handlers. Is this a problem? Should it be fixed?",
        "assertions": [
            {
                "type": "any_of",
                "label": "Direct answer first",
                "keywords": ["yes", "this is a problem", "blocking", "issue"],
            },
            {
                "type": "any_of",
                "label": "Event loop explained",
                "keywords": ["event loop", "blocking", "async", "await"],
            },
            {
                "type": "any_of",
                "label": "Fix provided",
                "keywords": ["async sqlalchemy", "run_in_executor", "asyncpg", "fix"],
            },
        ],
    },
    {
        "id": "T-04",
        "name": "Document Generation — DOCX with Table",
        "section": "auto-docs",
        "model_slug": "auto-documents",
        "timeout": 180,
        "workspace_tier": "ollama",
        "artifact_ext": "docx",
        "prompt": (
            'Create a Word document: "Vendor Security Assessment Checklist". '
            "Include a table with columns: Control Area | Check | Status | Notes. "
            "Pre-populate 6 rows covering: Data Encryption, Access Control, Patch Management, "
            "Incident Response, Data Residency, SOC 2 Certification. "
            "Add a Summary section after the table. Save as a .docx file."
        ),
        "assertions": [
            {
                "type": "not_contains",
                "label": "No error",
                "keywords": ["error", "failed", "unable to create"],
            },
            {"type": "docx_valid", "label": "DOCX file valid"},
        ],
    },
    {
        "id": "T-05",
        "name": "Document Generation — Excel Tracker",
        "section": "auto-docs",
        "model_slug": "auto-documents",
        "timeout": 180,
        "workspace_tier": "ollama",
        "artifact_ext": "xlsx",
        "prompt": (
            'Create an Excel workbook: "Security Incident Tracker". '
            "Columns: Incident ID | Date | Severity (Critical/High/Medium/Low) | "
            "Affected System | Status (Open/In Progress/Resolved) | Owner | Resolution Date. "
            "Add 5 sample rows with realistic incident data."
        ),
        "assertions": [
            {
                "type": "not_contains",
                "label": "No error",
                "keywords": ["an error occurred", "tool error", "failed to generate", "generation failed", "unable to create"],
            },
            {"type": "xlsx_valid", "label": "XLSX file valid"},
        ],
    },
    {
        "id": "T-06",
        "name": "Document Generation — PowerPoint Zero Trust",
        "section": "auto-docs",
        "model_slug": "auto-documents",
        "timeout": 180,
        "workspace_tier": "ollama",
        "artifact_ext": "pptx",
        "prompt": (
            'Create a 5-slide PowerPoint: "Introduction to Zero Trust Networking". '
            "Slide 1: Title. Slides 2–5: content slides with title + 3 bullet points each. "
            "Topics: (2) What is Zero Trust, (3) Core Principles, "
            "(4) Implementation Steps, (5) Common Mistakes."
        ),
        "assertions": [
            {
                "type": "not_contains",
                "label": "No error",
                "keywords": ["error generating", "failed to create", "unable to generate"],
                "critical": False,
            },
            {
                "type": "pptx_valid",
                "label": "PPTX has 5 slides",
                "min_slides": 5,
                "critical": False,
            },
        ],
    },
    {
        "id": "T-07",
        "name": "Document Reading — Parse Uploaded Word File",
        "section": "auto-docs",
        "model_slug": "auto-documents",
        "timeout": 120,
        "workspace_tier": "ollama",
        "skip_if": "no_docx_fixture",
        "prompt": (
            "Read this document. Tell me: how many sections or headings it has, "
            "summarize the main content of each section in one sentence, and list any "
            "tables present with their column headers."
        ),
        "assertions": [
            {
                "type": "not_contains",
                "label": "No 'cannot read'",
                "keywords": ["cannot read", "unable to read", "can't access"],
            },
            {"type": "min_length", "label": "Substantive summary", "chars": 150},
            {
                "type": "any_of",
                "label": "Document content found — proves read_word_document ran",
                "keywords": [
                    "Network Security", "Access Control", "Introduction",
                    "Authentication", "least privilege", "RBAC",
                ],
                "critical": False,
            },
        ],
    },
    # ── Tool-read validation (TV-07 – TV-10): prove read tools actually ran ──────
    # Each test stages a fixture to ~/AI_Output/uploads/ (→ /app/data/generated/uploads/
    # inside the documents container), then asks the model to read it at that path.
    # The assertion checks for specific fixture content — a model hallucinating without
    # calling the tool cannot produce those exact values.
    {
        "id": "TV-07",
        "name": "Tool Validation — read_excel proof (sample.xlsx)",
        "section": "auto-docs",
        "model_slug": "auto-documents",
        "timeout": 90,
        "workspace_tier": "ollama",
        "fixture": "sample.xlsx",
        "pre_stage_audio": True,
        "prompt": (
            "Use read_excel to read the file at /app/data/generated/uploads/sample.xlsx "
            "and tell me the column headers and every data value in the spreadsheet."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Column headers found — proves read_excel ran",
                "keywords": ["Name", "Value"],
            },
            {
                "type": "any_of",
                "label": "Row data found",
                "keywords": ["Test", "42"],
                "critical": False,
            },
            {
                "type": "not_contains",
                "label": "No file-not-found error",
                "keywords": ["file not found", "cannot read", "failed to read"],
                "critical": False,
            },
        ],
    },
    {
        "id": "TV-08",
        "name": "Tool Validation — read_pdf proof (sample.pdf)",
        "section": "auto-docs",
        "model_slug": "auto-documents",
        "timeout": 90,
        "workspace_tier": "ollama",
        "fixture": "sample.pdf",
        "pre_stage_audio": True,
        "prompt": (
            "Use read_pdf to read the file at /app/data/generated/uploads/sample.pdf "
            "and tell me the text content on each page."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Fixture text found — proves read_pdf ran",
                "keywords": ["Portal 5 UAT Fixture", "Portal 5", "UAT Fixture", "Section 1", "Overview"],
            },
            {
                "type": "not_contains",
                "label": "No file-not-found error",
                "keywords": ["file not found", "cannot read", "pdfplumber not installed"],
                "critical": False,
            },
        ],
    },
    {
        "id": "TV-09",
        "name": "Tool Validation — read_powerpoint proof (sample.pptx)",
        "section": "auto-docs",
        "model_slug": "auto-documents",
        "timeout": 90,
        "workspace_tier": "ollama",
        "fixture": "sample.pptx",
        "pre_stage_audio": True,
        "prompt": (
            "Use read_powerpoint to read the file at /app/data/generated/uploads/sample.pptx "
            "and tell me the title and content of each slide."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Slide content found — proves read_powerpoint ran",
                "keywords": ["Test Presentation", "acceptance testing", "Sample content"],
            },
            {
                "type": "not_contains",
                "label": "No file-not-found error",
                "keywords": ["file not found", "cannot read", "failed to read"],
                "critical": False,
            },
        ],
    },
    {
        "id": "TV-10",
        "name": "Tool Validation — read_word_document proof (sample.docx)",
        "section": "auto-docs",
        "model_slug": "auto-documents",
        "timeout": 90,
        "workspace_tier": "ollama",
        "fixture": "sample.docx",
        "pre_stage_audio": True,
        "prompt": (
            "Use read_word_document to read the file at /app/data/generated/uploads/sample.docx "
            "and tell me the document title and list each section heading."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Document title found — proves read_word_document ran",
                "keywords": [
                    "Network Security Policy",
                    "Access Control Framework",
                    "Network Security",
                ],
            },
            {
                "type": "any_of",
                "label": "Section headings found",
                "keywords": ["Introduction", "Access Control Policy", "Authentication", "Conclusion"],
                "critical": False,
            },
            {
                "type": "not_contains",
                "label": "No file-not-found error",
                "keywords": ["file not found", "cannot read", "failed to read"],
                "critical": False,
            },
        ],
    },]
