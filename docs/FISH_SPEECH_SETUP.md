# Portal 6.0.0 — Fish Speech Setup Guide

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-portal-6-0-0-fish-speech-setup-guide -->
Fish Speech is an **optional** TTS backend for Portal 5 that adds high-quality voice
cloning. It runs outside Docker on the host machine to access GPU/MPS hardware directly.

**Default (zero-setup)**: Portal 5 ships with **kokoro-onnx** as the primary TTS backend.
It downloads its model (~60 MB) automatically on first use — no setup required.
Fish Speech is only needed if you want voice cloning from reference audio.

**Note**: If Fish Speech is not configured, the TTS MCP automatically uses kokoro-onnx.
<!-- /WIKI:GENERATED -->

---

## Installation (macOS — Apple Silicon)

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-installation-macos-apple-silicon -->
```bash
<!-- /WIKI:GENERATED -->

---

# Clone Fish Speech repository

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-clone-fish-speech-repository -->
git clone https://github.com/fishaudio/fish-speech
cd fish-speech
<!-- /WIKI:GENERATED -->

---

# Create virtual environment

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-create-virtual-environment -->
python3 -m venv venv
source venv/bin/activate
<!-- /WIKI:GENERATED -->

---

# Install dependencies (requires PyTorch with MPS support)

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-install-dependencies-requires-pytorch-with-mps-support -->
pip install torch torchvision torchaudio
pip install -r requirements.txt
```
<!-- /WIKI:GENERATED -->

---

## Model Downloads

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-model-downloads -->
Fish Speech requires model weights. Download to `fish-speech/models/fish_speech/`:

```bash
mkdir -p models/fish_speech
cd models/fish_speech
<!-- /WIKI:GENERATED -->

---

# Download the 1.4 model (recommended)

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-download-the-1-4-model-recommended -->
git lfs install
git clone https://huggingface.co/fishaudio/Fish-Speech-1.4 .
```

Alternatively, models are downloaded automatically on first use if not present.
<!-- /WIKI:GENERATED -->

---

## Running Fish Speech

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-running-fish-speech -->
Start Fish Speech API server (add to startup script or run before using TTS):

```bash
cd fish-speech
source venv/bin/activate
<!-- /WIKI:GENERATED -->

---

# Start API server on port 5005

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-start-api-server-on-port-5005 -->
python -m tools.api --device mps --port 5005
```

**Note**: For CPU-only inference, use `--device cpu` instead of `--device mps`.
<!-- /WIKI:GENERATED -->

---

## Portal 5 Integration

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-portal-5-integration -->
The TTS MCP expects Fish Speech API at `http://localhost:5005` by default.

Set environment variable in `.env`:
```
FISH_SPEECH_URL=http://localhost:5005
```

To switch back to the built-in kokoro-onnx backend, set in `.env`:
```
TTS_BACKEND=kokoro
```
<!-- /WIKI:GENERATED -->

---

### Fish Speech Presets

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-fish-speech-presets -->
| Voice ID | Description |
|----------|-------------|
| female_zhang | Female Chinese (Zhang) |
| female_ning | Female Chinese (Ning) |
| male_yun | Male Chinese (Yun) |
| male_tian | Male Chinese (Tian) |
| english_alice | English (Alice) |
| english_marcus | English (Marcus) |
| japanese_yuki | Japanese (Yuki) |
<!-- /WIKI:GENERATED -->

---

### kokoro-onnx Voices (zero-setup fallback)

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-kokoro-onnx-voices-zero-setup-fallback -->
| Voice ID | Description |
|----------|-------------|
| af_heart | American English female (default) |
| af_sky | American English female |
| af_bella | American English female |
| af_nicole | American English female |
| af_sarah | American English female |
| am_adam | American English male |
| am_michael | American English male |
| bf_emma | British English female |
| bf_isabella | British English female |
| bm_george | British English male |
| bm_lewis | British English male |
<!-- /WIKI:GENERATED -->

---

## Voice Cloning

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-voice-cloning -->
Fish Speech supports zero-shot voice cloning from reference audio:

1. Prepare reference audio (5-30 seconds, clean speech)
2. Use the `clone_voice` tool in Open WebUI
3. Provide path to reference audio and text to synthesize
<!-- /WIKI:GENERATED -->

---

## Testing

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-testing -->
```bash
<!-- /WIKI:GENERATED -->

---

# Check if Fish Speech API is running

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-check-if-fish-speech-api-is-running -->
curl http://localhost:5005/v1/health
<!-- /WIKI:GENERATED -->

---

# Test TTS MCP directly

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-test-tts-mcp-directly -->
curl -X POST http://localhost:8916/tools/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from Portal 5!", "voice": "english_alice"}'
```
<!-- /WIKI:GENERATED -->

---

### Fish Speech not installed

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-fish-speech-not-installed -->
The TTS MCP automatically uses kokoro-onnx when Fish Speech is not configured.
To confirm which backend is active:
```bash
curl http://localhost:8916/health   # returns {"backend": "kokoro"} or {"backend": "fish_speech"}
./launch.sh logs mcp-tts
```
<!-- /WIKI:GENERATED -->

---

### MPS/GPU not available

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-mps-gpu-not-available -->
Fish Speech will fall back to CPU inference. This is slower but works:
```bash
python -m tools.api --device cpu --port 5005
```
<!-- /WIKI:GENERATED -->

---

### Model download failures

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-model-download-failures -->
Manually download models:
```bash
git lfs install
git clone https://huggingface.co/fishaudio/Fish-Speech-1.4 ./models/fish_speech
```
<!-- /WIKI:GENERATED -->

---

## Alternative: kokoro-onnx (built-in, no setup)

<!-- WIKI:GENERATED unit=unit-fish-speech-setup-alternative-kokoro-onnx-built-in-no-setup -->
If Fish Speech doesn't work on your system, set `TTS_BACKEND=kokoro` in `.env`.
kokoro-onnx is already installed inside the `mcp-tts` Docker container and requires
no additional setup. Its model (~60 MB) is downloaded automatically on first use.

kokoro-onnx provides:
- 11 English voices (American and British, male and female)
- Fast CPU inference via ONNX runtime
- No GPU required
<!-- /WIKI:GENERATED -->

---
