"""
Whisper MCP Server
Wraps faster-whisper for audio transcription as an MCP tool.
"""

import asyncio
import os
from pathlib import Path

from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

mcp = FastMCP("whisper-transcription")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "whisper-mcp"})


# Tool manifest for discovery
TOOLS_MANIFEST = [
    {
        "name": "transcribe_audio",
        "description": "Transcribe audio using faster-whisper",
        "parameters": {
            "type": "object",
            "properties": {
                "audio_path": {"type": "string", "description": "Path to audio file"},
                "language": {"type": "string", "description": "Language code (e.g., en, zh)", "default": "auto"},
                "model_size": {"type": "string", "description": "Whisper model size", "default": "base"},
            },
            "required": ["audio_path"],
        },
    },
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
_model = None


def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(WHISPER_MODEL_SIZE, device="auto", compute_type="auto")
    return _model


@mcp.tool()
async def transcribe_audio(file_path: str, language: str | None = None) -> dict:
    """
    Transcribe an audio file using Whisper.

    Args:
        file_path: Absolute path to the audio file (mp3, wav, m4a, ogg, flac)
        language: Language code (e.g. 'en', 'es'). Auto-detected if not provided.

    Returns:
        dict with 'text' (full transcript) and 'segments' (timestamped segments)
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    model = get_model()
    segments, info = await asyncio.to_thread(
        model.transcribe,
        str(path),
        language=language,
        beam_size=5,
    )

    segment_list = []
    full_text = []
    for seg in segments:
        segment_list.append(
            {
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
            }
        )
        full_text.append(seg.text.strip())

    return {
        "text": " ".join(full_text),
        "language": info.language,
        "duration": round(info.duration, 2),
        "segments": segment_list,
    }


if __name__ == "__main__":
    port = int(os.getenv("WHISPER_MCP_PORT", "8915"))
    mcp.settings.port = port
    mcp.run(transport="streamable-http")
