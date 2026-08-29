# Portal 5 — User Guide

## Getting Access

Using Portal 5 requires an account. Open WebUI runs with `WEBUI_AUTH=true`, so
the interface always demands authentication, and `ENABLE_SIGNUP` defaults to true
so a login page is available for new signups. New accounts land in the `pending`
role because `DEFAULT_USER_ROLE` defaults to `pending`; an administrator must
promote the account to `user` (Admin Panel → Users) before it can chat. Until
then the account shows a pending status. An admin account is created on first
launch by `scripts/openwebui_init.py`.

## Why

Access behaviour is not a policy of this repository's docs but a consequence of
the Open WebUI environment and the bootstrap script. Anchoring these claims to
`WEBUI_AUTH`, `ENABLE_SIGNUP`, and `DEFAULT_USER_ROLE` means the unit stays true
if an operator changes the signup or approval defaults, and it documents where
the approval flow actually lives.

---

## Workspaces

Workspaces are the routing layer. Each workspace defined in `config/portal.yaml`
declares a `name`, a `model_hint` that selects its model, `expose_to_owui`
(whether it becomes an Open WebUI preset), a tool list, and optional `variants`.
The synchronization script writes presets only for exposed workspaces, so the
model dropdown shows that curated set; variants such as the agentic coding lanes
or the security sub-roles (`blueteam`, `redteam`) are addressed by query hint, not
listed in the dropdown. `auto-video` is defined but `expose_to_owui: false` and
shelved, and `auto-council` runs an opt-in multi-model review chain whose quorum
and dissent handling are enforced in code.

## Why

The guide presented a fixed table of dropdown workspaces that mixed exposed
workspaces, hidden variants, a shelved service, and a persona that never existed
in config. Workspace presence in the interface is a mechanical consequence of
`expose_to_owui` in `portal.yaml` plus the preset generator, so the unit must
describe that rule instead of reprinting a snapshot. This keeps the claim stable
as workspaces are added or shelved.

---

## Personas

Personas are pre-configured specialists defined one-per-file under
`config/personas/`. Each YAML carries a `name`, `slug`, `category`, and a
`workspace_model` that routes the persona to a workspace (for example
`auto-security` or `auto-coding`). The bootstrap script reads every persona file
and creates an Open WebUI model preset for it, so personas appear in the same
model dropdown as workspaces. Examples include `Cyber Security Specialist`,
`Red Team Operator`, and `Python Code Generator`. A persona's system prompt comes
from the YAML's inline `system_prompt` or a shared `prompt_template` body.

## Why

The generated guide treated personas as if they were a frontend concept, but they
are declarative artifacts: one YAML file per specialist, resolved to presets only
by the seeding script. Grounding to `config/personas/` and `openwebui_init.py`
keeps the unit aligned with how a new persona is actually added, and explains why
persona names in the dropdown always mirror the YAML `name` field.

---

## Tools (MCP Servers)

Tool servers are registered with Open WebUI from `imports/openwebui/mcp-servers.json`,
which lists each server's name, stable id, and port. In a chat you enable a tool
server with the `+` icon, then call its tools through the model. Portal Documents
(`create_word_document`, `create_excel`, `create_powerpoint`) generates office
files; Portal Code runs `execute_bash`/`execute_python` in an isolated sandbox;
Portal TTS exposes `speak`; Portal Whisper offers `transcribe_audio` and
`transcribe_with_speakers` (speaker diarization, with an Apple Silicon primary at
port 8924 via the MLX transcribe server); Portal MFLUX exposes `generate_image` / `edit_image`
and `start_image_generation` backed by Qwen-Image models; Portal Music exposes
the MiniMax job-based music toolset.

## Why

The guide described tools by their names in the chat UI, which left the actual
mapping to ports and code unstated. The fleet table, registration logic, and
every tool signature live in the repository, so this unit anchors each Portal
tool to the manifest entry and the MCP module that implements it, making the tool
list verifiable rather than anecdotal.

---

## Knowledge Base & Document RAG

Knowledge features are built on Open WebUI's RAG plus the pipeline's own
knowledge bases. The Open WebUI container is configured with
`RAG_EMBEDDING_ENGINE=openai` backed by the local Harrier embedding server,
`ENABLE_RAG_HYBRID_SEARCH=true`, and `CHUNK_SIZE`/`CHUNK_OVERLAP`; chat
attachments are chunked, embedded, and retrieved so answers are grounded in the
uploaded content. Persistent knowledge collections are managed through the
pipeline RAG MCP server (`kb_ingest`, `kb_search`, `kb_list`), which stores
vectors in LanceDB and reranks candidates via the MLX reranker. Nothing here
contacts a cloud service.

## Why

RAG is the one feature where the guide's "built into Open WebUI" claim conflated
a vendor UI with repository-owned plumbing. The repository actually owns two
layers: Open WebUI's attachment pipeline configured through the compose manifest,
and the LanceDB-backed knowledge bases exposed as MCP tools. Grounding this unit
to both lets a reader see which file governs each retrieval path.

---

### Uploading Documents

Open the chat interface at the Open WebUI address (bound to `127.0.0.1:8080` by
default in the compose manifest), click the paperclip to attach a file, and
upload one of the supported formats. The attachment is automatically chunked per
`CHUNK_SIZE`/`CHUNK_OVERLAP`, embedded with the Harrier model on port 8917, and
indexed so the chat can ground answers in it. For a persistent library, create a
knowledge collection from the workspace knowledge panel and upload documents
there; the pipeline's RAG server stores them in LanceDB, and you can reference
the collection from any chat with a `#` marker.

## Why

Uploading is two different mechanisms that the guide blurred into one flow:
ad-hoc chat attachments handled by Open WebUI with repository-controlled chunk
and embedding settings, versus persistent knowledge collections owned by the RAG
MCP server. Grounding both halves to the compose manifest and `rag_mcp.py` makes
the distinction explicit and keeps the unit accurate if either path changes.

---

### Supported Formats

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

---

### How It Works

When you attach a document, Open WebUI chunks it at `CHUNK_SIZE` (1500
characters) with `CHUNK_OVERLAP` (100 characters) and embeds each chunk locally.
The embedding engine is not a chat model in Ollama: `RAG_EMBEDDING_ENGINE=openai`
points at the host-native embedding server on port 8917 running the Harrier model
(`RAG_EMBEDDING_MODEL`). Search is hybrid — `ENABLE_RAG_HYBRID_SEARCH=true` fuses
semantic and keyword results. Because every endpoint (`host.docker.internal:8917`
and the local Ollama host) is on your machine, no document content leaves it.

## Why

The original unit credited `nomic-embed-text` in Ollama as the embedding model,
which the generated guide copied from an older stack. The deployment manifest
shows the RAG engine is the Harrier model served on port 8917, so the claim had
to be corrected against the manifest rather than preserved. Grounding the chunk
sizes to `CHUNK_SIZE` and `CHUNK_OVERLAP` makes this unit's numbers enforceable
against the actual configuration.

---

### Cross-Session Memory

Portal 5 keeps a persistent memory of facts you share across conversations.
`ENABLE_MEMORY_FEATURE=true` turns on Open WebUI's native memory store, and the
pipeline's `remember`/`recall` tools let workspaces such as `auto-daily`
(explicitly flagged `inject_memory` and `memory_writeback`) both read and write
that store. Memories are embedded and indexed locally with the Harrier model
(`MEMORY_EMBEDDING_MODEL`), the same indexer the RAG pipeline uses, and persisted
in LanceDB. In the Open WebUI interface you can view or edit stored memories
under Settings → Personalization → Memory.

## Why

The guide's account of memory was a description of a UI surface; the feature's
existence and its indexer are decided by repository configuration. Grounding here
anchors the claim to `ENABLE_MEMORY_FEATURE` and `MEMORY_EMBEDDING_MODEL`, so a
future change to either flag cannot silently invalidate this unit's statement
about how memories are stored and retrieved across sessions.

---

## Tips

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

---
