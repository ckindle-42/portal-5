# Portal 6.0.0 — Fish Speech Setup Guide

Fish Speech is an optional TTS backend for Portal 5 whose only unique feature is
voice cloning from a reference recording, and it is not the default. The default
is Kokoro: `TTS_BACKEND` defaults to `kokoro`, `Dockerfile.mcp` installs
`kokoro-onnx` in the `mcp-tts` container, and `_ensure_kokoro_models` fetches the
ONNX weights and voices on first use with no operator action. When the optional
`fish_speech` package is missing, `_get_available_backend` and the `speak` tool
keep serving through Kokoro, so the system degrades to the built-in backend
rather than failing. Fish Speech does not run outside Docker; the MCP imports it
in-process and the service answers on port 8916.

## Why

This is the umbrella unit for the setup guide, so its job is to state the
default-versus-optional relationship once and accurately. Getting the container
boundary right matters here more than anywhere else because the old doc claimed
Fish Speech runs on the host for MPS, when the current code loads it inside the
mcp-tts process and leaves host MPS to the separate speech server.

---

## Installation (macOS — Apple Silicon)

On macOS Apple Silicon there is no Portal-specific Fish Speech installer;
`launch.sh` manages `install-comfyui`, `install-music-minimax`, `install-music-ace`, and the host-native
speech server, and nothing in the repo provisions Fish Speech. The zero-setup
speech backend is Kokoro inside the `mcp-tts` container, which `Dockerfile.mcp`
supplies at build time, while the host speech server in `scripts/mlx-speech.py`
runs natively for MPS access and serves Open WebUI through
`AUDIO_TTS_OPENAI_API_BASE_URL` pointing at port 8918. Fish Speech remains a
manual, optional install whose checkpoint the TTS MCP loads from
`models/fish_speech/fish-speech-1.4`.

## Why

The original section was a code fence with nothing behind it, so the truthful
content is negative: this repository installs Kokoro, not Fish Speech, and macOS
users get MPS acceleration through the host-native speech server rather than
through the optional backend. Recording that boundary prevents an operator from
expecting a fish install command that does not exist in the codebase.

---

# Clone Fish Speech repository

The Portal 5 tree does not clone or vendor the upstream Fish Speech source, and
no install step in this repository fetches it. The TTS MCP discovers the
capability at import time: `_check_fish_speech` attempts `import fish_speech`
and surfaces the result on the health route, so the package's presence controls
the `fish_speech` backend. `Dockerfile.mcp` deliberately installs only
`kokoro-onnx` for speech, which is why the zero-setup path works without any
source checkout; obtaining the Python package and its checkpoint is an operator
action that happens outside the image build.

## Why

Keeping Fish Speech an import-time optional dependency rather than vendoring a
repository tree is what lets the MCP container stay small and lets Kokoro answer
`speak` calls even when the optional package is missing. The discovery mechanism
treats the package as a feature flag, so the fallback path is exercised by the
same code every deployment runs.

---

# Create virtual environment

Portal 5 never creates a Python virtual environment for speech, because the
`mcp-tts` Docker container is the runtime. `docker-compose.yml` launches it with
`python -m portal.modules.media.tools.tts_mcp` and `Dockerfile.mcp` pins the
speech dependencies such as `kokoro-onnx`, `soundfile` and `numpy` into the image
at build time, so there is no virtualenv to activate before synthesis.
`tts_mcp.py` reads its configuration like `TTS_BACKEND`, `TTS_DEFAULT_VOICE` and
`TTS_MCP_PORT` from container environment variables supplied by the compose file,
which is the only environment the server ever sees.

## Why

The older guide assumed a host virtualenv because it described a manual Fish
Speech install that predates the containerised MCP. Writing the unit around the
container-as-environment model prevents operators from hunting for a virtualenv
that does not exist and makes the compose file the single source of truth for the
speech server's settings.

---

# Install dependencies (requires PyTorch with MPS support)

The speech containers do not need a host pip install because their Python
dependencies are baked into the images. `Dockerfile.mcp` installs `torch` and
`torchaudio` alongside `kokoro-onnx` and `soundfile`, and that same image serves
the TTS, music and document generation containers. Runtime device selection is
handled by `get_torch_device` in the shared media utilities, which returns `mps`
on Apple Silicon, `cuda` when a GPU is visible and `cpu` otherwise; the Fish
Speech loaders forward that value into `load_from_checkpoint`. There is no
separate `requirements.txt` step in the portal build, and `torchvision` is not
listed there.

## Why

Baking torch into the shared MCP image instead of telling operators to install it
by hand keeps every container reproducible and sidesteps the MPS wheel problems
that a manual macOS install tends to cause. The device helper centralises
selection so Fish Speech and music generation agree on what acceleration is
available instead of each probing independently.

---

## Model Downloads

Fish Speech requires its weights at a path the code asserts, not one the operator
chooses: the TTS MCP loads `Text2Speech` from `models/fish_speech/fish-speech-1.4`
in both `_fish_speech_sync` and `_fish_clone_sync`. The leading directory is
`models/fish_speech` inside the container working directory, not the source-tree
layout the older guide described. Kokoro, by contrast, downloads its own model
and voices on first use through `_ensure_kokoro_models` and caches them under
`HF_HOME`, so the built-in backend has no manual download step at all and never
requires the operator to create a model directory by hand.

## Why

The old path carried a source-checkout prefix that the containerised MCP does not
have, and repeating it would misdirect anyone placing weights by hand. Spelling
out the exact relative path the two loaders share keeps the manual step aligned
with the one location the code will actually read at synthesis time.

---

# Download the 1.4 model (recommended)

The Fish Speech 1.4 checkpoint location is a hardcoded contract in the TTS MCP:
`_fish_speech_sync` loads `Text2Speech` with `load_from_checkpoint` using the
checkpoint path `models/fish_speech/fish-speech-1.4`, and `_fish_clone_sync`
calls `from_pretrained` on the same relative string. Both resolve from the
container working directory, so the 1.4 weights must live at that exact location.
Unlike Kokoro, whose files `_ensure_kokoro_models` fetches automatically on first
use, Fish Speech has no download helper in the repository; a missing checkpoint
makes the loader raise and the tool return an error dictionary.

## Why

The exact directory is not a suggestion, it is what two separate loaders assert,
so placing the weights anywhere else turns every Fish Speech request into an
exception. Calling out the contrast with the Kokoro auto-download keeps operators
from assuming the heavy backend self-provisions, which only the built-in one does.

---

## Running Fish Speech

There is no separate start command for Fish Speech because it is not a standalone
process. The `mcp-tts` service defined in `docker-compose.yml` runs the TTS MCP
module as its entrypoint, and the MCP imports the optional `fish_speech` package
in-process when `TTS_BACKEND=fish_speech`. Bringing the stack up with `launch.sh`
starts the service, and `./launch.sh logs mcp-tts` tails its output. The only
prerequisite for the backend to activate is that the `fish_speech` package is
importable and the 1.4 checkpoint sits at `models/fish_speech/fish-speech-1.4`,
which is the path `load_from_checkpoint` asserts.

## Why

Operators coming from the old guide expected to launch an upstream API process
before using TTS, but the container entrypoint already owns the whole lifecycle.
Grounding the run step in the compose command removes a spurious manual step and
makes it explicit that activation depends on the package and checkpoint being
present at the paths the loader code asserts.

---

# Start API server on port 5005

The claim that Fish Speech listens on port 5005 is false for this repository. The
only speech endpoint the TTS MCP exposes is the MCP itself, which binds
`TTS_MCP_PORT` with a default of 8916, as shown in `docker-compose.yml` and the
variable read inside `tts_mcp.py`. The upstream `tools.api` server command
belongs to the Fish Speech source tree that Portal 5 does not run; the MCP loads
`Text2Speech` directly in-process. A working TTS stack therefore answers on 8916,
and the container healthcheck probes that same port via the health route.

## Why

A port that nothing listens on is a debugging trap, and the old guide set one up
at 5005 while the MCP served 8916. Pinning the port to the environment variable
that actually controls it makes the unit a reliable map from the compose file to
the running process, so an operator can predict exactly where to send a request.

---

## Portal 5 Integration

Integration with Portal 5 runs through the TTS MCP and the environment knobs that
configure it. `config/portal.yaml` registers the `tts` server as `portal-tts` on
port 8916, `docker-compose.yml` builds and runs it as the `mcp-tts` service
passing `TTS_BACKEND` and `TTS_DEFAULT_VOICE`, and `.env.example` documents those
variables. There is no `FISH_SPEECH_URL` variable anywhere in the repository; the
optional backend is chosen by setting `TTS_BACKEND=fish_speech`. Separately, Open
WebUI's own audio output does not use this MCP at all: the compose file points
`AUDIO_TTS_OPENAI_API_BASE_URL` at the host-native speech server on port 8918
(`scripts/mlx-speech.py`), which serves Kokoro and Qwen3-TTS.

## Why

The old guide invented an HTTP URL that the code never reads, and tracing the real
integration exposes two distinct speech surfaces that are easy to confuse: the
MCP tool server for persona tool-calls and the OpenAI-compatible server Open
WebUI speaks to directly. Naming both keeps operators from editing a variable
that does nothing while the actual switch lives in `TTS_BACKEND`.

---

### Fish Speech Presets

The TTS MCP exposes exactly two Fish Speech preset voice IDs. In `list_voices`
the `fish_speech` entry lists `female_zhang` and `male_yun`, and adds a third
`custom` entry that is served by cloning a voice from a reference recording
rather than by a fixed preset. The other identifiers from the older guide such as
english_alice, english_marcus and japanese_yuki do not appear anywhere in the
repository, so they are not returned by `list_voices` and cannot be relied on.
Voice selection for Fish Speech flows through the `speak` tool's `voice`
argument once `TTS_BACKEND=fish_speech`.

## Why

Listing presets that no code defines is exactly the kind of documented fantasy
the grounding pass exists to remove. The two IDs that `list_voices` actually
returns are the only safe ones to advertise, and the custom entry points at the
real extension path, cloning, which is the feature that justifies Fish Speech at
all.

---

### kokoro-onnx Voices (zero-setup fallback)

The Kokoro voice set is defined twice in the repository, in the `list_voices`
tool of the TTS MCP and in the `.env.example` comment for `TTS_DEFAULT_VOICE`,
and the two agree:

| Voice ID | Accent / gender |
|----------|-----------------|
| `af_heart` | American English female (default) |
| `af_sky` | American English female |
| `af_bella` | American English female |
| `af_nicole` | American English female |
| `af_sarah` | American English female |
| `am_adam` | American English male |
| `am_michael` | American English male |
| `bf_emma` | British English female |
| `bf_isabella` | British English female |
| `bm_george` | British English male |
| `bm_lewis` | British English male |

`af_heart` is the fallback when no `voice` argument is supplied, because it is the
value of `TTS_DEFAULT_VOICE` and the server-side `TTS_VOICE` default.

## Why

A voice table is only safe to document when a tool actually returns it, and
`list_voices` returns exactly these eleven IDs, so the table is grounded in
executable output rather than marketing copy. Matching the `.env.example` comment
confirms the two sources of truth have not drifted apart from each other.

---

## Voice Cloning

Voice cloning in the TTS MCP is implemented by the `clone_voice` tool, which
requires the `fish_speech` package: `_check_fish_speech` gates it, and when the
package is absent the tool returns an unavailable error with an `install_docs`
pointer rather than crashing. The reference audio should be a short clean
recording, five to thirty seconds, matching the parameter help, and the tool
passes the path into `_fish_clone_sync`, which loads the 1.4 checkpoint via
`from_pretrained` and writes a clone file into the output directory. A separate
cloning route exists on the host-native speech server: `scripts/mlx-speech.py`
sends a `clone:` voice prefix to the Qwen3-TTS Base model, which also clones from
a reference file without Fish Speech.

## Why

Cloning is the entire reason Fish Speech is worth installing, so its unit must
name the exact gating mechanism and the failure mode when the package is missing.
Documenting both the MCP tool and the Qwen3-TTS alternative prevents an operator
from assuming cloning is unavailable whenever Fish Speech is absent, when a
second route exists at the host speech server.

---

## Testing

Two probes exercise the speech stack without loading a model. First,
`curl http://localhost:8916/health` hits the TTS MCP health route, which reports
the active backend (`kokoro` or `fish_speech`) and whether voice cloning is
available; `docker-compose.yml` runs the same request as the container
healthcheck. Second, `./launch.sh logs mcp-tts` streams the service log so a
startup failure or a model download stall is visible. A full end-to-end check
calls the `speak` tool with a short text and a known voice ID, then verifies the
response carries a `download_url`. These are the checks the deployment itself
relies on, and they run entirely against the live service.

## Why

Testing guidance must name commands that exist, and the previous section was an
empty code fence that told an operator nothing. The health route, the compose
healthcheck and the logs subcommand are the verification points the platform
already depends on, so documenting them means the operator's checks and the
system's own health probes agree rather than contradict each other.

---

# Check if Fish Speech API is running

There is no standalone Fish Speech API server in Portal 5; when the optional
`fish_speech` package is importable, the TTS MCP loads it in-process instead of
proxying to a separate process. The correct way to ask whether speech is ready is
the MCP's own health route: `curl http://localhost:8916/health` returns JSON
whose `backend` field reads either `kokoro` or `fish_speech`. `docker-compose.yml`
uses that same request as the container healthcheck, and `./launch.sh logs mcp-tts`
streams the service log for diagnosing failures at request time.

## Why

The older guide pointed operators at a port 5005 API that no code in this
repository runs, so that check could never succeed against a healthy stack.
Pinning the probe to the route the MCP actually serves makes the verification
meaningful and keeps it identical to the healthcheck Docker already executes for
the container.

---

# Test TTS MCP directly

The `speak` tool is reachable over HTTP at the MCP's `/tools/speak` route, which
expects an `arguments` wrapper, so a direct request must wrap the tool arguments:

```bash
curl -X POST http://localhost:8916/tools/speak \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"text": "Hello from Portal 5!", "voice": "af_heart"}}'
```

The handler reads the `arguments` field and forwards `text`, `voice`, `speed` and
`backend` into the `speak` function, returning JSON with a `download_url` to the
generated WAV when synthesis succeeds. The voice name english_alice from the old
guide is not something the server knows; the valid preset IDs are the Kokoro list
in `list_voices` plus the Fish Speech IDs `female_zhang` and `male_yun`.

## Why

The old example posted a bare tool payload and a voice name that no code defines,
so it would fail even against a healthy server. The corrected shape mirrors what
the route actually parses, and using a real voice ID makes the test distinguish a
working stack from a voice-routing problem.

---

### Fish Speech not installed

When the optional `fish_speech` package is absent, the TTS MCP still serves
speech through Kokoro: `_get_available_backend` reports `kokoro` whenever the
`kokoro_onnx` import succeeds, and the `speak` tool falls back to the default
`TTS_BACKEND` value. To confirm which backend is live, `curl
http://localhost:8916/health` returns JSON with the `backend` field set to
`kokoro` or `fish_speech`, and `./launch.sh logs mcp-tts` shows the runtime log
of the service. That same health route is what `docker-compose.yml` polls for
the container healthcheck, so the probe is shared with the platform itself.

## Why

A speech system that silently degrades is only useful if the active backend is
observable, and the health route plus the compose healthcheck provide that
observability mechanically. This unit records the exact commands so an operator
diagnosing silence can tell a missing optional backend apart from a real
synthesis failure without guessing.

---

### MPS/GPU not available

Device selection for Fish Speech in the TTS MCP is not a command-line flag; it is
the `get_torch_device` helper in the shared media utilities. That function checks
`torch.backends.mps.is_available` first, then `torch.cuda.is_available`, and
returns `mps`, `cuda` or `cpu` in that order of preference. The Fish Speech
loaders forward the result into `load_from_checkpoint` and `from_pretrained`, so
a machine without MPS simply runs inference on `cpu`, which is slower but
functional. The old `--device` flag belongs to an upstream CLI that Portal 5 does
not invoke, because the MCP loads Fish Speech in-process rather than spawning the
upstream API.

## Why

A backend whose acceleration path is decided by one shared helper is easier to
reason about than one controlled by flags scattered through startup scripts.
Recording the fallback order makes it predictable that a Mac without a usable MPS
context still synthesises, just slower, and names the exact function an operator
should read when performance is poor.

---

### Model download failures

When the Fish Speech 1.4 weights are missing, the failure surfaces in the TTS MCP
because the loaders read a fixed path. `_fish_speech_sync` passes
`models/fish_speech/fish-speech-1.4` to `load_from_checkpoint` and
`_fish_clone_sync` uses `from_pretrained` on the same string, and neither call has
a download fallback. Kokoro is the only backend with an automated fetch,
performed by `_ensure_kokoro_models`, which pulls the ONNX weights and the voice
pack from the upstream GitHub release and caches them under `HF_HOME`. Placing
the 1.4 checkpoint at the hardcoded path is therefore the only recovery available
to an operator whose download failed midway.

## Why

Documenting recovery steps is only honest when the failure mode they address is
real, and this one is: a missing checkpoint converts every Fish Speech request
into an exception because the loaders will not self-provision. The contrast with
the Kokoro auto-download tells the operator exactly which backend recovers by
itself and which one requires manual placement of weights.

---

## Alternative: kokoro-onnx (built-in, no setup)

Setting `TTS_BACKEND=kokoro` in the environment selects the built-in backend, and
`.env.example` already ships that value as the default while `docker-compose.yml`
passes it to the `mcp-tts` container. `Dockerfile.mcp` installs `kokoro-onnx` at
image build time, so the container needs no per-run setup. On the first `speak`
call, `_ensure_kokoro_models` downloads the ONNX weights and the voices binary
from the upstream GitHub release and caches them under `HF_HOME`. The `list_voices`
tool reports eleven English voices spanning American and British male and female
speakers, and synthesis runs on CPU through the ONNX runtime, so no GPU and no
Hugging Face token are required. The host-native `mlx-speech` server is a second
Kokoro path that selects the same backend through `MLX_TTS_BACKEND` for Open
WebUI audio output.

## Why

Kokoro is the deliberate default because it collapses speech into one pip
dependency plus an on-demand model download, preserving the zero-setup contract
the container image promises. Fish Speech stays optional precisely because it
adds a heavy package and a large checkpoint, and it exists only to unlock voice
cloning from a reference recording, which the built-in backend cannot do.

---
