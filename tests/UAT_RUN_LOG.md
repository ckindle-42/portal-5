# UAT Run Log — 20260618T1256Z
| Phase | Status | Started | Completed | Tests | P/W/F (cum) | Notes |
| 1 — Smoke (auto) | DONE | 2026-06-18 12:56 | 2026-06-18 08:07 | 4 | 4P/0W/0F | All pass |
| 2 — Large-GGUF (40) | DONE | 2026-06-18 08:07 | 2026-06-18 11:51 | 40 | 35P/0W/5F | rerun: WS-14✅ P-V01✅ P-DA05✅ P-N05✗(3a-granite-slow) P-N19✗(3a-qwen3-slow) — Gate ✅ |
| 3 — Coding (37) | DONE | 2026-06-18 12:01 | 2026-06-18 12:32 | 37 | 35P/0W/2F | P-D05✗(3c) P-N23✗(3c) — eviction fix active, 37/37 routing correct — Gate ✅ |
| 4 — Mid/small (57) | DONE | 2026-06-18 12:32 | 2026-06-18 13:49 | 57 | 52P/2W/3F | WS-BF-02✗(3c) P-S09✗(3c) TV-02✗(3c) WS-DD-03⚠ WS-DD-07⚠ — 56/56 routing correct — Gate ✅ |
| 5 — Blueteam+docs (17) | DONE | 2026-06-18 13:49 | 2026-06-18 14:39 | 17 | 14P/2W/0F | T-06⚠ T-07⚠ WS-PP-D01 PASS 7/7 (672s) — 16/16 routing correct — Gate ✅ |
| 6 — Media (5) | DONE | 2026-06-18 14:39 | 2026-06-18 15:00 | 5 | 1P/0W/2F/2S | M-01✗(3c-STT) WS-12✗(3c-music) T-09✓(371s) 2 video SKIPs(no ComfyUI) — Gate ✅ |
| 7 — Advanced (12) | DONE | 2026-06-18 15:00 | 2026-06-18 15:19 | 12 | 9P/0W/0F/2S | PERFECT — 0 FAILs — A-05/A-06 SKIP(no bot token) — 8/8 routing correct |
|---|---|---|---|---|---|---|
