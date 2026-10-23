"""Task-directory tools owned by the orchestration bite worker."""

from __future__ import annotations

import base64
import os
import re
import shlex
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path, PureWindowsPath
from typing import Any

import httpx

FILE_READ_LIMIT = 20_000
FILE_WRITE_LIMIT = 200_000
PYTEST_OUTPUT_LIMIT = 8_000
PYTEST_TIMEOUT_SECONDS = 180
TASK_DATA_DIRECTORY = "data"
TASK_FILE_LIMIT = 128
TASK_BYTES_LIMIT = 16 * 1024 * 1024
READ_TOOLS = frozenset({"file_read"})
ACTION_TOOLS = frozenset({"file_write", "pytest_run"})


def tool_schema(name: str) -> dict[str, Any]:
    """Return a client schema for one declared bite tool."""
    schemas: dict[str, dict[str, Any]] = {
        "file_read": _schema(
            name,
            "Read a UTF-8 text file from this bite task directory.",
            {"path": {"type": "string"}},
            ["path"],
        ),
        "file_write": _schema(
            name,
            "Write a UTF-8 text file inside this bite task directory.",
            {"path": {"type": "string"}, "content": {"type": "string"}},
            ["path", "content"],
        ),
        "pytest_run": _schema(
            name,
            "Run selected pytest tests inside this bite task directory without network access.",
            {"args": {"type": "string"}},
            [],
        ),
    }
    if name in schemas:
        return schemas[name]
    return _schema(
        name,
        "Call this tool only when it is supplied by the Pipeline for this bite.",
        {},
        [],
        additional_properties=True,
    )


def _schema(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
    *,
    additional_properties: bool = False,
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": additional_properties,
            },
        },
    }


class TaskToolExecutor:
    """Execute confined client tools against one task data directory."""

    def __init__(
        self,
        task_dir: Path,
        allowed_tools: tuple[str, ...],
        *,
        readable_paths: tuple[str, ...] = (),
        writable_paths: tuple[str, ...] = (),
        aliases: dict[str, str] | None = None,
        sandbox_url: str = "http://127.0.0.1:8914",
    ) -> None:
        self.task_dir = Path(task_dir).resolve()
        self.allowed_tools = frozenset(allowed_tools)
        self.readable_paths = frozenset(self._relative_path(path) for path in readable_paths)
        self.writable_paths = frozenset(self._relative_path(path) for path in writable_paths)
        # Input names as the bite prompt lists them (discount.py) resolve to their staged paths.
        self.aliases = {
            self._relative_path(name): self._relative_path(path)
            for name, path in (aliases or {}).items()
        }
        self.sandbox_url = sandbox_url.rstrip("/")

    def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        """Return a bounded tool result, including structured argument errors."""
        if name not in self.allowed_tools:
            return f"ERROR: tool {name} is not allowed for this bite"
        try:
            if name == "file_read":
                return self.file_read(**arguments)
            if name == "file_write":
                return self.file_write(**arguments)
            if name == "pytest_run":
                return self.pytest_run(**arguments)
            return f"ERROR: no task-directory executor for tool {name}"
        except TypeError as exc:
            return f"ERROR: bad args for {name}: {exc}"
        except Exception as exc:
            return f"ERROR: {name} failed: {type(exc).__name__}: {exc}"

    def file_read(self, path: str) -> str:
        relative = self._resolve(path)
        if relative not in self.readable_paths:
            return f"ERROR: {path} is not readable for this bite"
        try:
            content = _read_task_file(self.task_dir, relative, FILE_READ_LIMIT + 1)
        except FileNotFoundError:
            return f"ERROR: cannot read {path}"
        if len(content) > FILE_READ_LIMIT:
            return f"ERROR: {path} exceeds the {FILE_READ_LIMIT}-byte read limit"
        return content.decode("utf-8", errors="ignore")

    def file_write(self, path: str, content: str) -> str:
        if not isinstance(content, str):
            return "ERROR: content must be a string"
        encoded = content.encode("utf-8")
        if len(encoded) > FILE_WRITE_LIMIT:
            return f"ERROR: content exceeds the {FILE_WRITE_LIMIT}-byte write limit"
        relative = self._resolve(path)
        if relative not in self.writable_paths:
            return f"ERROR: {path} is not writable for this bite"
        current_size = _task_file_size(self.task_dir, relative)
        additional_files = 1 if current_size is None else 0
        if (
            _task_size(self.task_dir, additional_files) - (current_size or 0) + len(encoded)
            > TASK_BYTES_LIMIT
        ):
            return f"ERROR: task data exceeds the {TASK_BYTES_LIMIT}-byte limit"
        _write_task_file(self.task_dir, relative, encoded)
        return f"wrote {len(content)} chars to {path}"

    def pytest_run(self, args: str = "") -> str:
        try:
            selectors = _pytest_selectors(args, self.task_dir, self.aliases)
            payload = {
                "files": _task_snapshot(self.task_dir, self.readable_paths | self.writable_paths),
                "selectors": selectors,
                "write_paths": sorted(self.writable_paths),
                "timeout": PYTEST_TIMEOUT_SECONDS,
            }
            result = _sandbox_request(self.sandbox_url, payload)
            if not isinstance(result, dict):
                raise RuntimeError("sandbox returned a non-object response")
            for path, encoded in _returned_files(result).items():
                content = base64.b64decode(encoded, validate=True).decode("utf-8")
                copied = self.file_write(path, content)
                if copied.startswith("ERROR:"):
                    raise RuntimeError(f"sandbox copy-back rejected: {copied}")
            output = str(result.get("stdout", "")) + str(result.get("stderr", ""))
            if result.get("timed_out"):
                return f"ERROR: pytest timed out after {PYTEST_TIMEOUT_SECONDS}s\n{output[:PYTEST_OUTPUT_LIMIT]}"
            return f"exit_code={int(result.get('exit_code', -1))}\n{output[:PYTEST_OUTPUT_LIMIT]}"
        except (OSError, RuntimeError, UnicodeError, ValueError, httpx.HTTPError) as exc:
            return f"ERROR: pytest could not run: {type(exc).__name__}: {exc}"

    def _resolve(self, path: str) -> str:
        relative = self._relative_path(path)
        return self.aliases.get(relative, relative)

    def _relative_path(self, path: str) -> str:
        if not isinstance(path, str) or not path.strip():
            raise ValueError("relative path required")
        posix = Path(path)
        windows = PureWindowsPath(path)
        if posix.is_absolute() or windows.is_absolute() or windows.drive:
            raise ValueError("absolute paths are not allowed")
        if ".." in posix.parts or ".." in windows.parts:
            raise ValueError("parent traversal is not allowed")
        parts = tuple(part for part in posix.parts if part not in ("", "."))
        if not parts:
            raise ValueError("file path required")
        return Path(*parts).as_posix()


def _pytest_selectors(
    args: str, task_dir: Path, aliases: dict[str, str] | None = None
) -> list[str]:
    """Allow only local test paths and a small set of harmless pytest selectors."""
    if not isinstance(args, str):
        raise ValueError("pytest args must be a string")
    selectors: list[str] = []
    tokens = iter(shlex.split(args))
    for token in tokens:
        if token == "-k":
            expression = next(tokens, None)
            if expression is None or expression.startswith("-"):
                raise ValueError("pytest -k needs one expression")
            selectors.extend((token, expression))
            continue
        if not _append_pytest_option(token, selectors):
            selectors.append(_pytest_path_selector(token, task_dir, aliases or {}))
    return selectors


def _append_pytest_option(token: str, selectors: list[str]) -> bool:
    allowed = {"-q", "-v", "-x", "--disable-warnings", "--tb=short", "--tb=line"}
    if token.startswith("-k=") or token in allowed or re.fullmatch(r"--maxfail=[1-9][0-9]*", token):
        selectors.append(token)
        return True
    if token.startswith("-"):
        raise ValueError(f"pytest option is not allowed: {token}")
    return False


def _pytest_path_selector(token: str, task_dir: Path, aliases: dict[str, str]) -> str:
    path_text, separator, node_id = token.partition("::")
    path_text = aliases.get(path_text, path_text)
    relative = Path(path_text or ".")
    windows = PureWindowsPath(path_text)
    if relative.is_absolute() or windows.is_absolute() or windows.drive:
        raise ValueError("pytest paths must be relative to the task directory")
    if ".." in relative.parts or ".." in windows.parts:
        raise ValueError("pytest paths cannot traverse to a parent directory")
    normalized = Path(*(part for part in relative.parts if part not in ("", "."))).as_posix()
    try:
        with _open_task_path(task_dir, normalized or "."):
            pass
    except FileNotFoundError:
        raise ValueError(
            f"pytest path is missing or outside the task directory: {path_text}"
        ) from None
    suffix = separator + node_id if separator else ""
    return normalized + suffix


def _task_snapshot(task_dir: Path, visible_paths: frozenset[str]) -> dict[str, str]:
    files: dict[str, str] = {}
    total = 0
    for relative in sorted(visible_paths):
        try:
            content = _read_task_file(task_dir, relative)
        except FileNotFoundError:
            continue
        if len(files) >= TASK_FILE_LIMIT:
            raise ValueError(f"task data exceeds the {TASK_FILE_LIMIT}-file limit")
        total += len(content)
        if total > TASK_BYTES_LIMIT:
            raise ValueError(f"task data exceeds the {TASK_BYTES_LIMIT}-byte limit")
        files[relative] = base64.b64encode(content).decode("ascii")
    return files


def _task_size(task_dir: Path, additional_files: int = 0) -> int:
    with _open_task_root(task_dir) as root_fd:
        total, files = _directory_size(root_fd, "", additional_files)
    if files > TASK_FILE_LIMIT:
        raise ValueError(f"task data exceeds the {TASK_FILE_LIMIT}-file limit")
    return total


_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK


@contextmanager
def _open_task_root(task_dir: Path) -> Iterator[int]:
    descriptor = os.open(task_dir, _DIRECTORY_FLAGS)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def _open_task_parent(
    task_dir: Path, relative: str, *, create: bool = False
) -> Iterator[tuple[int, str]]:
    parts = Path(relative).parts
    if not parts:
        raise ValueError("file path required")
    with _open_task_root(task_dir) as root_fd:
        parent_fd = root_fd
        try:
            for component in parts[:-1]:
                if create:
                    with suppress(FileExistsError):
                        os.mkdir(component, dir_fd=parent_fd)
                child_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=parent_fd)
                if parent_fd != root_fd:
                    os.close(parent_fd)
                parent_fd = child_fd
            yield parent_fd, parts[-1]
        finally:
            if parent_fd != root_fd:
                os.close(parent_fd)


@contextmanager
def _open_task_path(task_dir: Path, relative: str) -> Iterator[int]:
    if relative == ".":
        with _open_task_root(task_dir) as root_fd:
            yield root_fd
        return
    with _open_task_parent(task_dir, relative) as (parent_fd, name):
        descriptor = os.open(name, _FILE_READ_FLAGS, dir_fd=parent_fd)
        try:
            yield descriptor
        finally:
            os.close(descriptor)


def _read_task_file(task_dir: Path, relative: str, limit: int | None = None) -> bytes:
    with _open_task_path(task_dir, relative) as descriptor:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"task data path is not a file: {relative}")
        chunks: list[bytes] = []
        remaining = limit
        while remaining is None or remaining > 0:
            chunk = os.read(
                descriptor, 64 * 1024 if remaining is None else min(64 * 1024, remaining)
            )
            if not chunk:
                break
            chunks.append(chunk)
            if remaining is not None:
                remaining -= len(chunk)
        return b"".join(chunks)


def _task_file_size(task_dir: Path, relative: str) -> int | None:
    try:
        with _open_task_path(task_dir, relative) as descriptor:
            metadata = os.fstat(descriptor)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"task data path is not a file: {relative}")
    return metadata.st_size


def _write_task_file(task_dir: Path, relative: str, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    with _open_task_parent(task_dir, relative, create=True) as (parent_fd, name):
        descriptor = os.open(name, flags, 0o666, dir_fd=parent_fd)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError(f"task data path is not a file: {relative}")
            view = memoryview(content)
            while view:
                view = view[os.write(descriptor, view) :]
        finally:
            os.close(descriptor)


def _directory_size(directory_fd: int, prefix: str, files: int) -> tuple[int, int]:
    total = 0
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            metadata = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError(f"task data contains a symlink: {relative}")
            if stat.S_ISDIR(metadata.st_mode):
                child_fd = os.open(entry.name, _DIRECTORY_FLAGS, dir_fd=directory_fd)
                try:
                    child_total, files = _directory_size(child_fd, relative, files)
                finally:
                    os.close(child_fd)
                total += child_total
            elif stat.S_ISREG(metadata.st_mode):
                descriptor = os.open(entry.name, _FILE_READ_FLAGS, dir_fd=directory_fd)
                try:
                    opened = os.fstat(descriptor)
                    if not stat.S_ISREG(opened.st_mode):
                        raise ValueError(f"task data path changed during scan: {relative}")
                    total += opened.st_size
                finally:
                    os.close(descriptor)
                files += 1
                if files > TASK_FILE_LIMIT:
                    return total, files
    return total, files


def _returned_files(result: dict[str, Any]) -> dict[str, str]:
    value = result.get("files", {})
    if not isinstance(value, dict) or not all(
        isinstance(path, str) and isinstance(content, str) for path, content in value.items()
    ):
        raise RuntimeError("sandbox returned invalid file data")
    return value


def _sandbox_request(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(trust_env=False, timeout=PYTEST_TIMEOUT_SECONDS + 10) as client:
        response = client.post(f"{url}/internal/orchestration/pytest", json=payload)
        response.raise_for_status()
        result = response.json()
    if not isinstance(result, dict):
        raise RuntimeError("sandbox returned a non-object response")
    return result
