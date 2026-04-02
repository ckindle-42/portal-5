# Portal 5.2 — Fish Speech Setup Guide

Fish Speech is an **optional** TTS backend for Portal 5 that adds high-quality voice
cloning. It runs outside Docker on the host machine to access GPU/MPS hardware directly.

**Default (zero-setup)**: Portal 5 ships with **kokoro-onnx** as the primary TTS backend.
It downloads its model (~60 MB) automatically on first use — no setup required.
Fish Speech is only needed if you want voice cloning from reference audio.

**Note**: If Fish Speech is not configured, the TTS MCP automatically uses kokoro-onnx.

## Installation (macOS — Apple Silicon)

```bash
# Clone Fish Speech repository
git clone https://github.com/fishaudio/fish-speech
cd fish-speech

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies (requires PyTorch with MPS support)
pip install torch torchvision torchaudio
pip install -r requirements.txt
```

## Model Downloads

Fish Speech requires model weights. Download to `fish-speech/models/fish_speech/`:

```bash
mkdir -p models/fish_speech
cd models/fish_speech

# Download the 1.4 model (recommended)
git lfs install
git clone https://huggingface.co/fishaudio/Fish-Speech-1.4 .
```

Alternatively, models are downloaded automatically on first use if not present.

## Running Fish Speech

Start Fish Speech API server (add to startup script or run before using TTS):

```bash
cd fish-speech
source venv/bin/activate

# Start API server on port 5005
python -m tools.api --device mps --port 5005
```

**Note**: For CPU-only inference, use `--device cpu` instead of `--device mps`.

## Portal 5 Integration

The TTS MCP expects Fish Speech API at `http://localhost:5005` by default.

Set environment variable in `.env`:
```
FISH_SPEECH_URL=http://localhost:5005
```

To switch back to the built-in kokoro-onnx backend, set in `.env`:
```
TTS_BACKEND=kokoro
```

## Available Voices

### Fish Speech Presets
| Voice ID | Description |
|----------|-------------|
| female_zhang | Female Chinese (Zhang) |
| female_ning | Female Chinese (Ning) |
| male_yun | Male Chinese (Yun) |
| male_tian | Male Chinese (Tian) |
| english_alice | English (Alice) |
| english_marcus | English (Marcus) |
| japanese_yuki | Japanese (Yuki) |

### kokoro-onnx Voices (zero-setup fallback)
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

## Voice Cloning

Fish Speech supports zero-shot voice cloning from reference audio:

1. Prepare reference audio (5-30 seconds, clean speech)
2. Use the `clone_voice` tool in Open WebUI
3. Provide path to reference audio and text to synthesize

## Testing

```bash
# Check if Fish Speech API is running
curl http://localhost:5005/v1/health

# Test TTS MCP directly
curl -X POST http://localhost:8916/tools/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from Portal 5!", "voice": "english_alice"}'
```

## Troubleshooting

### Fish Speech not installed
The TTS MCP automatically uses kokoro-onnx when Fish Speech is not configured.
To confirm which backend is active:
```bash
curl http://localhost:8916/health   # returns {"backend": "kokoro"} or {"backend": "fish_speech"}
./launch.sh logs mcp-tts
```

### MPS/GPU not available
Fish Speech will fall back to CPU inference. This is slower but works:
```bash
python -m tools.api --device cpu --port 5005
```

### Model download failures
Manually download models:
```bash
git lfs install
git clone https://huggingface.co/fishaudio/Fish-Speech-1.4 ./models/fish_speech
```

## Alternative: kokoro-onnx (built-in, no setup)

If Fish Speech doesn't work on your system, set `TTS_BACKEND=kokoro` in `.env`.
kokoro-onnx is already installed inside the `mcp-tts` Docker container and requires
no additional setup. Its model (~60 MB) is downloaded automatically on first use.

kokoro-onnx provides:
- 11 English voices (American and British, male and female)
- Fast CPU inference via ONNX runtime
- No GPU required