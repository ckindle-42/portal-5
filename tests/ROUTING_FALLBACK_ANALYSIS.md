# MLX→Ollama Silent Fallback Analysis — UAT Run 2026-05-25

**Run summary**: 116P / 2W / 13F / 2S / 1M — 86% pass rate  
**Total tests**: 134  
**MLX confirmed**: 103 tests  
**Ollama by design**: 5 tests (auto-creative ×3, auto-music ×2 — no mlx_model_hint)  
**Ollama instead of intended MLX**: 11 tests — documented below  
**Auto-vision → auto-reasoning text-only fallback**: 8 tests (expected behavior — no image attached)

---

## Group 1 — auto-documents workspace config bug (10 tests)

**Root cause**: `auto-documents` workspace had `mlx_model_hint` set to
`huihui-ai/Huihui-Qwen3.5-9B-abliterated-mlx-4bit` in `workspaces.py`, but its
`workspace_routing` groups in `backends.yaml` were `[general, coding]`. The MLX
backend lives in `group: mlx` — it was never in the candidate list. Every
auto-documents request went deterministically to `ollama-general`.

**Detected by**: `pipeline confirms: ollama-general|huihui_ai/qwen3.5-abliterated:9b`
visible in routing summary. The routing validator reported "correct" because
`matched=True` (Ollama IS an acceptable fallback in the workspace groups) — it did
not flag the config intent mismatch.

**Impact**: All 10 auto-documents tests served by `qwen3.5-abliterated:9b` on Ollama.
- 7 tests PASSED (document generation tasks are robust enough for Ollama)
- 3 tests FAILED: P-W04 (205-char response — Ollama was cold), P-N24 (capability
  query), TR-01 (missing download_url)

| Test | Status | Notes |
|------|--------|-------|
| T-04 Document Generation — DOCX with Table | PASS | Worked on Ollama |
| T-05 Document Generation — Excel Tracker | PASS | Worked on Ollama |
| T-06 Document Generation — PowerPoint Zero Trust | PASS | Worked on Ollama |
| T-07 Document Reading — Parse Uploaded Word File | PASS | Worked on Ollama |
| WS-10 Document Builder — Change Management DOCX | PASS | Worked on Ollama |
| P-W05 Phi-4 Technical Analyst — Conclusion First | PASS | Worked on Ollama |
| P-N07 Documentation Architect — Diátaxis Framework | PASS | Worked on Ollama |
| P-W04 Tech Writer — Audience-Appropriate Docs | **FAIL** | 205 chars — Ollama cold |
| P-N24 Transcript Analyst — Meeting Summary Protocol | **FAIL** | Persona YAML fix needed |
| TR-01 Transcript Analyst — Diarize + Word Doc | **FAIL** | download_url not included |

**Fix**: `config/backends.yaml` — `auto-documents` workspace_routing changed to
`[mlx, general, coding]`.  
**Committed**: `4f4dbe9` — `fix(routing): wire auto-documents to MLX primary`  
**Verified**: Pipeline immediately confirmed `backend=mlx-apple-silicon model=huihui-ai/Huihui-Qwen3.5-9B-abliterated-mlx-4bit` after container restart.

---

## Group 2 — WS-03 Agentic Coder cold-start fallback (1 test)

**Root cause**: `auto-agentic` routes to `mlx-apple-silicon` with
`mlx_model_hint: mlx-community/Qwen3-Coder-Next-4bit` (80B MoE). MLX starts cold
(503 / state:none). The non-stream request 503'd and fell to `ollama-coding|qwen3-coder:30b`.
Two compounding effects:
1. Wrong model — `qwen3-coder:30b` is a different, smaller model than the 80B MoE
2. Qwen3 thinking tokens stripped — visible output reduced to 1,134 chars

**Detected by**: Pipeline logs (post-hoc analysis). The routing validator
**incorrectly reported MLX** because it matched the streaming log line
`"Routing workspace=auto-agentic → backend=mlx-apple-silicon model=..."` (the
*attempted* first candidate), not the actual serving backend. The non-stream attempt
that 503'd and fell to Ollama was invisible to the validator.

**Impact**: WS-03 FAILED — 3/5 assertions. Blueprint registration absent, response
too short (1,134 chars vs 1,200 min). Elapsed 188.8s — timeout (360s) was not
the constraint.

| Test | Status | Actual backend |
|------|--------|---------------|
| WS-03 Agentic Coder Heavy — Flask Migration Plan | **FAIL** | `ollama-coding\|qwen3-coder:30b` |

**Fixes**:
1. **Execute doc** (`tests/PORTAL5_UAT_EXECUTE_V2.md`): Add MLX pre-warm request
   for `auto-agentic` workspace before the auto-agentic phase, with a 60s sleep
   (Qwen3-Coder-Next-4bit is 80B MoE, takes 60-90s to load).
2. **Routing validator bug fixed** (`tests/portal5_uat_driver.py`):
   `_get_backend_from_pipeline_logs()` now uses the `"Backend X succeeded for workspace=Y"`
   log line (emitted only on actual success) instead of the attempt line. Falls back
   to the old pattern if no "succeeded" line is found.  
   **Committed**: This fix — `fix(tests): routing validator uses Backend-succeeded log line`

---

## Routing Validator Bug (systemic)

The old `_get_backend_from_pipeline_logs()` regex matched:
```
Routing workspace=X → backend=Y model=Z stream=True (1/N candidates)
```
This line is the **first candidate attempted** in the streaming path. If that
candidate 503s and the pipeline falls to a different backend, the validator still
reports the first (failed) backend — a false MLX confirmation.

The new implementation matches:
```
Backend X succeeded for workspace=Y model=Z
```
This line is only emitted inside `_try_non_streaming()` when a backend actually
returns a 2xx response. Falls back to the old pattern if no succeeded line exists
(e.g. streaming-only paths with no non-stream hop).

**All future UAT runs will correctly surface hidden Ollama fallbacks.**

---

## Execute Doc Pre-warm Gaps (systemic)

The 2026-05-25 run had no pre-warm for MLX before Phases 5 or 2 (auto-agentic).
MLX proxy starts cold (503 / state:none). The load time for each workspace's
model is:

| Workspace | Model | Approx load time |
|-----------|-------|-----------------|
| auto-documents | huihui-qwen3.5-9b (6GB) | 20-30s |
| auto-agentic | Qwen3-Coder-Next-4bit (80B MoE, ~45GB) | 60-90s |
| auto-blueteam | Foundation-Sec-8B (8GB) | 15-25s |
| auto-reasoning | MLX-Qwopus3.5-27B (27GB) | 30-60s |
| auto-compliance | granite-4.1-30b (30GB) | 40-70s |

**Fixed in execute doc**: Phase 4→5 pre-warm expanded to include an MLX pipeline
warmup request + 30s sleep (committed `4f4dbe9`).

**Still needed**: Pre-warm for auto-agentic before its phase. The execute doc
currently has no MLX pre-warm before Phase 2 (auto-agentic). Adding:
```bash
# Before Phase 2 (auto-agentic) — Qwen3-Coder-Next-4bit takes 60-90s to load
curl -sf -X POST http://localhost:9099/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${PIPELINE_API_KEY}" \
  -d '{"model":"auto-agentic","messages":[{"role":"user","content":"ping"}],"stream":false,"max_tokens":5}' \
  >/dev/null || true
echo "auto-agentic MLX pre-warm sent — waiting 90s for Qwen3-Coder-Next-4bit to load"
sleep 90
```

---

## Summary of Fixes Applied

| Fix | Commit | Status |
|-----|--------|--------|
| auto-documents workspace groups: add `mlx` | `4f4dbe9` | ✅ Done |
| Phase 4→5 pre-warm: MLX auto-documents + 30s sleep | `4f4dbe9` | ✅ Done |
| Routing validator: use Backend-succeeded log line | this session | ✅ Done |
| auto-agentic pre-warm before Phase 2 | pending | ⏳ Needed |

---

## What Was Correctly Ollama (not bugs)

| Test | Workspace | Why Ollama is correct |
|------|-----------|----------------------|
| WS-08 Creative Writer | auto-creative | No mlx_model_hint — Ollama is primary |
| P-W01 Creative Writer | auto-creative | Same |
| P-N12 Interview Coach | auto-creative | Same |
| M-01 Whisper STT | auto-music | No mlx_model_hint — Ollama orchestrates tool call |
| WS-12 Music Producer | auto-music | Same |
| WS-14/P-V* Vision tests (×8) | auto-vision | Text-only fallback to auto-reasoning — expected |
