"""publish_text stays collision-free when concurrent builders rewrite one file.

xdist workers publish the same committed suite files; the old shared
`<name>.tmp` made two publishers collide on os.replace (FileNotFoundError
on test_runs.py.tmp, seen twice under `pytest tests/unit tests/wfe -n 2`).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.wfe.suites import _publish
from tests.wfe.suites._publish import publish_text


def test_concurrent_publishes_leave_one_whole_file_and_no_temp(tmp_path: Path) -> None:
    target = tmp_path / "test_runs.py"
    texts = {i: f"# builder {i}\n" + "x" * 4000 + f"\n# end {i}\n" for i in range(8)}
    barrier = threading.Barrier(len(texts))

    def publish(i: int) -> None:
        barrier.wait()
        for _ in range(20):
            publish_text(target, texts[i])

    with ThreadPoolExecutor(max_workers=len(texts)) as pool:
        for fut in [pool.submit(publish, i) for i in sorted(texts)]:
            fut.result(timeout=60)
    assert target.read_text(encoding="utf-8") in texts.values()
    assert [p.name for p in tmp_path.iterdir()] == ["test_runs.py"]


def test_identical_content_skips_the_write(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "suite.jsonl"
    publish_text(target, "same\n")

    def _no_replace(*_a):
        raise AssertionError("identical content must not be rewritten")

    monkeypatch.setattr(_publish.os, "replace", _no_replace)
    publish_text(target, "same\n")
    assert target.read_text(encoding="utf-8") == "same\n"


def test_a_failed_replace_leaves_no_temp_file_behind(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "suite.jsonl"
    publish_text(target, "old\n")

    def _boom(*_a):
        raise OSError("replace failed")

    monkeypatch.setattr(_publish.os, "replace", _boom)
    with pytest.raises(OSError):
        publish_text(target, "new\n")
    assert target.read_text(encoding="utf-8") == "old\n"
    assert [p.name for p in tmp_path.iterdir()] == ["suite.jsonl"]
