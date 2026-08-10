---
id: unit-HOWTO-7-document-generation
kind: why
title: "HOWTO \u2014 7. Document Generation"
sources:
- type: code
  path: config/portal.yaml
last_generated_commit: 0fec84d46a8898b1b5baf0508af1e25634b099af
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.842816
updated_at: 1783195000.842816
---

**What:** Generate Word (.docx), Excel (.xlsx), and PowerPoint (.pptx) files from chat.

**Activate:** Select `Portal Document Builder` (`auto-documents`) from the model dropdown. Its `tools` list in `config/portal.yaml` grants `create_word_document`, `create_excel`, `create_powerpoint`, the matching `read_*` tools, and `transcribe_with_speakers`, so the Documents tool is available automatically in that workspace.

**How:** Documents are produced by the `portal-documents` MCP server (Docker container at port 8913, code under `portal/modules/documents/tools/`), which builds the bytes with `python-docx`, `openpyxl`, and `python-pptx`. Files are written to the shared workspace's `generated/documents/` directory and returned with a `download_url`. The `auto-documents` system prompt requires the model to include that link in its reply so the user can download the file from the chat.

## Why

Document output is a two-part contract: the MCP server owns the byte-level format work while the workspace prompt owns the chat behavior (always returning a download link). Keeping generation in a dedicated MCP means the same file-producing tools are available to any workspace that lists them, and writing into the shared workspace means files are immediately reachable by other services and by the host.
