---
id: unit-user-guide-supported-formats
kind: what
title: "USER_GUIDE \u2014 Supported Formats"
sources:
- type: code
  path: portal/modules/research/tools/rag_mcp.py
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: portal/modules/documents/tools/document_mcp.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5159261
updated_at: 1784946220.5159261
---

Knowledge-base ingestion accepts `.md`, `.txt`, `.pdf`, `.docx`, `.pptx`,
`.xlsx`, `.html`, `.htm`, and `.epub` source files via the RAG server's
`kb_ingest` tool. Chat attachments additionally benefit from
`PDF_EXTRACT_IMAGES=true`, so images inside PDFs are transcribed and indexed
rather than dropped. The document MCP server can read `.docx`, `.pdf`, `.xlsx`,
and `.pptx` files directly with its `read_*` tools, and can write Word, Excel,
and PowerPoint. CSV files are not part of the repository's RAG ingestion list.

## Why

The guide's format list mixed Open WebUI's general uploader with repository-owned
ingestion and invented a CSV claim. The formats Portal actually determines are the
`kb_ingest` extension set in `rag_mcp.py` and the `read_*`/`create_*` tools in
`document_mcp.py`. Grounding this unit to those files makes the supported-format
statement testable against the code instead of a stale doc paragraph.
