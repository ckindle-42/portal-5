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

**To do:**
- [ ] Restart ComfyUI (`launchctl kickstart -k gui/$(id -u)/com.portal5.comfyui`)
      as a clean-state precaution before the real test, even though live re-scan
      already picked up the files without one.
- [ ] Re-verify `/object_info/UNETLoader`, `/object_info/VAELoader`,
      `/object_info/CLIPLoader` still show the three Wan2.2 files post-restart.
- [ ] Prepare/select a start-frame image — **required input** for `wan22-ti2v-5b`
      per `video_mcp.py`'s own tool description (image-to-video, not text-to-video).
- [ ] Run one `start_video_generation` call (`mcp__portal-video__start_video_generation`,
      `model=wan22-ti2v-5b`) and poll `get_video_status` to completion or failure.
- [ ] Watch ComfyUI's logs during the run for the pre-existing objc duplicate-class
      warning (`cv2` and `av` both bundle a `libavdevice` dylib registering the same
      class names — ComfyUI's own log calls this a risk for "spurious casting
      failures and mysterious crashes"). It has never actually triggered a failure
      yet, but if the generation crashes oddly, this is the first thing to check —
      likely needs pinning one of `cv2`/`av`'s bundled ffmpeg libs.
- [ ] On success: close out P4 task #10, fold into the closeout report.
- [ ] On failure: capture full ComfyUI error/log output before touching anything
      else (don't restart/clear state reflexively — that's how the previous root
      cause took two sessions to find).

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

- [ ] Item 1: `smoke_stream.sh` green, streaming.py fix committed.
- [ ] Item 2: one successful (or clearly diagnosed-failed) Wan2.2 TI2V-5B generation,
      P4 task #10 closed either way.
- [ ] Item 3: explicit decision recorded (implement now / defer / not worth it) —
      doesn't need to be done, just decided.
