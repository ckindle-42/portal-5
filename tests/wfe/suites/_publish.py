"""Atomic publication for the committed suite files the builders rewrite.

Builders run concurrently with other pytest workers that fingerprint
tests/wfe by content (campaign.instrument_fingerprint); a plain
write_text truncates the file first, so a concurrent digest can observe
a torn suite and refuse a campaign on phantom instrument drift. The
temp file is unique per publish: two workers rewriting the same suite
must not share one `.tmp` name.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def publish_text(path: Path, text: str) -> None:
    try:
        if path.read_text(encoding="utf-8") == text:
            return
    except FileNotFoundError:
        pass
    fd, name = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(name, 0o644)
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def publish_bytes(path: Path, content: bytes) -> None:
    try:
        if path.read_bytes() == content:
            return
    except FileNotFoundError:
        pass
    fd, name = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        os.chmod(name, 0o644)
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
