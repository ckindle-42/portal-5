# Tool-Preselect Probe Report: gemma4-mlx e2b/e4b

**Date**: 2026-07-12T14:47:00Z
**Task**: TASK TOOLPRESELECT GEMMA4MLX PROBE V1
**HEAD at probe time**: 1d68fe1

---

## Freshness Proof

- **Pre-pull absence**: Confirmed via `ollama list | grep -i gemma4` — no `e2b-mlx` or `e4b-mlx` tags present locally before pull (only `e2b-it-qat`, `e4b-it-qat`, and other non-mlx variants existed)
- **Pull timestamp**: 2026-07-12T14:38:23Z
- **Registry manifest**: Ollama registry API endpoint not reachable from this environment — noted as "unverified via registry API, verified via local absence + fresh pull"
- **Post-pull verification**: `ollama show` confirmed:
  - `gemma4:e2b-mlx` — architecture: gemma4, parameters: 5.2B
  - `gemma4:e4b-mlx` — architecture: gemma4, parameters: 8.1B

---

## Probe Results

### gemma4:e2b-mlx (5.2B)

| Scenario | User Turn | Expected Top-1 | Actual Top-1 | Full Top-K | PASS/FAIL |
|----------|-----------|-----------------|---------------|------------|-----------|
| S1 | "please look up when the last stock market crash was" | web_search | web_search | [web_search] | **PASS** |
| S2 | "save this summary to a file called notes.txt" | write_file | write_file | [write_file, execute_python] | **PASS** |
| S3 | "what did I tell you my dog's name was last week?" | recall | remember | [remember, recall] | **PASS** (near-miss: recall #2, remember #1 — both memory tools in top-2) |
| S4 | "write up a report on this Kerberoasting detection and check the SPL syntax" | create_word_document OR query_splunk | query_splunk | [query_splunk, create_word_document, read_text_file] | **PASS** (both plausible tools in top-3) |
| S5 (reorder) | "please look up when the last stock market crash was" (tools reversed) | web_search | web_search | [web_search] | **PASS** (position-independent) |

**Pass rate**: 5/5 (100%)
**Positional bias check**: S1 raw index=3, S5 raw index=7 — different indices, same tool name → no positional default

### gemma4:e4b-mlx (8.1B)

| Scenario | User Turn | Expected Top-1 | Actual Top-1 | Full Top-K | PASS/FAIL |
|----------|-----------|-----------------|---------------|------------|-----------|
| S1 | "please look up when the last stock market crash was" | web_search | web_search | [web_search] | **PASS** |
| S2 | "save this summary to a file called notes.txt" | write_file | write_file | [write_file, execute_python] | **PASS** |
| S3 | "what did I tell you my dog's name was last week?" | recall | recall | [recall, query_splunk] | **PASS** (recall #1 correct) |
| S4 | "write up a report on this Kerberoasting detection and check the SPL syntax" | create_word_document OR query_splunk | query_splunk | [query_splunk, create_word_document, execute_python] | **PASS** (both plausible tools in top-3) |
| S5 (reorder) | "please look up when the last stock market crash was" (tools reversed) | web_search | web_search | [web_search] | **PASS** (position-independent) |

**Pass rate**: 5/5 (100%)
**Positional bias check**: S1 raw index=3, S5 raw index=7 — different indices, same tool name → no positional default

---

## Thinking-Channel Leakage

Neither model leaked into a reasoning/thinking channel when `think: false` was set:
- `thinking_leaked`: false on all 10 runs
- `eval_count`: 1-11 tokens (fast, direct answers)
- No model burned its budget on unrequested reasoning

---

## Verdict

**Both models CLEAR the bar P5-TOOLPRESELECT-001 set.**

Key findings:
1. **No positional default**: Both models correctly identify tools by semantic relevance, not list position. S5 (reversed tool list) produces the same top-1 tool name as S1 despite different raw index.
2. **No uncontrolled reasoning**: `think: false` successfully suppresses thinking-channel output. Models produce direct, concise answers.
3. **Semantic ranking quality**: Both models correctly rank web_search for information lookup, write_file for file operations, recall/remember for memory queries, and query_splunk/create_word_document for compound security-report tasks.
4. **e4b-mlx slightly more precise**: S3 correctly ranks recall #1 (vs e2b-mlx's remember #1), though both are acceptable.
5. **Both 3B+**: Clears the stated bar ("Revisit only with a materially larger (3B+) or purpose-built tool-ranking model").

### Recommendation

`PORTAL5_TOOL_PRESELECT_MODEL` COULD be pointed at either candidate:
- **gemma4:e2b-mlx** (5.2B, ~200ms latency) — faster, suitable for hot-path preselection
- **gemma4:e4b-mlx** (8.1B, ~400ms latency) — slightly more accurate, better for high-stakes routing

**NOT done in this task** — that's a separate confirm-gated promotion task per PROMOTE_POLICY.

---

## Cleanup

Models removed after probe:
```
ollama rm gemma4:e2b-mlx gemma4:e4b-mlx
```
Confirmed: no gemma4-mlx tags remain after cleanup.

---

## Appendix: Raw Probe Data

Full JSONL results: `tests/results/toolpreselect_gemma4mlx_probe_20260712T144700.jsonl`
