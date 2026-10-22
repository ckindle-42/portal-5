"""Atomic publication for the committed suite files the builders rewrite.

Builders run concurrently with other pytest workers that fingerprint
tests/wfe by content (campaign.instrument_fingerprint); a plain
write_text truncates the file first, so a concurrent digest can observe
a torn suite and refuse a campaign on phantom instrument drift.
"""

from __future__ import annotations

import os
from pathlib import Path


def publish_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
