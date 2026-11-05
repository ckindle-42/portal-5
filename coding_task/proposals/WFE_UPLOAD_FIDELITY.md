# WFE upload fidelity — round 2

Pinned Open WebUI is `v0.12.5`. This round did not open the live container or `webui.db`. The orchestrator read that database and reported the values below. `DEFAULT_RAG_TEMPLATE` in `tests/wfe/owui_rag.py` was compared to v0.12.5 `config.py` and is the same 1445-character string.

## What production sends

Reported settings, not re-read here: `rag.full_context=false`, `rag.bypass_embedding_and_retrieval=false`, `rag.top_k=3`, `rag.top_k_reranker=3`, `rag.relevance_threshold=0`, `rag.enable_hybrid_search=true` (bm25 weight 0.2), reranker `BAAI/bge-reranker-v2-m3`, embedding `google/embeddinggemma-2`, `rag.chunk_size=1500`, `rag.chunk_overlap=100`, `rag.text_splitter=""` (character splitter), `rag.pdf_loader_mode="page"`, `rag.content_extraction_engine=""` (default loaders). `rag.template` was reported as the stock default; the v0.12.5 source default matches that text. No user has `defaultUploadContext` set. `auto-daily` / `auto-coding` capabilities are `{"builtin_tools": false}`, so `file_context` stays at its default, true. `RAG_SYSTEM_CONTEXT` is unset (env default false).

Open WebUI pops `files` before the upstream POST. Each turn of a chat that already has an uploaded file reaches the Pipeline with the RAG template prepended to the last user message, and with no `files` key. `apply_source_context_to_messages` fills `{{CONTEXT}}` and, because `RAG_SYSTEM_CONTEXT` is false, sets the last user message to `prefix + "\n" + message`. The stock template has no `{{QUERY}}`, so the original user text stays after the template. `prompt_template` is not applied to this template: it has no date or user placeholders. The query is passed through only so a `[query]` or `{{QUERY}}` token inside a document would be substituted the way Open WebUI does.

`full_context` and bypass are both false, so each file is retrieved from collection `file-{id}`. `top_k=3` applies per file. Hybrid search plus the reranker cannot be reproduced offline, and neither can the generated retrieval query.

Source tags carry `id` (1-based, shared by every chunk of one file), `name` (basename), `resource-type="file"`, and `resource-id`. Names and bodies are not escaped. Env default `RAG_SOURCE_METADATA_KEYS` is empty, so page and `start_index` are not attributes. That key was not in the database report.

Assumptions taken from v0.12.5 env defaults, because the database report did not list them:

- `ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER` is true. The splitter rewrites blank-line-separated text with `"  \n"` joins. It is not a no-op.
- `PDF_EXTRACT_IMAGES` is false.
- `CHUNK_MIN_SIZE_TARGET` is 0.
- `ENABLE_RAG_CSV_SUMMARY` is false: one document per CSV row, no summary document.

Images go to Open WebUI's vision path. They are not RAG context.

## What changed

Round 1 (`lane/wfe-upload-fidelity`, `b118862b8`, not merged) sent `body["files"]` and did not prepend document text. This round does not send `body["files"]`. `resolve_upload_path` is unchanged and is not required: the pipeline never sees those ids, and `stage_upload_tree` still places the files at `/workspace/uploads`.

When `WFE_ENGINE=pipeline`, from the turn that introduces a document fixture onward, the harness prepends the v0.12.5 template onto that turn's new user message only. The next turn strips the prefix from the previous user message before prepending the accumulated context. A direct engine gets an empty prefix. Introduction detection is round 1's: a whole-token basename, the upload id, or the upload directory in the user text. Chat files accumulate. Repo paths under `fixtures/realuse_v1/` are reads, not uploads. `.py` and `.json` fixtures are not documents.

Loaders, with no new project dependencies:

- pdf: PyMuPDF page text, stripped. A probe in this lane compared it to pypdf 6.21.2 `extract_text().strip()` on all 7 realuse PDFs and they matched. This finishing pass did not repeat that comparison.
- docx: a port of docx2txt 0.9 (`word/header*.xml`, `word/document.xml`, `word/footer*.xml`). That same probe matched `docx2txt.process` on all 11 realuse docx files.
- csv: `csv.DictReader`, one `key: value` document per row.
- txt and md: the whole file, UTF-8 then latin-1. The suite has txt files and no md files.
- xlsx and pptx: Open WebUI's unstructured-missing fallbacks (pandas `Sheet: {name}` plus `DataFrame.to_string`, and python-pptx `Slide {n}:` text). The suite has neither type. Production with unstructured installed uses `partition_xlsx` / `partition_pptx`.

Split order is the markdown header splitter (`#` through `######`, `strip_headers=False`; header metadata is dropped) and then the recursive character splitter at 1500/100, separator kept, whitespace stripped, a piece split again when its length is not strictly under 1500. `start_index` is metadata only and is not emitted. `ftfy.fix_text` is not applied. NUL and surrogate stripping runs after the split.

Stand-in name: `splitter_order_prefix` (the first `top_k` chunks in loader-then-splitter order). `ranked_standin` is true when any injected file has more than 3 raw chunks. A file at or under 3 contributes every chunk and does not set the flag; retrieval order can still differ from production. A walk of `tests/fixtures/realuse_v1` this pass found exactly four files over 3, all CSV, each kept at 3:

- `ru-v1-005/customers.csv` raw 8
- `ru-v1-008/orders.csv` raw 8
- `ru-v1-022/survey.csv` raw 14
- `ru-v1-035/adopted.csv` raw 25

No pdf, docx, or txt fixture exceeds 3. There is no md, xlsx, or pptx fixture. The three jpg fixtures stay on the vision path.

A completed `run_task` records `instrument.upload = {shape: "owui_rag_v0.12.5", turns: [{turn, files}], chunks, ranked_standin}`. `files` are the relative upload paths actually injected. `chunks` is the number of `<source>` bodies on the last turn, which is the accumulated set. The fingerprint parts include `upload_delivery: "owui-rag-v0.12.5"`.

`tool_grounded` still accepts a successful tool call first. The injected prefix can satisfy the check only when the check's tool set is non-empty and every name is one of `read_pdf`, `read_word_document`, `read_excel`, and every evidence pattern matches the prefix. The result is `grounded_by: "owui_context"`. A check that names any other tool, including `execute_python`, is not satisfied by the prefix. `expect_tools` dropped a read tool only where that array was exactly one of those three names. Every other expected tool stays.

Suite `expect_tools` changes, 16 arrays:

- `ru-v1-001` turn 0 `["read_pdf"]` → `[]`
- `ru-v1-002` turn 0 `["read_word_document"]` → `[]`
- `ru-v1-002` turn 1 `["read_word_document"]` → `[]`
- `ru-v1-003` turn 1 `["read_word_document"]` → `[]`
- `ru-v1-004` turn 0 `["read_pdf"]` → `[]`
- `ru-v1-006` turn 0 `["read_word_document"]` → `[]` (turn 1 `create_word_document` stays)
- `ru-v1-018` turn 0 `["read_pdf"]` → `[]` (turn 1 `create_word_document` stays)
- `ru-v1-019` turn 0 `["read_pdf"]` → `[]` (turn 1 `create_word_document` stays)
- `ru-v1-028` turn 0 `["read_word_document"]` → `[]`
- `ru-v1-028` turn 1 `["read_word_document"]` → `[]`
- `ru-v1-029` turn 0 `["read_pdf"]` → `[]` (turn 1 `create_word_document` stays)
- `ru-v1-048` turn 0 `["read_pdf"]` → `[]` (turn 1 `execute_python` stays; `metrics.py` is not injected)
- `ru-v1-064` turn 0 `["read_word_document"]` → `[]`
- `ru-v1-065` turn 1 `["read_word_document"]` → `[]`
- `ru-v1-069` turn 0 `["read_word_document"]` → `[]`
- `ru-v1-070` turn 0 `["read_pdf"]` → `[]` (turn 1 `create_word_document` stays)

`tool_grounded` tool lists on those checks are unchanged. `ru-v1-012` and `ru-v1-034` still expect `["explore_repository", "read_text_file"]`. The suite has no `read_excel` expectation.

## What stays different

- Production `resource-id` is a UUID, and the stored path is `/app/backend/data/uploads/{uuid}_{filename}`. The harness uses the relative upload path `realuse_v1/<task>/<file>` as both the source key and `resource-id`. `name` is the basename.
- Hybrid rank is the `splitter_order_prefix` stand-in. A row with `ranked_standin` false still may not match production's chunk order.
- PDF text is PyMuPDF. It matched pypdf on the 7 realuse PDFs. An unseen PDF can still differ. Image extraction stays off.
- xlsx and pptx follow the unstructured-missing fallback. No realuse row uses them.
- `ftfy` is omitted. An earlier measurement in this lane found it was an identity on the realuse document strings. This pass did not repeat that measurement. The frozen pdf and docx goldens are plain ASCII.
- The markdown header splitter is on because the env default is true. The live database was not checked for an override.
- `RAG_SOURCE_METADATA_KEYS` is assumed empty. The database report did not include it.
- The prefix is rebuilt onto the current turn's last user message and removed from the previous user message. Middleware applies it per request. Whether a saved Open WebUI transcript keeps the prefix was not re-checked.
- A `run_task` that returns before the turn loop has no `instrument.upload`. The campaign fingerprint still carries `upload_delivery`.
- Saved rows from before this change have no `owui_context`, so a rescore cannot context-ground them. Rescore reads `expect_tools` from the current suite, so those read tools are no longer required. A historical row that called `read_pdf` still passes `tool_grounded` through the tool.
- The three jpg fixtures stay on the existing vision path. Files remain at `/workspace/uploads`.
