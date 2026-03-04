# Portal 5.0 — Fish Speech Setup Guide

Fish Speech is the primary TTS (text-to-speech) engine for Portal 5. It provides high-quality speech synthesis with voice cloning capabilities. Fish Speech runs **outside Docker** on the host machine to access GPU/MPS hardware directly.

**Note**: If Fish Speech is not available, the TTS MCP will automatically fall back to CosyVoice.

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

Or switch to CosyVoice fallback in `.env`:
```
TTS_BACKEND=cosyvoice
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

### CosyVoice Fallback (if Fish Speech unavailable)
| Voice ID | Description |
|----------|-------------|
| 中文女 | Chinese female |
| 中文男 | Chinese male |
| 英文女 | English female |
| 英文男 | English male |
| 日文女 | Japanese female |
| 日文男 | Japanese male |

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
The TTS MCP will automatically use CosyVoice fallback if Fish Speech is not available. Check logs:
```bash
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

## Alternative: CosyVoice

If Fish Speech doesn't work on your system, set `TTS_BACKEND=cosyvoice` in `.env`:

```bash
# Install CosyVoice
pip install cosyvoice torchaudio
```

CosyVoice provides:
- Pre-trained SFT voices
- Zero-shot voice cloning
- Multi-language support (Chinese, English, Japanese)