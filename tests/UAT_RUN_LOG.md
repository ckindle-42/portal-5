# UAT Run Log — 20260610T1921Z

| Phase | Status | Started | Completed | Tests | P/W/F (cum) | Notes |
|---|---|---|---|---|---|---|
| 0 — Preflight | DONE | 2026-06-10 19:21 | 2026-06-10 19:44 | — | — | All health checks green; freshness warning false positive |
| 1 — Smoke | DONE | 2026-06-10 19:44 | 2026-06-10 19:57 | 4 | 4P/0W/0F | Clean |
| 2 — Large-GGUF | DONE | 2026-06-10 19:57 | 2026-06-11 00:30 | 37 | 38P/1W/3F (cum) | Interrupted mid-run to fix drain logic; resumed; P-N19 /nothink issue; P-DA05 37min deepseek latency |
| 3 — Bulk coding | DONE | 2026-06-11 00:34 | 2026-06-11 01:09 | 30 | 64P/1W/6F (cum) | 3 behavioral misses |
| 4 — Mid/small | DONE | 2026-06-11 01:12 | 2026-06-11 02:30 | 36 | 93P/2W/12F (cum) | WS-DD-03 Gemma4 timeout; T-11/T-12 assertion issues |
| 5 — Blueteam/docs | DONE | 2026-06-11 02:33 | 2026-06-11 03:20 | 12 | 101P/2W/13F (cum) | T-05 likely false positive |
| 6 — Media | DONE | 2026-06-11 03:22 | 2026-06-11 05:15 | 5 | 102P/2W/15F (cum) | T-09 TTS pass on retry; T-08/WS-11 skipped (no ComfyUI) |
| 7 — Advanced | DONE | 2026-06-11 05:17 | 2026-06-11 06:10 | 12 | 112P/2W/15F (cum) | A-08 memory PASS; A-05/A-06 BLOCKED (no bot tokens); A-07 MANUAL |
| 8 — Challenge | DONE | 2026-06-11 06:15 | 2026-06-11 08:31 | 28/39 | 140P/7W/17F (cum) | 11 skipped (models not installed); phi4-reasoning 3431s (stop_seen gap bug); matrix: CC01_CHALLENGE_MATRIX_20260611T083155Z.md |
