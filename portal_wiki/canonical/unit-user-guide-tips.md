---
id: unit-user-guide-tips
kind: what
title: "USER_GUIDE \u2014 Tips"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: config/portal.yaml
last_generated_commit: de01e9b1e91aa629f9d80d26a890483a552e43e0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.51699
updated_at: 1784946220.51699
---

Several day-to-day behaviors follow from repository configuration rather than
from this guide. You can attach files for document analysis through Open WebUI's
uploader; attachments are then chunked and embedded according to the RAG settings
(`CHUNK_SIZE`, `RAG_EMBEDDING_MODEL`). In a chat you can reference a persistent
knowledge collection with a `#` marker, which resolves against the same
knowledge bases the pipeline's `kb_search` serves. Long reasoning sessions, such
as the `auto-reasoning` workspace, intentionally run slow because reasoning
models trade latency for depth. Keyboard and icon shortcuts in the chat UI are
Open WebUI affordances, not Portal settings.

## Why

The original tips unit asserted UI shortcuts as facts about Portal, but those are
features of the Open WebUI frontend, which this repository does not modify. The
behaviors this repo actually decides are attachment chunking, knowledge
collection retrieval, and which workspaces run slow reasoning models. Grounding
the unit to the compose manifest and `config/portal.yaml` separates repo-owned
behavior from vendor UI.
