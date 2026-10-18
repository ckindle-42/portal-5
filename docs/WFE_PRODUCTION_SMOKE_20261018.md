# WFE Production Smoke — 2026-10-18 (S2)

**Build:** deployed `6813621a` (`/health` `build_dirty: 0`, backends 12/12); `git diff 6813621a..HEAD -- portal/` is empty, so every claim below is against HEAD's `portal/` code.
**Run:** `scripts/wfe_production_smoke.py` (HEAD, 4f8109ab) — one real OWUI :8080 turn per offered tool, incumbent seat, production path (preset prompt, native model id, no evaluation scope), plus one empty turn per workspace for P-4. 73 turns, ≈50 min wall clock, one request in flight throughout.
**Workspaces / seats served:** auto-research `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M-ctx16k` · general-fast `unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit` (omlx-general) · general-deep `Qwen3.8-27B-oQ4e-mtp` (omlx-general) · auto-daily `gemma-4-26b-a4b-it-QAT-4bit` (omlx-general) · auto-coding `Qwen3-Coder-30B-A3B-Instruct-4bit` (omlx-coding) with one late turn on `qwen3-coder:30b-a3b-q4_K_M-ctx256k` (ollama-coding) · auto-documents `granite4.1:8b-ctx16k` (ollama).
**Delivery verdict:** `tools_offered` matched each workspace's allowlist on **every** turn (11/13/13/16/8/7 — harvested `/v1/trace/<cid>`, all 73 in `wfe_s2/traces.json`). No delivery defect: every non-call below is seat behavior with the tool correctly offered.

**Script result line:** `21 of 68 rows need a look` — each is classified in the findings.

## P-4: empty-turn prompt tokens vs context_limit

| workspace | empty-turn tokens | context_limit | share |
|---|---|---|---|
| auto-research | 1554 | 16384 | 9% |
| general-fast | 3235 | 98304 | 3% |
| general-deep | 3232 | 98304 | 3% |
| auto-daily | **2996** | **8192** | **37%** |
| auto-coding | 1817 | 262144 | 1% |
| auto-documents | 1506 | 16384 | 9% |

Caveat: the general/daily seats pre-inject memories on every turn (`memory_injected: 3–4` per trace), so these numbers are the operator account's real production prompt, not a bare floor. auto-research/coding/documents traces show no injection field.

**Known item 1 — auto-daily 8k vs 16 tools: CONFIRMED.** 37% of the window is gone before the user types. Decomposition of the 2996: the 16 tool schemas alone ≈ **1713 tokens** (sum of manifest parameter JSON ÷ 4; create_excel 354, minimax_generate 154, create_powerpoint 168), plus persona/appends, plus 3–4 injected memories, plus framing. S1's parked prompt additions for auto-daily (surface audit rows "waits for the S2 P-4 measurement") are **unaffordable at 8192**.

**Known item 2 — Qwen3-Coder not calling execute_bash: NOT REPRODUCED on bash.** Trace `p5-4070cf2f3dc8`: offered 8 (incl. execute_bash), called, outcome ok, answer correct ("hello-smoke"), 283 prompt tokens. Delivery first, as ordered — delivery is clean. The behavior family moved: `execute_nodejs` was hand-computed (6×7=42, no call, trace `p5-ab032f19579f`), and document-read prompts stalled the seat entirely (§H below).

## Per tool (68 cases; `offered` = tools_offered count on that turn; `args` INVALID = tool completed with error)

| workspace | tool | offered | called | args | outcome | answer | garbage | prompt tok | s | trace |
|---|---|---|---|---|---|---|---|---|---|---|
| auto-research | web_search | 11 | yes | valid | ok | n/a | - | 1003 | 4.3 | p5-d3484f0183f0 |
| auto-research | web_fetch | 11 | yes | valid | ok | yes | - | 390 | 2.1 | p5-e54a71c088e1 |
| auto-research | news_search | 11 | yes | valid | ok | n/a | - | 1611 | 24.5 | p5-caf92b2984db |
| auto-research | kb_search | 11 | NO | - | - | n/a | - | 311 | 2.2 | p5-228b67900938 |
| auto-research | kb_search_all | 11 | NO | - | - | n/a | - | 312 | 4.3 | p5-77e19e6aceb0 |
| auto-research | kb_list | 11 | yes | valid | ok | n/a | - | 304 | 1.7 | p5-f129fa9f2e03 |
| auto-research | remember | 11 | yes | valid | ok | n/a | - | 393 | 8.3 | p5-479fd541500c |
| auto-research | recall | 11 | yes | valid | ok | yes | - | 963 | 2.4 | p5-20465d3dd063 |
| auto-research | graph_recall | 11 | yes | valid | ok | n/a | - | 1423 | 4.2 | p5-c200f7d1e7bb |
| auto-research | neighbors | 11 | yes | valid | ok | n/a | - | 365 | 3.2 | p5-1f9efb8dbb9a |
| auto-research | entity_timeline | 11 | yes | valid | ok | n/a | - | 403 | 4.5 | p5-4559c64955ed |
| general-fast | web_search | 13 | yes | valid | ok | n/a | - | 1227 | 7.1 | p5-ea02d5aaa3a3 |
| general-fast | web_fetch | 13 | yes | valid | ok | yes | - | 699 | 5.5 | p5-9e6dbd9ffc59 |
| general-fast | kb_search | 13 | NO | - | - | n/a | - | 806 | 5.6 | p5-ddcf8cb77274 |
| general-fast | kb_list | 13 | yes | valid | ok | n/a | - | 607 | 5.2 | p5-c07eb8a7d92a |
| general-fast | read_pdf | 13 | yes | INVALID | error | NO | - | 641 | 7.0 | p5-42303addf2cd |
| general-fast | read_word_document | 13 | yes | INVALID | error | NO | - | 830 | 6.2 | p5-84dd57bd2cd3 |
| general-fast | read_excel | 13 | yes | INVALID | error | NO | - | 656 | 8.7 | p5-7a2f0b8edf34 |
| general-fast | create_word_document | 13 | yes | valid | ok | yes | - | 837 | 4.6 | p5-80cc465055a5 |
| general-fast | create_excel | 13 | yes | valid | ok | yes | - | 829 | 5.4 | p5-6d5487a1e70e |
| general-fast | create_powerpoint | 13 | yes | valid | ok | yes | - | 817 | 5.0 | p5-ed5b39fc6938 |
| general-fast | execute_python | 13 | yes | valid | ok | yes | - | 645 | 3.1 | p5-ed0711a6cef2 |
| general-fast | remember | 13 | yes | valid | ok | n/a | - | 701 | 11.1 | p5-3d7286b4234e |
| general-fast | recall | 13 | NO | - | - | yes | - | 3250 | 4.4 | p5-ba99af542ae2 |
| general-deep | web_search | 13 | yes | valid | ok | n/a | - | 1212 | 41.0 | p5-22acdd03783c |
| general-deep | web_fetch | 13 | yes | valid | ok | yes | - | 696 | 35.4 | p5-f4b7d205b35d |
| general-deep | kb_search | 13 | NO | - | - | n/a | - | 714 | 36.3 | p5-6a90d86cf74c |
| general-deep | kb_list | 13 | yes | valid | ok | n/a | - | 604 | 33.9 | p5-cb480fbe86b4 |
| general-deep | read_pdf | 13 | yes | INVALID | error | NO | - | 640 | 35.6 | p5-b812732eb856 |
| general-deep | read_word_document | 13 | yes | valid | ok | yes | - | 754 | 36.5 | p5-189d209a9b5d |
| general-deep | read_excel | 13 | yes | valid | ok | yes | - | 740 | 35.9 | p5-caca93dafb31 |
| general-deep | create_word_document | 13 | yes | valid | ok | yes | - | 845 | 20.9 | p5-2565a97ce592 |
| general-deep | create_excel | 13 | yes | valid | ok | yes | - | 850 | 23.0 | p5-dc7c16a431e3 |
| general-deep | create_powerpoint | 13 | yes | valid | ok | yes | - | 856 | 20.7 | p5-f986d0417dcf |
| general-deep | execute_python | 13 | yes | valid | ok | yes | - | 642 | 15.0 | p5-9bc8f9a104f3 |
| general-deep | remember | 13 | yes | valid | ok | n/a | - | 692 | 39.0 | p5-781d8ceb833d |
| general-deep | recall | 13 | NO | - | - | yes | - | 3246 | 29.9 | p5-0d5061087b0b |
| auto-daily | web_search | 16 | yes | valid | ok | n/a | - | 1012 | 7.1 | p5-799b98a1d4d7 |
| auto-daily | web_fetch | 16 | yes | valid | ok | yes | - | 467 | 5.5 | p5-f0bf59c20a17 |
| auto-daily | kb_search | 16 | NO | - | - | n/a | - | 394 | 5.3 | p5-19a52d15c943 |
| auto-daily | kb_list | 16 | yes | valid | ok | n/a | - | 373 | 5.3 | p5-a166c6867103 |
| auto-daily | read_pdf | 16 | yes | valid | ok | yes | - | 461 | 5.7 | p5-495e6eb52e92 |
| auto-daily | read_word_document | 16 | yes | valid | ok | yes | - | 507 | 5.8 | p5-2450c635faa8 |
| auto-daily | read_excel | 16 | yes | valid | ok | yes | - | 493 | 3.0 | p5-da973dfe6c4e |
| auto-daily | create_word_document | 16 | yes | valid | ok | yes | - | 606 | 3.8 | p5-b6c1593f26e8 |
| auto-daily | create_excel | 16 | yes | valid | ok | yes | - | 617 | 4.2 | p5-eaca3b1b454d |
| auto-daily | create_powerpoint | 16 | yes | valid | ok | yes | - | 631 | 3.8 | p5-63865119cc51 |
| auto-daily | execute_python | 16 | yes | valid | ok | yes | - | 409 | 2.4 | p5-021ce205b5d1 |
| auto-daily | remember | 16 | yes | valid | ok | n/a | - | 429 | 4.3 | p5-e645e50f1470 |
| auto-daily | recall | 16 | NO | - | - | yes | - | 3011 | 5.1 | p5-2bdacbad8b0d |
| auto-daily | minimax_status | 16 | yes | valid | ok | n/a | refusal | 399 | 7.9 | p5-521013cc1b0c |
| auto-daily | transcribe_audio | 16 | yes | valid | ok | yes | - | 764 | 11.4 | p5-905635dc5c05 |
| auto-coding | execute_python | 8 | yes | valid | ok | yes | - | 292 | 2.5 | p5-66c33292b637 |
| auto-coding | execute_nodejs | 8 | NO | - | - | yes | - | 1825 | 1.3 | p5-ab032f19579f |
| auto-coding | execute_bash | 8 | yes | valid | ok | yes | - | 283 | 2.3 | p5-4070cf2f3dc8 |
| auto-coding | sandbox_status | 8 | yes | valid | ok | n/a | - | 381 | 2.5 | p5-2a43bc5e2a61 |
| auto-coding | read_word_document | 8 | NO | - | - | NO | - | 0 | 292.2 | p5-0e707c84d963 |
| auto-coding | read_pdf | 8 | NO | - | - | NO | - | 0 | 293.3 | p5-a66247a0a741 |
| auto-coding | remember | 8 | yes | valid | ok | n/a | - | 311 | 11.6 | p5-fe5d84d65992 |
| auto-coding | recall | 8 | NO | - | - | yes | - | 974 | 338.0 | p5-601de90eaa79 |
| auto-documents | create_word_document | 7 | yes | valid | ok | yes | - | 537 | 4.1 | p5-e90dc1f697b1 |
| auto-documents | create_excel | 7 | yes | valid | ok | yes | - | 530 | 4.7 | p5-49135fec7531 |
| auto-documents | create_powerpoint | 7 | yes | valid | ok | yes | - | 552 | 4.6 | p5-d62fa403b8ac |
| auto-documents | read_word_document | 7 | yes | valid | ok | yes | download link on a non-create | 462 | 3.1 | p5-b16e39cc5135 |
| auto-documents | read_excel | 7 | yes | valid | ok | NO | - | 435 | 6.3 | p5-f7b29ca00ac1 |
| auto-documents | read_powerpoint | 7 | yes | valid | ok | yes | download link on a non-create | 454 | 11.3 | p5-5eb30a61fc68 |
| auto-documents | read_pdf | 7 | yes | valid | ok | yes | download link on a non-create | 428 | 9.9 | p5-408134f21e1b |

## Findings and proposed fixes

Every defect gets: file, change, evidence. **No portal/ or config/ edits were made** — fixes are proposals for the orchestrator. Backlog lines added to `coding_task/WFE_LIVE_BACKLOG.md` §"S2 production smoke (2026-10-18)".

### A. documents read tools refuse absolute-path args in ~1.5 ms; the general-fast seat then answers with an EMPTY string
- **Smoke rows:** general-fast read_pdf/read_word_document/read_excel — called, outcome **error**, answer NO (traces `p5-42303addf2cd`, `p5-84dd57bd2cd3`, `p5-7a2f0b8edf34`; error spans 4.3–6.0 ms). general-deep read_pdf errored once the same way (`p5-b812732eb856`).
- **Repro** `p5-258888759383`: same prompt on general-fast → `read_pdf` error 6.0 ms → **answer is the empty string**.
- **Arg-shape map (MCP-direct, :8913, no model; fixture uploaded through OWUI):** bare filename and OWUI file id → success ≈8 ms; **any absolute path** (`/uploads/…`, `/tmp/…`, an OWUI content URL) → structured error ≈1–1.5 ms: `"<path>" is outside the readable roots ['/app/data/generated'] (set DOCUMENTS_READ_ROOTS to allow more)`; wrong key / missing arg → HTTP 400.
- **Diagnosis:** the read tools resolve bare names and ids but refuse absolute paths that aren't under the container's OUTPUT_DIR; the general-fast seat passes an absolute path (args unseen — trace carries no bodies), the tool refuses in ~5 ms, and the seat gives up with an empty answer. 4–6 ms rules out file access — this is the roots refusal.
- **Proposed fix:** `portal/modules/documents/tools/document_mcp.py`, `_resolve_input_path` (line 262): after the readable-roots refusal, retry resolution with `os.path.basename(file_path)` through the same uploads lookup before returning the error. Alternatively set `DOCUMENTS_READ_ROOTS` on the documents container to include OWUI's upload dir (config change — orchestrator's). Evidence: the arg map above; the error text itself names the lever.

### B. auto-documents read_excel: tool ok, seat mis-sums (answer wrong ×2)
- Smoke row + repro `p5-cab7a496f71c`: read_excel ok (16 ms), answer "The total … is **2335** (1200 + 340 + 85 + 610 = 2335)" — the correct total is 2235. granite4.1:8b arithmetic slip, deterministic seed (1002). **Seat finding**, no delivery involvement. Watch: the same slip will grade the general suite's gen-document rows.

### C. auto-daily minimax_status: tool ok, seat denies having access
- `p5-1a4252d6a7c7`: minimax_status called, outcome ok, 6.6 ms — then the answer claims "I do not have access to a real-time monitoring system …". The seat ignored the tool result (refusal-pattern garbage flag). **Seat finding** (gemma-4-26b on the daily lane).

### D. Download-link verdict (S4 follow-on): container path does NOT reproduce; link is the public URL and needs auth
- Two fresh create turns on auto-documents: answers give `Download: https://chat.intoodeep.systems/api/v1/files/{id}/content/<name>` (PORTAL_PUBLIC_URL). **No `/app/data/generated/…` path in any answer.**
- Resolution: GET the file **direct on OWUI :8080** with the owner's key → **200**, real docx bytes (`PK\x03\x04…`); anonymous → 401; through the public URL with the key as Bearer → 403, but that 403 is the tunnel's bot filtering: a **real browser** (headless, logged out) navigating the link gets OWUI's `{"detail": "Not authenticated"}` — the tunnel passes browsers, OWUI enforces auth.
- Verdict: the S4 observation is closed as *not reproduced at this build*; the residual is a one-click manual check (logged-in browser → expect 200) for the operator.
- **Mechanism of the old observation, and the residual leak:** `_published()` returns the container path as `path` (`/app/data/generated/Smoke_….docx`) alongside `download_url`, and error texts name `/app/data/generated` — both can be quoted by the model.
- **Proposed fix:** `portal/modules/documents/tools/document_mcp.py:74–85` — drop `path` from the success dict (or rename it `container_path`) so the only user-facing reference the model sees is `download_url`. Evidence: result shape at those lines + the decision-doc's original observation.

### E. Read answers carry hallucinated download links (cross-talk the prompt already forbids)
- Smoke rows: auto-documents read_word_document / read_powerpoint / read_pdf all flagged `download link on a non-create`.
- Repro `p5-057a425ccf92`: read turn answers "…is **4471**. Download: https://files.mocki.io/1b7d8ac1-…" — a **fabricated** URL. The workspace prompt explicitly says "Never write a download link unless a create tool returned one in this turn" — granite4.1:8b ignores it; read tools never return `download_url` (only create/convert do).
- **Proposed fix (pipeline-side, prompt already failed once):** in `portal/platform/inference/router/non_streaming.py` and `streaming.py`, when the turn's completed tools include no `create_*` tool, strip any `Download:`-style line from the final content before delivery (the same post-processing slot that already handles tool-call salvage). Evidence: rows above; the prompt rule in `config/portal.yaml` `workspaces.auto-documents` `owui_system_prompt`.

### F. kb_search / kb_search_all never called anywhere — instrument finding, not a seat defect
- 5 rows (auto-research ×2, general-fast/deep/daily ×1) called `kb_list` instead. Production truth: `POST :8921/tools/kb_list` → `{"knowledge_bases":[{"kb_id":"smoketest","chunks":0,…}]}` — **one KB, zero chunks**; the manifest requires `kb_id` for `kb_search`. A model that lists the KBs and answers from the (empty) list is behaving correctly. Fix belongs to the instrument: seed a KB fixture or expect the empty answer. Hygiene: the leftover `smoketest` KB (0 chunks) is itself smoke debris an operator may want to delete.

### G. recall is pre-empted by memory injection on general/daily/coding (production behavior, measured)
- recall answered correctly WITHOUT the call on general-fast/general-deep/auto-daily/auto-coding (auto-research's seat did call it). Recall-row prompts jump to 3011–3250 tokens vs ~600 on sibling rows: the router's memory pre-injection carries the note into the system prompt (`memory_injected: 3–4` on those seats, absent on research/documents/coding). Users get right answers; the WFE checkers that require the call will not. No fix proposed here — record as the production grounding rule for the general slice (its backlog already asks exactly this question).

### H. auto-coding: bash fine, node hand-computed, document-reads stall the seat, backend switched mid-smoke
- execute_bash: called, ok, correct (`p5-4070cf2f3dc8`) — close-out finding **not reproduced**.
- execute_nodejs: offered, not called, answer 42 by hand (`p5-ab032f19579f`) — the short-compute pattern lives on node.
- read_word_document / read_pdf: **292 s per turn, zero tool calls, wrong answers, usage prompt_tokens 0** (`p5-0e707c84d963`, `p5-a66247a0a741`) — the omlx-coding seat stalled on these prompts; the very next turn was served by a DIFFERENT backend (`p5-601de90eaa79`, ollama-coding `qwen3-coder:30b-a3b-q4_K_M-ctx256k`, 338 s). The coding slice's live screen should preflight exactly these two prompt shapes and watch the backend identity.

### I. Smoke script cleanup gap (the only defect in the instrument's own code)
- The docstring promises "the memory note is forgotten again"; `cleanup()` deletes only files. The run left 8 bluefinch notes in the operator's memory store — hand-deleted this run via `POST :8920/tools/forget` (ids in the EVIDENCE of the dispatch report; ZETA-4471 / `uat_test_key` markers predate this run and were left).
- **Proposed fix:** `scripts/wfe_production_smoke.py` `cleanup()` — capture the id from the `remember` case's tool result (or `list`+forget by the smoke sentence) and POST `{"arguments": {"id": …}}` to `:8920/tools/forget`.

### J. (informational) memory-MCP argument wrapper inconsistency
- `:8920/tools/*` expects `{"arguments": {…}}` (`graph_memory.py:430` unwraps `arguments`); `:8921/tools/kb_list` takes bare args. Not in the brief's scope — noted for whoever next scripts direct MCP probes.

## What would make the re-run clean
Fixes A (root fallback) and E (post-filter) plus the config decision on auto-daily (raise `context_limit` or trim the roster — orchestrator's call, config is sacred per the dispatch). B, C, H are seat findings for the S5–S8 slices; F is a fixture change in the smoke script.

## Residual / not done
- Logged-in browser click on a public download URL (expect 200) — needs a human session; structural evidence complete (D).
- minimax_generate skipped by design (heavy GPU; covered by the music UAT).
- `PORTAL_TRACE_BODIES=1` would pin A's exact bad arg; needs a pipeline restart (orchestrator's) — the arg-shape map constrains it to an absolute-path arg already.

## Re-check 85d26a10

**Build:** `/health` → `build_sha 85d26a10708a…`, `build_dirty: 0`, 12/12 backends; HEAD == deployed. Fix batch `21d5aed1` (A: documents read-path basename retry; D: create result drops top-level `path`; E: Download-line holdback; I: smoke forgets its memory note). Stack held exclusively; one request in flight; ≈10 min wall clock.

| item | workspace | tool / case | offered | called | outcome | answer check | Download line | trace |
|---|---|---|---|---|---|---|---|---|
| A | general-fast | read_pdf | 13 | yes | ok | "5521" ✓ | none | p5-63e1740a07bb |
| A | general-fast | read_word_document | 13 | yes | ok | "37" ✓ | none | p5-1bf5e9cc360e |
| A | general-fast | read_excel | 13 | yes | ok | "2,235" ✓ | none | p5-5a165b6f68d8 |
| A | general-deep | read_pdf | 13 | yes | ok | "The vault code … is **5521**" ✓ | none | p5-462cc9df2f91 |
| A | general-deep | read_word_document | 13 | yes | ok | "**37 days**" ✓ | none | p5-c8836e2a9f9b |
| A | general-deep | read_excel | 13 | yes | ok | "**2,235** (1,200 + 340 + 85 + 610)" ✓ — the §B mis-sum did not recur | none | p5-6e162101efe2 |
| D | auto-documents | create_word_document | 7 | yes | ok | "Download: https://chat.intoodeep.systems/api/v1/files/a5dfba9b…/content/…" — **no `/app/data` path in the answer** | kept (public URL only) | p5-addd37bbcb94 |
| D | documents MCP :8913 (direct, no model) | create_word_document | - | - | ok | result top-level keys = `download_url, filename, message, success` — **`path` gone**; message names only the public URL | n/a | - (MCP-direct, no pipeline trace) |
| E | auto-documents | read_word_document | 7 | yes | ok | "**37 days**" ✓ — **no Download line, no URL** | none | p5-f95740259b98 |
| E | auto-documents | read_powerpoint | 7 | yes | ok | "**Ilse Mott**" ✓ — no Download line | none | p5-85db16156407 |
| E | auto-documents | read_pdf | 7 | yes | ok | "**5521**" ✓ — no Download line | none | p5-1c011112cb74 |
| I | general-fast | `wfe_production_smoke.py` full run (13 cases) | 13 | 11/13 | 11 ok | 2/13 flagged = the two known instrument rows (kb_search empty-KB §F, recall pre-injection §G); all 6 read/create rows ok | - | p5-cee929d36a5d … p5-540eafdc1a76 |
| I | memory MCP :8920 | recall "bluefinch" after the run | - | - | - | **FAIL — 1 note still present** (`8a8a5c7c-9fbf-4bb4-a532-cce9260ecd95`); hand-deleted | - | - |

**A — PASS.** All six read rows called + ok + correct on both seats; no empty answers. The general-fast seat now passes an arg the tool accepts (the basename retry absorbs it), and the §B arithmetic slip did not recur on general-deep.
**D — PASS.** The create answer gives only the public download URL; the tool result no longer carries a top-level container `path` (verified both through OWUI and MCP-direct); the create turn keeps its link.
**E — PASS.** No Download line (fabricated or real) on any read answer; the create turn's link survives the holdback.
**I — FAIL (instrument residual).** The script's cleanup takes the memory id from the **model's answer** (`scripts/wfe_production_smoke.py:291`, `_memory_id_from_tool_result_text`); this run the model stored the whole prompt sentence as the note and never echoed a UUID, so `memory_id` stayed empty, nothing was forgotten, and no WARNING printed. Proposed instrument fix: after `cleanup()`, sweep `POST :8920/tools/recall {"arguments": {"query": "smoke test code word bluefinch"}}` and `_forget_memory` every hit matching the smoke sentence — self-healing regardless of whether the model echoes the id. The leftover was hand-deleted; the store is clean again.

No `portal/` or `config/` edits; no git.

