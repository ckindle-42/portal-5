"""Offline checks for the streaming smoke gate's SSE accounting.

`curl` is replaced by a shim on PATH that writes a captured SSE sample, so these run with no
network and no live pipeline (the live gate itself is ./scripts/smoke_stream.sh).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "smoke_stream.sh"

SAMPLE = """\
data: {"id":"smoke","choices":[{"delta":{"role":"assistant","content":""}}]}

data: {"id":"smoke","choices":[{"delta":{"content":"PONG"}}]}

data: [DONE]
"""

FAKE_CURL = """\
#!/usr/bin/env bash
out=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        -o) out="$2"; shift 2 ;;
        -w|-X|-H|-d|--max-time) shift 2 ;;
        *) shift ;;
    esac
done
[ -n "$out" ] && cp "$SMOKE_STREAM_SAMPLE" "$out"
printf '%s' "${SMOKE_STREAM_CODE:-200}"
"""


def _run(tmp_path: Path, sample: str, *, code: str = "200") -> subprocess.CompletedProcess[str]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    curl = bindir / "curl"
    curl.write_text(FAKE_CURL)
    curl.chmod(0o755)
    sample_path = tmp_path / "stream.sse"
    sample_path.write_text(sample)
    env = {
        **os.environ,
        "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
        "PIPE": "http://pipeline.invalid",
        "PIPELINE_API_KEY": "test-key",
        "SMOKE_STREAM_SAMPLE": str(sample_path),
        "SMOKE_STREAM_CODE": code,
    }
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_smoke_stream_has_valid_shell_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_smoke_stream_passes_on_captured_sse_sample(tmp_path: Path) -> None:
    result = _run(tmp_path, SAMPLE)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS — 2 SSE chunk(s), 1 with token delta(s), [DONE] received" in result.stdout
    assert "integer expression expected" not in result.stderr


def test_smoke_stream_fails_without_done_instead_of_integer_error(tmp_path: Path) -> None:
    result = _run(tmp_path, SAMPLE.replace("data: [DONE]\n", ""))
    assert result.returncode == 1
    assert "FAIL — stream did not terminate with [DONE]" in result.stdout
    assert "integer expression expected" not in result.stderr


def test_smoke_stream_fails_without_chunks_instead_of_integer_error(tmp_path: Path) -> None:
    result = _run(tmp_path, "")
    assert result.returncode == 1
    assert "FAIL — no data chunks received" in result.stdout
    assert "integer expression expected" not in result.stderr
