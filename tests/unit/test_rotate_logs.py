from __future__ import annotations

import gzip
from pathlib import Path

from scripts import rotate_logs


def test_rotation_compresses_snapshot_truncates_same_inode_and_keeps_bytes(tmp_path):
    path = tmp_path / "service.log"
    original = b"important service log line\n" * 50
    path.write_bytes(original)
    inode = path.stat().st_ino

    result = rotate_logs.rotate_file(path, max_bytes=100, keep=5)

    assert result.action == "rotated"
    assert result.size_bytes == len(original)
    assert path.stat().st_ino == inode
    assert path.stat().st_size == 0
    with gzip.open(f"{path}.1.gz", "rb") as archive:
        assert archive.read() == original
    assert not Path(f"{path}.1").exists()


def test_threshold_skips_file_at_or_below_limit(tmp_path):
    path = tmp_path / "small.log"
    path.write_bytes(b"x" * 100)

    result = rotate_logs.rotate_file(path, max_bytes=100)

    assert result.action == "skip"
    assert result.detail == "below threshold"
    assert path.read_bytes() == b"x" * 100
    assert not Path(f"{path}.1.gz").exists()


def test_generation_shift_prunes_only_oldest_to_keep_count(tmp_path):
    path = tmp_path / "service.log"
    path.write_bytes(b"new log contents" * 20)
    for generation in range(1, 6):
        with gzip.open(f"{path}.{generation}.gz", "wb") as archive:
            archive.write(f"generation-{generation}".encode())

    result = rotate_logs.rotate_file(path, max_bytes=10, keep=5)

    assert result.action == "rotated"
    assert gzip.open(f"{path}.1.gz", "rb").read() == b"new log contents" * 20
    assert gzip.open(f"{path}.2.gz", "rb").read() == b"generation-1"
    assert gzip.open(f"{path}.5.gz", "rb").read() == b"generation-4"
    assert not Path(f"{path}.6.gz").exists()


def test_keep_one_prunes_previous_archive_after_new_copy_is_ready(tmp_path):
    path = tmp_path / "service.log"
    path.write_bytes(b"replacement log" * 20)
    with gzip.open(f"{path}.1.gz", "wb") as archive:
        archive.write(b"old generation")

    result = rotate_logs.rotate_file(path, max_bytes=10, keep=1)

    assert result.action == "rotated"
    assert gzip.open(f"{path}.1.gz", "rb").read() == b"replacement log" * 20
    assert path.stat().st_size == 0


def test_unwritable_snapshot_skips_without_changing_original(tmp_path, monkeypatch):
    path = tmp_path / "readonly.log"
    original = b"keep the original intact" * 20
    path.write_bytes(original)

    def deny_copy(source: Path, staging: Path, mode: int) -> int:
        raise PermissionError("read-only destination")

    monkeypatch.setattr(rotate_logs, "_copy_snapshot", deny_copy)
    result = rotate_logs.rotate_file(path, max_bytes=10)

    assert result.action == "skip"
    assert "not writable" in result.detail
    assert path.read_bytes() == original
    assert not Path(f"{path}.1.gz").exists()


def test_source_growth_during_copy_is_added_as_an_archive_member(tmp_path, monkeypatch):
    path = tmp_path / "busy.log"
    original = b"initial log data" * 20
    path.write_bytes(original)
    copy_snapshot = rotate_logs._copy_snapshot

    def append_while_copying(source: Path, staging: Path, mode: int) -> int:
        size = copy_snapshot(source, staging, mode)
        with source.open("ab") as log:
            log.write(b"new concurrent line\n")
        return size

    monkeypatch.setattr(rotate_logs, "_copy_snapshot", append_while_copying)
    result = rotate_logs.rotate_file(path, max_bytes=10)

    assert result.action == "rotated"
    with gzip.open(f"{path}.1.gz", "rb") as archive:
        assert archive.read() == original + b"new concurrent line\n"
    assert path.read_bytes() == b""
    assert not Path(f"{path}.1").exists()


def test_source_shrink_during_copy_is_skipped_without_truncation(tmp_path, monkeypatch):
    path = tmp_path / "shrinking.log"
    original = b"initial log data" * 20
    path.write_bytes(original)
    copy_snapshot = rotate_logs._copy_snapshot

    def shrink_while_copying(source: Path, staging: Path, mode: int) -> int:
        size = copy_snapshot(source, staging, mode)
        source.write_bytes(b"short replacement")
        return size

    monkeypatch.setattr(rotate_logs, "_copy_snapshot", shrink_while_copying)
    result = rotate_logs.rotate_file(path, max_bytes=10)

    assert result.action == "skip"
    assert "shrank" in result.detail
    assert path.read_bytes() == b"short replacement"
    assert not Path(f"{path}.1.gz").exists()


def test_environment_configuration_overrides_dotenv_and_expands_file_patterns(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LOG_ROTATE_MAX_MB=25\n"
        "LOG_ROTATE_KEEP=3\n"
        'LOG_ROTATE_FILES="/var/log/one.log;~/.portal5/logs/*.log"\n',
        encoding="utf-8",
    )
    config = rotate_logs.load_config({"LOG_ROTATE_KEEP": "2"}, env_file=env_file)

    assert config.max_bytes == 25 * 1024 * 1024
    assert config.keep == 2
    assert config.patterns == ("/var/log/one.log", "~/.portal5/logs/*.log")
