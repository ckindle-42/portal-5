#!/usr/bin/env python3
"""Do the live Open WebUI workspace and persona presets match imports/openwebui/workspaces/*.json?

`./launch.sh up` (and `seed`) upsert Portal-owned presets in place. This reports any preset
that still differs, preset by preset. Exit 1 on drift; exit 0 when Open WebUI or its key is
unavailable (there is nothing to compare) or every preset matches. `./launch.sh reseed` remains
the destructive delete-and-recreate path.

    uv run python scripts/check_owui_preset_drift.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKSPACES = REPO / "imports" / "openwebui" / "workspaces"
Fetch = Callable[[str], dict | None]


def _env(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    env = REPO / ".env"
    for line in env.read_text().splitlines() if env.is_file() else []:
        key, sep, val = line.strip().partition("=")
        if sep and key == name:
            return val.strip().strip("'\"")
    return ""


def fetch_live(model_id: str) -> dict | None:
    """The live preset for `model_id`, or None when Open WebUI has none (a 404/401)."""
    base = os.environ.get("OWUI_URL") or f"http://localhost:{_env('OPENWEBUI_PORT') or '8080'}"
    req = urllib.request.Request(
        f"{base}/api/v1/models/model?id={urllib.parse.quote(model_id)}",
        headers={"Authorization": f"Bearer {_env('OWUI_API_KEY')}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            body = json.load(resp)
    except urllib.error.HTTPError:
        return None
    return body if isinstance(body, dict) and body.get("id") == model_id else None


def drift(expected: dict, live: dict | None) -> list[str]:
    """Differences between a seeded preset file and the live preset (empty = in sync)."""
    if live is None:
        return ["missing from Open WebUI"]
    out = []
    if expected.get("name") != live.get("name"):
        out.append(f"name: {live.get('name')!r} != {expected.get('name')!r}")
    for k, want in (expected.get("params") or {}).items():
        have = (live.get("params") or {}).get(k)
        if have != want:
            out.append(f"params.{k}: live {str(have)[:70]!r} != file {str(want)[:70]!r}")
    want_tools = (expected.get("meta") or {}).get("toolIds") or []
    if sorted((live.get("meta") or {}).get("toolIds") or []) != sorted(want_tools):
        out.append(
            f"meta.toolIds: live {(live.get('meta') or {}).get('toolIds')} != file {want_tools}"
        )
    return out


def expected_personas(personas: Path = REPO / "config" / "personas") -> list[dict]:
    """The preset each persona file seeds — the seeder's own builder, so the expectation
    cannot diverge from what a seed writes (variant tool resolution and skips included)."""
    import importlib.util

    import yaml

    owi_spec = importlib.util.spec_from_file_location(
        "openwebui_init", REPO / "scripts" / "openwebui_init.py"
    )
    owi = importlib.util.module_from_spec(owi_spec)
    owi_spec.loader.exec_module(owi)
    uwt_spec = importlib.util.spec_from_file_location(
        "uwt", REPO / "scripts" / "update_workspace_tools.py"
    )
    uwt = importlib.util.module_from_spec(uwt_spec)
    uwt_spec.loader.exec_module(uwt)
    ws_tools = uwt.load_workspace_raw_tools()
    prompts = REPO / "portal" / "modules" / "eval" / "persona_matrix" / "prompts"
    out = []
    for f in sorted(personas.glob("*.yaml")):
        persona = yaml.safe_load(f.read_text()) or {}
        payload = owi.persona_preset_payload(persona, f.stem, ws_tools, prompts)
        if payload is not None:
            out.append(payload)
    return out


def workspace_ids() -> set[str]:
    import yaml

    return set(yaml.safe_load((REPO / "config" / "portal.yaml").read_text())["workspaces"])


def shadowed_personas(expected: list[dict] | None = None) -> list[str]:
    """Personas whose slug is also a workspace id: Open WebUI already has a model of that id
    (the pipeline's), so the seeder skips the persona ('already registered') and it never
    reaches users. Reported, not drift."""
    ws = workspace_ids()
    return sorted(
        e["id"]
        for e in (expected if expected is not None else expected_personas())
        if e["id"] in ws
    )


def check_personas(
    fetch: Fetch = fetch_live, expected: list[dict] | None = None
) -> dict[str, list[str]]:
    exp_all = expected if expected is not None else expected_personas()
    shadowed = set(shadowed_personas(exp_all))
    result = {}
    for exp in (e for e in exp_all if e["id"] not in shadowed):
        live = fetch(exp["id"])
        if d := drift(exp, live):
            if live is not None and live.get("base_model_id") != exp["base_model_id"]:
                d.append(
                    f"base_model_id: live {live.get('base_model_id')!r} != file {exp['base_model_id']!r}"
                )
            result[exp["id"]] = d
    return result


def check(fetch: Fetch = fetch_live, workspaces: Path = WORKSPACES) -> dict[str, list[str]]:
    result = {}
    for f in sorted(workspaces.glob("workspace_*.json")):  # not workspaces_all.json (a bundle)
        exp = json.loads(f.read_text())
        if d := drift(exp, fetch(exp["id"])):
            result[exp["id"]] = d
    return result


def main() -> int:
    if not _env("OWUI_API_KEY"):
        print("owui preset drift: no OWUI_API_KEY, nothing to compare")
        return 0
    try:
        found = check()
    except (urllib.error.URLError, OSError) as e:
        print(f"owui preset drift: Open WebUI unreachable ({e}), nothing to compare")
        return 0
    expected = expected_personas()
    personas = check_personas(expected=expected)
    if shadowed := shadowed_personas(expected):
        print(
            f"info: {len(shadowed)} persona(s) share a workspace id and are never seeded: {', '.join(shadowed)}"
        )
    found = {**found, **{f"persona:{k}": v for k, v in personas.items()}}
    for ws, diffs in found.items():
        print(f"DRIFT {ws}")
        for d in diffs:
            print(f"    {d}")
    if found:
        print(
            f"\n{len(found)} Open WebUI preset(s) differ from the repo: "
            "./launch.sh up updates Portal presets in place"
        )
        return 1
    print("owui preset drift: none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
