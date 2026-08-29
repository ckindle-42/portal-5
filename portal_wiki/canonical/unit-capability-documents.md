---
id: unit-capability-documents
kind: mixed
title: "Documents MCP \u2014 office file create/read/convert"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/documents/tools/document_mcp.py
- type: code
  path: config/inference/tools_manifest_document_mcp.json
claims: []
confidence: high
tags:
- capability
- mcp
- documents
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Documents MCP — office file create/read/convert

## What

The Documents MCP (`portal/modules/documents/tools/document_mcp.py`, port
8913) creates, reads, and converts office files — Word, PowerPoint, Excel,
and PDF. It is pipeline- and IDE-exposed and backs the `auto-documents`
workspace.

## How it's used

Creation tools build `.docx`, `.pptx`, and `.xlsx` from structured input
(`create_word_document`, `create_powerpoint`, `create_excel`); readers extract
text, tables, and structure back out (`read_word_document`, `read_powerpoint`,
`read_excel`, `read_pdf`); `convert_document` changes a file's format family
(LibreOffice-backed where available); `export_pdf` renders to PDF;
`prepare_embed_image` stages an image for embedding; and `list_generated_files`
enumerates what the module has produced in the shared output tree.

## Why it exists

Reports, decks, and spreadsheets are a first-class output of an agentic
platform, and they must be real files a human can open — not a raw format
mashup. Owning the document surface as an MCP keeps the heavy dependencies
(isolated in the `portal5-mcp` container) away from the pipeline and gives a
persona a typed create/read/convert vocabulary instead of a shell escape hatch.

## Value

A single prompt can produce a formatted brief, a slide deck, or a workbook
with tables, then re-read it to verify the content landed. Files land in the
shared workspace so a human picks them up where every other generated artifact
lives.
