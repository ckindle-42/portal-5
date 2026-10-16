"""R2-29: no Ollama target that a tool workspace can reach is smaller than that workspace's
context_limit. Tags carry their baked window (ctxNk); a tag without one is listed as a known
exception until P-4 prevent (Phase B) pins its window."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]

# No known exceptions: every tool workspace's Ollama hint bakes its context_limit (P-4 prevent).
KNOWN_UNPINNED: set[tuple[str, str]] = set()


def _baked(tag: str) -> int | None:
    m = re.search(r"ctx(\d+)k", tag)
    return int(m.group(1)) * 1024 if m else None


def _ollama_models(backends: dict) -> set[str]:
    out: set[str] = set()
    for b in backends.get("backends") or []:
        if b.get("type") == "ollama":
            for m in b.get("models") or []:
                out.add(m.get("id") if isinstance(m, dict) else m)
    return out


def test_every_ollama_hint_has_a_window_at_least_its_context_limit() -> None:
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text()) or {}
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text()) or {}
    ollama = _ollama_models(backends)
    short: list[str] = []
    for base, ws in (portal.get("workspaces") or {}).items():
        entries = [(base, ws)] + [
            (f"{base}::{k}", v) for k, v in ((ws or {}).get("variants") or {}).items()
        ]
        for wid, d in entries:
            if not isinstance(d, dict) or d.get("model_hint") not in ollama:
                continue
            hint, limit = d["model_hint"], int(d.get("context_limit") or 0)
            window = _baked(hint)
            if window is None or (wid, hint) in KNOWN_UNPINNED:
                continue
            if window < limit:
                short.append(f"{wid}: {hint} window {window} < context_limit {limit}")
    assert not short, "\n".join(short)
