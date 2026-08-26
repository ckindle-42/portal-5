"""Policy: path jail (to the project dir), denylist, output truncation, host-exec gate."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_DENY = ["rm -rf /", "mkfs", "dd if="]
_NETWORK_COMMANDS = {"curl", "wget", "nc", "ssh", "pip", "pip3", "npm", "yarn"}
_READ_COMMANDS = {
    "cat",
    "file",
    "strings",
    "xxd",
    "hexdump",
    "readelf",
    "nm",
    "objdump",
    "llvm-objdump",
    "otool",
    "lipo",
    "codesign",
    "rabin2",
    "rizin",
    "r2",
    "radare2",
    "binwalk",
    "unblob",
    "yara",
    "ssdeep",
    "rg",
    "grep",
    "head",
    "tail",
    "sha256sum",
    "shasum",
    "md5sum",
    "stat",
    "ls",
    "find",
    "wc",
}


@dataclass
class Policy:
    job_root: Path  # the resolved project directory
    allow_network: bool = False
    allow_execution_of_artifacts: bool = False
    allow_host_exec: bool = False
    deny_command_substrings: list[str] = field(default_factory=lambda: list(_DEFAULT_DENY))
    extra_allowed_roots: list[Path] = field(default_factory=list)
    tool_output_chars: int = 24_000
    tool_timeout_sec: int = 120

    @property
    def allowed_roots(self) -> list[Path]:
        return [self.job_root.resolve()] + [p.resolve() for p in self.extra_allowed_roots]

    def resolve_path(self, raw: str) -> Path:
        candidate = (self.job_root / raw).resolve()
        for root in self.allowed_roots:
            if candidate == root or root in candidate.parents:
                return candidate
        raise PermissionError(
            f"Path {raw!r} -> {candidate}, outside allowed roots {self.allowed_roots}"
        )

    def check_bash(self, command: str) -> str | None:
        for pattern in self.deny_command_substrings:
            if pattern in command:
                return f"DENIED: command contains blocked substring {pattern!r}"
        if not self.allow_network:
            base = os.path.basename(re.split(r"[\s;|&]", command.strip())[0])
            if base in _NETWORK_COMMANDS:
                return f"DENIED: {base!r} requires allow_network policy"
        if not self.allow_execution_of_artifacts and "artifacts/" in command:
            first = os.path.basename(re.split(r"[\s;|&]", command.strip())[0])
            if first not in _READ_COMMANDS and first not in {"python3", "python", "bash", "sh"}:
                return "DENIED: executing artifacts requires allow_execution_of_artifacts policy"
            if first in {"python3", "python", "bash", "sh"} and "artifacts/" in command:
                return "DENIED: executing artifacts requires allow_execution_of_artifacts policy"
        return None

    def truncate(self, text: str) -> str:
        if len(text) <= self.tool_output_chars:
            return text
        half = self.tool_output_chars // 2
        return (
            text[:half]
            + f"\n\n... [TRUNCATED — {len(text)} chars total, showing first/last {half}] ...\n\n"
            + text[-half:]
        )
