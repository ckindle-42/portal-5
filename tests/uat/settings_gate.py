"""Portal 5 UAT — settings-delivery gate, run before any section.

A UAT verdict means nothing if the model under test is not the one configured,
or is not running with the settings configured. On 2026-09-25 all three were
found silently broken: every Ollama seat's sampling was dropped at Ollama's
/v1 (fixed by ollama_native.OllamaNativeTransport), two coding variants were
served a different model because their hint was unregistered, and the harness
sent oMLX a repeat_penalty key it ignores. None of it failed loudly. This gate
refuses to start a UAT while any of that class is present:

  1. engine contract — the values Portal sends reach the model on the RUNNING
     Ollama and oMLX versions (scripts/engine_contract_check.py --if-changed:
     seconds when already proven for these versions, ~3 min otherwise);
  2. routing — no seat's model_hint is absent or unroutable (the router would
     otherwise serve backend.models[0], a different model, and log a warning);
  3. OWUI — Open WebUI injects no sampling of its own. The pipeline lets a
     caller's values win, so an OWUI default temperature/top_k (admin default
     model params, a model's params, the user's chat params) would silently
     override every seat's configured sampling.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import httpx

from tests.uat.config import OPENWEBUI_URL

REPO = Path(__file__).resolve().parents[2]
SAMPLING_PARAMS = frozenset(
    {
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "repeat_penalty",
        "presence_penalty",
        "frequency_penalty",
        "seed",
        "mirostat",
    }
)
ROUTING_KINDS = frozenset({"hint_unroutable", "hint_absent", "hint_unregistered"})


def _contract_problems() -> list[str]:
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "engine_contract_check.py"), "--if-changed"],
        capture_output=True,
        text=True,
        timeout=3600,
    )
    if r.returncode == 0:
        return []
    tail = "\n".join(line for line in r.stdout.splitlines() if "FAIL" in line or "CANNOT" in line)
    return [f"engine contract rc={r.returncode}: {tail or r.stdout[-400:]}"]


def _routing_problems() -> list[str]:
    from tests.wfe.settings_audit import run_audit

    report = run_audit()
    return [
        f"{v['workspace']}: {v['kind']} — {v['detail']}"
        for v in report["violations"]
        if v["kind"] in ROUTING_KINDS and not v["workspace"].startswith("bench-")
    ]


def _sampling_in(params: dict | None) -> list[str]:
    return sorted(k for k in (params or {}) if k in SAMPLING_PARAMS)


def _owui_problems(token: str) -> list[str]:
    h = {"Authorization": f"Bearer {token}"}
    out: list[str] = []
    with httpx.Client(base_url=OPENWEBUI_URL, headers=h, timeout=20) as c:
        cfg = c.get("/api/v1/configs/models").json()
        if keys := _sampling_in(cfg.get("DEFAULT_MODEL_PARAMS")):
            out.append(f"OWUI admin DEFAULT_MODEL_PARAMS sets {keys} for every model")
        user = c.get("/api/v1/users/user/settings").json() or {}
        if keys := _sampling_in((user.get("ui") or {}).get("params")):
            out.append(f"OWUI user chat params set {keys} for every chat")
        page, seen = 1, 0
        while True:  # /api/v1/models/list pages 30 at a time ({"items", "total"})
            body = c.get("/api/v1/models/list", params={"page": page}).json() or {}
            items = body.get("items") or []
            for m in items:
                if keys := _sampling_in(m.get("params")):
                    out.append(f"OWUI model {m.get('id')} params set {keys}")
            seen += len(items)
            if not items or seen >= int(body.get("total") or 0):
                break
            page += 1
    return out


def settings_gate(token: str) -> list[str]:
    """Every reason the UAT would measure something other than the configured
    seat. Empty = safe to run."""
    problems: list[str] = []
    for label, check in (
        ("contract", _contract_problems),
        ("routing", _routing_problems),
        ("owui", lambda: _owui_problems(token)),
    ):
        try:
            problems += check()
        except Exception as e:  # a gate that cannot run must say so, not pass
            problems.append(f"{label} check could not run: {type(e).__name__}: {e}")
    return problems
