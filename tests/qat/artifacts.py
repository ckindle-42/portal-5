"""Byte-level artifact validators for QAT media/document outputs.

Each validator returns an error string on rejection, or None when the bytes
match the format contract. No file is trusted by extension alone.
"""

from __future__ import annotations

import io
import zipfile

PNG_SIG = b"\x89PNG\r\n\x1a\n"
PDF_SIG = b"%PDF-"

# Raw tool/trace leakage that must never surface to a user as "the answer".
_LEAK_MARKERS: tuple[str, ...] = (
    "Traceback (most recent call last):",
    "JSONDecodeError",
    "httpx.HTTPStatusError",
    "Internal Server Error",
    '"code": -32603',
    "jsonrpc error",
    "Tool execution failed",
)


def validate_png(data: bytes) -> str | None:
    if not data.startswith(PNG_SIG):
        return f"missing PNG signature (first 8 bytes {data[:8]!r})"
    if len(data) < 33 or data[12:16] != b"IHDR":
        return "PNG missing IHDR chunk"
    return None


def validate_mp4(data: bytes) -> str | None:
    if len(data) < 12 or data[4:8] != b"ftyp":
        return "missing ftyp box at offset 4"
    return None


def validate_wav(data: bytes) -> str | None:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return "missing RIFF/WAVE header"
    return None


def validate_mp3(data: bytes) -> str | None:
    if data[:3] == b"ID3":
        return None
    if len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return None
    return "neither ID3 tag nor MPEG frame sync"


def validate_audio(data: bytes) -> str | None:
    """WAV or MP3 — whatever the audio MCP produced."""
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return validate_wav(data)
    return validate_mp3(data)


def validate_stl(data: bytes) -> str | None:
    """Binary STL (80-byte header + uint32 count + 50*N bytes) or ASCII
    (solid..endsolid). The size check disambiguates: binary STLs may also
    start with 'solid'."""
    if len(data) >= 84:
        count = int.from_bytes(data[80:84], "little")
        if len(data) == 84 + 50 * count:
            return None
    if data.startswith(b"solid") and b"endsolid" in data.lower():
        return None
    return "STL neither valid binary (84+50*N) nor ASCII with endsolid"


_ZIP_ENTRY: dict[str, tuple[str, ...]] = {
    "docx": ("word/document.xml",),
    "xlsx": ("xl/workbook.xml",),
    "pptx": ("ppt/presentation.xml",),
}


def _validate_zip_kind(data: bytes, kind: str) -> str | None:
    if not data.startswith(b"PK\x03\x04"):
        return f"{kind} missing PK zip signature"
    required = _ZIP_ENTRY[kind]
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            present = set(zf.namelist())
    except zipfile.BadZipFile as exc:
        return f"{kind} unreadable zip: {exc}"
    missing = [entry for entry in required if entry not in present]
    if missing:
        return f"{kind} zip missing internal entries: {', '.join(missing)}"
    return None


def validate_docx(data: bytes) -> str | None:
    return _validate_zip_kind(data, "docx")


def validate_xlsx(data: bytes) -> str | None:
    return _validate_zip_kind(data, "xlsx")


def validate_pptx(data: bytes) -> str | None:
    return _validate_zip_kind(data, "pptx")


def validate_pdf(data: bytes) -> str | None:
    if not data.startswith(PDF_SIG):
        return "missing %PDF- header"
    return None


VALIDATORS: dict[str, object] = {
    "png": validate_png,
    "mp4": validate_mp4,
    "wav": validate_wav,
    "mp3": validate_mp3,
    "audio": validate_audio,
    "stl": validate_stl,
    "docx": validate_docx,
    "xlsx": validate_xlsx,
    "pptx": validate_pptx,
    "pdf": validate_pdf,
}


def validate_artifact(kind: str, data: bytes) -> str | None:
    """Dispatch to the kind's validator; empty bytes always rejected."""
    if not data:
        return "empty artifact"
    validator = VALIDATORS.get(kind)
    if validator is None:
        return f"no validator for artifact kind {kind!r}"
    result = validator(data)  # type: ignore[operator]
    return result if isinstance(result, str) else None


def raw_tool_error_leak(text: str) -> str | None:
    """First leak marker found in model-visible text, or None."""
    lowered = text.lower()
    for marker in _LEAK_MARKERS:
        if marker.lower() in lowered:
            return marker
    return None
