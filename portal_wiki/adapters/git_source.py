"""Git source connector — wires SourceConnector to the repo.

Portal-5 specific.  Walks the repo for .py modules and docs/.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from portal_wiki.core.interfaces import SourceConnector


class GitSourceConnector(SourceConnector):
    """Source connector wired to the portal-5 git repo."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()

    def iter_sources(self) -> list[dict[str, Any]]:
        """Walk the repo for source files."""
        sources = []

        # Python modules
        for py_file in sorted(self.repo_root.rglob("*.py")):
            rel = py_file.relative_to(self.repo_root)
            parts = rel.parts
            # Skip test results, __pycache__, .git
            if any(p.startswith(".") or p == "__pycache__" or p == "results" for p in parts):
                continue
            if py_file.stat().st_size > 0:
                sources.append(
                    {
                        "type": "code",
                        "path": str(rel),
                        "language": "python",
                    }
                )

        # Markdown docs
        for md_file in sorted(self.repo_root.glob("docs/*.md")):
            rel = md_file.relative_to(self.repo_root)
            sources.append(
                {
                    "type": "design",
                    "path": str(rel),
                    "language": "markdown",
                }
            )

        # CLAUDE.md
        claude = self.repo_root / "CLAUDE.md"
        if claude.exists():
            sources.append(
                {
                    "type": "design",
                    "path": "CLAUDE.md",
                    "language": "markdown",
                }
            )

        # Design docs
        for md_file in sorted(self.repo_root.rglob("DESIGN_*.md")):
            rel = md_file.relative_to(self.repo_root)
            if ".git" not in str(rel):
                sources.append(
                    {
                        "type": "design",
                        "path": str(rel),
                        "language": "markdown",
                    }
                )

        return sources

    def read_source(self, path: str) -> str:
        """Read a source file by relative path."""
        full_path = self.repo_root / path
        if not full_path.exists():
            raise FileNotFoundError(f"Source not found: {path}")
        return full_path.read_text(encoding="utf-8", errors="replace")

    def get_current_commit(self) -> str:
        """Get the current git HEAD SHA."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip()[:12]
        except Exception:
            return "unknown"
