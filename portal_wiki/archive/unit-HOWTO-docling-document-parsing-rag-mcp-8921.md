---
id: unit-HOWTO-docling-document-parsing-rag-mcp-8921
kind: why
title: "HOWTO \u2014 Docling Document Parsing (RAG MCP :8921)"
sources:
- type: design
  path: docs/HOWTO.md
  section: Docling Document Parsing (RAG MCP :8921)
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.853506
updated_at: 1783195000.853506
---


Portal 5's RAG MCP uses Docling (`docling>=2.0.0`, installed in `Dockerfile.mcp`)
for document text extraction during `kb_ingest`. This is separate from Open
WebUI's built-in RAG above.

| Feature | Without Docling | With Docling |
|---|---|---|
| PDF table extraction | Lost | Preserved as Markdown tables |
| Multi-column layout | Reading order scrambled | Correct reading order |
| Supported formats | .md, .txt, .pdf, .docx | + .pptx, .xlsx, .html, .htm, .epub |

`_read_file()` in `portal_mcp/rag/rag_mcp.py` tries Docling first for
PDF/DOCX/PPTX/XLSX/HTML/EPUB (in a worker thread, with a cached converter).
If Docling is unavailable, fails, or returns no usable text, it falls back to
pypdf (PDF) or python-docx (DOCX) — no loss of existing functionality. Docling
is a soft dependency: the MCP image includes it (model weights pre-fetched at
build time), the code does not hard-require it.

The `kb_ingest` tool surface is unchanged — you still point it at a directory;
the improvement is in what text gets extracted from each file.

Optional: Docling also ships an Open WebUI document-extraction integration
(OWUI Admin → Settings → Document Extraction), independent of this MCP. See
https://docs.openwebui.com/features/rag/document-extraction/docling
