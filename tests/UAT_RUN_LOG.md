# UAT Run Log — 20260515T2057Z

| Phase | Status | Started | Completed | Tests | P/W/F | Notes |
|---|---|---|---|---|---|---|
| 1. smoke (auto) | DONE | 20260515T2057Z | 21:18Z | 4 | 4P/0W/0F | exit=0 |
| 1. gate | PASS | 21:22Z | 21:22Z | — | — | wired=0.0GB inactive=0.0GB after 200s |
| 1. gate | PASS | 21:27Z | 21:27Z | — | — | wired=0.0GB inactive=0.0GB after 200s |
| 1. gate | PASS | 22:06Z | 22:06Z | — | — | wired=2.6GB inactive=14.8GB after 70s |
| 2. gate | PASS | 02:33Z | 02:33Z | — | — | wired=2.5GB inactive=19.7GB after 70s |
| 2. mlx_large heavy | DONE | 21:37Z | 02:37Z | 35 | 36P/2W/0F (cum) | exit=0; 4 OOM crashes auto-recovered by CrashWatcher; WS-16 rerun in flight (unicode dash fix); P-N09 reclassified WARN (prompt framing) |
| 2. WS-16 rerun | PASS | 02:37Z | 03:12Z | 1 | WS-16 5/5 PASS — unicode dash normalization fix confirmed |
| 3. gate | PASS | 04:59Z | 04:59Z | — | — | wired=0.0GB inactive=0.0GB after 90s |
| 3. auto-coding | DONE | 05:00Z | 05:28Z | 30 | 49P/6W/14F (cum) | 14F all Laguna-XS.2-4bit structured code gen failures (no code blocks, wrong format) — product limitation; P-D16 session corruption from earlier crash caused 42min stuck-session; driver stuck twice in pre-warm loop (pipeline falls back to Ollama when proxy has consecutive_failures); fixed: direct proxy kick fallback in _wait_for_mlx_ready |
| 3. post-gate | PASS | 05:28Z | 05:30Z | — | — | wired=2.0GB inactive=22.5GB → proxy restarted → wired=0.0GB inactive=0.0GB; safe to proceed |
