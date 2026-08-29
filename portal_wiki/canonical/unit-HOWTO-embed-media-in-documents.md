---
id: unit-HOWTO-embed-media-in-documents
kind: why
title: "HOWTO \u2014 Generate and embed media in documents"
sources:
- type: code
  path: portal/modules/documents/tools/document_mcp.py
claims: []
confidence: high
tags:
- HOWTO
- docs
---

**What:** Embed a generated image into a Word or PowerPoint document.

**How:** Generate an image with the enabled media tool and use its published Open WebUI URL as `image_url` in `prepare_embed_image`. Pass the returned object in `create_word_document(images=[...])` or in a PowerPoint slide's `images` list. Remote images must use public HTTPS URLs; private and local network addresses are rejected. Local images may be referenced only from the configured document output directory. Use `also_pdf=true` for a second PDF result when LibreOffice is installed on the MCP host.

## Why

Images are passed by reference rather than embedded as raw bytes so the document MCP never depends on the image engine that produced them: a model can generate with whatever media tool a workspace grants and hand the published URL to the document tool without the two sharing a filesystem contract. Enforcing public HTTPS for remote sources keeps the embed path free of SSRF, and `also_pdf` makes the PDF variant a second rendering of the same object rather than a separate pipeline.
