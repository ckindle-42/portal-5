#!/usr/bin/env python3
"""Copy-truncate oversized Portal host logs into bounded gzip generations.

The log writer keeps its open file descriptor. This script therefore preserves
the log inode and truncates it in place only after a complete compressed copy
has been written and verified. Files that change while the snapshot is copied
are left untouched for the next hourly pass.
"""

from __future__ import annotations

import argparse
import fcntl
import glob
import gzip
import os
import shlex
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAX_MB = 100.0
DEFAULT_KEEP = 5
DEFAULT_LOG_PATTERNS = (
    "/opt/homebrew/var/log/ollama.log",
    "/opt/homebrew/var/log/omlx.log",
    "~/.portal5/logs/*.log",
)
_COPY_CHUNK_BYTES = 1024 * 1024
_MAX_TAIL_PASSES = 10


@dataclass(frozen=True)
class RotationConfig:
    max_bytes: int
    keep: int
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class RotationResult:
    path: Path
    action: str
    size_bytes: int = 0
    detail: str = ""


class SourceChangedError(Exception):
    """The log changed in a way that cannot be safely included in the archive."""


@dataclass
class RotationStage:
    path: Path
    staging: Path
    compressed: Path
    final_archive: Path
    staging_created: bool = False
    compressed_created: bool = False

    def cleanup(self) -> None:
        if self.staging_created and self.staging.exists():
            self.staging.unlink()
        if self.compressed_created and self.compressed.exists():
            self.compressed.unlink()


def _dotenv_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        name, raw_value = line.split("=", 1)
        if not name or not name.replace("_", "").isalnum() or not name[0].isalpha():
            continue
        try:
            parsed = shlex.split(raw_value, comments=True, posix=True)
        except ValueError:
            continue
        if parsed:
            values[name] = parsed[0]
    return values


def load_config(
    environ: Mapping[str, str] | None = None, *, env_file: Path | None = None
) -> RotationConfig:
    """Resolve process environment over .env values and built-in defaults."""
    effective = _dotenv_values(env_file or REPO_ROOT / ".env")
    effective.update(os.environ if environ is None else environ)
    try:
        max_mb = float(effective.get("LOG_ROTATE_MAX_MB") or DEFAULT_MAX_MB)
        keep = int(effective.get("LOG_ROTATE_KEEP") or DEFAULT_KEEP)
    except ValueError as exc:
        raise ValueError("LOG_ROTATE_MAX_MB and LOG_ROTATE_KEEP must be numeric") from exc
    if max_mb <= 0:
        raise ValueError("LOG_ROTATE_MAX_MB must be greater than zero")
    if keep < 1:
        raise ValueError("LOG_ROTATE_KEEP must be at least 1")

    raw_patterns = effective.get("LOG_ROTATE_FILES")
    patterns = (
        tuple(part.strip() for part in raw_patterns.split(";") if part.strip())
        if raw_patterns
        else DEFAULT_LOG_PATTERNS
    )
    return RotationConfig(max_bytes=int(max_mb * 1024 * 1024), keep=keep, patterns=patterns)


def discover_paths(config: RotationConfig) -> list[Path]:
    """Expand configured globs, preserving order and removing duplicates."""
    paths: dict[str, Path] = {}
    for pattern in config.patterns:
        expanded = os.path.expandvars(os.path.expanduser(pattern))
        matches = glob.glob(expanded)
        for match in matches or ([expanded] if not glob.has_magic(expanded) else []):
            path = Path(match)
            paths.setdefault(str(path), path)
    return list(paths.values())


def _copy_snapshot(source: Path, staging: Path, mode: int) -> int:
    try:
        with source.open("rb") as src, staging.open("xb") as dst:
            shutil.copyfileobj(src, dst, length=_COPY_CHUNK_BYTES)
            os.fchmod(dst.fileno(), mode | 0o200)
            dst.flush()
            os.fsync(dst.fileno())
    except OSError:
        staging.unlink(missing_ok=True)
        raise
    return staging.stat().st_size


def _gzip_snapshot(staging: Path, compressed: Path, filename: str, mode: int) -> None:
    try:
        with staging.open("rb") as src, compressed.open("xb") as raw:
            os.fchmod(raw.fileno(), mode | 0o200)
            with gzip.GzipFile(filename=filename, mode="wb", fileobj=raw, mtime=0) as archive:
                shutil.copyfileobj(src, archive, length=_COPY_CHUNK_BYTES)
            raw.flush()
            os.fsync(raw.fileno())
    except OSError:
        compressed.unlink(missing_ok=True)
        raise


def _verify_gzip(compressed: Path, expected_size: int) -> None:
    size = 0
    with gzip.open(compressed, "rb") as archive:
        while chunk := archive.read(_COPY_CHUNK_BYTES):
            size += len(chunk)
    if size != expected_size:
        raise OSError(f"archive verification failed: expected {expected_size} bytes, found {size}")


def _inspect_source(
    path: Path, max_bytes: int, keep: int
) -> tuple[os.stat_result | None, RotationStage | None, RotationResult | None]:
    try:
        if path.is_symlink():
            return None, None, RotationResult(path, "skip", detail="symbolic link")
        before = path.stat()
    except FileNotFoundError:
        return None, None, RotationResult(path, "skip", detail="missing")
    except OSError as exc:
        return None, None, RotationResult(path, "skip", detail=f"stat failed: {exc}")
    if not path.is_file():
        return None, None, RotationResult(path, "skip", detail="not a regular file")
    if before.st_size <= max_bytes:
        return None, None, RotationResult(path, "skip", before.st_size, "below threshold")
    if keep < 1:
        return (
            None,
            None,
            RotationResult(path, "error", before.st_size, "keep count must be at least 1"),
        )

    staging = Path(f"{path}.1")
    compressed = Path(f"{path}.1.gz.tmp")
    final_archive = Path(f"{path}.1.gz")
    if staging.exists() or compressed.exists():
        return (
            None,
            None,
            RotationResult(path, "skip", before.st_size, "staging file already exists"),
        )
    return before, RotationStage(path, staging, compressed, final_archive), None


def _append_gzip_member(path: Path, compressed: Path, start: int, end: int) -> None:
    remaining = end - start
    try:
        with path.open("rb") as source, compressed.open("ab") as raw:
            source.seek(start)
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as archive:
                while remaining:
                    chunk = source.read(min(_COPY_CHUNK_BYTES, remaining))
                    if not chunk:
                        raise SourceChangedError("log shrank while copying its appended tail")
                    archive.write(chunk)
                    remaining -= len(chunk)
            raw.flush()
            os.fsync(raw.fileno())
    except OSError as exc:
        raise SourceChangedError(f"could not capture appended tail: {exc}") from exc


def _capture_appended_tail(
    path: Path,
    compressed: Path,
    *,
    inode: int,
    copied_size: int,
    expected_mtime_ns: int,
) -> os.stat_result:
    """Append new log bytes as gzip members until the source is stable."""
    for _ in range(_MAX_TAIL_PASSES):
        try:
            current = path.stat()
        except OSError as exc:
            raise SourceChangedError(f"could not stat source after snapshot: {exc}") from exc
        if current.st_ino != inode or current.st_size < copied_size:
            raise SourceChangedError("source inode changed or log shrank during copy")
        if current.st_size == copied_size:
            if current.st_mtime_ns != expected_mtime_ns:
                raise SourceChangedError("source changed without an appended tail")
            return current

        target_size = current.st_size
        _append_gzip_member(path, compressed, copied_size, target_size)
        try:
            after_tail = path.stat()
        except OSError as exc:
            raise SourceChangedError(f"could not stat source after tail copy: {exc}") from exc
        if after_tail.st_ino != inode or after_tail.st_size < target_size:
            raise SourceChangedError("source inode changed or log shrank during tail copy")
        if after_tail.st_size == target_size and after_tail.st_mtime_ns != current.st_mtime_ns:
            raise SourceChangedError("source changed without appending while copying its tail")
        copied_size = target_size
        expected_mtime_ns = after_tail.st_mtime_ns

    raise SourceChangedError("log kept growing while its appended tail was captured")


def _shift_generations(stage: RotationStage, keep: int) -> None:
    for generation in range(keep, 0, -1):
        current = Path(f"{stage.path}.{generation}.gz")
        if not current.exists():
            continue
        if generation == keep:
            current.unlink()
        else:
            current.replace(Path(f"{stage.path}.{generation + 1}.gz"))
    stage.compressed.replace(stage.final_archive)
    stage.compressed_created = False


def _truncate_source(path: Path, inode: int, size: int, mtime_ns: int) -> str | None:
    try:
        current = path.stat()
        if current.st_ino != inode or current.st_size != size or current.st_mtime_ns != mtime_ns:
            return "source changed before truncate; archive kept, original retained"
        with path.open("r+b") as current_log:
            current_log.truncate(0)
            current_log.flush()
            os.fsync(current_log.fileno())
    except PermissionError:
        raise
    except OSError as exc:
        return f"could not truncate source; archive kept, original retained: {exc}"
    return None


def rotate_file(path: Path, *, max_bytes: int, keep: int = DEFAULT_KEEP) -> RotationResult:
    """Rotate one path without replacing its inode or truncating on copy failure."""
    before, stage, early = _inspect_source(path, max_bytes, keep)
    if early:
        return early
    assert before is not None and stage is not None
    try:
        copied_size = _copy_snapshot(path, stage.staging, before.st_mode & 0o777)
        stage.staging_created = True
        snapshot_stat = path.stat()
        if snapshot_stat.st_ino != before.st_ino or snapshot_stat.st_size < copied_size:
            raise SourceChangedError("source inode changed or log shrank during initial copy")
        _gzip_snapshot(stage.staging, stage.compressed, path.name, before.st_mode & 0o777)
        stage.compressed_created = True
        final_stat = _capture_appended_tail(
            path,
            stage.compressed,
            inode=before.st_ino,
            copied_size=copied_size,
            expected_mtime_ns=snapshot_stat.st_mtime_ns,
        )
        _verify_gzip(stage.compressed, final_stat.st_size)
        os.chmod(stage.compressed, before.st_mode & 0o777)

        _shift_generations(stage, keep)
        stage.staging.unlink()
        stage.staging_created = False
        truncate_error = _truncate_source(
            path, before.st_ino, final_stat.st_size, final_stat.st_mtime_ns
        )
        if truncate_error:
            return RotationResult(path, "error", before.st_size, truncate_error)
        return RotationResult(path, "rotated", before.st_size, f"saved {stage.final_archive}")
    except SourceChangedError as exc:
        return RotationResult(path, "skip", before.st_size, str(exc))
    except PermissionError as exc:
        return RotationResult(path, "skip", before.st_size, f"not writable: {exc}")
    except (OSError, EOFError) as exc:
        return RotationResult(path, "error", before.st_size, f"I/O error: {exc}")
    finally:
        # An already-published .1.gz is retained if truncation fails.
        stage.cleanup()


def _run(*, dry_run: bool = False, config: RotationConfig | None = None) -> int:
    config = config or load_config()
    paths = discover_paths(config)
    if not paths:
        print("SKIP no configured log paths matched")
        return 0

    lock_file = Path.home() / ".portal5" / "logs" / ".rotate_logs.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    with lock_file.open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("SKIP another log rotation run holds the lock")
            return 0
        errors = 0
        for path in paths:
            if dry_run:
                try:
                    size = path.stat().st_size
                except FileNotFoundError:
                    print(f"SKIP {path}: missing")
                    continue
                except OSError as exc:
                    print(f"SKIP {path}: stat failed: {exc}")
                    continue
                if path.is_file() and not path.is_symlink() and size > config.max_bytes:
                    print(f"WOULD ROTATE {path}: {size} bytes")
                else:
                    print(f"SKIP {path}: {size} bytes, threshold {config.max_bytes}")
                continue

            result = rotate_file(path, max_bytes=config.max_bytes, keep=config.keep)
            print(
                f"{result.action.upper()} {result.path}: {result.size_bytes} bytes; {result.detail}"
            )
            errors += result.action == "error"
        return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="list files over the threshold")
    args = parser.parse_args(argv)
    try:
        config = load_config()
    except ValueError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    return _run(dry_run=args.dry_run, config=config)


if __name__ == "__main__":
    raise SystemExit(main())
