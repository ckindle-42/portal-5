"""review_eval.stamp -- what a number was measured on.

Nineteen run reports in this lab are unstamped: none records the commit or the embedder it ran
on, so after the next engine change none is evidence. A ``Stamp`` is mandatory on every report;
an incomplete one is a hard error (``Stamp.problems``), not a warning.

Network access is injected (``get_json``) so the stamp logic is testable offline.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import HARNESS_VERSION

GetJson = Callable[[str], Mapping[str, Any]]
GitRunner = Callable[..., Any]


def canonical_hash(payload: Mapping[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Stamp:
    harness_version: str
    commit: str
    dirty: bool
    embedder_id: str
    model_digests: tuple[tuple[str, str], ...]
    config_hash: str
    corpus_snapshot: str
    policy: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "harness_version": self.harness_version,
            "commit": self.commit,
            "dirty": self.dirty,
            "embedder_id": self.embedder_id,
            "model_digests": [list(pair) for pair in self.model_digests],
            "config_hash": self.config_hash,
            "corpus_snapshot": self.corpus_snapshot,
            "policy": self.policy,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.to_dict())

    def problems(self) -> list[str]:
        out: list[str] = []
        if self.harness_version != HARNESS_VERSION:
            out.append(f"harness_version {self.harness_version!r} != {HARNESS_VERSION!r}")
        for name in ("commit", "embedder_id", "config_hash", "corpus_snapshot"):
            if not getattr(self, name):
                out.append(f"stamp.{name} is empty")
        if self.corpus_snapshot and not self.corpus_snapshot.startswith(("real:", "proxy:")):
            out.append(
                "stamp.corpus_snapshot must start with 'real:' or 'proxy:' (claims accept only real)"
            )
        return out


def git_state(repo: Path, run: GitRunner = subprocess.run) -> tuple[str, bool]:
    """(HEAD commit, working tree dirty?). A dirty tree is recorded, never hidden."""
    head = run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    status = run(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return head, bool(status)


def fetch_embedder_identity(get_json: GetJson, base_url: str) -> str:
    """The model identity the embedding service reports at ``/ready`` (the same contract the
    reviewer's own identity check reads)."""
    ready = get_json(f"{base_url.rstrip('/')}/ready")
    identity = ready.get("identity") or {}
    return str(identity.get("model") or "")


def fetch_model_digests(get_json: GetJson, base_url: str, models: list[str]) -> dict[str, str]:
    """Ollama digests for ``models`` via ``/api/tags``. A model the server does not list gets
    the digest ``"unlisted"`` -- visible, never silently omitted."""
    tags = get_json(f"{base_url.rstrip('/')}/api/tags")
    listed = {
        str(m.get("name") or m.get("model")): str(m.get("digest") or "")
        for m in tags.get("models") or []
    }
    return {model: listed.get(model) or "unlisted" for model in models}


def build_stamp(
    *,
    repo: Path,
    embedder_id: str,
    model_digests: Mapping[str, str],
    config: Mapping[str, Any],
    corpus_snapshot: str,
    policy: str,
    git: Callable[[Path], tuple[str, bool]] = git_state,
) -> Stamp:
    commit, dirty = git(repo)
    return Stamp(
        harness_version=HARNESS_VERSION,
        commit=commit,
        dirty=dirty,
        embedder_id=embedder_id,
        model_digests=tuple(sorted(model_digests.items())),
        config_hash=canonical_hash(config),
        corpus_snapshot=corpus_snapshot,
        policy=policy,
    )
