---
id: unit-USER_GUIDE-uploading-documents
kind: why
title: "USER_GUIDE \u2014 Uploading Documents"
sources:
- type: design
  path: docs/USER_GUIDE.md
  section: Uploading Documents
last_generated_commit: ''
confidence: high
tags:
- docs
- USER_GUIDE
created_at: 1783195000.9207969
updated_at: 1783195000.9207969
---


1. Open the chat interface at http://localhost:8080
2. Click the **+** (paperclip) icon in the chat input area
3. Upload PDF, DOCX, TXT, Markdown, or other supported formats
4. The document is automatically chunked, embedded with `nomic-embed-text`, and indexed

For a persistent document library accessible across all chats:
1. Go to **Workspace → Knowledge** in the left sidebar
2. Click **+ New Collection** and give it a name (e.g., "Company Policies")
3. Upload documents to the collection
4. In any chat, type `#` to reference the collection
