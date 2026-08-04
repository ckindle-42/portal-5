# Portal 5 — ComfyUI Setup Guide

<!-- WIKI:GENERATED unit=unit-comfyui-setup-portal-5-comfyui-setup-guide -->
This is the top-level orientation for the ComfyUI integration. ComfyUI is the
image-generation engine and runs natively on the host rather than in a container,
so the MPS accelerator is reachable directly. The `mcp-comfyui` bridge container
is enabled by default in the compose file and reaches the engine through the
`COMFYUI_URL` address, while the browser-facing links use the public URL. The
video service that once shared this lane is shelved and profile-gated, so the
guide's supported scope is image generation: install via launch.sh, pull models
per family, generate through the MCP tools.

## Why

The native-vs-container split is the load-bearing decision of the whole setup:
Metal access requires the engine to be a host process, which in turn is why
installation, model pulling, and lifecycle management all sit in launch.sh
scripts instead of compose profiles, and why the compose stack only ever talks to
ComfyUI over HTTP.
<!-- /WIKI:GENERATED -->

---

## Quick Install (Apple Silicon)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-quick-install-apple-silicon -->
`./launch.sh install-comfyui` installs the engine on Apple Silicon. The handler
exits early on any non-arm64 machine with a pointer to the Docker profile. On a
supported host it clones the ComfyUI repository into `~/ComfyUI`, creates an
isolated virtual environment, installs the project requirements plus the PyTorch
family, and provisions the standard model directories. It writes the launch
script, installs the VideoHelperSuite custom node for video output, and registers
a launchd agent that starts on login and restarts on exit, with logs redirected
under the home portal directory.

## Why

A dedicated installer exists because ComfyUI sits outside the Docker lifecycle,
and on Apple Silicon the entire point is running on the Metal device the
container boundary would blunt. Bundling clone, venv, torch install, and agent
registration into one command keeps the optional add-on reproducible instead of
documented-as-mandatory.
<!-- /WIKI:GENERATED -->

---

## Download Models

<!-- WIKI:GENERATED unit=unit-comfyui-setup-download-models -->
The supported model download command is `pull-qwen-image`, implemented by
`_launch_pull_qwen_image` in `scripts/lib/services.sh`. It bootstraps the
`huggingface_hub` CLI when absent, then pulls the Qwen-Image checkpoints verified
on Apple Silicon MPS into ComfyUI's flat model layout — the T2I diffusion model,
the edit-2509 model, the shared FP8-scaled text encoder, the VAE, and the
Lightning distillation LoRA — skipping any file already present. The legacy
`download-comfyui-models` alias is retired: `_launch_download_comfyui_models`
exits with an error explaining that the monolithic downloader was deleted and
pointing to the family commands. Video models are not part of this set.

## Why

A single downloader script could not stay current across model families whose
sources and verification differ, so it was replaced by per-family handlers keyed
to what each family actually needs. Keeping the dead alias registered but failing
loudly with a pointer preserves CLI compatibility while forcing the operator to
the command that works for their target family.
<!-- /WIKI:GENERATED -->

---

### Image: flux-schnell (default)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-image-flux-schnell-default -->
Flux is the default image backend. The MCP resolves `IMAGE_BACKEND` to the
checkpoint via `_MODEL_CKPT_MAP`, and the compose service's environment block
carries matching defaults: `FLUX_CKPT_FILE` for the UNet, `FLUX_CLIP_L_FILE` for
the CLIP-L encoder, `FLUX_CLIP_T5_FILE` for the T5 encoder, and `FLUX_VAE_FILE`
for the autoencoder. The split-loader workflow (`FLUX_WORKFLOW`) loads CLIP and
VAE as separate nodes because the official schnell checkpoint carries no embedded
text encoder or VAE. The T5 filename must point at the single-file ComfyUI-native
repackaging; pointing at one shard of the raw diffusers sharded T5 silently loads
half the weights and fails prompt validation with a "Value not in list" error
from `DualCLIPLoader`.

## Why

The flux checkpoint ships without text encoders, so the split-loader graph is the
only way to condition prompts, and each component file is a separately tracked
env default to keep the workflow honest about what is actually installed. The
single-file T5 requirement exists because `DualCLIPLoader` performs a plain
single-file state-dict load, so a lone shard of a sharded encoder is silently
wrong.
<!-- /WIKI:GENERATED -->

---

### Image: sdxl (simpler, single self-contained file, no separate CLIP/VAE needed)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-image-sdxl-simpler-single-self-contained-file-no-separate-clip-vae-needed -->
SDXL is the simpler backend because its checkpoint is self-contained. The
`SDXL_WORKFLOW` graph uses a single `CheckpointLoaderSimple` and draws the text
encoder from output slot 1 and the VAE from output slot 2 of that one file — no
separate `DualCLIPLoader` or `VAELoader` nodes, unlike the FLUX split-loader
graph. It is selected with `IMAGE_BACKEND=sdxl` and samples at 25 steps with a
CFG of 7.5 by default. The admission map mirrors that simplicity: the
`comfyui:sdxl` entry in `MEDIA_MODEL_MEMORY_GB` is a small single-file budget,
far below the multi-file FLUX estimate.

## Why

A self-contained checkpoint is operationally simpler on MPS because it needs no
assembly of separately downloaded encoders and costs less memory to load. That
is why the workflow exists as a minimal seven-node graph and why admission treats
it as the cheapest image backend — a deliberate contrast with the split-loader
complexity FLUX requires.
<!-- /WIKI:GENERATED -->

---

### Archived video backend: wan21-nsfw (shelved)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-video-wan21-nsfw-currently-configured-video-backend-in-env -->
The unit's title is stale: the currently configured default is not wan21-nsfw.
Both the compose environment and `.env.example` set `VIDEO_BACKEND` to wan22.
The wan21-nsfw backend is legacy code in `video_mcp.py` — a dedicated NSFW
fine-tune checkpoint with a matched text encoder and VAE, driven by a CLIPLoader
typed for the Wan architecture and a CFG-guider sampler stack — and its memory
admission estimate is set well above its static weight because a measured peak
consumed nearly the entire unified pool. Its weights are not fetched by any
current command, and enabling it is outside the supported image-only install.

## Why

The default drifted from the documentation while the code stayed put, and the
unit's job is to make the actual state — wan22 as the compose default, wan21-nsfw
as unoperated legacy — the discoverable truth. The admission figure also encodes
a hard-won incident: the measured peak of this backend wildly exceeded its disk
size.
<!-- /WIKI:GENERATED -->

---

### Archived activation step — do not enable

<!-- WIKI:GENERATED unit=unit-comfyui-setup-then-set-video-backend-wan21-nsfw-in-env-and-restart-docker-compose-restart-mcp-video -->
Do not perform this procedure. The `mcp-video` service is gated behind the video
profile, so a plain compose restart of that container in a default stack is a
no-op, and the fleet table does not advertise it regardless. The `VIDEO_BACKEND`
variable still exists in the compose environment with a wan22 default, and
`.env.example` mirrors that default; a wan21-nsfw value selects a legacy backend
in `video_mcp.py` with an admission budget far above its on-disk weight, but no
supported workflow leads an operator to set it. The instruction is archival and
contradicts the current operating posture.

## Why

Documenting the obsolete procedure is necessary so readers understand why it must
not be followed: the env var and backend code are still present, and only the
registration and profile gating make them inert. Naming that gap prevents an
operator from resurrecting a broken lane by following stale instructions.
<!-- /WIKI:GENERATED -->

---

## Wan 2.2 Family (archived; service shelved)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-wan-2-2-family-v6-2-addition -->
The Wan 2.2 family is an implementation inventory, not a service. The workflow
registry in `video_mcp.py` maps four variants: t2v-a14b is a real two-expert
graph whose fp8 checkpoints crash on MPS; ti2v-5b is a real fp16 graph that was
verified but shelved by decision; animate-14b is a stub that raises an
explanatory error when selected; s2v-14b is a real graph whose fp8 checkpoint
also crashes at dequantization. The compose profile keeps the container out of
the default start set, and the fleet table omits the video entry entirely. None
of the four variants is exposed as a supported Portal capability.

## Why

The registry is kept as a complete inventory even though only the shelving is
operational because each variant carries a different reason for being inactive —
crash, decision, or stub — and conflating them would mislead a future operator.
The stub in particular is deliberate: it raises loudly rather than silently
producing nothing.
<!-- /WIKI:GENERATED -->

---

### Step 1 — Pull the weights (opt-in, ~80GB total)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-step-1-pull-the-weights-opt-in-80gb-total -->
No Wan weights are required for the supported image-only setup, so step one of
the old video guide is optional. The handler `_launch_pull_wan22` remains
available and downloads the full Wan 2.2 set into the engine's flat layout — the
fp16 TI2V model, the fp8 S2V and the high/low-noise T2V expert pair, plus the
shared text encoder, VAE, and audio encoder — flattening the repackaged
repository's internal folder prefix so the engine can find the files. The set is
large and consumes disk, and nothing in the compose file starts the video service
that would use it. Running the pull does not enable video operation.

## Why

The pull command is retained for re-evaluation rather than deleted because the
shelving decision is reversible: if MPS fp8 support lands, the weights are one
command away. Keeping it explicit and archival — with the folder-flattening
handling that fixed a real download bug — preserves the path without implying the
service is operated.
<!-- /WIKI:GENERATED -->

---

### TI2V-5B archival status

<!-- WIKI:GENERATED unit=unit-comfyui-setup-ti2v-5b-fast-image-to-video-single-file-comfyui-native-repackaging -->
The TI2V-5B lane is shelved despite being verified. Its single-file checkpoint is
`wan2.2_ti2v_5B_fp16.safetensors` — the compose default for `WAN22_TI2V_MODEL` —
and the workflow in `video_mcp.py` consumes a start-frame image through
`Wan22ImageToVideoLatent`, producing video at a default resolution and frame
count. Full fp16 is why it avoided the fp8 dequantization crash that disabled the
rest of the family. The project nevertheless decided not to expose one working
video variant while the others fail, so neither a tool nor a preset presents it.

## Why

Exposing a single verified lane among broken siblings would advertise video
operation the fleet does not actually run. Keeping the workflow and its env
defaults in the code preserves the proof it works and the exact download target,
so re-enabling later is a registration change rather than a reconstruction.
<!-- /WIKI:GENERATED -->

---

### Step 2 — Export ComfyUI workflow templates

<!-- WIKI:GENERATED unit=unit-comfyui-setup-step-2-export-comfyui-workflow-templates -->
There is no workflow-template export step in the supported setup. The Wan 2.2
graphs are hand-authored dictionaries in `video_mcp.py` — the `WAN22_WORKFLOWS`
registry keys t2v-a14b, ti2v-5b, animate-14b, and s2v-14b — with node layouts
mirroring ComfyUI's official reference JSON rather than imported templates. The
compose file mounts a `workflows` directory into the engine read-only, but no
such directory ships in the repository. The video service is also absent from the
`config/portal.yaml` fleet, so even exported templates would have no consumer.

## Why

Defining workflows as code instead of exported JSON keeps them version-controlled
and reviewable with the MCP that executes them, and it means no manual export
step can fall out of sync with the code. The empty mount and missing fleet entry
are the concrete markers that this step has no operated target.
<!-- /WIKI:GENERATED -->

---

### Step 3 — Use

<!-- WIKI:GENERATED unit=unit-comfyui-setup-step-3-use -->
Usage runs through the image MCP rather than the raw engine API. The
`gen-image.py` CLI posts a generation request to the bridge on the loopback port,
then polls status until the image is ready, and can send a push notification when
done. The underlying MCP exposes blocking generation, an asynchronous start plus
status lookup, a recent-images listing, and a workflow listing. The CLI ships
presets: the default FLUX run, a quality profile at higher resolution, a fast
profile with fewer steps, and a family of Qwen-Image presets for text rendering.

## Why

Exposing a poll-loop CLI on top of the async MCP tools gives a terminal operator
the same job tracking the chat interface gets from start-then-status, without
blocking for minutes on a single call. The preset table collapses the model,
step, and guidance decisions into named choices so iteration is repeatable.
<!-- /WIKI:GENERATED -->

---

### Fast preset (unavailable)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-fast-preset-ti2v-5b-9-min-per-5s-clip -->
No fast TI2V preset is exposed. The image-to-video backend itself is real code:
`_WAN22_TI2V_5B_WORKFLOW` in `video_mcp.py` feeds a `LoadImage` start frame into
`Wan22ImageToVideoLatent` and samples it at a default resolution over 121 frames
(about five seconds at 24 fps), with the single-file fp16 checkpoint
`wan2.2_ti2v_5B_fp16.safetensors` configured as the compose default for
`WAN22_TI2V_MODEL`. It was verified working because full fp16 avoids the fp8
dequantization crash that kills the other Wan 2.2 variants. The project then
chose not to expose a lone partial video family, so `mcp-video` stays profile
gated and no preset exists in any CLI.

## Why

The TI2V variant survived because it is the only Wan 2.2 checkpoint shipped as
full fp16 rather than fp8-quantized, so it never hits the MPS dequantization
failure. Shelving it anyway, despite the proof it works, reflects a deliberate
scoping decision: advertising one working video lane alongside several broken
ones would mislead operators into expecting a service that is not operated.
<!-- /WIKI:GENERATED -->

---

### Cinematic preset (unavailable)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-cinematic-quality-t2v-a14b-slower -->
The cinematic-quality video preset is not available because Portal 5 operates
image generation only. The Wan 2.2 T2V-A14B backend still exists as code: the
`_WAN22_T2V_A14B_WORKFLOW` graph in `video_mcp.py` chains a high-noise and a
low-noise `UNETLoader` through two staged `KSamplerAdvanced` nodes that split the
denoising steps in half, matching ComfyUI's reference two-expert MoE layout.
Every published fp8-scaled checkpoint for it crashes on Apple Silicon MPS at
dequantization, and the `mcp-video` container is profile-gated in the compose
file. No quality T2V preset is reachable anywhere; the workflow is retained as an
archival implementation.

## Why

The graph mirrors ComfyUI's official Wan 2.2 template because the high-noise and
low-noise experts ship as separate checkpoints with no merged single file; a
single UNETLoader assumption would silently drop half the model. The workflow is
kept alongside the shelving decision so that resuming video later — after MPS fp8
support improves — starts from code that already reflects the real layout rather
than a guessed graph.
<!-- /WIKI:GENERATED -->

---

### Video model override (unavailable)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-explicit-model-override -->
Explicit video model overrides are unreachable while video is shelved. The
`video_mcp.py` dispatch still accepts a `model` argument that selects a key from
`WAN22_WORKFLOWS` — t2v-a14b, ti2v-5b, animate-14b, s2v-14b — and the tool
documentation still lists those variants. What changed is registration:
`config/portal.yaml` removed the video entry from `mcp_fleet`, so no video tool
is advertised to the pipeline or the IDE, and the compose file gates the
`mcp-video` container behind a non-default profile. With the service never
started, no override can be exercised. Image-model overrides on the `comfyui_mcp`
service remain fully operational.

## Why

Making a tool reachable is a registration act, not a code act: the fleet table in
`config/portal.yaml` is what the pipeline and Open WebUI discover, so deleting
the video entry is what actually takes the capability away. Leaving the dispatch
and workflows intact keeps the removal reversible — one YAML line restores video
advertisement if the MPS fp8 blocker is ever resolved.
<!-- /WIKI:GENERATED -->

---

### Video MCP tool (unavailable)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-via-mcp-tool -->
The image capability is consumed as MCP tools on the `portal-comfyui` bridge at
the reserved port. The fleet table registers the service as pipeline-callable and
IDE-visible, and the tool manifest in `comfyui_mcp.py` enumerates the image
operations — blocking generation, asynchronous submission with a job id,
status lookup, recent-image retrieval, and workflow listing. No video tool exists
on this service, and the separate video bridge is absent from the fleet, so the
only media tools an agent can invoke are image generation and its follow-ups.

## Why

Tool advertisement is controlled by the fleet registration, not by the code that
implements the tools: a manifest that lists operations means nothing until the
service appears in the fleet table with pipeline exposure on. That is why image
tools are callable while the fully implemented video tools are invisible.
<!-- /WIKI:GENERATED -->

---

## Manual Start / Stop

<!-- WIKI:GENERATED unit=unit-comfyui-setup-manual-start-stop -->
Manual start and stop are a fallback beside the auto-start agent. The generated
`~/ComfyUI/start.sh` launches the venv interpreter on the main entrypoint bound
to all interfaces on the reserved port, which is also the exact command the
launchd plist runs. Stopping manually uses the agent label, and since the plist
declares KeepAlive, the service is expected to come back after a stop; fully
unloading the agent is the way to keep it down. The installer pre-creates the
model and output folders both paths rely on.

## Why

ComfyUI runs as a host process outside the Docker lifecycle, so a foreground
script and a launchd agent are two faces of the same invocation. Manual control
exists for debugging — running `start.sh` in a terminal surfaces errors the
agent swallows into its log files — while the agent provides the login-time
resilience production needs.
<!-- /WIKI:GENERATED -->

---

# Start

<!-- WIKI:GENERATED unit=unit-comfyui-setup-start -->
Starting the engine manually runs `~/ComfyUI/start.sh`. That generated script
resolves its own directory, changes into it, and executes the virtualenv Python
against the main entrypoint with a listen flag bound to all interfaces and the
fixed port. The same arguments are baked into the launchd plist, so the manual
script and the auto-start agent run identical invocations. After start, the
bridge MCP can reach the engine at the loopback address.

## Why

A generated start script exists so the manual and agent-managed paths invoke the
engine identically; duplicating the command by hand invites drift between what an
operator runs in a terminal and what the agent runs at login. Binding all
interfaces lets the Docker bridge reach the host engine over the shared network.
<!-- /WIKI:GENERATED -->

---

# Stop

<!-- WIKI:GENERATED unit=unit-comfyui-setup-stop -->
Stopping the engine uses the launchctl agent label. Because the plist declares
KeepAlive, a stop only halts the current process and the agent may relaunch it
shortly after; keeping the engine down requires unloading the agent entirely.
Logs are written to the files configured in the plist, so inspecting them is the
diagnostic step before deciding whether a stop is clean. On the Docker fallback
path the equivalent is stopping the compose service instead.

## Why

The KeepAlive flag makes plain stop transient by design, so the unit has to
distinguish a momentary stop from a persistent shutdown to avoid confusing
operators. Documenting the unload form prevents a false "it won't stay stopped"
conclusion, and the log paths give the follow-up diagnostic.
<!-- /WIKI:GENERATED -->

---

# Restart

<!-- WIKI:GENERATED unit=unit-comfyui-setup-restart -->
The restart idiom is the launchd agent: stop the agent then start it again, both
under the registered label. The admission module's refusal message uses the more
aggressive kickstart form with the kill flag when it wants to force a full
restart after unloading a heavy model. Restarting matters operationally because
the engine's single long-running MPS process does not reliably evict one model
family's weights when another loads, so a restart is the practical way to clear
resident memory between different model families — the same reason the memory
admission gate exists.

## Why

Restart is the memory-eviction mechanism for a process that cannot reliably
release a previous model family's weights on MPS. The admission gate blocks
oversized jobs pre-flight, but between-family switching still requires an actual
process restart, which is why the refusal message and the documentation both
route operators to the launchd restart command.
<!-- /WIKI:GENERATED -->

---

# View logs

<!-- WIKI:GENERATED unit=unit-comfyui-setup-view-logs -->
Engine logs live under the home portal directory because the installer's launchd
plist redirects standard output and standard error to those files. `tail -f`
follows the output stream in real time, which is the practical way to watch a
generation in progress or catch a startup failure the agent swallowed. The
installer creates the log directory when it writes the plist, so the paths exist
as soon as the agent is registered. A separate error file receives the
exception stream.

## Why

A host-native agent has no container log driver to capture output, so the plist
explicitly redirects both streams to files under the portal state directory.
Naming those exact paths in the unit keeps the diagnostic step unambiguous —
watching a live stream versus reading the error file are distinct operations.
<!-- /WIKI:GENERATED -->

---

## Linux (NVIDIA GPU)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-linux-nvidia-gpu -->
On Linux the Docker route is the `docker-comfyui` profile. The compose file
defines a `comfyui` service from the ai-dock image pinned to the CPU tag with an
explicit `linux/amd64` platform, loopback port 8188, and a health check that
probes `system_stats`. Torch device selection is driven by the
`CF_TORCH_DEVICE` environment variable, which defaults to cpu; setting it to cuda
in `.env` moves compute onto an NVIDIA GPU. The compose definition itself
reserves no GPU device — the image tag is the CPU variant, so CUDA support is
inherited from the ai-dock image rather than declared in the compose file.

## Why

ComfyUI runs host-native on Apple Silicon to reach MPS directly, so the Docker
image is the fallback only for platforms that cannot run a host process — hence
the amd64 CPU default and the device knob rather than a GPU reservation. Keeping
CUDA opt-in via an env var preserves a working CPU container everywhere while
letting NVIDIA hosts accelerate without a second image.
<!-- /WIKI:GENERATED -->

---

# Use Docker ComfyUI with CUDA profile

<!-- WIKI:GENERATED unit=unit-comfyui-setup-use-docker-comfyui-with-cuda-profile -->
The Docker path for non-Apple-Silicon hosts is the `docker-comfyui` profile, but
the documented `./launch.sh up --profile docker-comfyui` form is inaccurate: the
launch script's up command forwards only auto-detected channel profiles and does
not pass a profile argument through. The correct activation is a direct compose
invocation from the deploy directory with the profile flag. The service image is
the CPU-tagged ai-dock build on the amd64 platform, and NVIDIA acceleration is
selected by setting `CF_TORCH_DEVICE` to cuda rather than by any GPU reservation
in the compose file.

## Why

The unit corrects a command that cannot work because profile activation is a
compose-level flag and launch.sh deliberately hides profile mechanics behind its
own interface. Recording the real invocation prevents an operator on a Linux
NVIDIA host from concluding the Docker path is broken when the wrapper simply
does not forward the flag.
<!-- /WIKI:GENERATED -->

---

# Models download automatically on first start

<!-- WIKI:GENERATED unit=unit-comfyui-setup-models-download-automatically-on-first-start -->
The "automatic first-start download" claim is no longer true and must not be
relied on. The compose file still defines a one-shot `comfyui-model-init`
service whose command runs a model downloader, but that script was deleted and
the container would fail at launch. The working model-fetch path is the explicit
family commands `pull-qwen-image` and `pull-wan22` implemented in
`scripts/lib/services.sh`. The init service and its volume mount remain in the
compose definition as stale scaffolding, so an operator who enables the
`docker-comfyui` profile should expect to pull models manually rather than wait
for an automatic step.

## Why

The downloader was removed because one script could not track checkpoint sources
across model families, but the compose service that invoked it was not updated at
the same time — the two files drifted. Recording that drift as a known-limitation
grounded in the actual files prevents an operator from trusting a documented
first-start promise that the code can no longer deliver.
<!-- /WIKI:GENERATED -->

---

## Verify

<!-- WIKI:GENERATED unit=unit-comfyui-setup-verify -->
Verification is a single request to the engine's system statistics endpoint.
Because the engine is host-native, hitting the loopback port from the host
confirms both that the process is up and that it answers the same health URL the
compose definition polls in its health check. A JSON document in the response
with device and memory fields indicates the engine is ready; a connection
refusal means the launchd agent is not running, and the log files are the next
place to look.

## Why

The verification command is the same endpoint the container health check probes,
which keeps the operator's manual check and the stack's automated check in
agreement about what healthy means. That symmetry avoids the classic case where a
service passes its health check but the human verification URL differs.
<!-- /WIKI:GENERATED -->

---

# Should return JSON with GPU info showing MPS device

<!-- WIKI:GENERATED unit=unit-comfyui-setup-should-return-json-with-gpu-info-showing-mps-device -->
The system statistics endpoint answers with JSON. `curl http://localhost:8188/system_stats`
returns a document that on Apple Silicon reports the MPS accelerator in the
devices array and current memory availability. Two consumers depend on that
shape: the compose health check requests the endpoint directly, and the admission
gate parses the free-RAM field out of the same response to size pre-flight
checks. Because the engine is host-native, this endpoint is the one place a
Docker-side process can read true host memory rather than its own cgroup view.

## Why

The endpoint doubles as the health probe and the admission input because it is
host truth: a containerized consumer sees real host RAM here, unlike its own
container limits. Standardizing both on one endpoint keeps the two checks in
agreement about what "free" means.
<!-- /WIKI:GENERATED -->

---

### FLUX images are pure static / TV noise

<!-- WIKI:GENERATED unit=unit-comfyui-setup-flux-images-are-pure-static-tv-noise -->
`--force-fp16` is nowhere in the ComfyUI launch path. The install function
`_launch_install_comfyui` writes `start.sh` and the launchd plist with only the
listen address and port arguments, and the MCP's ETA estimator documents its
Apple Silicon timing assumption as running without fp16. The FLUX graph itself
pins the `KSampler` cfg to 1.0 and routes guidance through the `FluxGuidance`
node, because CFG-style extrapolation on a flow-matching model with a real CFG
scale produces exactly the static output users report. If FLUX output looks like
TV noise while SDXL is clean, inspect the running process flags; a launch script
carrying `--force-fp16` is the classic cause and must be edited out.

## Why

FLUX is a diffusion transformer whose attention math accumulates float16
precision error across sampling steps, so forcing fp16 on MPS degrades the output
to noise; SDXL's convolutional U-Net tolerates the same precision loss. The
launch scripts therefore must never add the flag, and the workflow keeps CFG at
1.0 with separate guidance scaling for the same numerical-sensitivity reason.
<!-- /WIKI:GENERATED -->

---
