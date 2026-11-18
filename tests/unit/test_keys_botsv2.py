"""keys_botsv2 builder: a value is located in whichever normalization form the index stores."""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from scripts.hunt_bed.keys_botsv2 import main

VALUE = "나는_데이비드를_사랑한다.hwp"  # NFC, 17 code points — the key's cited spelling
NFD = unicodedata.normalize("NFD", VALUE)  # the index's spelling, 32 Hangul-jamo code points
CUSTOM = (
    'search index=botsv2 sourcetype="stream:ftp" "{value}" | stats count '
    "dc(sourcetype) as sourcetypes dc(host) as hosts"
)


def _source(tmp_path: Path, entry: dict[str, Any]) -> Path:
    path = tmp_path / "source.json"
    path.write_text(json.dumps([entry], ensure_ascii=False), encoding="utf-8")
    return path


def _run(
    tmp_path: Path, entry: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> tuple[list[str], Path]:
    out = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        ["keys_botsv2.py", "--source", str(_source(tmp_path, entry)), "--out-dir", str(out)],
    )
    assert main() == 0
    return (out / "keys_audit_queries.spl").read_text(encoding="utf-8").splitlines(), out


def _entry(value: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "dataset": "botsv2",
        "scenario": "taedonggang_phish",
        "step": "ftp_download",
        "value": value,
        "entity": "file",
        "role": "artefact",
        "citations": ["https://example.invalid/writeup §Q404"],
    }
    row.update(extra)
    return row


def test_value_with_two_forms_emits_locators_for_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lines, out = _run(tmp_path, _entry(VALUE, locator=CUSTOM.format(value=VALUE)), monkeypatch)
    assert len(lines) == 4  # primary + fallback per form
    assert [line.rsplit('probe="', 1)[1] for line in lines] == [
        'primary"',
        'fallback"',
        'primary"',
        'fallback"',
    ]
    queries = [line.split(" | eval ", 1)[0] for line in lines]
    assert [query for query in queries if VALUE in query] == queries[:2]
    assert [query for query in queries if NFD in query] == queries[2:]
    trailer = f'artefact="{VALUE}", role="artefact"'
    assert all(trailer in line for line in lines)  # same self-label trailer on every form
    assert queries[2] == CUSTOM.format(value=NFD)  # custom locator retargeted
    assert (
        queries[3]
        == f'search index=botsv2 "{NFD}" | head 1000 | stats count dc(sourcetype) as sourcetypes dc(host) as hosts'
    )
    keys = [
        json.loads(raw) for raw in (out / "keys.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert keys[0]["value"] == VALUE  # the key keeps the cited spelling


def test_value_with_one_form_emits_one_locator_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lines, _ = _run(tmp_path, _entry("eidk.duckdns.org"), monkeypatch)
    assert len(lines) == 2
    assert 'probe="primary"' in lines[0] and 'probe="fallback"' in lines[1]
    assert unicodedata.normalize("NFD", "eidk.duckdns.org") == "eidk.duckdns.org"
