#!/usr/bin/env python3
"""Make oMLX's per-model sampling defaults equal the seat that serves the model.

The pipeline sends every seat's sampling explicitly, so pipeline traffic never
depends on these defaults. A client that talks to oMLX DIRECTLY does — the IDE
paths (``./launch.sh coder-reap288`` opens opencode straight at :8085, sending
no sampling at all). Without this, REAP-288 ran there on oMLX's global defaults
(temperature 1.0, top_k 0, repetition_penalty 1.0) instead of its seat's
0.6 / 20 / min_p 0.05 / 1.05.

oMLX honours per-model defaults in ``~/.omlx/model_settings.json`` (temperature,
top_p, top_k, min_p, repetition_penalty, presence_penalty, enable_thinking) for
any key a request omits — verified 2026-09-25 (a per-model top_k=1 collapsed a
request without top_k to one output across seeds).

For each oMLX-served model: its seats are every workspace/variant whose
model_hint resolves to it (a priority-10 alias or the raw oMLX id); bench-*
workspaces are instrumentation and do not count. A model with exactly ONE
production seat gets that seat's whole resolved sampling (production's own
resolver, think profile included) as its default. A model shared by several
production seats is left on oMLX's global defaults — no single seat speaks for
it — and reported. Keys this script wrote before but no longer
applies are removed; keys it never wrote are never touched. oMLX is restarted
only when the file changed.

Run by ``./launch.sh sync-config`` and ``./launch.sh coder-reap288``.
Usage: uv run python scripts/omlx_seat_defaults.py [--dry-run] [--no-restart]
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from portal.platform.inference.router.validation import _resolve_sampling_values  # noqa: E402

SETTINGS = Path.home() / ".omlx" / "model_settings.json"
STATE = Path.home() / ".portal5" / "omlx_seat_defaults.json"
#: Seat key -> oMLX ModelSettings field.
_FIELDS = {
    "temperature": "temperature",
    "top_p": "top_p",
    "top_k": "top_k",
    "min_p": "min_p",
    "repeat_penalty": "repetition_penalty",
    "presence_penalty": "presence_penalty",
}


def _seats(portal: dict):
    for ws_id, ws in (portal.get("workspaces") or {}).items():
        if not isinstance(ws, dict):
            continue
        if ws.get("model_hint"):
            yield ws_id, ws
        for vname, v in (ws.get("variants") or {}).items():
            merged = {**ws, **(v or {})}
            if merged.get("model_hint"):
                yield f"{ws_id}::{vname}", merged


def seat_defaults(portal: dict, backends: dict) -> tuple[dict[str, dict], list[str]]:
    """{omlx model id: {field: value}} plus human-readable conflict notes."""
    aliases: dict[str, str] = {}
    omlx_ids: set[str] = set()
    for b in backends.get("backends", []):
        if b.get("type") != "omlx":
            continue
        for m in b.get("models") or []:
            omlx_ids.add(m["id"] if isinstance(m, dict) else m)
        if b.get("priority") == 10:
            aliases.update(b.get("aliases") or {})
    per_model: dict[str, list[tuple[str, dict]]] = {}
    for seat_id, ws in _seats(portal):
        hint = ws["model_hint"]
        target = aliases.get(hint) or (hint if hint in omlx_ids else None)
        if not target:
            continue
        values = {_FIELDS[k]: v for k, v in _resolve_sampling_values(ws).items() if k in _FIELDS}
        if ws.get("think") is not None:
            values["enable_thinking"] = bool(ws["think"])
        per_model.setdefault(target, []).append((seat_id, values))
    out: dict[str, dict] = {}
    notes: list[str] = []
    for model, seats in per_model.items():
        prod = [(sid, v) for sid, v in seats if not sid.startswith("bench-")]
        if len(prod) == 1:
            out[model] = prod[0][1]
        elif prod:
            out[model] = {}
            notes.append(
                f"{model}: {len(prod)} production seats share it ({', '.join(s for s, _ in prod)}) "
                "— direct clients get oMLX's global defaults; the pipeline sends each seat's own"
            )
    return out, notes


def apply(defaults: dict[str, dict], dry_run: bool) -> bool:
    """Write the defaults; return True when the file changed."""
    data = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {"models": {}}
    models = data.setdefault("models", {})
    managed = json.loads(STATE.read_text()) if STATE.exists() else {}
    before = json.dumps(data, sort_keys=True)
    for model in set(managed) | set(defaults):
        entry = models.setdefault(model, {})
        for k in managed.get(model, []):
            if k not in defaults.get(model, {}):
                entry.pop(k, None)
        entry.update(defaults.get(model, {}))
        if not entry:
            models.pop(model, None)
    changed = json.dumps(data, sort_keys=True) != before
    if changed and not dry_run:
        shutil.copy2(SETTINGS, SETTINGS.with_name(SETTINGS.name + ".bak.seat-defaults"))
        SETTINGS.write_text(json.dumps(data, indent=2))
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({m: sorted(v) for m, v in defaults.items() if v}, indent=1))
    return changed


def main(argv: list[str]) -> int:
    if not SETTINGS.parent.exists():
        print("oMLX not installed on this host — nothing to sync")
        return 0
    portal = yaml.safe_load((REPO / "config" / "portal.yaml").read_text())
    backends = yaml.safe_load((REPO / "config" / "backends.yaml").read_text())
    defaults, notes = seat_defaults(portal, backends)
    for n in notes:
        print(f"  note: {n}")
    dry = "--dry-run" in argv
    changed = apply(defaults, dry)
    for m, v in sorted(defaults.items()):
        print(f"  {m}: {v or '(no agreed keys)'}")
    if not changed:
        print("oMLX per-model seat defaults already current")
        return 0
    print("oMLX per-model seat defaults " + ("WOULD change (dry run)" if dry else "updated"))
    if not dry and "--no-restart" not in argv:
        subprocess.run(
            ["brew", "services", "restart", "jundot/omlx/omlx"], capture_output=True, timeout=120
        )
        print("oMLX restarted to load them")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
