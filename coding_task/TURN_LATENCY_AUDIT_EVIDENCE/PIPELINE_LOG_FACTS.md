# Preserved pipeline.log facts (window 14:02–14:42Z = 08:02–08:42 CST, captured 08:45 CST before the
# portal5-pipeline restart at 15:12:54Z wiped docker logs). Source: docker logs --timestamps portal5-pipeline.

Startup: 13:57:21Z "Starting Portal Pipeline on :9099 with 4 worker(s)"
BackendRegistry loaded: 12 backends, 50 workspace routes, request_timeout=300s, hot_seat_protect_s=900, preferred_residents=0

## load_guard cold-load admits (UTC, engine, model, need_gib, headroom_gib, waited_s) — 57 total; key rows:
13:58:41 ollama Nemotron-3.5-Lightning-30B Q4_K_M-ctx32k need=23.8 headroom=31.3 waited=0.2   (pre-run)
13:59:19 omlx Qwen3.8-27B-oQ4e-mtp need=16.6 headroom=26.1 waited=2.5                          (pre-run)
14:02:37 ollama gemma-4-E4B-OBLITERATED ctx2k need=5.0 headroom=16.2 waited=0.0
14:03:08 ollama gemma-4-E4B ctx2k need=5.0 headroom=35.4 waited=0.1
14:03:10 omlx Qwen3.8-27B need=16.6 headroom=26.1 waited=1.1        <- kubernetes-rbac turn 1
14:08:48 ollama Nemotron ctx32k (after eviction pass)               <- tls-firewall turn 1
14:09:14 / 14:10:25 / 14:11:16 / 14:13:02 / 14:14:55 / 14:16:09 / 14:26:06 / 14:31:22 / 14:34:35 / 14:38:41 / 14:39:32  gemma-E4B ctx2k (classifier) — 13 admits in-run
14:11:18 ollama Nemotron; 14:16:41 Nemotron; 14:23:21 Nemotron; 14:25:12 Nemotron; 14:39:35 Nemotron — 6 in-run
14:09:46 glm-4.7-flash ctx24k; 14:27:27 glm again
14:13:03 omlx Qwen3.8; 14:14:56 Qwen3.8; 14:18:33 Qwen3.8; 14:21:55 Qwen3.8; 14:23:56 Qwen3.8; 14:28:58 Qwen3.8 — 7 loads in-run
14:18:53 omlx Qwen3-Coder-30B-A3B; 14:21:01 Qwen3-Coder (2nd)
14:16:11 / 14:25:39 / 14:26:10 omlx gemma-4-26b-a4b-it-QAT-4bit (3 loads)
14:23:07 omlx mlx-community--gemma-4-26b-a4b-it-4bit; 14:24:16 unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit
14:26:45 Inkling-2-Mini-abliterated; 14:28:33 Inkling-2-Mini
14:17:51 gemma4:12b-it-qat-ctx16k; 14:18:12+14:18:27+14:30:57+14:31:23+14:31:27 granite4.1:8b-ctx16k; 14:18:20+14:34:36 lfm2.5:8b; 14:24:45 inkling-2-mini:ctx256k; 14:27:04 K2-Horizon-MoVA; 14:27:58 Nex-N2-mini; 14:29:50 qwen3-vl:32b; 14:38:43 gemma4:12b; 14:39:57 gemma4:e4b-it-qat-ctx8k

## Headroom wait (Nemotron, tls-firewall turn 1): 14:08:22 → 14:08:47
"load_guard: Nemotron...ctx32k needs 23.8 GiB, 17.3-19.0 available; waiting for engine activity" ×43 lines (25.5 s),
while Qwen3.8 turn 2 (kubernetes-rbac, timed-out row) was still streaming (completed 14:08:46.9Z).

## Evictions logged by load_guard (whole container life 13:57–14:41Z):
13:59:18 evicted VulnLLM-R-7B-4bit on omlx, 4.2 GiB (idle LRU)            [pre-run]
13:59:18 evicted Nemotron ctx32k on ollama, 22.7 GiB (idle LRU)            [pre-run]
14:08:47 evicted Qwen3.8-27B-oQ4e-mtp on omlx, 16.6 GiB (idle LRU) ×3 workers (one eviction)
14:08:47 eviction pass for Nemotron: shortage_gib=5.5 evicted=omlx:Qwen3.8-27B-oQ4e-mtp ×3
14:31:27 evicted granite4.1:8b-ctx16k on ollama, 6.0 GiB (idle LRU)
14:31:27 eviction pass for job reclaim: shortage_gib=0.0 evicted=ollama:granite4.1:8b-ctx16k
   -> POST /admin/reclaim-idle from 192.168.65.1 at 14:31:27.647Z (200 OK); granite had served the
      image-quality scenario turn ending 14:31:27.34Z and was re-admitted 14:31:27.69Z (need 6.3 GiB, headroom 23.6).

## Classifier (task-router, non-stream, gemma-E4B ctx2k on Ollama):
74 calls in container life; median 1.6 s (Non-stream routing → Backend succeeded); 59 in run window,
159.9 s total wall; 33,850 prompt tok (37.6 s prefill), 3,548 gen tok (100.2 s decode).

## Tool exposure (workspace persona N tools) — full in-run list:
07:58:41 auto-daily auto 16 | 07:59:10 auto-daily auto 16 | 07:59:16 auto-coding auto-coding 3
08:00:23 auto-coding auto 63 | 08:03:09 auto-coding auto 63 | 08:07:09 auto-coding auto 63
08:08:22 auto-daily auto 16 | 08:09:20 auto-daily auto 16 | 08:11:18 auto-daily auto-daily 16
08:11:58 auto-daily auto-daily 16 | 08:12:32 auto-daily auto-daily 16 | 08:13:02 auto-coding auto-coding 64
08:13:37 auto-coding auto-coding 64 | 08:14:55 auto-coding auto-coding 3 | 08:15:35 auto-coding auto-coding 3
08:16:09 auto-documents auto-documents 3 | 08:16:41 auto-daily auto 16 | 08:17:29 auto-daily auto 16
08:17:51 auto-audio 2 | 08:18:12 auto-audio::image 4 | 08:18:20 auto-audio::music 8 | 08:18:27 auto-audio::video 3
08:18:33 auto-coding 63 | 08:18:53 auto-coding::bigfix 3 | 08:21:01 auto-coding::cad 22
08:21:55 auto-compliance 46 | 08:23:07 auto-compliance::reading 19 | 08:23:21 auto-daily 16
08:23:56 auto-daily::deep 13 | 08:24:16 auto-daily::fast 71 | 08:24:45 auto-daily::inkling 16
08:25:12 auto-daily::nemotron 8 | 08:25:39 auto-documents 10 | 08:26:06/31 auto-documents 1→10
08:26:45 auto-general-uncensored 6 | 08:27:58 auto-research 15 | 08:28:33 auto-security 19
08:28:58 auto-spl 32 | 08:29:50 auto-vision 5 | 08:30:57 security-reviewer 13
08:31:22–08:38:41 media workspaces 1 tool each | 08:39:35+ auto-daily 1 | 08:41:05 security-reviewer 1
Also: "Tool-merge: dropped 39 OWUI portal_* mirror schema(s)" ×5.

## Routing counts in container life:
task-router (classifier) 74 non-stream; auto-daily→Nemotron stream ×12; auto-coding→Qwen3.8 stream ×8.
132 POST /v1/chat/completions 200 OK (uvicorn access).
