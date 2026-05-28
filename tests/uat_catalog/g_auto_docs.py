"""UAT catalog group: auto-docs (documents workspace)."""
from __future__ import annotations

from tests.uat_catalog._shared import REFUSAL_PHRASES, _CC01_ASSERTIONS, _CC01_ASSERTIONS_BENCH  # noqa: F401

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "WS-10",
        "name": "Document Builder — Change Management DOCX",
        "section": "auto-docs",
        "model_slug": "auto-documents",
        "timeout": 180,
        "workspace_tier": "mlx_small",
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
        "workspace_tier": "mlx_small",
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
        "workspace_tier": "mlx_small",
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
        "workspace_tier": "mlx_small",
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
                "keywords": ["error", "failed", "unable"],
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
        "workspace_tier": "mlx_small",
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
        "workspace_tier": "mlx_small",
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
        ],
    },]
