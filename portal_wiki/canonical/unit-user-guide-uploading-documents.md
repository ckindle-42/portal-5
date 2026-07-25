---
id: unit-user-guide-uploading-documents
kind: what
title: "USER_GUIDE \u2014 Uploading Documents"
sources:
- type: doc
  path: docs/USER_GUIDE.md
  commit: 05e42ec2
  section: Uploading Documents
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.515612
updated_at: 1784946220.515612
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
