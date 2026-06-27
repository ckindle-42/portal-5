# UAT Run Log — 20260627T0112Z
| Phase | Status | Started | Completed | Tests | P/W/F (cum) | Notes |
|---|---|---|---|---|---|---|
| 1 — Smoke (6) | DONE | 2026-06-27 01:12 | 2026-06-26 20:46 | 6 | 5P/0W/1F | routing.py PersonaSpec crash after test 3 (fixed); WS-33 3c(LFM2.5 prompt misread, 2x confirmed) — Gate ✅ |
| 2 — Large-GGUF (43) | DONE | 2026-06-27 20:47 | 2026-06-28 02:00 | 43 | 37P/0W/12F (cum) | WS-04/P-R06/P-R05 3f(tongyi-deepresearch wrong workspace ×3); P-DA05 3f(phi4-reasoning:plus 67min 3×cap); TV-04/WS-08/WS-13/P-D17/P-V01/P-S06/P-R07 3c; routing 43/43 ✅ — Gate ✅ |
| 3 — Bulk coding (42) | DONE | 2026-06-28 02:00 | 2026-06-28 03:10 | 42 | 67P/1W/23F (cum) | T-01/T-02/T-03 3c(sandbox MCP ×3); P-D02/P-D03/P-D04/P-D22 3c(qwen3-coder review cluster); P-D15/P-DA06 3c(Excel formula); P-D12/P-D13 3c(interpreter); WS-25 GLM PASS@1068s; routing 42/42 ✅ — Gate ✅ |
| 4 — Mid/small lanes (62) | DONE | 2026-06-28 03:10 | 2026-06-28 07:28 | 62 | 117P/2W/34F (cum) | sandbox MCP ×4 3c; WS-DD-09/WS-DD-14/WS-09/P-S08/WS-28/P-C02 3c; WS-PHI4-02 3f(phi4-reasoning:plus 901s); TV-02 ⚠3f(baronllm 900s); routing 62/62 ✅ — Gate ✅ |
| 5 — Blueteam+docs (27) | DONE | 2026-06-28 07:28 | 2026-06-28 10:08 | 27 | 137P/3W/40F (cum) | sandbox MCP 3c ×3(PE01/PE02/PE03 — execute_bash, first UAT run post-refactor); PT02 3f 1293s; TR-01 3c(diarize 3/5=60%); WS-CAD-03 3c; routing 27/27 ✅ — Gate ✅ |
| 6 — Media-heavy (5) | DONE | 2026-06-28 10:09 | 2026-06-28 10:16 | 5 | 139P/3W/41F (cum) | T-08/WS-11 SKIP(ComfyUI not ready); M-01 3c(Whisper 3/4=75%); T-09/WS-12 ✓; routing 3/3 ✅ — Gate ✅ |
| 7 — Advanced (12) | DONE | 2026-06-28 10:17 | 2026-06-28 10:42 | 12 | 147P/3W/42F (cum) | A-08 3c(cross-session memory 2/6=33%); A-05/A-06 SKIP(no bot tokens); A-07 MANUAL(Grafana); routing 8/8 ✅ |

## Targeted Re-run — 2026-06-27

| Phase | Status | Tests | P/F/K | Notes |
|---|---|---|---|---|
| Re-run (11 targeted) | DONE | 11 | 2P/8F/1K | T-01 ✅(fix); A-08 ✅(fix); T-02/TV-01/04/05/06/DD-TV-01 ✗(tool_choice:auto); WS-PE01/02 ✗(supergemma4 hallucinates); WS-PE03 KILLED@1353s (same pattern) |

**Fix applied:** `lifespan.py` injects `registry` into `validation` module — tools now correctly dispatched. Verified: A-08 6/6=100%, T-01 3/3=100%.

**Open defect class:** `tool_choice:auto` — 9 tests require actual tool dispatch but models compute/hallucinate answers instead. Needs `tool_choice:required` in catalog entries + pipeline handler support before these can pass.

**Timeout tuning:** WS-04/P-R05/P-R06 → 1200s; P-DA05/WS-PT02 → 1500s; WS-PE02/PE03 → 900s cap.
