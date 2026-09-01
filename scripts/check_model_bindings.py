#!/usr/bin/env python3
"""Verify every model binding resolves to a currently-installed Ollama tag.

TASK-LANE-CLOSEOUT-001 deleted a bench-* workspace's model out from under
4 personas' `model_pin` override without anyone catching it — 994 unit tests
and 74 validate_system.py checks all stayed green, since nothing checks that
`model_pin`/`model_hint` still resolves to an installed model.

Deliberately NOT a tests/unit/ check (CLAUDE.md: no live Ollama/network
there). A live gate, same family as scripts/smoke_stream.sh — run it before
trusting a delete batch, and again before push.

Checks every binding surface: config/portal.yaml workspaces[*].model_hint,
config/personas/*.yaml model_pin, config/backends.yaml aliases (the
omlx-shadow-shift keys), config/promptfoo/*.yaml providers[*].id.

Does NOT check `preferred_models`/`suggested_model` — confirmed dead
metadata, never consumed by the serving path.

A binding resolves if its tag matches an installed Ollama tag (case-insensitively
— Ollama's own tag lookup is case-folded, so ``:Q4_K_M`` and ``:q4_K_M`` are the
same model) OR an oMLX-served model id (``:8085/v1/models``) — omlx-* backends and
oMLX personas pin those and they never appear in Ollama's tag list.

Usage:
    python3 scripts/check_model_bindings.py                # full live gate
    python3 scripts/check_model_bindings.py --check-tag <t> # is <t> safe to delete?
    python3 scripts/check_model_bindings.py --ollama-url http://host:11434
    python3 scripts/check_model_bindings.py --omlx-url http://host:8085

Exit codes: 0 = all bindings resolve, 1 = at least one orphan found.
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def live_model_tags(ollama_url: str) -> set[str]:
    resp = httpx.get(f"{ollama_url}/api/tags", timeout=10)
    resp.raise_for_status()
    return {m["name"] for m in resp.json().get("models", [])}


def live_omlx_models(omlx_url: str) -> set[str]:
    """oMLX-served model ids (:8085/v1/models). Empty set if oMLX is unreachable —
    a bench box may run Ollama only, and an omlx-* binding is not an error there."""
    try:
        resp = httpx.get(f"{omlx_url}/v1/models", timeout=10)
        resp.raise_for_status()
        return {m["id"] for m in resp.json().get("data", [])}
    except httpx.HTTPError:
        return set()


Binding = tuple[str, str, str]


def _workspace_bindings(repo_root: Path) -> list[Binding]:
    portal_yaml = repo_root / "config" / "portal.yaml"
    if not portal_yaml.exists():
        return []
    cfg = yaml.safe_load(portal_yaml.read_text())
    return [
        (f"config/portal.yaml [{ws_id}]", "model_hint", ws["model_hint"])
        for ws_id, ws in (cfg.get("workspaces") or {}).items()
        if isinstance(ws, dict) and isinstance(ws.get("model_hint"), str)
    ]


def _persona_bindings(repo_root: Path) -> list[Binding]:
    out: list[Binding] = []
    for path in sorted(glob.glob(str(repo_root / "config" / "personas" / "*.yaml"))):
        p = Path(path)
        data = yaml.safe_load(p.read_text())
        if isinstance(data, dict) and isinstance(data.get("model_pin"), str):
            out.append((f"config/personas/{p.name}", "model_pin", data["model_pin"]))
    return out


def _backend_alias_bindings(repo_root: Path) -> list[Binding]:
    backends_yaml = repo_root / "config" / "backends.yaml"
    if not backends_yaml.exists():
        return []
    cfg = yaml.safe_load(backends_yaml.read_text())
    out: list[Binding] = []
    for backend in cfg.get("backends") or []:
        if not isinstance(backend, dict):
            continue
        bid = backend.get("id", "?")
        for alias_key in backend.get("aliases") or {}:
            out.append((f"config/backends.yaml [{bid}]", "aliases key", alias_key))
    return out


def _promptfoo_bindings(repo_root: Path) -> list[Binding]:
    out: list[Binding] = []
    prefix = "ollama:chat:"
    for path in sorted(glob.glob(str(repo_root / "config" / "promptfoo" / "*.yaml"))):
        p = Path(path)
        data = yaml.safe_load(p.read_text())
        if not isinstance(data, dict):
            continue
        for provider in data.get("providers") or []:
            pid = provider.get("id", "") if isinstance(provider, dict) else ""
            if pid.startswith(prefix):
                out.append((f"config/promptfoo/{p.name}", "providers[].id", pid[len(prefix) :]))
    return out


def collect_bindings(repo_root: Path = REPO_ROOT) -> list[Binding]:
    """Return (source_file, field, tag) for every live model-tag binding."""
    return [
        *_workspace_bindings(repo_root),
        *_persona_bindings(repo_root),
        *_backend_alias_bindings(repo_root),
        *_promptfoo_bindings(repo_root),
    ]


def find_orphans(bindings: list[Binding], live_tags: set[str]) -> list[Binding]:
    """A tag resolves if it matches an Ollama tag case-insensitively (Ollama's own
    lookup is case-folded) or an oMLX model id exactly (case matters there)."""
    ollama_folded = {t.lower() for t in live_tags}
    omlx_exact = {t for t in live_tags if "/" not in t and ":" not in t}  # oMLX ids
    return [
        (src, field, tag)
        for src, field, tag in bindings
        if tag.lower() not in ollama_folded and tag not in omlx_exact
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--omlx-url", default="http://localhost:8085")
    parser.add_argument(
        "--check-tag",
        help="Pre-delete check: report which bindings would break if this exact tag were removed.",
    )
    args = parser.parse_args()

    bindings = collect_bindings()

    if args.check_tag:
        hits = [(src, field, tag) for src, field, tag in bindings if tag == args.check_tag]
        if hits:
            print(f"UNSAFE TO DELETE — {args.check_tag!r} is bound:")
            for src, field, tag in hits:
                print(f"  {src}  ({field})")
            return 1
        print(f"safe — no binding references {args.check_tag!r}")
        return 0

    try:
        ollama_tags = live_model_tags(args.ollama_url)
    except httpx.HTTPError as exc:
        print(f"Cannot reach Ollama at {args.ollama_url}: {exc}", file=sys.stderr)
        return 1
    omlx_ids = live_omlx_models(args.omlx_url)
    live_tags = ollama_tags | omlx_ids

    orphans = find_orphans(bindings, live_tags)
    print(
        f"{len(bindings)} model binding(s) checked against {len(ollama_tags)} Ollama tag(s) "
        f"+ {len(omlx_ids)} oMLX model(s)."
    )
    if not orphans:
        print("PASS — every binding resolves to an installed model.")
        return 0

    print(f"FAIL — {len(orphans)} orphaned binding(s):")
    for src, field, tag in orphans:
        print(f"  {src}  ({field}) -> {tag!r} — NOT INSTALLED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
