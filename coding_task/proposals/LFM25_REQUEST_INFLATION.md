# RCA — LFM2.5 ~350k-token tool-loop request inflation (read-only analysis)

**Verdict.** The inflated requests are accumulated tool results, not duplicated history and
not LFM2.5-specific behaviour. The chain is:

1. **Trigger** — on the realuse PDF tasks the first `read_pdf` call at the model's natural
   path (`/workspace/<task file>`) fails with an opaque MCP-level error, while the fixture
   actually lives under `/workspace/uploads/<suite>/<task>/`. No path hint is returned.
2. **Recovery** — the model falls back to `execute_python` `os.listdir` / recursive
   `os.walk` over `/workspace` — which mounts the whole `${AI_OUTPUT_DIR}` (portal-data,
   including `worktree_archive_20261021/`), so each walk prints hundreds of thousands of
   path names and saturates the sandbox's 50,000-byte stdout cap.
3. **Accumulation** — the Pipeline appends each result (JSON-escaped, ≤ ~52 KB) to
   `messages` and re-sends the whole conversation at every tool-loop hop, with no
   accumulated-size guard. `ToolRepeatGuard` only suppresses exact-argument repeats, so
   near-duplicate walks with different code strings always run.

**Not the model:** Qwen3.6-35B-A3B (`UD-Q4_K_XL-ctx96k`), the incumbent challenger
benchmark arm, inflates identically and *more* on the same tasks in the same campaign
(90,221 / 91,886-token single requests vs LFM2.5's 74,141). **Not the engine/template:**
Ollama v0.40.13 renders each message once per call (`server/prompt.go` `chatPrompt` /
`renderPrompt`, `template/template.go` legacy path, `model/renderers/lfm2.go` — all
audited, all linear). The unseating of LFM2.5 therefore rests on a platform defect that
hits every seat whose first read fails.

## Evidence on disk

All under `~/AI_Output/portal-data/tests/wfe/results/campaigns/` (WFE harness debug dumps
`debug/*.debug.jsonl` carry per-turn `prompt_tokens`, `sent_chars`, per-call
`raw_args`/`output` — both log-capped at 500/4,000 chars).

### Inflation follows the failed first read, not the model

| row | task | first call result | tool calls | filesystem walks | last-hop prompt tokens |
| --- | --- | --- | --- | --- | --- |
| `realuse_s8_20261030f` Qwen3.6 `ru-v1-001` (`rows/2736e0f680b4.json`) | PDF | `read_pdf` **MCP error** | 4 | 2 | **90,221** (rollup 93,630, prefill 227.7 s) |
| `realuse_s8_20261030f` Qwen3.6 `ru-v1-004` (`rows/2d05e582a232.json`) | PDF | `read_pdf` **MCP error** | 4 | 2 | **91,886** (rollup 95,264, prefill 222.4 s) |
| `realuse_s8_20261030f` Qwen3.6 `ru-v1-002` | DOCX | `read_word_document` success | 1 | 0 | 3,281 |
| `realuse_s8_20261030f` Qwen3.6 `ru-v1-003` | DOCX | `read_word_document` success | 1 | 0 | 3,062 |
| `realuse_s8_20261030f` LFM2.5 `ru-v1-001` (`rows/ff54324762c8.json`) | PDF | `read_pdf` **MCP error** | 19 | ≥2 | **74,141** (t0 2,576; rollup 76,717; turn prefill 117.2 s, engine-timed) |
| `realuse_s8_20261030f` LFM2.5 `ru-v1-004` (`rows/7ffd23c39bbc.json`) | PDF | `read_pdf` success (516 chars) | 2 | 0 | ~3.6k (rollup 6,034) |
| `realuse_s8_rerun_20261030c` LFM2.5 `ru-v1-001` (control, same task+seed) | PDF | `read_pdf` success (284 chars, uploads path) | 1 | 0 | 2,779 (rollup 5,355) |

Debug dumps: `realuse_s8_20261030f/debug/hf.co_unsloth_Qwen3.6-35B-A3B-GGUF_UD-Q4_K_XL-ctx96k.debug.jsonl`
and `.../hf.co_unsloth_LFM2.5-24B-A2B-GGUF_UD-Q4_K_XL-ctx96k@card-5ffa1fb8.debug.jsonl`;
control `realuse_s8_rerun_20261030c/debug/...LFM2.5...debug.jsonl`.

### The exact call sequence (Qwen3.6 `ru-v1-001`, turn 0)

1. `read_pdf /workspace/final_invoice.pdf` →
   `{"error": "Tool 'read_pdf' returned an MCP tool error", "detail": "Error executing tool read_pdf"}`
   (98 chars — no path hint).
2. `execute_python` `os.listdir('/workspace')` → log-capped at 4,000 chars (real ≤ 50,000:
   `generated/`, `portal-data/worktree_archive_20261021/...`, uploads, every MCP output).
3. `execute_python` recursive "find files with 'invoice' in name" `os.walk('/workspace')`
   → log-capped at 4,000 chars (real ≤ 50,000; walks the entire shared tree).
4. `read_pdf /workspace/uploads/realuse_v1/ru-v1-001/final_invoice.pdf` → **success** with
   the invoice text ("Timeline slipped by 3 days / labor 2400 …").

LFM2.5 `ru-v1-001` (campaign f) made 19 such calls in one turn; arithmetic: 2 walk results
near the 50 KB cap + 17 small ones ≈ 110–160 KB of JSON-escaped content, and path-listing
text tokenizes poorly (UUID/hex runs ≈ 1.5–2 chars/token) → ≈ 70 k tokens + base ≈ the
observed 74,141. Qwen3.6's 90,221 is the same mechanism with a tokenizer that chunks the
listings even less efficiently.

### Worst case brackets the intake's ~350–369k

- Sandbox stdout cap: `portal/modules/coding/tools/code_sandbox_mcp.py:83`
  (`MAX_OUTPUT_BYTES = 50_000`, applied at :553-554).
- Streamed tool-loop ceiling: `portal/platform/inference/router/workspaces.py:128`
  (`MAX_TOOL_HOPS = 20`, env-overridable).
- Worst case ≈ 20 hops × ~52 KB (JSON-escaped) ≈ ~1.0 MB ≈ **350–500k tokens** at 2–3
  chars/token for path listings. The intake's ~350–369k needs only ~7–14 maxed hops —
  inside the bound the shipped code permits. The saved rows are the smaller tail of the
  same distribution.

### Trace-body evidence was written where the code says, then pruned

`PORTAL_TRACE_BODIES` capture lives in `portal/platform/inference/router/trace.py`
(`CAPTURE_BODIES` :54; digests via `_digest_request` :149-187) and writes to
`PORTAL_TRACE_DIR` or `/tmp/portal_traces` (:78-81) under a 200-record mtime ring
(`MAX_RECORDS` :55, `_prune` :293-302). Verified 2026-11-04: `/tmp/portal_traces` holds
200 records, oldest surviving 2026-10-31 09:37 — every Oct-29/30 record, including all
LFM2.5 turns, has been pruned. No 300k+ `prompt_tokens` value exists anywhere in the saved
campaign tree (regex sweep over all `rows/*.json`: max LFM-related single turn 74,141; max
any model 231,694 in an unrelated Sept oMLX campaign).

### Harness note, not engine truncation

The `context overflow: turn 1: prompt shrank 5936 -> 2758 tokens (engine truncation)`
notes on campaign-f LFM rows are false positives from the pre-fix detector: per-turn usage
is the tool loop's **last hop** (its tool results are legitimately dropped by the next
turn's fresh conversation). The current detector documents exactly this and only flags a
shrink near the window (`tests/wfe/runner.py:1372-1417`, comment citing these very
campaign-f rows) — the fix postdates campaign f.

## Owner classification

| candidate | verdict |
| --- | --- |
| **Pipeline / host tooling — tool-result size policy** | **Primary owner.** 50 KB model-facing stdout cap (`code_sandbox_mcp.py:83`); results appended uncapped at the loop's append sites (`streaming.py:1467-1469`, `non_streaming.py:1039`) and the whole conversation re-sent per hop (`streaming.py:971` POST of `current_body`) with no accumulated-bytes guard; `ToolRepeatGuard` compares exact canonical args only (`tool_repeat.py:89-97`) so near-duplicate walks never trip `FORCE_SYNTHESIS_AT` (:40). |
| **Trigger — read tool contract + staging** | Secondary owner. `read_pdf` fails at the natural path with an opaque wrapper error on the *deployed* build; the current tree returns structured N-23 errors (`portal/modules/documents/tools/document_mcp.py:1134-1141`, `_resolve_input_path` :261-290, eval-scope confine :269-275), but even a structured error names no working path. WFE staging places fixtures at sandbox-root + `uploads/<suite>/<task>/`, not where a confined read resolves them. |
| Harness (`tests/wfe`) | Exonerated as cause. It caps *its own* model-facing tool results at 4,000 chars (`runner.py:1472`) — the exact scale the Pipeline lacks — and its debug dumps are what made this RCA possible. |
| Engine/template (Ollama lfm2) | Exonerated for inflation. v0.40.13 renders linearly. (Separate defect, does not inflate: the raw `UD-Q4_K_XL` tag carries a 197-byte legacy template layer with no tool protocol — `config/ollama_modelfiles/README.md` — and the legacy `Template.Execute` path drops `role:"tool"` messages entirely, so LFM2.5 may literally never see tool results; that explains the 0/4 tool-grounded FAILs, not the token counts. The `lfm2-thinking` repair failed `think=false` and was not applied.) |
| Model behaviour | Exonerated for inflation. Qwen3.6 (seated, incumbent arm) inflates the same or worse on identical tasks. LFM2.5's always-think leak is a separate, already-documented risk. |

## Proposed minimal fixes (NOT implemented)

1. **Cap the model-facing tool result at the single chokepoint** —
   `portal/platform/inference/router/tools.py:329-333` (`_dispatch_tool_call` return):
   truncate `content` to a model-facing ceiling (4,000 chars, matching the WFE harness's
   own cap at `tests/wfe/runner.py:1472`) and append a `[… truncated N chars]` marker.
   One site protects the streaming loop, the non-streaming loop, and chains. This alone
   bounds every future balloon to ~`hops × 4 KB` ≈ ≤ 25 k tokens at `MAX_TOOL_HOPS=20`.
2. **Per-request tool-bytes budget** (defence in depth) — at the two append sites
   (`streaming.py:1467-1469`, `non_streaming.py:1039`): accumulate appended result bytes;
   past a fraction (e.g. 50%) of the workspace's `context_limit`, set the existing
   `force_synthesis` path (`streaming.py:1470-1475`) so the loop finishes with a toolless
   final turn instead of climbing to the hop ceiling.
3. **Make the trigger actionable** — the read tools' eval-scope refusal should name the
   path that would resolve (`document_mcp.py:1134-1141` + `eval_scope.confine`), and WFE
   fixture staging should place the file where a confined read resolves it, so a model
   never has to walk `/workspace` to find its task file.
4. **Do not** "fix" this by shrinking `num_ctx` — truncation masks the balloon and degrades
   every seat sharing the tag.

**Seat recommendation.** The LFM2.5 unseating decision (arm HALTED 0/4, campaign f) was
made on rows dominated by this platform defect: its two PDF rows burned 117 s of prefill
each on walks the incumbent also ran. Re-screen LFM2.5 after fix 1/2; its always-think
leak (renderers.yaml note) remains the separate consideration it already was.

**Relation to parallel lane work.** Commit `32f2cd214` (lane
`fix(pipeline): carry bounded tool results across turns`,
`coding_task/proposals/TOOL_RESULT_CARRY.md`) is complementary, not a substitute: it caps a
collapsible tool-receipt record (2,048 chars, `PORTAL_TOOL_RESULT_CARRY`-gated) appended to
the *returned assistant content* so the next turn's client-sent history carries receipts.
It does not bound the `role:tool` messages the loop accumulates *within* one request — the
mechanism quantified above — so fixes 1 and 2 remain necessary; the two changes touch the
same files (`tools.py`, `streaming.py`, `non_streaming.py`) and should be reconciled by
whoever merges second.

## The single live probe that would settle the residual

The only thing disk evidence cannot show is the exact per-hop request digest for the
largest turns (the trace bodies were pruned; per-hop message counts/bytes per role are not
in the harness dumps). One traced re-run settles it:

Set on the pipeline `PORTAL_TRACE_BODIES=1 PORTAL_TRACE_MAX_BYTES=262144
PORTAL_TRACE_MAX=50`, then run ONE request — workspace `auto-daily::fast`, model
`hf.co/unsloth/LFM2.5-24B-A2B-GGUF:UD-Q4_K_XL-ctx96k`, messages = system + user "Read
final_invoice.pdf and report the labor line" — and `GET /v1/trace/<X-Correlation-ID>`. The
per-hop `backend_request` digests give `n_messages`, per-message `chars`/`sha256`/`head`,
`prefix_sha256` and per-hop usage: expect each hop to grow by the previous hop's escaped
tool result, with the walks visible as ~50 k-char `role:tool` entries. (Live stack — the
orchestrator runs it; this lane made no live calls.)
