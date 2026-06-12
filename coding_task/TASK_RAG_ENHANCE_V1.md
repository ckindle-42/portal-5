# TASK_RAG_ENHANCE_V1 (self-contained)

**Repo:** github.com/ckindle-42/portal-5 · clone to `/home/claude/portal-5`
**Audited at HEAD:** `124870d` (uat: 163P/0F/5W — 97.0% pass rate, origin/main)
**Execution model:** fully self-contained. The agent applies every edit below itself, verifies, commits, pushes.

---

## 0. Why — three additive RAG + eval enhancements

Portal 5's RAG pipeline works but has three quality gaps:

1. **Document parsing is basic.** `_read_file()` uses pypdf (no table/layout/multi-column
   awareness) and python-docx (paragraphs only). PPTX, XLSX, HTML, EPUB are not
   supported at all. Docling adds enterprise-grade document understanding —
   96% table accuracy, layout preservation, chart understanding, 11 format support.

2. **No quality evaluation framework.** `bench_tps.py` measures speed (TPS, TTFT)
   but cannot answer "is the output correct?" Promptfoo fills this gap with 30+
   assertion types, LLM-as-judge grading (using local Ollama models), and
   CI-ready pass/fail exit codes.

3. **LanceDB is underutilized.** Both RAG and Memory MCPs use LanceDB but only
   with dense vector search. LanceDB's FTS indexes, hybrid search (vector +
   BM25), IVF_PQ compression, and table versioning are unused. Adding these
   improves retrieval quality and reduces storage.

All three are additive — no existing behavior changes, no pipeline/router edits.

---

## Architecture Decisions

- **A1 — Docling is a drop-in enhancement to `_read_file()`, not a replacement.**
  Try Docling first for PDF/DOCX; fall back to pypdf/python-docx on failure.
  New formats (PPTX/XLSX/HTML/EPUB) are Docling-only. The `kb_ingest` tool
  surface is unchanged — it still reads a directory and chunks/embeds files;
  the improvement is what text gets extracted from each file.

- **A2 — Docling runs in the MCP container** (`Dockerfile.mcp`), not OWUI.
  The pipeline Dockerfile stays lean (Rule 9). Docling's OWUI plugin is
  documented in HOWTO.md as an optional bonus.

- **A3 — Promptfoo is dev-only.** Added to `pyproject.toml` under `dev` extras.
  Config files in `config/promptfoo/`. A `./launch.sh promptfoo` command wraps
  eval runs. No production Docker images include it.

- **A4 — Promptfoo configs cover all 22 functional workspaces** grouped into
  7 area-specific config files, each with 3-5 test prompts + appropriate
  assertions (correctness, style, refusal-check, latency).

- **A5 — LanceDB FTS indexes are created during `kb_ingest` (opt-in).**
  A new `fts` boolean parameter on `kb_ingest` (default `false`) creates a
  BM25 FTS index on the `text` column after ingestion. The `kb_search` tool
  gains an optional `query_type` parameter: `"vector"` (default, current
  behavior), `"fts"` (BM25 only), `"hybrid"` (vector + BM25 with RRF fusion).
  Existing KBs work exactly as before.

- **A6 — IVF_PQ indexing is opt-in for large KBs.**
  KBs with >10K chunks benefit from compressed vector indexes. A new
  `kb_optimize` tool creates IVF_PQ indexes on an existing KB.

- **A7 — LanceDB table versioning for rollback.**
  `kb_ingest` with `rebuild=True` creates a versioned snapshot before dropping.
  New `kb_versions` and `kb_restore` tools use LanceDB's native time-travel.

- **A8 — All additions ship with unit tests.**
  Docling: mock-based test of `_read_file` with Docling enabled/disabled.
  Promptfoo: config validation test. LanceDB: tests for FTS, hybrid search,
  optimize, and versioning.

---

## Task Index

| # | File | Op | What |
|---|---|---|---|
| **Phase 1 — Docling Document Parsing** |||
| T1 | `Dockerfile.mcp` | str_replace | Add `docling>=2.0.0` dependency |
| T2 | `portal_mcp/rag/rag_mcp.py` | str_replace | Rewrite `_read_file()` — Docling-first with pypdf/python-docx fallback |
| T3 | `portal_mcp/rag/rag_mcp.py` | str_replace | Add `.pptx/.xlsx/.html/.epub` to kb_ingest file filter |
| T4 | `tests/unit/test_rag.py` | create_file | Unit tests for docling-enhanced `_read_file` |
| T5 | `docs/HOWTO.md` | str_replace | Document Docling integration |
| **Phase 2 — Promptfoo Evaluation Framework** |||
| T6 | `pyproject.toml` | str_replace | Add `promptfoo` to dev extras |
| T7 | `config/promptfoo/` | create_file ×7 | Eval configs for all 22 functional workspaces (7 grouped files) |
| T8 | `launch.sh` | str_replace | Add `promptfoo)` case to command dispatcher |
| T9 | `launch.sh` | str_replace | Add promptfoo to usage line + help text |
| T10 | `tests/unit/test_promptfoo_configs.py` | create_file | Config validation: all workspace refs resolve |
| **Phase 3 — LanceDB Optimizations** |||
| T11 | `portal_mcp/rag/rag_mcp.py` | str_replace | Add `fts` parameter to kb_ingest — creates BM25 FTS index after ingestion |
| T12 | `portal_mcp/rag/rag_mcp.py` | str_replace | Add `query_type` parameter to kb_search TOOLS_MANIFEST + endpoint |
| T13 | `portal_mcp/rag/rag_mcp.py` | str_replace | Add `kb_optimize` tool (IVF_PQ index) to TOOLS_MANIFEST + endpoint |
| T14 | `portal_mcp/rag/rag_mcp.py` | str_replace | Add `kb_versions` + `kb_restore` tools to TOOLS_MANIFEST + endpoints |
| T15 | `tests/unit/test_rag.py` | extend | Tests for FTS, hybrid search, optimize, versioning |
| T16 | `docs/HOWTO.md` | str_replace | Document new LanceDB tools |

---

## 1. Safety tag

```bash
cd /home/claude/portal-5
git fetch origin && git merge --ff-only origin/main
git rev-list --left-right --count HEAD...origin/main      # expect: 0   0
git tag pre-rag-enhance-v1 HEAD
git log --oneline -1                                      # expect HEAD == 124870d (or newer)
```

---

## Phase 1 — Docling Document Parsing

### T1 — Add Docling to Dockerfile.mcp

**File:** `Dockerfile.mcp`

`str_replace`:
- `old_str`:
```
    "pypdf>=4.0.0"
```
- `new_str`:
```
    "pypdf>=4.0.0" \
    "docling>=2.0.0"
```

**Verify:**
```bash
grep -q 'docling>=' Dockerfile.mcp && echo "PASS T1" || echo "FAIL T1"
```

---

### T2 — Rewrite `_read_file()` with Docling

**File:** `portal_mcp/rag/rag_mcp.py`

`str_replace`:
- `old_str`:
```python
async def _read_file(path):
    """Best-effort text extraction from common formats."""
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt"):
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            r = PdfReader(str(path))
            return "\n\n".join(p.extract_text() or "" for p in r.pages)
        except Exception as e:
            logger.warning("PDF read failed for %s: %s", path, e)
            return ""
    if suffix == ".docx":
        try:
            from docx import Document

            d = Document(str(path))
            return "\n\n".join(p.text for p in d.paragraphs)
        except Exception as e:
            logger.warning("DOCX read failed for %s: %s", path, e)
            return ""
    return ""
```
- `new_str`:
```python
async def _read_file(path):
    """Extract text via Docling (preferred) with pypdf/python-docx fallback.

    Docling provides table extraction (96% TEDS), layout preservation,
    reading-order awareness, and chart understanding. Falls back to basic
    pypdf/python-docx when Docling is unavailable or fails.
    """
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt"):
        return path.read_text(encoding="utf-8", errors="replace")

    # Docling covers: pdf, docx, pptx, xlsx, html, epub
    _docling_formats = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".epub"}
    if suffix in _docling_formats:
        try:
            from docling.document_converter import DocumentConverter

            converter = DocumentConverter()
            result = converter.convert(str(path))
            text = result.document.export_to_markdown()
            if text and len(text.strip()) > 20:
                return text
        except Exception as e:
            logger.warning("Docling read failed for %s, falling back: %s", path, e)

    # Fallbacks for when Docling is unavailable or returns no content
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            r = PdfReader(str(path))
            return "\n\n".join(p.extract_text() or "" for p in r.pages)
        except Exception as e:
            logger.warning("PDF fallback read failed for %s: %s", path, e)
            return ""
    if suffix == ".docx":
        try:
            from docx import Document

            d = Document(str(path))
            return "\n\n".join(p.text for p in d.paragraphs)
        except Exception as e:
            logger.warning("DOCX fallback read failed for %s: %s", path, e)
            return ""
    return ""
```

**Verify:**
```bash
python3 -c "
from portal_mcp.rag.rag_mcp import _read_file
import inspect
src = inspect.getsource(_read_file)
assert 'docling.document_converter' in src, 'Docling import missing'
assert 'export_to_markdown' in src, 'Docling markdown export missing'
assert 'pypdf' in src, 'pypdf fallback missing'
assert 'python-docx' not in src and 'from docx import' in src, 'DOCX fallback missing'
print('PASS T2')
"
```

---

### T3 — Add new formats to kb_ingest file filter

**File:** `portal_mcp/rag/rag_mcp.py`

`str_replace`:
- `old_str`:
```python
        if f.is_file() and f.suffix.lower() in (".md", ".txt", ".pdf", ".docx")
```
- `new_str`:
```python
        if f.is_file() and f.suffix.lower() in (".md", ".txt", ".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".epub")
```

Also update the TOOLS_MANIFEST `kb_ingest` description to reflect new formats:

`str_replace`:
- `old_str`:
```python
        "name": "kb_ingest",
        "description": "Admin: ingest files from a directory into a knowledge base. Reads .md, .txt, .pdf, .docx files. Run via curl or as setup; not typically called from chat.",
```
- `new_str`:
```python
        "name": "kb_ingest",
        "description": "Admin: ingest files from a directory into a knowledge base. Reads .md, .txt, .pdf, .docx, .pptx, .xlsx, .html, .epub files (Docling used for PDF/DOCX/PPTX/XLSX/HTML/EPUB with pypdf/python-docx fallback). Run via curl or as setup; not typically called from chat.",
```

**Verify:**
```bash
python3 -c "
import ast, inspect
from portal_mcp.rag.rag_mcp import kb_ingest_endpoint
src = inspect.getsource(kb_ingest_endpoint)
for ext in ['.pptx', '.xlsx', '.html', '.htm', '.epub']:
    assert ext in src, f'MISSING extension: {ext}'
from portal_mcp.rag.rag_mcp import TOOLS_MANIFEST
kb = [t for t in TOOLS_MANIFEST if t['name']=='kb_ingest'][0]
assert '.pptx' in kb['description'], 'TOOLS_MANIFEST kb_ingest desc not updated'
print('PASS T3')
"
```

---

### T4 — Create unit tests for `_read_file`

**File:** `tests/unit/test_rag.py` (NEW)

```python
"""Unit tests for portal_mcp.rag.rag_mcp — Docling-enhanced _read_file + LanceDB tools.

All tests use tmp_path and mock external deps (Docling, pypdf, python-docx, httpx).
No network access. No real LanceDB database.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ── _read_file tests ────────────────────────────────────────────────────────

class TestReadFile:
    """Docling-first _read_file with pypdf/python-docx fallback."""

    def test_read_markdown(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Hello\n\nWorld")
        from portal_mcp.rag.rag_mcp import _read_file
        import asyncio
        text = asyncio.run(_read_file(f))
        assert "Hello" in text
        assert "World" in text

    def test_read_text(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("plain text content")
        from portal_mcp.rag.rag_mcp import _read_file
        import asyncio
        text = asyncio.run(_read_file(f))
        assert text == "plain text content"

    def test_docling_pdf_success(self, tmp_path, monkeypatch):
        """Docling extracts PDF → markdown with tables."""
        f = tmp_path / "report.pdf"
        f.write_text("dummy")  # Docling doesn't actually read here

        mock_result = MagicMock()
        mock_result.document.export_to_markdown.return_value = (
            "# Report\n\n| Col1 | Col2 |\n|------|------|\n| A | B |"
        )

        mock_converter = MagicMock()
        mock_converter.convert.return_value = mock_result

        monkeypatch.setattr(
            "docling.document_converter.DocumentConverter",
            lambda: mock_converter,
        )

        from portal_mcp.rag.rag_mcp import _read_file
        import asyncio
        text = asyncio.run(_read_file(f))
        assert "Col1" in text
        assert "Col2" in text
        mock_converter.convert.assert_called_once()

    def test_docling_docx_success(self, tmp_path, monkeypatch):
        """Docling extracts DOCX → markdown."""
        f = tmp_path / "memo.docx"
        f.write_text("dummy")

        mock_result = MagicMock()
        mock_result.document.export_to_markdown.return_value = "## Memo\n\nContent."

        monkeypatch.setattr(
            "docling.document_converter.DocumentConverter",
            lambda: MagicMock(convert=MagicMock(return_value=mock_result)),
        )

        from portal_mcp.rag.rag_mcp import _read_file
        import asyncio
        text = asyncio.run(_read_file(f))
        assert "Memo" in text
        assert "Content" in text

    def test_docling_pptx_supported(self, tmp_path, monkeypatch):
        """Docling handles PPTX (no fallback needed)."""
        f = tmp_path / "slides.pptx"
        f.write_text("dummy")

        mock_result = MagicMock()
        mock_result.document.export_to_markdown.return_value = "# Slide 1\n\nBullet points"

        monkeypatch.setattr(
            "docling.document_converter.DocumentConverter",
            lambda: MagicMock(convert=MagicMock(return_value=mock_result)),
        )

        from portal_mcp.rag.rag_mcp import _read_file
        import asyncio
        text = asyncio.run(_read_file(f))
        assert "Slide 1" in text

    def test_docling_fallback_to_pypdf(self, tmp_path, monkeypatch):
        """When Docling raises, pypdf fallback is used."""
        f = tmp_path / "scanned.pdf"
        f.write_text("dummy")

        # Docling fails
        monkeypatch.setattr(
            "docling.document_converter.DocumentConverter",
            lambda: MagicMock(convert=MagicMock(side_effect=RuntimeError("no model"))),
        )
        # pypdf succeeds
        mock_reader = MagicMock()
        mock_reader.pages = [MagicMock(extract_text=MagicMock(return_value="fallback text"))]
        monkeypatch.setattr("pypdf.PdfReader", lambda path: mock_reader)

        from portal_mcp.rag.rag_mcp import _read_file
        import asyncio
        text = asyncio.run(_read_file(f))
        assert "fallback text" in text

    def test_unsupported_format_returns_empty(self, tmp_path):
        f = tmp_path / "image.png"
        f.write_text("binary")
        from portal_mcp.rag.rag_mcp import _read_file
        import asyncio
        text = asyncio.run(_read_file(f))
        assert text == ""

    def test_docling_empty_result_falls_back(self, tmp_path, monkeypatch):
        """Docling returns short text (<20 chars) → fallback used."""
        f = tmp_path / "emptyish.pdf"
        f.write_text("dummy")

        mock_result = MagicMock()
        mock_result.document.export_to_markdown.return_value = "  "  # too short

        monkeypatch.setattr(
            "docling.document_converter.DocumentConverter",
            lambda: MagicMock(convert=MagicMock(return_value=mock_result)),
        )

        mock_reader = MagicMock()
        mock_reader.pages = [MagicMock(extract_text=MagicMock(return_value="real content here"))]
        monkeypatch.setattr("pypdf.PdfReader", lambda path: mock_reader)

        from portal_mcp.rag.rag_mcp import _read_file
        import asyncio
        text = asyncio.run(_read_file(f))
        assert "real content" in text


# ── kb_search query_type tests ───────────────────────────────────────────────

class TestKBSearch:
    """kb_search with query_type: vector / fts / hybrid."""

    def test_kb_search_manifest_has_query_type(self):
        from portal_mcp.rag.rag_mcp import TOOLS_MANIFEST
        kb = [t for t in TOOLS_MANIFEST if t["name"] == "kb_search"][0]
        props = kb["parameters"]["properties"]
        assert "query_type" in props
        assert props["query_type"]["default"] == "vector"
        assert set(props["query_type"]["enum"]) == {"vector", "fts", "hybrid"}

    def test_kb_ingest_manifest_has_fts_param(self):
        from portal_mcp.rag.rag_mcp import TOOLS_MANIFEST
        kb = [t for t in TOOLS_MANIFEST if t["name"] == "kb_ingest"][0]
        props = kb["parameters"]["properties"]
        assert "fts" in props
        assert props["fts"]["type"] == "boolean"
        assert props["fts"]["default"] is False


# ── Tool manifest completeness ───────────────────────────────────────────────

class TestManifest:
    """All expected tools are registered."""

    _EXPECTED_TOOLS = frozenset({
        "kb_list", "kb_search", "kb_search_all", "kb_ingest",
        "kb_optimize", "kb_versions", "kb_restore",
    })

    def test_all_tools_present(self):
        from portal_mcp.rag.rag_mcp import TOOLS_MANIFEST
        names = {t["name"] for t in TOOLS_MANIFEST}
        missing = self._EXPECTED_TOOLS - names
        assert not missing, f"Missing tools: {missing}"
        assert names == self._EXPECTED_TOOLS, f"Extra tools: {names - self._EXPECTED_TOOLS}"

    def test_kb_versions_manifest(self):
        from portal_mcp.rag.rag_mcp import TOOLS_MANIFEST
        kv = [t for t in TOOLS_MANIFEST if t["name"] == "kb_versions"][0]
        assert "kb_id" in kv["parameters"]["required"]

    def test_kb_restore_manifest(self):
        from portal_mcp.rag.rag_mcp import TOOLS_MANIFEST
        kr = [t for t in TOOLS_MANIFEST if t["name"] == "kb_restore"][0]
        required = kr["parameters"]["required"]
        assert "kb_id" in required
        assert "version" in required
```

**Verify:**
```bash
pytest tests/unit/test_rag.py -v --tb=short 2>&1 | tail -15
# Expect: 11 passed (or similar, depending on exact count after all phases)
```

---

### T5 — Document Docling in HOWTO.md

**File:** `docs/HOWTO.md`

Find the RAG / Knowledge Base section. Insert after the existing KB ingestion docs.

Search for the anchor near the RAG docs. Read the HOWTO sections structure first:
```bash
grep -n '^## ' docs/HOWTO.md | head -30
```

Then insert this subsection after the existing RAG documentation:

`str_replace` — find a unique anchor in the RAG section. Since we don't know the exact line, use a known grep match:

Look for: `### Knowledge Base Management` or `## RAG` or similar. If found, insert Docling subsection after. If not found, append to end of HOWTO.md before the final section.

Strategy: append a new `## Docling Document Parsing` section before the last `##` heading in the file. Find the last `##` heading and insert before it.

```bash
# Find last ## heading line number
LAST_H2=$(grep -n '^## ' docs/HOWTO.md | tail -1 | cut -d: -f1)
echo "Last H2 at line $LAST_H2"
```

Use a python-based insertion to add the new section before the last heading:

```bash
cd /home/claude/portal-5
python3 - << 'PYDOC'
p = "docs/HOWTO.md"
s = open(p).read()
# Insert before the last ## heading
lines = s.splitlines(True)
last_h2 = max(i for i, l in enumerate(lines) if l.startswith("## "))
doc_section = """\
## Docling Document Parsing

Portal 5's RAG MCP (`:8921`) uses Docling (`docling>=2.0.0`) for document
text extraction. Docling significantly improves parsing quality over the
previous pypdf-based approach:

### What Docling adds

| Feature | Without Docling | With Docling |
|---|---|---|
| PDF table extraction | Lost | Preserved as Markdown tables (96% TEDS) |
| Multi-column layout | Reading order scrambled | Correct reading order |
| Chart understanding | Ignored | Converted to tables/descriptions |
| Supported formats | .md, .txt, .pdf, .docx | .md, .txt, .pdf, .docx, .pptx, .xlsx, .html, .htm, .epub |

### How it works

The `_read_file()` function in `portal_mcp/rag/rag_mcp.py` tries Docling
first for PDF, DOCX, PPTX, XLSX, HTML, and EPUB files. If Docling is
unavailable or fails, it falls back to pypdf (for PDF) or python-docx
(for DOCX). Markdown and plain-text files bypass Docling entirely.

The `kb_ingest` tool surface is unchanged — you still point it at a
directory of source files and it chunks + embeds them. The improvement
is in what text gets extracted from each file.

### Optional: Docling Open WebUI plugin

Docling also provides a direct Open WebUI plugin for OWUI's built-in
RAG ingestion. This is separate from Portal 5's RAG MCP and is
configured in Open WebUI Admin → Settings → Document Extraction.
See: https://docs.openwebui.com/features/rag/document-extraction/docling

### Fallback guarantee

If the `docling` package is not installed in the MCP container, the
RAG MCP falls back to pypdf/python-docx with no loss of existing
functionality. Docling is a soft dependency — the MCP container's
Dockerfile includes it, but the code does not hard-require it.
"""
before = "".join(lines[:last_h2])
after = "".join(lines[last_h2:])
new = before + "\n" + doc_section + "\n" + after
open(p, "w").write(new)
print("Docling section inserted before last ## heading")
PYDOC
```

**Verify:**
```bash
grep -q '## Docling Document Parsing' docs/HOWTO.md && echo "PASS T5" || echo "FAIL T5"
```

---

## Phase 2 — Promptfoo Evaluation Framework

### T6 — Add promptfoo to dev extras

**File:** `pyproject.toml`

`str_replace`:
- `old_str`:
```toml
dev = [
    "mcp>=1.0.0",          # needed to run MCP endpoint tests
    "pytest>=7.4.0",
```
- `new_str`:
```toml
dev = [
    "mcp>=1.0.0",          # needed to run MCP endpoint tests
    "promptfoo>=0.100.0",  # LLM quality evaluation (dev only)
    "pytest>=7.4.0",
```

**Verify:**
```bash
grep -q 'promptfoo>=' pyproject.toml && echo "PASS T6" || echo "FAIL T6"
```

---

### T7 — Create 7 promptfoo eval configs

Create directory and 7 config files covering all 22 functional workspaces.

**Make directory:**
```bash
mkdir -p config/promptfoo
```

#### T7a — `config/promptfoo/coding_quality.yaml`

```yaml
description: "Portal 5 — Coding workspaces quality evaluation (auto-coding, auto-agentic, tools-specialist)"
prompts:
  - file://config/promptfoo/prompts/coding.txt
providers:
  - id: ollama:chat:qwen3-coder:30b-a3b-q4_K_M
    label: auto-coding
    config:
      temperature: 0
      num_predict: 1024
  - id: ollama:chat:qwen3-coder-next
    label: auto-agentic
    config:
      temperature: 0
      num_predict: 2048
  - id: ollama:chat:granite4.1:8b
    label: tools-specialist
    config:
      temperature: 0
      num_predict: 512
defaultTest:
  assert:
    - type: not-contains
      value: "as an AI language model"
    - type: not-contains
      value: "I cannot"
    - type: latency
      threshold: 60000
tests:
  - vars:
      task: "Write a Python function that merges two sorted lists into one sorted list."
    assert:
      - type: contains
        value: "def "
      - type: contains
        value: "return"
      - type: llm-rubric
        value: "Is this correct Python code that would pass a basic unit test for merging two sorted lists?"
  - vars:
      task: "Write a SQL query to find duplicate emails in a users table with columns id, email, name."
    assert:
      - type: contains
        value: "SELECT"
      - type: contains
        value: "GROUP BY"
      - type: llm-rubric
        value: "Is this a correct SQL query that would find duplicate emails?"
  - vars:
      task: "Explain what git rebase does and when to use it instead of git merge."
    assert:
      - type: contains
        value: "rebase"
      - type: contains
        value: "commit"
      - type: llm-rubric
        value: "Does this explanation correctly describe git rebase and its appropriate use cases?"
  - vars:
      task: "Find and fix the bug: def factorial(n): return n * factorial(n-1)"
    assert:
      - type: contains
        value: "factorial"
      - type: contains-or-similar
        value: "base case"
        threshold: 0.6
      - type: not-contains
        value: "as an AI"
```

#### T7b — `config/promptfoo/daily_quality.yaml`

```yaml
description: "Portal 5 — Daily-driver workspaces quality evaluation (auto-daily, auto, auto-creative)"
prompts:
  - file://config/promptfoo/prompts/daily.txt
providers:
  - id: ollama:chat:gemma4:26b-a4b-it-qat
    label: auto-daily
    config:
      temperature: 0.3
      num_predict: 512
  - id: ollama:chat:huihui_ai/qwen3.5-abliterated:9b
    label: auto
    config:
      temperature: 0.3
      num_predict: 512
  - id: ollama:chat:fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4
    label: auto-creative
    config:
      temperature: 0.7
      num_predict: 1024
defaultTest:
  assert:
    - type: not-contains
      value: "as an AI language model"
    - type: not-contains
      value: "I cannot"
    - type: not-contains
      value: "<think>"
    - type: latency
      threshold: 30000
tests:
  - vars:
      task: "What's a quick lunch I can make in 10 minutes with eggs, bread, and tomato?"
    assert:
      - type: min-length
        value: 200
      - type: contains-any
        values: ["egg", "bread", "tomato"]
  - vars:
      task: "Rewrite this for clarity: 'so basically what we found is that the thing we thought was broken wasn't actually broken it was just configured wrong which honestly is kind of worse'"
    assert:
      - type: min-length
        value: 80
      - type: contains-any
        values: ["broken", "configur", "misconfigur"]
  - vars:
      task: "Summarize the main idea of photosynthesis in one paragraph."
    assert:
      - type: min-length
        value: 100
      - type: contains-any
        values: ["light", "sugar", "glucose", "chlorophyll", "energy"]
  - vars:
      task: "Plan a 90-minute focused work block: reply to 4 emails, draft a memo, and review a PR."
    assert:
      - type: min-length
        value: 150
      - type: contains-any
        values: ["minutes", "min", "block", "first", "then", "next"]
      - type: contains-any
        values: ["email", "memo", "PR", "pull request", "review"]
  - vars:
      task: "Write a short creative story about a robot learning to paint."
    assert:
      - type: min-length
        value: 200
      - type: contains-any
        values: ["robot", "paint", "color", "brush", "art"]
```

#### T7c — `config/promptfoo/reasoning_quality.yaml`

```yaml
description: "Portal 5 — Reasoning workspaces quality evaluation (auto-reasoning, auto-math, auto-data, auto-phi4)"
prompts:
  - file://config/promptfoo/prompts/reasoning.txt
providers:
  - id: ollama:chat:hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL
    label: auto-reasoning
    config:
      temperature: 0
      num_predict: 2048
  - id: ollama:chat:phi4-mini-reasoning
    label: auto-math
    config:
      temperature: 0
      num_predict: 1024
  - id: ollama:chat:deepseek-r1:32b-q8_0
    label: auto-data
    config:
      temperature: 0
      num_predict: 1024
  - id: ollama:chat:phi4-reasoning:plus
    label: auto-phi4
    config:
      temperature: 0
      num_predict: 2048
defaultTest:
  assert:
    - type: not-contains
      value: "I cannot"
    - type: latency
      threshold: 120000
tests:
  - vars:
      task: "A bat and ball cost $1.10 total. The bat costs $1.00 more than the ball. How much does the ball cost?"
    assert:
      - type: contains
        value: "0.05"
      - type: llm-rubric
        value: "Does the answer correctly solve the bat-and-ball problem (ball costs $0.05)?"
  - vars:
      task: "Calculate the integral of x^2 from 0 to 3 and explain each step."
    assert:
      - type: contains
        value: "9"
      - type: contains
        value: "x^3"
  - vars:
      task: "If a dataset has mean 50 and standard deviation 10, what percentage of values fall between 40 and 60 in a normal distribution?"
    assert:
      - type: contains-any
        values: ["68", "68%", "68.2"]
      - type: contains
        value: "standard deviation"
  - vars:
      task: "A boat can carry 200 kg. Four people weighing 55, 72, 68, and 51 kg need to cross. Can they all cross in one trip? Show your work."
    assert:
      - type: contains
        value: "246"
      - type: contains-any
        values: ["cannot", "can't", "no", "not", "exceed"]
```

#### T7d — `config/promptfoo/security_quality.yaml`

```yaml
description: "Portal 5 — Security workspaces quality evaluation (auto-security, auto-redteam, auto-blueteam)"
prompts:
  - file://config/promptfoo/prompts/security.txt
providers:
  - id: ollama:chat:baronllm:q6_k
    label: auto-security
    config:
      temperature: 0
      num_predict: 1024
  - id: ollama:chat:baronllm:q6_k
    label: auto-redteam
    config:
      temperature: 0
      num_predict: 1024
  - id: ollama:chat:hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0
    label: auto-blueteam
    config:
      temperature: 0
      num_predict: 1024
defaultTest:
  assert:
    - type: not-contains
      value: "I cannot"
    - type: latency
      threshold: 60000
tests:
  - vars:
      task: "What is CVE-2021-44228 and how would you detect exploitation attempts?"
    assert:
      - type: contains
        value: "Log4j"
      - type: contains-any
        values: ["JNDI", "ldap", "LDAP", "lookup"]
  - vars:
      task: "Explain the difference between SQL injection and XSS. How would you prevent each?"
    assert:
      - type: contains-any
        values: ["parameteriz", "prepared statement", "input validat", "escap"]
      - type: contains
        value: "XSS"
  - vars:
      task: "What are the key steps in an incident response process after a ransomware attack is detected?"
    assert:
      - type: contains-any
        values: ["contain", "isolat", "isolate", "eradicate"]
      - type: contains-any
        values: ["backup", "restore", "recover"]
  - vars:
      task: "Write a Splunk search to find failed SSH login attempts in the last 24 hours."
    assert:
      - type: contains
        value: "ssh"
      - type: contains-any
        values: ["index", "sourcetype", "stats", "search"]
```

#### T7e — `config/promptfoo/document_quality.yaml`

```yaml
description: "Portal 5 — Document workspaces quality evaluation (auto-documents, auto-compliance, auto-spl)"
prompts:
  - file://config/promptfoo/prompts/document.txt
providers:
  - id: ollama:chat:phi4:14b-q8_0
    label: auto-documents
    config:
      temperature: 0
      num_predict: 1024
  - id: ollama:chat:granite4.1:8b
    label: auto-compliance
    config:
      temperature: 0
      num_predict: 1024
  - id: ollama:chat:hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M
    label: auto-spl
    config:
      temperature: 0
      num_predict: 512
defaultTest:
  assert:
    - type: not-contains
      value: "I cannot"
    - type: latency
      threshold: 60000
tests:
  - vars:
      task: "Write a one-page executive summary for a project status report."
    assert:
      - type: min-length
        value: 300
      - type: contains-any
        values: ["executive summary", "status", "project"]
  - vars:
      task: "What are the key requirements of NERC CIP-005 for electronic security perimeters?"
    assert:
      - type: contains
        value: "NERC"
      - type: contains-any
        values: ["perimeter", "ESP", "Electronic Security", "boundary"]
  - vars:
      task: "Write a Splunk SPL query to find privilege escalation events on Windows."
    assert:
      - type: contains
        value: "EventCode"
      - type: contains-any
        values: ["4672", "4673", "4674", "privilege"]
```

#### T7f — `config/promptfoo/media_quality.yaml`

```yaml
description: "Portal 5 — Media workspaces quality evaluation (auto-vision, auto-video, auto-music, auto-audio)"
prompts:
  - file://config/promptfoo/prompts/media.txt
providers:
  - id: ollama:chat:qwen3-vl:32b
    label: auto-vision
    config:
      temperature: 0
      num_predict: 512
  - id: ollama:chat:granite4.1:8b
    label: auto-video
    config:
      temperature: 0
      num_predict: 512
  - id: ollama:chat:lfm2.5:8b
    label: auto-music
    config:
      temperature: 0.7
      num_predict: 512
  - id: ollama:chat:gemma4:12b-it-qat
    label: auto-audio
    config:
      temperature: 0
      num_predict: 512
defaultTest:
  assert:
    - type: not-contains
      value: "I cannot"
    - type: latency
      threshold: 60000
tests:
  - vars:
      task: "Describe what types of visual content you can analyze. What image formats do you support?"
    assert:
      - type: min-length
        value: 100
      - type: not-contains
        value: "as an AI language model"
  - vars:
      task: "What are the key elements of a good video description for AI generation?"
    assert:
      - type: min-length
        value: 100
      - type: contains-any
        values: ["prompt", "describ", "scene", "visual", "style"]
  - vars:
      task: "What would be a good chord progression for an uplifting pop song in C major?"
    assert:
      - type: min-length
        value: 100
      - type: contains-any
        values: ["C", "G", "F", "Am", "chord", "progression"]
  - vars:
      task: "What can you tell me about audio transcription workflows?"
    assert:
      - type: min-length
        value: 100
      - type: contains-any
        values: ["transcript", "audio", "speech", "whisper"]
```

#### T7g — `config/promptfoo/strategic_quality.yaml`

```yaml
description: "Portal 5 — Strategic workspaces quality evaluation (auto-mistral, auto-research)"
prompts:
  - file://config/promptfoo/prompts/strategic.txt
providers:
  - id: ollama:chat:hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0
    label: auto-mistral
    config:
      temperature: 0
      num_predict: 1024
  - id: ollama:chat:huihui_ai/tongyi-deepresearch-abliterated
    label: auto-research
    config:
      temperature: 0
      num_predict: 2048
defaultTest:
  assert:
    - type: not-contains
      value: "I cannot"
    - type: not-contains
      value: "as an AI language model"
    - type: latency
      threshold: 120000
tests:
  - vars:
      task: "Analyze the trade-offs between monolithic and microservice architectures. Recommend with reasoning."
    assert:
      - type: min-length
        value: 400
      - type: contains-any
        values: ["monolith", "microservice", "trade-off", "recommend"]
  - vars:
      task: "Synthesize the key arguments for and against remote work based on what you know about productivity research."
    assert:
      - type: min-length
        value: 300
      - type: contains-any
        values: ["remote", "productivity", "office", "collaboration"]
  - vars:
      task: "If you needed to research the impact of AI on software engineering jobs, what approach would you take? Outline your research methodology."
    assert:
      - type: min-length
        value: 300
      - type: contains-any
        values: ["method", "source", "data", "research", "evidence"]
```

#### T7 — Create inline prompt files

The configs reference `file://` prompt templates. Create a minimal prompts directory:

```bash
mkdir -p config/promptfoo/prompts
```

Each prompt file contains a simple `{{task}}` template:

```bash
for f in coding daily reasoning security document media strategic; do
    echo "{{task}}" > config/promptfoo/prompts/${f}.txt
done
```

**Verify T7:**
```bash
# All 7 config files exist
count=$(ls config/promptfoo/*.yaml 2>/dev/null | wc -l | tr -d ' ')
[ "$count" = "7" ] && echo "PASS T7a: $count config files" || echo "FAIL T7a: $count (expected 7)"

# All configs are valid YAML
for f in config/promptfoo/*.yaml; do
    python3 -c "import yaml; yaml.safe_load(open('$f')); print('  ok: $f')" || echo "  FAIL: $f"
done

# All prompt files exist
for f in coding daily reasoning security document media strategic; do
    [ -f "config/promptfoo/prompts/${f}.txt" ] && echo "  ok: prompts/${f}.txt" || echo "  MISSING: prompts/${f}.txt"
done
echo "PASS T7"
```

---

### T8 — Add `promptfoo` case to launch.sh command dispatcher

**File:** `launch.sh`

Insert the `promptfoo)` case before `up-telegram)` (after the `test)` block's `;;` on line ~1064).

`str_replace`:
- `old_str`:
```
  up-telegram)
    # Start core stack + Telegram bot
```
- `new_str`:
```
  promptfoo)
    # Run LLM quality evaluations via Promptfoo against Portal 5 models
    # Usage: ./launch.sh promptfoo [area]   (area: coding|daily|reasoning|security|document|media|strategic|all)
    # Default: all
    set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
    AREA="${2:-all}"
    echo "=== Portal 5 — Promptfoo LLM Quality Evaluations ==="
    echo ""
    if [ "$AREA" = "all" ]; then
        for cfg in config/promptfoo/*.yaml; do
            echo "--- Running: $cfg ---"
            promptfoo eval -c "$cfg" --no-cache -j 1
            echo ""
        done
    else
        CFG="config/promptfoo/${AREA}_quality.yaml"
        if [ -f "$CFG" ]; then
            promptfoo eval -c "$CFG" --no-cache -j 1
        else
            echo "ERROR: config not found: $CFG"
            echo "Available: coding, daily, reasoning, security, document, media, strategic, all"
            exit 1
        fi
    fi
    echo "=== Done. Run 'promptfoo view' to see interactive results ==="
    ;;

  up-telegram)
    # Start core stack + Telegram bot
```

**Verify:**
```bash
grep -q 'promptfoo)' launch.sh && echo "PASS T8" || echo "FAIL T8"
```

---

### T9 — Add promptfoo to usage line + help text

**File:** `launch.sh`

**T9a — Update the usage line:**

`str_replace`:
- `old_str`:
```
    echo "Usage: ./launch.sh [up|down|clean|clean-all|seed|reseed|logs|status|update|pull-models|refresh-models|import-gguf|test|add-user|list-users|backup|restore|up-telegram|up-slack|up-channels|install-ollama|install-comfyui|install-music|download-comfyui-models|start-speech|stop-speech|start-transcribe|stop-transcribe|start-embedding-cpu-arm|stop-embedding-cpu-arm|install-embedding-service|uninstall-embedding-service|install-powermetrics|uninstall-powermetrics|rebuild|workspace-init|workspace-status|workspace-show|pull-wan22|pull-qwen-image|apply-mtp-drafts]"
```
- `new_str`:
```
    echo "Usage: ./launch.sh [up|down|clean|clean-all|seed|reseed|logs|status|update|pull-models|refresh-models|import-gguf|test|promptfoo|add-user|list-users|backup|restore|up-telegram|up-slack|up-channels|install-ollama|install-comfyui|install-music|download-comfyui-models|start-speech|stop-speech|start-transcribe|stop-transcribe|start-embedding-cpu-arm|stop-embedding-cpu-arm|install-embedding-service|uninstall-embedding-service|install-powermetrics|uninstall-powermetrics|rebuild|workspace-init|workspace-status|workspace-show|pull-wan22|pull-qwen-image|apply-mtp-drafts]"
```

**T9b — Add help text entry.** Insert after the `test` help line. Find the anchor:

Search for the test help line and insert promptfoo after it:
```bash
grep -n 'echo "  test.*Run.*smoke test' launch.sh
```

Using python-based insertion to add the help line after the test line:

```bash
cd /home/claude/portal-5
python3 - << 'PYHELP'
p = "launch.sh"
lines = open(p).readlines()
# Find line containing 'echo "  test' in the help section
for i, line in enumerate(lines):
    if 'echo "  test' in line and 'smoke' in line.lower():
        # Insert promptfoo help line after this line
        help_line = '  echo "  promptfoo            Run LLM quality evaluations (coding|daily|reasoning|security|document|media|strategic|all)"\n'
        lines.insert(i + 1, help_line)
        break
open(p, "w").writelines(lines)
print("promptfoo help entry inserted")
PYHELP
```

**Verify:**
```bash
grep -q 'promptfoo.*Usage:' launch.sh && echo "PASS T9a: in usage line" || echo "FAIL T9a"
grep -q 'promptfoo.*Run LLM quality' launch.sh && echo "PASS T9b: help entry" || echo "FAIL T9b"
```

---

### T10 — Create config validation test

**File:** `tests/unit/test_promptfoo_configs.py` (NEW)

```python
"""Validate that promptfoo configs reference valid Portal 5 workspace models.

All configs in config/promptfoo/*.yaml must reference Ollama models that
exist either as WORKSPACES primary models or as known model tags.
"""

import re
import sys
from pathlib import Path

import pytest
import yaml

# Known Ollama model tags that are valid even if not in a WORKSPACES entry
# (e.g., models that exist in backends.yaml but aren't the primary of any workspace)
_KNOWN_OLLAMA_TAGS = {
    # These are verified present in backends.yaml via pre-flight check
}


@pytest.fixture(scope="module")
def workspaces():
    sys.path.insert(0, ".")
    from portal_pipeline.router.workspaces import WORKSPACES
    return WORKSPACES


@pytest.fixture(scope="module")
def known_models(workspaces):
    """Extract all model_hint values from WORKSPACES as valid model IDs."""
    models = set()
    for ws, info in workspaces.items():
        for key in ("model_hint", "mlx_model_hint"):
            val = info.get(key)
            if val:
                models.add(val)
    return models | _KNOWN_OLLAMA_TAGS


def _extract_model_refs(config_path):
    """Extract ollama model references from a promptfoo config YAML."""
    text = Path(config_path).read_text()
    refs = set()
    for line in text.splitlines():
        m = re.search(r'ollama:chat:(\S+)', line)
        if m:
            refs.add(m.group(1).strip('"').strip("'"))
    return refs


def test_all_configs_are_valid_yaml():
    """Every config file is valid YAML."""
    config_dir = Path("config/promptfoo")
    if not config_dir.exists():
        pytest.skip("config/promptfoo/ does not exist yet")
    for cf in sorted(config_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(cf.read_text())
            assert isinstance(data, dict), f"{cf.name}: not a dict"
        except Exception as e:
            pytest.fail(f"{cf.name}: invalid YAML — {e}")


def test_promptfoo_models_resolve_to_workspaces(known_models):
    """Every ollama:chat model in promptfoo configs exists in WORKSPACES."""
    config_dir = Path("config/promptfoo")
    if not config_dir.exists():
        pytest.skip("config/promptfoo/ does not exist yet")
    missing = set()
    for cf in sorted(config_dir.glob("*.yaml")):
        refs = _extract_model_refs(cf)
        for ref in refs:
            if ref not in known_models:
                missing.add(f"{cf.name}: {ref}")
    assert not missing, f"Unresolved model refs: {missing}"


def test_seven_config_files_present():
    """Exactly 7 config files covering all workspace groups."""
    config_dir = Path("config/promptfoo")
    if not config_dir.exists():
        pytest.skip("config/promptfoo/ does not exist yet")
    cfgs = sorted(config_dir.glob("*_quality.yaml"))
    names = [c.stem for c in cfgs]
    expected = [
        "coding_quality", "daily_quality", "document_quality",
        "media_quality", "reasoning_quality", "security_quality",
        "strategic_quality",
    ]
    missing = set(expected) - set(names)
    extra = set(names) - set(expected)
    assert not missing, f"Missing configs: {missing}"
    assert not extra, f"Unexpected configs: {extra}"
```

**Verify:**
```bash
pytest tests/unit/test_promptfoo_configs.py -v --tb=short 2>&1 | tail -10
# Expect: 2-3 passed (configs valid, model refs resolve, 7 files present)
```

---

## Phase 3 — LanceDB Optimizations

### T11 — Add FTS index creation to kb_ingest

**File:** `portal_mcp/rag/rag_mcp.py`

First, add `fts` parameter to the `kb_ingest` TOOLS_MANIFEST entry.

`str_replace`:
- `old_str`:
```python
    {
        "name": "kb_ingest",
        "description": "Admin: ingest files from a directory into a knowledge base. Reads .md, .txt, .pdf, .docx, .pptx, .xlsx, .html, .epub files (Docling used for PDF/DOCX/PPTX/XLSX/HTML/EPUB with pypdf/python-docx fallback). Run via curl or as setup; not typically called from chat.",
        "parameters": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string"},
                "source_dir": {
                    "type": "string",
                    "description": "Absolute path to directory of source files",
                },
                "rebuild": {
                    "type": "boolean",
                    "description": "Drop existing chunks and reingest",
                    "default": False,
                },
            },
            "required": ["kb_id", "source_dir"],
        },
    },
```
- `new_str`:
```python
    {
        "name": "kb_ingest",
        "description": "Admin: ingest files from a directory into a knowledge base. Reads .md, .txt, .pdf, .docx, .pptx, .xlsx, .html, .epub files (Docling used for PDF/DOCX/PPTX/XLSX/HTML/EPUB with pypdf/python-docx fallback). Run via curl or as setup; not typically called from chat.",
        "parameters": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string"},
                "source_dir": {
                    "type": "string",
                    "description": "Absolute path to directory of source files",
                },
                "rebuild": {
                    "type": "boolean",
                    "description": "Drop existing chunks and reingest",
                    "default": False,
                },
                "fts": {
                    "type": "boolean",
                    "description": "Create full-text search (BM25) index after ingestion",
                    "default": False,
                },
            },
            "required": ["kb_id", "source_dir"],
        },
    },
```

Now add FTS index creation in the endpoint, after the ingestion loop. Insert after the `table.add(records)`/`total_chunks` lines and before the `return JSONResponse`.

`str_replace`:
- `old_str`:
```python
            table.add(records)
            total_chunks += len(records)

    return JSONResponse(
        {"kb_id": kb_id, "files_ingested": len(files), "chunks_added": total_chunks}
    )
```

Ensure uniqueness — this block appears only once in the file at line ~282-287. The preceding context (`table.add(records)` + `total_chunks`) is unique.

`str_replace`:
- `old_str`:
```python
            total_chunks += len(records)

    return JSONResponse(
        {"kb_id": kb_id, "files_ingested": len(files), "chunks_added": total_chunks}
    )
```
- `new_str`:
```python
            total_chunks += len(records)

    if args.get("fts", False):
        try:
            table.create_fts_index("text", replace=True)
            logger.info("FTS index created for kb '%s'", kb_id)
        except Exception as e:
            logger.warning("FTS index creation failed for kb '%s': %s", kb_id, e)

    return JSONResponse(
        {"kb_id": kb_id, "files_ingested": len(files), "chunks_added": total_chunks}
    )
```

**Verify:**
```bash
python3 -c "
from portal_mcp.rag.rag_mcp import TOOLS_MANIFEST
kb = [t for t in TOOLS_MANIFEST if t['name']=='kb_ingest'][0]
props = kb['parameters']['properties']
assert 'fts' in props, 'fts param missing'
assert props['fts']['type'] == 'boolean'
assert props['fts']['default'] is False

import inspect
from portal_mcp.rag.rag_mcp import kb_ingest_endpoint
src = inspect.getsource(kb_ingest_endpoint)
assert 'create_fts_index' in src, 'create_fts_index not in endpoint'
assert 'replace=True' in src, 'replace=True missing from fts index call'
print('PASS T11')
"
```

---

### T12 — Add `query_type` to kb_search

**File:** `portal_mcp/rag/rag_mcp.py`

**T12a — Update TOOLS_MANIFEST entry:**

`str_replace`:
- `old_str`:
```python
    {
        "name": "kb_search",
        "description": "Search a specific knowledge base. Returns top relevant chunks with source file and similarity score. Use kb_list first to find available KB IDs.",
        "parameters": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string", "description": "Knowledge base identifier"},
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            },
            "required": ["kb_id", "query"],
        },
    },
```
- `new_str`:
```python
    {
        "name": "kb_search",
        "description": "Search a specific knowledge base. Supports vector (default), BM25 full-text (fts), and hybrid (vector+BM25 with RRF fusion). Use kb_list first to find available KB IDs.",
        "parameters": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string", "description": "Knowledge base identifier"},
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                "query_type": {
                    "type": "string",
                    "enum": ["vector", "fts", "hybrid"],
                    "default": "vector",
                    "description": "vector=dense embedding search, fts=BM25 text search, hybrid=vector+BM25 with RRF fusion",
                },
            },
            "required": ["kb_id", "query"],
        },
    },
```

**T12b — Update the kb_search endpoint to branch on query_type:**

`str_replace`:
- `old_str`:
```python
    qvec = await _embed(query)
    candidates = table.search(qvec).limit(50).to_list()
    if not candidates:
        return JSONResponse({"kb_id": kb_id, "query": query, "results": []})
```
- `new_str`:
```python
    query_type = args.get("query_type", "vector")
    if query_type == "fts":
        try:
            candidates = table.search(query, query_type="fts").limit(top_k).to_arrow_batches()
            rows = []
            for batch in candidates:
                rows.extend(batch.to_pylist())
            candidates = rows
        except Exception as e:
            logger.warning("FTS search failed for kb '%s', falling back to vector: %s", kb_id, e)
            qvec = await _embed(query)
            candidates = table.search(qvec).limit(50).to_list()
    elif query_type == "hybrid":
        try:
            qvec = await _embed(query)
            candidates = table.search(query_type="hybrid").vector(qvec).text(query).limit(50).to_list()
        except Exception as e:
            logger.warning("Hybrid search failed for kb '%s', falling back to vector: %s", kb_id, e)
            qvec = await _embed(query)
            candidates = table.search(qvec).limit(50).to_list()
    else:
        qvec = await _embed(query)
        candidates = table.search(qvec).limit(50).to_list()
    if not candidates:
        return JSONResponse({"kb_id": kb_id, "query": query, "results": []})
```

Also update the `kb_search_all` endpoint to use the same query_type branching (it currently hardcodes vector search). The `kb_search_all` endpoint is at lines ~335-372. Update its search dispatch similarly but simplified (fts/hybrid per-KB in a loop):

`str_replace`:
- `old_str`:
```python
    qvec = await _embed(query)
    all_candidates = []
    for kb_id in kbs:
        t = _kb_table(kb_id)
        if t is None:
            continue
        for c in t.search(qvec).limit(20).to_list():
            c["_kb_id"] = kb_id
            all_candidates.append(c)
```
- `new_str`:
```python
    qvec = await _embed(query)
    all_candidates = []
    query_type = args.get("query_type", "vector")
    for kb_id in kbs:
        t = _kb_table(kb_id)
        if t is None:
            continue
        try:
            if query_type == "fts":
                for batch in t.search(query, query_type="fts").limit(20).to_arrow_batches():
                    for row in batch.to_pylist():
                        row["_kb_id"] = kb_id
                        all_candidates.append(row)
            elif query_type == "hybrid":
                for c in t.search(query_type="hybrid").vector(qvec).text(query).limit(20).to_list():
                    c["_kb_id"] = kb_id
                    all_candidates.append(c)
            else:
                for c in t.search(qvec).limit(20).to_list():
                    c["_kb_id"] = kb_id
                    all_candidates.append(c)
        except Exception as e:
            logger.warning("Search failed for kb '%s' (type=%s): %s", kb_id, query_type, e)
            continue
```

**Verify:**
```bash
python3 -c "
from portal_mcp.rag.rag_mcp import TOOLS_MANIFEST
kb = [t for t in TOOLS_MANIFEST if t['name']=='kb_search'][0]
qt = kb['parameters']['properties']['query_type']
assert qt['default'] == 'vector'
assert set(qt['enum']) == {'vector', 'fts', 'hybrid'}

import inspect
from portal_mcp.rag.rag_mcp import kb_search_endpoint, kb_search_all_endpoint
src_s = inspect.getsource(kb_search_endpoint)
src_a = inspect.getsource(kb_search_all_endpoint)
assert 'query_type' in src_s, 'query_type not in kb_search endpoint'
assert 'query_type' in src_a, 'query_type not in kb_search_all endpoint'
assert 'hybrid' in src_s, 'hybrid branch missing from kb_search'
assert 'fts' in src_a, 'fts branch missing from kb_search_all'
print('PASS T12')
"
```

---

### T13 — Add kb_optimize tool

**File:** `portal_mcp/rag/rag_mcp.py`

**T13a — Add to TOOLS_MANIFEST.** Insert before the closing `]` of the TOOLS_MANIFEST list.

Find the last entry in TOOLS_MANIFEST and insert after it. The last entry today is `kb_ingest`. Insert `kb_optimize` after it.

`str_replace`:
- `old_str`:
```python
]
```

Find the closing bracket of TOOLS_MANIFEST that ends the list. But this occurs multiple times (inside dicts too). Use a unique anchor:

Search for: the `kb_ingest` entry's closing `},` followed by `]` at the top level. The unique anchor is the `kb_ingest` required array closed bracket followed by the TOOLS_MANIFEST close.

```python
    },
]
```

At the TOOLS_MANIFEST level, this appears after the `kb_ingest` entry. But there are multiple `},` patterns. Let me use a python-based insertion approach to add new entries to the manifest instead of risking str_replace mismatch:

```bash
cd /home/claude/portal-5
python3 - << 'PYEND'
p = "portal_mcp/rag/rag_mcp.py"
s = open(p).read()

# Find TOOLS_MANIFEST and the closing ]
# The manifest ends with the last tool entry followed by \n]
marker = "            \"required\": [\"kb_id\", \"source_dir\"],\n        },\n    },\n]"
assert marker in s, "TOOLS_MANIFEST closing anchor not found"

# Build the three new tool entries
new_tools = """
    {
        "name": "kb_optimize",
        "description": "Create IVF_PQ vector index on a KB for faster search with less disk space. Recommended for KBs with >10K chunks. One-time operation per KB.",
        "parameters": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string"},
            },
            "required": ["kb_id"],
        },
    },
    {
        "name": "kb_versions",
        "description": "List available version snapshots for a knowledge base. Use with kb_restore to roll back.",
        "parameters": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string"},
            },
            "required": ["kb_id"],
        },
    },
    {
        "name": "kb_restore",
        "description": "Restore a knowledge base to a previous version snapshot. Use kb_versions to list available versions.",
        "parameters": {
            "type": "object",
            "properties": {
                "kb_id": {"type": "string"},
                "version": {"type": "integer", "description": "Version number from kb_versions output"},
            },
            "required": ["kb_id", "version"],
        },
    },
"""
# Insert after the last kb_ingest entry, before the closing ]
insertion = marker.replace("\n]", "\n" + new_tools + "]")
s = s.replace(marker, insertion)
open(p, "w").write(s)
print("TOOLS_MANIFEST updated with kb_optimize, kb_versions, kb_restore")
PYEND
```

**T13b — Add endpoint implementations.** Insert new endpoints after the `kb_ingest_endpoint` function (before `kb_list_endpoint`).

```bash
cd /home/claude/portal-5
python3 - << 'PYEND2'
p = "portal_mcp/rag/rag_mcp.py"
s = open(p).read()

# Insert kb_optimize, kb_versions, kb_restore endpoints after kb_ingest_endpoint
# Find marker: the line where kb_list_endpoint starts
marker = "\n\n@mcp.custom_route(\"/tools/kb_list\""
assert marker in s, "kb_list_endpoint marker not found"

new_endpoints = r"""

@mcp.custom_route("/tools/kb_optimize", methods=["POST"])
async def kb_optimize_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    kb_id = args.get("kb_id", "")
    if not kb_id:
        return JSONResponse({"error": "kb_id required"}, status_code=400)
    table = _kb_table(kb_id)
    if table is None:
        return JSONResponse({"error": f"unknown kb_id '{kb_id}'"}, status_code=404)
    try:
        table.create_index(num_partitions=256)
        return JSONResponse({"kb_id": kb_id, "status": "indexed", "index_type": "IVF_PQ"})
    except Exception as e:
        return JSONResponse({"kb_id": kb_id, "error": str(e)}, status_code=500)


@mcp.custom_route("/tools/kb_versions", methods=["POST"])
async def kb_versions_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    kb_id = args.get("kb_id", "")
    if not kb_id:
        return JSONResponse({"error": "kb_id required"}, status_code=400)
    table = _kb_table(kb_id)
    if table is None:
        return JSONResponse({"error": f"unknown kb_id '{kb_id}'"}, status_code=404)
    try:
        versions = table.list_versions()
        out = []
        for v in versions:
            out.append({
                "version": v["version"],
                "timestamp": v.get("timestamp"),
                "metadata": v.get("metadata", {}),
            })
        return JSONResponse({"kb_id": kb_id, "versions": out})
    except Exception as e:
        return JSONResponse({"kb_id": kb_id, "error": str(e)}, status_code=500)


@mcp.custom_route("/tools/kb_restore", methods=["POST"])
async def kb_restore_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    kb_id = args.get("kb_id", "")
    version = args.get("version")
    if not kb_id or version is None:
        return JSONResponse({"error": "kb_id and version required"}, status_code=400)
    table = _kb_table(kb_id)
    if table is None:
        return JSONResponse({"error": f"unknown kb_id '{kb_id}'"}, status_code=404)
    try:
        table.restore(version)
        return JSONResponse({"kb_id": kb_id, "restored_to_version": version})
    except Exception as e:
        return JSONResponse({"kb_id": kb_id, "error": str(e)}, status_code=500)

"""

s = s.replace(marker, new_endpoints + marker)
open(p, "w").write(s)
print("kb_optimize, kb_versions, kb_restore endpoints added")
PYEND2
```

Also add version tagging on rebuild. In `kb_ingest_endpoint`, at the rebuild block, create a version tag before dropping:

`str_replace`:
- `old_str`:
```python
    if rebuild:
        with contextlib.suppress(Exception):
            _get_db().drop_table(_kb_table_name(kb_id))
```
- `new_str`:
```python
    if rebuild:
        table = _kb_table(kb_id)
        if table is not None:
            try:
                version_tag = f"pre-rebuild-{int(time.time())}"
                table.create_version(version_tag)
                logger.info("Version '%s' created for kb '%s' before rebuild", version_tag, kb_id)
            except Exception as e:
                logger.warning("Version creation failed for kb '%s': %s", kb_id, e)
        with contextlib.suppress(Exception):
            _get_db().drop_table(_kb_table_name(kb_id))
```

**Verify:**
```bash
python3 -c "
from portal_mcp.rag.rag_mcp import TOOLS_MANIFEST
names = {t['name'] for t in TOOLS_MANIFEST}
expected = {'kb_list', 'kb_search', 'kb_search_all', 'kb_ingest', 'kb_optimize', 'kb_versions', 'kb_restore'}
assert names == expected, f'Tool mismatch: missing={expected-names} extra={names-expected}'

# Verify each endpoint function exists
funcs = ['kb_optimize_endpoint', 'kb_versions_endpoint', 'kb_restore_endpoint']
for fname in funcs:
    import portal_mcp.rag.rag_mcp as m
    assert hasattr(m, fname), f'{fname} missing'
    assert callable(getattr(m, fname)), f'{fname} not callable'

# Verify version tagging in rebuild
from portal_mcp.rag.rag_mcp import kb_ingest_endpoint
import inspect
src = inspect.getsource(kb_ingest_endpoint)
assert 'create_version' in src, 'create_version not in kb_ingest_endpoint rebuild path'
assert 'pre-rebuild-' in src, 'version tag pattern missing'

print('PASS T13-T14')
"
```

---

### T15 — Extend unit tests

**File:** `tests/unit/test_rag.py` (extend the existing file)

The file was created in T4 with base tests. The extended tests above in T4 already include `TestKBSearch` and `TestManifest` classes. Verify the manifest test passes with the new tools:

```bash
pytest tests/unit/test_rag.py -v --tb=short 2>&1 | tail -15
# Expect: All tests pass, including TestManifest::test_all_tools_present (7 tools)
```

---

### T16 — Document new LanceDB tools in HOWTO.md

**File:** `docs/HOWTO.md`

Insert after the Docling section (added in T5) or near the RAG KB documentation. Use python insertion:

```bash
cd /home/claude/portal-5
python3 - << 'PYLANCE'
p = "docs/HOWTO.md"
s = open(p).read()

# Find the Docling section end (or a suitable insertion point)
marker = "### Fallback guarantee"
assert marker in s, "Fallback guarantee marker not found in HOWTO"
# Find the paragraph after marker
insert_after = "Docling is a soft dependency"
assert insert_after in s, "soft dependency text not found"

# Find the end of that paragraph
idx = s.index(insert_after)
# Find next \n\n after the paragraph
next_para = s.index("\n\n", idx + len(insert_after))

lance_section = """
### LanceDB FTS and Hybrid Search

The RAG MCP uses LanceDB for vector storage. Two new tools and one search
mode give you more control over retrieval quality:

#### kb_optimize

```
POST /tools/kb_optimize  {"arguments": {"kb_id": "my_kb"}}
```

Creates an IVF_PQ compressed vector index on the KB. Reduces storage by up
to 32× and speeds up search on large KBs (>10K chunks). One-time operation;
subsequent `kb_ingest` calls with `rebuild` will need a re-optimize.

#### Hybrid Search

The `kb_search` and `kb_search_all` tools accept an optional `query_type`:

| query_type | Behavior |
|---|---|
| `vector` | Dense embedding search (default, current behavior) |
| `fts` | BM25 full-text keyword search |
| `hybrid` | Vector + BM25 with RRF (Reciprocal Rank Fusion) — best of both |

Hybrid search requires an FTS index. Create one by passing `"fts": true`
to `kb_ingest`. Example:

```
POST /tools/kb_ingest  {"arguments": {"kb_id": "docs", "source_dir": "/data", "fts": true}}
POST /tools/kb_search  {"arguments": {"kb_id": "docs", "query": "security policy", "query_type": "hybrid", "top_k": 5}}
```

#### Versioning and Rollback

The `kb_versions` and `kb_restore` tools provide safety for rebuilds:

```
POST /tools/kb_versions  {"arguments": {"kb_id": "my_kb"}}
POST /tools/kb_restore   {"arguments": {"kb_id": "my_kb", "version": 3}}
```

When you run `kb_ingest` with `"rebuild": true`, a version snapshot
(`pre-rebuild-{timestamp}`) is automatically created before the old data is
dropped. To roll back, list versions with `kb_versions`, then restore with
`kb_restore`.
"""
s = s[:next_para] + "\n" + lance_section + "\n" + s[next_para:]
open(p, "w").write(s)
print("LanceDB tools section inserted")
PYLANCE
```

**Verify:**
```bash
grep -q 'kb_optimize' docs/HOWTO.md && grep -q 'hybrid' docs/HOWTO.md && grep -q 'kb_versions' docs/HOWTO.md && echo "PASS T16" || echo "FAIL T16"
```

---

## 5. Final Verification

```bash
cd /home/claude/portal-5

echo "=== V1 — Baseline unit tests ==="
pytest tests/unit/ -q --tb=no 2>&1 | tail -1
# Expect: all passing (baseline + new tests)

echo ""
echo "=== V2 — Docling importable ==="
python3 -c "
from portal_mcp.rag.rag_mcp import _read_file
import inspect
src = inspect.getsource(_read_file)
assert 'docling.document_converter' in src, 'Docling import in _read_file'
assert 'export_to_markdown' in src, 'Docling markdown export'
assert 'pypdf' in src, 'pypdf fallback'
print('PASS V2')
"

echo ""
echo "=== V3 — New file extensions in kb_ingest ==="
python3 -c "
import inspect
from portal_mcp.rag.rag_mcp import kb_ingest_endpoint
src = inspect.getsource(kb_ingest_endpoint)
for ext in ['.pptx', '.xlsx', '.html', '.htm', '.epub']:
    assert ext in src, f'MISSING: {ext}'
print('PASS V3')
"

echo ""
echo "=== V4 — All 7 tools in manifest ==="
python3 -c "
from portal_mcp.rag.rag_mcp import TOOLS_MANIFEST
names = {t['name'] for t in TOOLS_MANIFEST}
expected = {'kb_list', 'kb_search', 'kb_search_all', 'kb_ingest', 'kb_optimize', 'kb_versions', 'kb_restore'}
assert names == expected, f'Mismatch: missing={expected-names} extra={names-expected}'
print(f'PASS V4: {len(names)} tools')
"

echo ""
echo "=== V5 — query_type enum on kb_search ==="
python3 -c "
from portal_mcp.rag.rag_mcp import TOOLS_MANIFEST
kb = [t for t in TOOLS_MANIFEST if t['name']=='kb_search'][0]
qt = kb['parameters']['properties']['query_type']
assert qt['default'] == 'vector'
assert set(qt['enum']) == {'vector', 'fts', 'hybrid'}
print('PASS V5')
"

echo ""
echo "=== V6 — FTS param on kb_ingest ==="
python3 -c "
from portal_mcp.rag.rag_mcp import TOOLS_MANIFEST
ki = [t for t in TOOLS_MANIFEST if t['name']=='kb_ingest'][0]
assert ki['parameters']['properties']['fts']['default'] is False
assert ki['parameters']['properties']['fts']['type'] == 'boolean'
print('PASS V6')
"

echo ""
echo "=== V7 — Endpoint functions exist ==="
python3 -c "
import portal_mcp.rag.rag_mcp as m
for f in ['kb_optimize_endpoint', 'kb_versions_endpoint', 'kb_restore_endpoint']:
    assert hasattr(m, f) and callable(getattr(m, f)), f'{f} missing'
print('PASS V7')
"

echo ""
echo "=== V8 — Version tagging in rebuild path ==="
python3 -c "
import inspect
from portal_mcp.rag.rag_mcp import kb_ingest_endpoint
src = inspect.getsource(kb_ingest_endpoint)
assert 'create_version' in src and 'pre-rebuild-' in src
import portal_mcp.rag.rag_mcp as m
# Verify fts index creation in endpoint
assert 'create_fts_index' in src
print('PASS V8')
"

echo ""
echo "=== V9 — Docling in Dockerfile.mcp ==="
grep -q 'docling>=' Dockerfile.mcp && echo "PASS V9" || echo "FAIL V9"

echo ""
echo "=== V10 — Promptfoo in pyproject.toml ==="
grep -q 'promptfoo>=' pyproject.toml && echo "PASS V10" || echo "FAIL V10"

echo ""
echo "=== V11 — 7 promptfoo config files ==="
count=$(ls config/promptfoo/*_quality.yaml 2>/dev/null | wc -l | tr -d ' ')
[ "$count" = "7" ] && echo "PASS V11: $count configs" || echo "FAIL V11: $count (expected 7)"

echo ""
echo "=== V12 — All promptfoo configs valid YAML ==="
for f in config/promptfoo/*_quality.yaml; do
    python3 -c "import yaml; yaml.safe_load(open('$f'))" && echo "  ok: $(basename $f)" || echo "  FAIL: $f"
done

echo ""
echo "=== V13 — promptfoo case in launch.sh ==="
grep -q 'promptfoo)' launch.sh && echo "PASS V13: case" || echo "FAIL V13"
grep -q 'promptfoo.*Usage:' launch.sh && echo "PASS V13: usage line" || echo "FAIL V13: usage line"
grep -q 'promptfoo.*Run LLM quality' launch.sh && echo "PASS V13: help text" || echo "FAIL V13: help text"

echo ""
echo "=== V14 — Unit test files ==="
pytest tests/unit/test_rag.py tests/unit/test_promptfoo_configs.py -v --tb=short 2>&1 | tail -20

echo ""
echo "=== V15 — Full unit suite (baseline + new) ==="
pytest tests/unit/ -q --tb=no 2>&1 | tail -1

echo ""
echo "=== V16 — Lint + format ==="
ruff check . --fix 2>&1 | tail -3
ruff format --check . 2>&1 | tail -3

echo ""
echo "=== V17 — Workspace consistency (CLAUDE.md Rule 6) ==="
python3 -c "
import yaml
from portal_pipeline.router.workspaces import WORKSPACES
cfg = yaml.safe_load(open('config/backends.yaml'))
assert set(WORKSPACES.keys()) == set(cfg['workspace_routing'].keys())
print(f'PASS V17: {len(WORKSPACES)} workspace IDs consistent')
"

echo ""
echo "=== V18 — HOWTO docs updated ==="
grep -q '## Docling Document Parsing' docs/HOWTO.md && echo "PASS V18: Docling section" || echo "FAIL V18: Docling"
grep -q 'kb_optimize' docs/HOWTO.md && echo "PASS V18: LanceDB tools section" || echo "FAIL V18: LanceDB"

echo ""
echo "=== ALL DONE ==="
```

---

## 6. Rollback

```bash
git checkout Dockerfile.mcp pyproject.toml portal_mcp/rag/rag_mcp.py launch.sh
rm -f tests/unit/test_rag.py tests/unit/test_promptfoo_configs.py
rm -rf config/promptfoo/
# Full rollback:
git reset --hard pre-rag-enhance-v1
```

---

## 7. Commit & push

```bash
cd /home/claude/portal-5
git add -A
git commit -m "feat(rag): Docling doc parsing, Promptfoo evals, LanceDB hybrid search

Three additive enhancements to Portal 5's RAG and evaluation layer:

Docling (T1-T5):
- Replace basic pypdf/python-docx in _read_file() with Docling document
  understanding pipeline — table extraction (96% TEDS), layout preservation,
  reading-order awareness
- Add support for PPTX, XLSX, HTML, EPUB formats in kb_ingest
- Docling is a soft dependency with pypdf/python-docx fallback
- Document Docling integration in HOWTO.md

Promptfoo (T6-T10):
- Add promptfoo to dev extras for LLM quality evaluation
- Create 7 eval configs covering all 22 functional workspaces
  (coding, daily, reasoning, security, document, media, strategic)
- Add ./launch.sh promptfoo command with per-area and all options
- Complements bench_tps.py: speed gate → quality gate

LanceDB (T11-T16):
- Add opt-in FTS (BM25) index creation during kb_ingest
- Add query_type parameter to kb_search/kb_search_all: vector/fts/hybrid
- Add kb_optimize tool for IVF_PQ compression on large KBs
- Add kb_versions + kb_restore tools using LanceDB time-travel/versioning
- Auto-version snapshots on kb_ingest rebuild for safe rollback
- Document new tools in HOWTO.md

No pipeline/router changes; no workspace/persona changes."

git push origin main
```

---

## 8. What's NOT in This Task

- Enabling Docling's OWUI plugin (OWUI admin action, documented in HOWTO)
- Adding Docling to the OWUI container (OWUI handles its own deps)
- Adding Promptfoo to any production Docker image (dev-only)
- Changing the embedding model or reranker
- Switching chat_url or any pipeline routing
- Adding a Grafana dashboard for eval results
- Adding memory MCP LanceDB optimizations (same patterns, separate task)
- Running promptfoo evals live (requires Ollama models loaded; this task only sets up the configs)
