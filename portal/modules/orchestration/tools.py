"""Task-directory tools owned by the orchestration bite worker."""

from __future__ import annotations

import base64
import re
import shlex
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
        sandbox_url: str = "http://127.0.0.1:8914",
    ) -> None:
        self.task_dir = Path(task_dir).resolve()
        self.allowed_tools = frozenset(allowed_tools)
        self.readable_paths = frozenset(self._relative_path(path) for path in readable_paths)
        self.writable_paths = frozenset(self._relative_path(path) for path in writable_paths)
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
        target = self._resolve(path)
        if target.relative_to(self.task_dir).as_posix() not in self.readable_paths:
            return f"ERROR: {path} is not readable for this bite"
        if not target.is_file():
            return f"ERROR: cannot read {path}"
        with target.open("rb") as stream:
            content = stream.read(FILE_READ_LIMIT + 1)
        if len(content) > FILE_READ_LIMIT:
            return f"ERROR: {path} exceeds the {FILE_READ_LIMIT}-byte read limit"
        return content.decode("utf-8", errors="ignore")

    def file_write(self, path: str, content: str) -> str:
        if not isinstance(content, str):
            return "ERROR: content must be a string"
        encoded = content.encode("utf-8")
        if len(encoded) > FILE_WRITE_LIMIT:
            return f"ERROR: content exceeds the {FILE_WRITE_LIMIT}-byte write limit"
        target = self._resolve(path)
        relative = target.relative_to(self.task_dir).as_posix()
        if relative not in self.writable_paths:
            return f"ERROR: {path} is not writable for this bite"
        if target == self.task_dir or target.is_dir():
            return f"ERROR: {path} is a directory"
        current_size = target.stat().st_size if target.is_file() else 0
        additional_files = 0 if target.is_file() else 1
        if (
            _task_size(self.task_dir, additional_files) - current_size + len(encoded)
            > TASK_BYTES_LIMIT
        ):
            return f"ERROR: task data exceeds the {TASK_BYTES_LIMIT}-byte limit"
        target.parent.mkdir(parents=True, exist_ok=True)
        target = self._resolve(path)
        if target == self.task_dir or target.is_dir():
            return f"ERROR: {path} is a directory"
        target.write_bytes(encoded)
        return f"wrote {len(content)} chars to {path}"

    def pytest_run(self, args: str = "") -> str:
        try:
            selectors = _pytest_selectors(args, self.task_dir)
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

    def _resolve(self, path: str) -> Path:
        if not isinstance(path, str) or not path.strip():
            raise ValueError("relative path required")
        posix = Path(path)
        windows = PureWindowsPath(path)
        if posix.is_absolute() or windows.is_absolute() or windows.drive:
            raise ValueError("absolute paths are not allowed")
        if ".." in posix.parts or ".." in windows.parts:
            raise ValueError("parent traversal is not allowed")
        target = (self.task_dir / path).resolve()
        if not target.is_relative_to(self.task_dir):
            raise ValueError("path escapes the task directory")
        return target

    def _relative_path(self, path: str) -> str:
        return self._resolve(path).relative_to(self.task_dir).as_posix()


def _pytest_selectors(args: str, task_dir: Path) -> list[str]:
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
            selectors.append(_pytest_path_selector(token, task_dir))
    return selectors


def _append_pytest_option(token: str, selectors: list[str]) -> bool:
    allowed = {"-q", "-v", "-x", "--disable-warnings", "--tb=short", "--tb=line"}
    if token.startswith("-k=") or token in allowed or re.fullmatch(r"--maxfail=[1-9][0-9]*", token):
        selectors.append(token)
        return True
    if token.startswith("-"):
        raise ValueError(f"pytest option is not allowed: {token}")
    return False


def _pytest_path_selector(token: str, task_dir: Path) -> str:
    path_text, separator, node_id = token.partition("::")
    relative = Path(path_text or ".")
    windows = PureWindowsPath(path_text)
    if relative.is_absolute() or windows.is_absolute() or windows.drive:
        raise ValueError("pytest paths must be relative to the task directory")
    if ".." in relative.parts or ".." in windows.parts:
        raise ValueError("pytest paths cannot traverse to a parent directory")
    target = (task_dir / relative).resolve()
    if not target.is_relative_to(task_dir) or not target.exists():
        raise ValueError(f"pytest path is missing or outside the task directory: {path_text}")
    suffix = separator + node_id if separator else ""
    return target.relative_to(task_dir).as_posix() + suffix


def _task_snapshot(task_dir: Path, visible_paths: frozenset[str]) -> dict[str, str]:
    files: dict[str, str] = {}
    total = 0
    for relative in sorted(visible_paths):
        path = task_dir / relative
        if not path.exists():
            continue
        if path.is_symlink():
            raise ValueError(f"task data contains a symlink: {path.relative_to(task_dir)}")
        if not path.is_file():
            raise ValueError(f"task data path is not a file: {relative}")
        if len(files) >= TASK_FILE_LIMIT:
            raise ValueError(f"task data exceeds the {TASK_FILE_LIMIT}-file limit")
        content = path.read_bytes()
        total += len(content)
        if total > TASK_BYTES_LIMIT:
            raise ValueError(f"task data exceeds the {TASK_BYTES_LIMIT}-byte limit")
        files[path.relative_to(task_dir).as_posix()] = base64.b64encode(content).decode("ascii")
    return files


def _task_size(task_dir: Path, additional_files: int = 0) -> int:
    total = 0
    files = additional_files
    for path in task_dir.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"task data contains a symlink: {path.relative_to(task_dir)}")
        if not path.is_file():
            continue
        files += 1
        if files > TASK_FILE_LIMIT:
            raise ValueError(f"task data exceeds the {TASK_FILE_LIMIT}-file limit")
        total += path.stat().st_size
    return total


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
