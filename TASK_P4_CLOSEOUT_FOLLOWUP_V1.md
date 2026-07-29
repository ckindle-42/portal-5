# TASK: P4 Closeout Follow-Up — Video Test, Streaming Fix Verification, Pull-Wan22 Gap

**Task ID:** TASK-P4-FOLLOWUP-001
**Priority:** Normal
**Category:** Verification / Bug fix follow-through
**Protected files touched:** `portal/platform/inference/router/streaming.py` (already edited, needs `smoke_stream.sh` gate)
**Estimated risk:** Low — fixes are already applied and syntax-verified; this task is about running the verification gates that were deliberately deferred, not writing new code.

---

## Context

During the 2026-07-28 P4 closeout session (Ollama 0.32.5 migration, 50-model disk
cleanup ~709GB reclaimed, 3 candidate models pulled/benched), two known bugs were
diagnosed and fixed in code but **deliberately not verified live**, per explicit
instruction to move on to remaining closeout steps rather than spend the session
re-running things. This file is the checklist for closing both out next session.

See memory (`project_granite_empty_completion_open.md`,
`project_comfyui_unetloader_empty_open.md`) for full diagnosis detail — this file
is the actionable to-do, those are the record of *why*.

---

## Item 1 — Verify the empty-completion SSE fix (streaming.py)

**What was fixed:** `portal/platform/inference/router/streaming.py`, two call sites
(`_stream_with_tool_loop_impl` ~line 549, `_stream_from_backend_guarded` ~line 958).
The zero-content safety net previously yielded a bare `{"error": "..."}` JSON object,
which is not a valid OpenAI `chat.completion.chunk` shape — OWUI's SSE parser silently
dropped it, so the fix that was supposed to make empty completions visible to the user
never actually worked. Now both sites yield a proper chunk with
`choices[0].delta.content` carrying a visible "⚠️ Model returned an empty response —
please retry." message, `finish_reason: "stop"`, then `[DONE]`.

**Verified so far:** `python3 -m py_compile` and `ruff check` both pass. NOT verified
against a live stream — no request has actually hit either safety-net branch since the
edit.

**To do:**
- [ ] Run `./scripts/smoke_stream.sh` against the live stack — **mandatory per
      CLAUDE.md Rule/Testing-Rules before this can be committed**, this was skipped
      intentionally this session.
- [ ] If possible, force a real empty-completion trip (e.g. replay the exact P-W04
      prompt from `tests/uat_catalog/g_auto_docs.py` through the full pipeline —
      `techwriter` persona / `auto-documents` workspace / `granite4.1:8b-ctx16k`,
      not raw Ollama) and confirm the visible warning now appears in OWUI instead of
      a blank message. Note: isolated testing against raw Ollama (both `/api/chat`
      and `/v1/chat/completions`) did NOT reproduce the original empty-completion
      symptom — it may need real pipeline load/context to trigger, so this may need
      a few attempts or may simply not recur outside the original UAT conditions.
- [ ] Once verified, this change is ready to commit (not committed yet — pending
      this gate).

---

## Item 2 — Wan2.2 TI2V-5B video generation test

**What was fixed:**
1. Wan2.2 diffusion model, VAE, and text encoder files were downloaded to the wrong
   nested path (`~/ComfyUI/models/split_files/<type>/...`, mirroring the HF repo's
   internal structure) instead of ComfyUI's actually-scanned folders
   (`~/ComfyUI/models/diffusion_models/`, `models/vae/`, `models/text_encoders/`).
   Moved all three into the correct flat locations — confirmed live via
   `/object_info/UNETLoader` etc., ComfyUI already sees all three with no restart.
2. `portal/modules/media/tools/video_mcp.py`'s `WAN22_TI2V_MODEL`, `WAN22_TI2V_VAE`,
   `WAN22_CLIP_FP8` env var defaults still pointed at the old nested paths — updated
   to the flat filenames matching the corrected layout.

**Verified so far:** File registration confirmed live (all 3 files show up in the
relevant ComfyUI model-type listings). `video_mcp.py` syntax-checked clean. The
actual video generation call has **never been made** — this is still an untested
code path end to end.

**Result (2026-07-29): SUCCESS.** First end-to-end Wan2.2 TI2V-5B generation.

- [x] Restarted ComfyUI clean before the test (`launchctl kickstart -k`).
- [x] Re-verified `/object_info/UNETLoader`/`VAELoader`/`CLIPLoader` post-restart
      — all three Wan2.2 files present.
- [x] Generated a start-frame image via `mcp__portal-comfyui__generate_image`
      (FLUX, puppy-in-meadow). Hit two path-resolution snags getting it to
      `start_video_generation`: the host `/tmp` path isn't visible inside the
      `mcp-video` container, and the host `~/AI_Output/uploads/` path isn't
      either — the container only sees its own mount point. Fix: place the file
      under the shared workspace and pass the **container-side** path,
      `/workspace/uploads/<file>` (Rule 11) — not the host path in either form.
- [x] Ran `start_video_generation(model=wan22-ti2v-5b)` — but it initially
      failed ComfyUI validation with the exact old nested `split_files/<type>/`
      paths for all three TI2V-5B files, even though `video_mcp.py`'s source was
      already fixed. Root cause: `docker-compose.yml`'s `mcp-video` environment
      block hardcoded the old wrong paths as env var defaults, which override
      the (correctly fixed) Python-level `os.getenv(...)` defaults at container
      start — the earlier fix never actually took effect in the running
      container. Fixed at the source (commit 68e3e97d) and force-recreated the
      container; retried and the job started cleanly (ETA ~23 min).
- [x] Watched for the objc duplicate-class warning during the run — it fired
      (690 occurrences in the log, consistent with prior runs) but did **not**
      cause a crash or failure. No action needed at this time.
- [x] On success: downloaded and verified the output — valid H.264 MP4,
      1024×576, 8fps, 5.125s (41 frames as requested), `portal_ti2v__00001_.mp4`.
      Closes P4 task #10.

---

## Item 3 — `./launch.sh pull-wan22` has no implementation (separate, non-blocking)

Discovered while diagnosing Item 2: `pull-wan22` is documented in `launch.sh`'s
usage/help text (`scripts/gen-video.py` also references it in comments) but there is
**no actual case handler or download logic anywhere in `scripts/`**. Any future
fresh install that relies on this documented command will hit the exact same
wrong-directory bug as this session, by hand, with no automation to fix at the
source.

**Decision (2026-07-29): implemented for TI2V-5B + S2V-14B, deferred for
T2V-A14B/Animate-14B.** `_launch_pull_wan22` in `scripts/lib/services.sh`,
wired to `./launch.sh pull-wan22`. Also discovered and fixed a related dead
reference: `download-comfyui-models` called `scripts/download_comfyui_models.py`,
which was deleted in `ea864cf2` (2026-05-23) on the assumption pull-wan22/
pull-qwen-image would replace it — neither ever did until now. That handler
now exits with a clear pointer instead of a bare `ModuleNotFoundError`.
`pull-qwen-image` remains unimplemented (out of scope, not touched).

- [x] Implement `pull-wan22` using the verified flat download layout (`hf
      download Comfy-Org/Wan_2.2_ComfyUI_Repackaged
      split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors --local-dir
      ~/ComfyUI/models/diffusion_models/`, then flatten the resulting
      `split_files/<type>/` subdir). Covers TI2V-5B (already present) + VAE +
      shared fp8 text encoder + S2V-14B + its audio encoder.
- [x] S2V-14B (`WAN22_S2V_MODEL`) fixed to the same flat pattern in both
      `video_mcp.py` and `docker-compose.yml` — it had the identical nested-path
      bug as TI2V-5B, just never downloaded/hit yet. Live-verified: ran
      `./launch.sh pull-wan22`, downloaded S2V-14B (15GB) + audio encoder,
      confirmed both show up in `/object_info/UNETLoader` and
      `/object_info/AudioEncoderLoader` with no ComfyUI restart needed.
- [ ] T2V-A14B and Animate-14B explicitly NOT covered — T2V-A14B uses a
      different HF repo/layout (`Wan2.2-T2V-A14B/diffusion_pytorch_model_comfyui.safetensors`)
      that was not re-verified this session (would require a ~24GB download to
      confirm); Animate-14B is a stub needing custom ComfyUI nodes that aren't
      installed. Left as a documented gap in the `pull-wan22` help text and
      code comment rather than silently promised.

---

## Definition of Done

- [x] Item 1: `smoke_stream.sh` green, streaming.py fix committed (53cfe938).
- [x] Item 2: successful Wan2.2 TI2V-5B generation (2026-07-29), P4 task #10 closed.
- [x] Item 3: implemented for TI2V-5B + S2V-14B (572c0792), T2V-A14B/Animate-14B
      explicitly deferred with reasons recorded above.

All three items closed 2026-07-29. Also fixed along the way, outside the
original scope but discovered while executing it: unpinned `mcp` SDK
dependency broke CI when upstream published a breaking 2.0.0 release
(3dc92bf6, migration tracked in `TASK_MCP_V2_MIGRATION_V1.md`).
