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
| 4. daily/data/reasoning/creative/mistral/spl/math | DONE | 20260515T2200Z | 09:50Z | 28/34 | 73P/8W/14F cum; 2B | 6 WS-DD skipped (gemma-4-26b-a4b-it-4bit OOM after heretic switch — consecutive model pressure); P-N19 RECLASSIFIED WARN (memory pressure → empty response; feature confirmed via direct test); mlx_large eviction guard prevented further OOM |
| 4. gate | PASS | 09:50Z | 09:50Z | — | — | wired=2.0GB inactive=10.9GB after 0s |
| 5. auto-blueteam + auto-docs | DONE | 09:51Z | 10:11Z | 11 | 84P/8W/14F cum | 11/11 PASS — perfect phase; phi-4 docs + lily-cybersecurity blueteam all clean |
| 5. gate | PASS | 10:14Z | 10:14Z | — | — | proxy restart (inactive=22.5GB cleared); wired=0.0GB inactive=0.0GB after 130s |
| 6. auto-music + auto-video | DONE | 10:15Z | 11:36Z | 5 | 89P/8W/14F cum | 5/5 PASS — perfect phase; T-09 TTS slow (57min, model load); WS-12 music + WS-11 video all clean |
| 6. gate | PASS | 11:39Z | 11:39Z | — | — | wired=2.2GB inactive=11.3GB after 70s; ComfyUI stopped |
| 7. benchmark | DONE | 11:41Z | 14:04Z | 18 | 103P/10W/16F cum | 14P/2W/2F phase; FAIL: OLMo3-32b(5/10) + OmniCoder2(all 3 attempts hit 994s poll cap); WARN: phi4-reasoning(5/10) + GLM(6/10); all MLX/Ollama infra clean |
| 7. gate | PASS | 14:04Z | 14:07Z | — | — | wired=0.0GB inactive=0.0GB after 160s; proxy restart (inactive=21.8GB cleared) |
| 8. advanced | IN PROGRESS | 14:09Z | — | 12 | — | advanced personas + edge cases |
| 8. gate | PASS | 14:27Z | 14:27Z | — | — | wired=2.5GB inactive=15.9GB after 70s |
| 8. gate | PASS | 15:45Z | 15:45Z | — | — | wired=1.9GB inactive=11.7GB after 70s |
| 8. gate | PASS | 16:45Z | 16:45Z | — | — | wired=1.8GB inactive=12.5GB after 70s |
| 1. gate | PASS | 19:39Z | 19:39Z | — | — | wired=0.0GB inactive=0.0GB after 70s |
| 2. gate | PASS | 21:58Z | 21:58Z | — | — | wired=2.8GB inactive=17.2GB after 70s |
| 3. gate | PASS | 23:49Z | 23:49Z | — | — | wired=0.0GB inactive=0.0GB after 200s |
| 4. gate | PASS | 01:34Z | 01:34Z | — | — | wired=2.8GB inactive=4.9GB after 140s |
| 5. gate | PASS | 02:08Z | 02:08Z | — | — | wired=0.0GB inactive=0.0GB after 200s |
| 6. gate | PASS | 02:21Z | 02:21Z | — | — | wired=3.4GB inactive=6.9GB after 70s |
| 7. gate | PASS | 03:23Z | 03:23Z | — | — | wired=0.0GB inactive=0.0GB after 320s |
| 8. gate | PASS | 04:21Z | 04:21Z | — | — | wired=0.0GB inactive=0.0GB after 200s |
