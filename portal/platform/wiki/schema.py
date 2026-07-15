"""Knowledge Unit schema — the canonical layer foundation.

Stack-agnostic: ZERO Portal-specific imports.  This is the extraction boundary.
Every unit is markdown + frontmatter with MANDATORY provenance (never-bloat rule).
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceRef:
    """A provenance source reference.  Every unit must have at least one."""

    type: str  # "code" | "design" | "spl" | "mitre" | "scenario" | "doc"
    path: str  # file path, URL, or identifier
    commit: str = ""  # git SHA (optional but recommended for code sources)
    section: str = ""  # heading/anchor within the source

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type, "path": self.path}
        if self.commit:
            d["commit"] = self.commit
        if self.section:
            d["section"] = self.section
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceRef:
        return cls(
            type=data.get("type", ""),
            path=data.get("path", ""),
            commit=data.get("commit", ""),
            section=data.get("section", ""),
        )


@dataclass
class KnowledgeUnit:
    """A canonical knowledge unit: markdown body + frontmatter.

    The foundation of the wiki.  Every unit carries provenance — a unit with
    empty `sources` is INVALID (the never-bloat rule).  The model may write
    prose; the CITATION is a deterministic fact, never a model assertion.
    """

    id: str
    kind: str  # "what" | "why" | "mixed"
    title: str
    sources: list[SourceRef]
    body: str = ""
    last_generated_commit: str = ""
    confidence: str = "high"  # "high" | "medium" | "low"
    tags: list[str] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.sources:
            raise ValueError(
                f"KnowledgeUnit '{self.id}' has no sources — "
                "every unit must cite its source (never-bloat rule)"
            )
        if self.kind not in ("what", "why", "mixed"):
            raise ValueError(f"Invalid kind '{self.kind}'; must be what|why|mixed")
        if self.confidence not in ("high", "medium", "low"):
            raise ValueError(f"Invalid confidence '{self.confidence}'; must be high|medium|low")
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_frontmatter(self) -> dict[str, Any]:
        """Serialize to YAML-compatible frontmatter dict."""
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "sources": [s.to_dict() for s in self.sources],
            "last_generated_commit": self.last_generated_commit,
            "confidence": self.confidence,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_markdown(self) -> str:
        """Serialize to markdown with YAML frontmatter."""
        import io

        import yaml

        buf = io.StringIO()
        buf.write("---\n")
        yaml.dump(self.to_frontmatter(), buf, default_flow_style=False, sort_keys=False)
        buf.write("---\n\n")
        buf.write(self.body)
        if not self.body.endswith("\n"):
            buf.write("\n")
        return buf.getvalue()

    @classmethod
    def from_markdown(cls, text: str) -> KnowledgeUnit:
        """Parse markdown with YAML frontmatter into a KnowledgeUnit."""
        import yaml

        match = re.match(r"^---\n(.*?\n)---\n\n?(.*)", text, re.DOTALL)
        if not match:
            raise ValueError("No YAML frontmatter found")

        fm = yaml.safe_load(match.group(1))
        body = match.group(2).strip()

        sources = [SourceRef.from_dict(s) for s in fm.get("sources", [])]
        if not sources:
            raise ValueError(f"Unit '{fm.get('id', '?')}' has no sources — invalid")

        return cls(
            id=fm["id"],
            kind=fm["kind"],
            title=fm["title"],
            sources=sources,
            body=body,
            last_generated_commit=fm.get("last_generated_commit", ""),
            confidence=fm.get("confidence", "high"),
            tags=fm.get("tags", []),
            created_at=fm.get("created_at", 0),
            updated_at=fm.get("updated_at", 0),
        )

    def content_hash(self) -> str:
        """Hash of the unit content for change detection."""
        return hashlib.sha256(
            f"{self.id}:{self.kind}:{self.title}:{self.body}".encode()
        ).hexdigest()[:16]
