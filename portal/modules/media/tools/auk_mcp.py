"""AuK MCP — MLX-native speech generation and editing (Apple Silicon).

Headless wrapper over the AuK MLX CLI (Tencent-Hunyuan/AuK,
``feat/mlx-apple-silicon``). Runs on the host MLX layer (like mflux /
mlx-transcribe), NOT in any Docker image. Does NOT replace the seated
Kokoro + Qwen3-TTS + Qwen3-ASR stack on port 8918 — this is a parallel MCP
for content edit, paralinguistic edit, enhancement, and source separation.

Port is ``AUK_MCP_PORT`` (P0 discovered 8940). Apple Silicon only.

The MLX branch does not ship ``inference_mlx.py``. Inference is
``python -m auk_mlx.cli`` with ``--instruction`` / ``--audio`` / ``--output``.
Weights must already be converted into ``$AUK_CHECKPOINT_DIR/mlx``.
"""

from __future__ import annotations

import asyncio
import os
import uuid
import wave
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from portal.modules.media.tools._admission import admit
from portal.platform.mcp_host import assert_public_http_url, resolve_upload_path
from portal.platform.mcp_host.owui_files import publish_file
from portal.platform.mcp_host.workspace import get_generated_dir

port = int(os.getenv("AUK_MCP_PORT", "8940"))
mcp = MCPServer("auk-speech")

_route: Callable[
    ...,
    Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]],
] = mcp.custom_route

AUK_REPO_ROOT = os.environ.get("AUK_REPO_ROOT", os.path.expanduser("~/.portal5/auk/repo"))
AUK_CHECKPOINT_DIR = os.environ.get(
    "AUK_CHECKPOINT_DIR", os.path.expanduser("~/.portal5/auk/ckpts")
)
AUK_PYTHON = os.environ.get("AUK_PYTHON", os.path.expanduser("~/.portal5/auk/.venv/bin/python"))
AUK_VARIANT = os.environ.get("AUK_VARIANT", "flash")  # flash | base
AUK_TIMEOUT = int(os.environ.get("AUK_TIMEOUT", "600"))
AUK_MODULE = os.environ.get("AUK_MODULE", "auk_mlx.cli")
AUK_BITS = os.environ.get("AUK_BITS", "8").strip()
AUK_SEQUENTIAL = os.environ.get("AUK_SEQUENTIAL", "1") not in ("", "0", "false", "no")

# Cookbook templates (docs/COOKBOOK.md on the MLX branch). The seated probe
# passes content/paralinguistic instructions through; enhance and separate
# have no instruction argument, so they use these templates.
_ENHANCE_INSTRUCTION = (
    "Preserve all speakers, remove noise and reverberation, "
    "and output clean speech of the same length."
)
_SEPARATE_INSTRUCTION = (
    "Keep all human voices, including speech and singing, and remove everything else."
)


def _mlx_dir() -> str:
    return os.path.join(AUK_CHECKPOINT_DIR, "mlx")


def _variant_config() -> str:
    name = "AuK-Flash" if AUK_VARIANT == "flash" else "AuK"
    return os.path.join(AUK_CHECKPOINT_DIR, name, "config.yaml")


def _cli_path() -> str:
    return os.path.join(AUK_REPO_ROOT, "src", "auk_mlx", "cli.py")


def _checkpoint_present() -> bool:
    mlx = _mlx_dir()
    dit = "dit_flash.safetensors" if AUK_VARIANT == "flash" else "dit_base.safetensors"
    thinker = os.path.join(mlx, "thinker")
    return (
        os.path.isfile(os.path.join(mlx, dit))
        and os.path.isfile(os.path.join(mlx, "vae.safetensors"))
        and os.path.isdir(thinker)
        and os.path.isfile(_variant_config())
    )


@_route("/health", methods=["GET"])
async def health_check(_request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "auk-speech",
            "variant": AUK_VARIANT,
            "checkpoint_present": _checkpoint_present(),
            "cli_present": os.path.isfile(_cli_path()),
            "bits": AUK_BITS or "fp32",
            "sequential": AUK_SEQUENTIAL,
        }
    )


TOOLS_MANIFEST = [
    {
        "name": "synthesize",
        "description": "Zero-shot TTS: generate speech from text, optionally cloning a reference voice.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "reference_audio_url": {"type": "string", "nullable": True},
            },
            "required": ["text"],
        },
    },
    {
        "name": "edit_content",
        "description": "Replace words or phrases in a source recording without re-recording.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_audio_url": {"type": "string"},
                "instruction": {"type": "string"},
            },
            "required": ["source_audio_url", "instruction"],
        },
    },
    {
        "name": "edit_paralinguistic",
        "description": "Change emotion, prosody, or acoustic properties of a source recording.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_audio_url": {"type": "string"},
                "instruction": {"type": "string"},
            },
            "required": ["source_audio_url", "instruction"],
        },
    },
    {
        "name": "enhance",
        "description": "Speech enhancement / denoise on a source recording.",
        "inputSchema": {
            "type": "object",
            "properties": {"source_audio_url": {"type": "string"}},
            "required": ["source_audio_url"],
        },
    },
    {
        "name": "separate",
        "description": (
            "Source separation: keep human voices and drop noise, music, or other non-speech."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"source_audio_url": {"type": "string"}},
            "required": ["source_audio_url"],
        },
    },
]


@_route("/tools", methods=["GET"])
async def list_tools(_request: Request) -> JSONResponse:
    return JSONResponse({"tools": TOOLS_MANIFEST})


async def _fetch_source(url: str) -> Path:
    dst = get_generated_dir("speech") / f"src_{uuid.uuid4().hex[:8]}.wav"
    if url.startswith(("http://", "https://")):
        import httpx

        assert_public_http_url(url)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            dst.write_bytes(resp.content)
        return dst
    resolved = resolve_upload_path(url)
    if resolved is None:
        raise ValueError(
            f"audio url must be an http(s) URL or an existing upload filename, not: {url!r}"
        )
    dst.write_bytes(resolved.read_bytes())
    return dst


def _duration_s(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            if rate <= 0:
                return None
            return handle.getnframes() / rate
    except (wave.Error, OSError):
        return None


def _tts_seconds(text: str) -> float:
    words = max(1, len(text.split()))
    return max(2.0, min(15.0, words * 0.45 + 0.6))


async def _invoke(
    *,
    instruction: str,
    source: Path | None = None,
    gen_seconds: float | None = None,
) -> dict[str, Any]:
    """Shell out to ``python -m auk_mlx.cli``. Arg names match branch tip
    ``6943a1e`` (``--instruction``, ``--audio``, ``--output``, ``--flash``).
    """
    out = get_generated_dir("speech") / f"auk_{uuid.uuid4().hex[:8]}.wav"
    cmd: list[str] = [
        AUK_PYTHON,
        "-m",
        AUK_MODULE,
        "--mlx_dir",
        _mlx_dir(),
        "--qwen_path",
        os.path.join(AUK_CHECKPOINT_DIR, "Qwen2.5-Omni-3B"),
        "--config",
        _variant_config(),
        "--instruction",
        instruction,
        "--output",
        str(out),
    ]
    if AUK_VARIANT == "flash":
        cmd.append("--flash")
    if AUK_BITS:
        cmd += ["--bits", AUK_BITS]
    if AUK_SEQUENTIAL:
        cmd.append("--sequential")
    if source is not None:
        cmd += ["--audio", str(source)]
    if gen_seconds is not None:
        cmd += ["--gen_seconds", f"{gen_seconds:.3f}"]

    env = os.environ.copy()
    src = os.path.join(AUK_REPO_ROOT, "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=AUK_TIMEOUT)
    except TimeoutError:
        proc.kill()
        raise RuntimeError(f"AuK timed out after {AUK_TIMEOUT}s") from None
    if proc.returncode != 0 or not out.is_file():
        tail = (stdout or b"").decode(errors="replace")[-2000:]
        raise RuntimeError(f"AuK exited {proc.returncode}: {tail}")
    try:
        published = await publish_file(str(out))
    except Exception as exc:  # noqa: BLE001 — publish is best-effort; the wav is the artifact
        published = {"error": f"{type(exc).__name__}: {exc}"}
    return {"output_path": str(out), "published": published, "cmd_tail": cmd[-6:]}


async def _guard() -> dict[str, Any] | None:
    return await admit(f"auk:{AUK_VARIANT}")


@mcp.tool()
async def synthesize(text: str, reference_audio_url: str | None = None) -> dict[str, Any]:
    """Zero-shot TTS, optionally in the voice of a reference clip."""
    refusal = await _guard()
    if refusal:
        return refusal
    if reference_audio_url:
        ref = await _fetch_source(reference_audio_url)
        instruction = f"Say the following with the same voice: '{text}'"
        seconds = _duration_s(ref) or _tts_seconds(text)
        return await _invoke(instruction=instruction, source=ref, gen_seconds=seconds)
    instruction = (
        'Generate speech based on the following description: "a clear neutral adult '
        f'speaking voice, moderate pace". The content to speak is: "{text}".'
    )
    return await _invoke(instruction=instruction, gen_seconds=_tts_seconds(text))


@mcp.tool()
async def edit_content(source_audio_url: str, instruction: str) -> dict[str, Any]:
    """Replace words or phrases in a source recording."""
    refusal = await _guard()
    if refusal:
        return refusal
    src = await _fetch_source(source_audio_url)
    return await _invoke(
        instruction=instruction,
        source=src,
        gen_seconds=_duration_s(src),
    )


@mcp.tool()
async def edit_paralinguistic(source_audio_url: str, instruction: str) -> dict[str, Any]:
    """Change emotion, prosody, or acoustic properties of a source recording."""
    refusal = await _guard()
    if refusal:
        return refusal
    src = await _fetch_source(source_audio_url)
    return await _invoke(instruction=instruction, source=src)


@mcp.tool()
async def enhance(source_audio_url: str) -> dict[str, Any]:
    """Denoise and dereverberate a source recording."""
    refusal = await _guard()
    if refusal:
        return refusal
    src = await _fetch_source(source_audio_url)
    return await _invoke(instruction=_ENHANCE_INSTRUCTION, source=src)


@mcp.tool()
async def separate(source_audio_url: str) -> dict[str, Any]:
    """Keep human voices and remove noise, music, or other non-speech."""
    refusal = await _guard()
    if refusal:
        return refusal
    src = await _fetch_source(source_audio_url)
    return await _invoke(instruction=_SEPARATE_INSTRUCTION, source=src)


async def _tool_body(request: Request) -> dict[str, Any]:
    body = await request.json()
    if not isinstance(body, dict):
        return {}
    nested = body.get("arguments")
    if isinstance(nested, dict) and set(body.keys()) <= {"arguments"}:
        return nested
    return body


@_route("/tools/synthesize", methods=["POST"])
async def synthesize_endpoint(request: Request) -> JSONResponse:
    return JSONResponse(await synthesize(**await _tool_body(request)))


@_route("/tools/edit_content", methods=["POST"])
async def edit_content_endpoint(request: Request) -> JSONResponse:
    return JSONResponse(await edit_content(**await _tool_body(request)))


@_route("/tools/edit_paralinguistic", methods=["POST"])
async def edit_paralinguistic_endpoint(request: Request) -> JSONResponse:
    return JSONResponse(await edit_paralinguistic(**await _tool_body(request)))


@_route("/tools/enhance", methods=["POST"])
async def enhance_endpoint(request: Request) -> JSONResponse:
    return JSONResponse(await enhance(**await _tool_body(request)))


@_route("/tools/separate", methods=["POST"])
async def separate_endpoint(request: Request) -> JSONResponse:
    return JSONResponse(await separate(**await _tool_body(request)))


def main() -> None:
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
