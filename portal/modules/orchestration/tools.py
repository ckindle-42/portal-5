"""Task-directory tools owned by the orchestration bite worker."""

from __future__ import annotations

import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path, PureWindowsPath
from typing import Any

FILE_READ_LIMIT = 20_000
FILE_WRITE_LIMIT = 200_000
PYTEST_OUTPUT_LIMIT = 8_000
PYTEST_TIMEOUT_SECONDS = 180
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
    """Execute the three host tools within one task directory."""

    def __init__(self, task_dir: Path, allowed_tools: tuple[str, ...]) -> None:
        self.task_dir = Path(task_dir).resolve()
        self.allowed_tools = frozenset(allowed_tools)

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
        if target == self.task_dir or target.is_dir():
            return f"ERROR: {path} is a directory"
        target.parent.mkdir(parents=True, exist_ok=True)
        target = self._resolve(path)
        if target == self.task_dir or target.is_dir():
            return f"ERROR: {path} is a directory"
        target.write_bytes(encoded)
        return f"wrote {len(content)} chars to {path}"

    def pytest_run(self, args: str = "") -> str:
        try:
            selectors = _pytest_selectors(args, self.task_dir)
            self._prepare_temp_dir()
            command = [
                *_sandbox_prefix(self.task_dir),
                sys.executable,
                "-m",
                "pytest",
                "-c",
                os.devnull,
                "--rootdir",
                str(self.task_dir),
                "--confcutdir",
                str(self.task_dir),
                "--log-file",
                str(self.task_dir / ".pytest-tmp" / "pytest.log"),
                "-q",
                "-p",
                "no:cacheprovider",
                "--import-mode=importlib",
                *selectors,
            ]
            env = {
                **os.environ,
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(self.task_dir),
                "TMPDIR": str(self.task_dir / ".pytest-tmp"),
            }
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=PYTEST_TIMEOUT_SECONDS,
                cwd=self.task_dir,
                env=env,
                check=False,
            )
            output = (result.stdout + result.stderr)[:PYTEST_OUTPUT_LIMIT]
            return f"exit_code={result.returncode}\n{output}"
        except subprocess.TimeoutExpired as exc:
            output = _timeout_output(exc)[:PYTEST_OUTPUT_LIMIT]
            return f"ERROR: pytest timed out after {PYTEST_TIMEOUT_SECONDS}s\n{output}"
        except (OSError, RuntimeError, ValueError) as exc:
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

    def _prepare_temp_dir(self) -> None:
        (self.task_dir / ".pytest-tmp").mkdir(exist_ok=True)


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


def _sandbox_prefix(task_dir: Path) -> list[str]:
    """Fail closed unless the host can isolate pytest from network and host writes."""
    system = platform.system()
    if system == "Darwin":
        executable = shutil.which("sandbox-exec")
        if executable is None:
            raise RuntimeError("sandbox-exec is required for network-isolated pytest")
        profile = f'(version 1) (allow default) (deny network*) (deny file-write* (require-not (subpath "{task_dir}")))'
        return [executable, "-p", profile]
    if system == "Linux":
        executable = shutil.which("bwrap")
        if executable is None:
            raise RuntimeError("bwrap is required for network-isolated pytest")
        return [
            executable,
            "--die-with-parent",
            "--unshare-net",
            "--ro-bind",
            "/",
            "/",
            "--bind",
            str(task_dir),
            str(task_dir),
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--chdir",
            str(task_dir),
        ]
    raise RuntimeError(f"network-isolated pytest is unsupported on {system}")


def _timeout_output(exc: subprocess.TimeoutExpired) -> str:
    output = exc.stdout or b""
    errors = exc.stderr or b""
    output_text = output.decode("utf-8", errors="replace") if isinstance(output, bytes) else output
    error_text = errors.decode("utf-8", errors="replace") if isinstance(errors, bytes) else errors
    return output_text + error_text
