"""Splash sweep engine — the promoted-sweep lane's operational preconditions.

SPLASH_SWEEP_ACCELERATION_V1 P7.2. When the compliance sweep lane is promoted
to the splash dialect (``config/compliance/sweep_engine.json``), two things
must hold at validation time, because the reuse verdict that justified the
promotion lives on them:

* the forwarder relay answers (the sweep addresses splash through
  ``http://127.0.0.1:8086``, not through the pipeline);
* the RUNNING splash process carries ``--max-context 32768`` — a serve line
  without the pin serves a different window than the one the bake-off measured,
  and a receipt would claim a context the engine did not provide.

When the config file is absent the sweep lane is the incumbent and the check
SKIPs: nothing promoted, nothing to assert. A check that asserted splash
health unconditionally would tax every push for a lane the decision declined
to promote.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from scripts.validation.registry import register

REPO_ROOT = Path(__file__).resolve().parents[2]
SWEEP_ENGINE_CONFIG = REPO_ROOT / "config" / "compliance" / "sweep_engine.json"


def _relay_answers() -> tuple[bool, str]:
    """True when something answers on the relay surface (200 or 401 both prove
    the relay forwards; 401 is splash's auth wall, not a dead transport)."""
    request = urllib.request.Request("http://127.0.0.1:8086/v1/models")
    key = os.environ.get("SPLASH_API_KEY")
    if key:
        request.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(request, timeout=8) as response:  # noqa: S310
            return True, f"relay answered {response.status}"
    except urllib.error.HTTPError as exc:
        return True, f"relay answered {exc.code} (auth wall — transport up)"
    except Exception as exc:  # noqa: BLE001 - anything else is a dead lane
        return False, f"relay unreachable: {type(exc).__name__}: {exc}"


def _serve_line_pin() -> tuple[bool, str]:
    """True when a running splash process carries the 32768 pin."""
    for proc in Path("/proc").glob("[0-9]*/cmdline") if Path("/proc").is_dir() else []:
        try:
            cmdline = proc.read_bytes().replace(b"\x00", b" ").decode(errors="replace")
        except OSError:
            continue
        if "splash" in cmdline and "--max-context 32768" in cmdline:
            return True, f"pid {proc.parent.name} carries --max-context 32768"
    # macOS has no /proc; fall back to ps.
    import subprocess

    try:
        out = subprocess.run(
            ["ps", "-axo", "command="], capture_output=True, text=True, timeout=15
        ).stdout
    except Exception as exc:  # noqa: BLE001 - an unreadable process table is not a pin
        return False, f"process table unreadable: {exc}"
    for line in out.splitlines():
        if "splash" in line and "--max-context 32768" in line:
            return True, "a running splash process carries --max-context 32768"
    return False, "no running splash process carries --max-context 32768"


@register(
    "splash_sweep_engine",
    "splash_sweep_engine. when the compliance sweep lane is promoted to splash, "
    "the forwarder answers and the running splash carries the 32768 serve-line pin",
    order=198,
)
def check_splash_sweep_engine() -> tuple[str, str, list[dict]]:
    if not SWEEP_ENGINE_CONFIG.is_file():
        return (
            "SKIP",
            "no config/compliance/sweep_engine.json — the sweep lane is the "
            "incumbent; nothing promoted, nothing to assert",
            [],
        )
    try:
        cfg = json.loads(SWEEP_ENGINE_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return "FAIL", f"sweep engine config unreadable: {exc}", []

    if cfg.get("dialect") != "openai-compat":
        return (
            "SKIP",
            f"sweep lane dialect is {cfg.get('dialect')!r}, not splash — nothing to assert",
            [],
        )

    findings: list[dict] = []
    relay_ok, relay_detail = _relay_answers()
    findings.append({"check": "forwarder answers", "ok": relay_ok, "detail": relay_detail})
    pin_ok, pin_detail = _serve_line_pin()
    findings.append({"check": "serve-line pin", "ok": pin_ok, "detail": pin_detail})

    if relay_ok and pin_ok:
        return "PASS", "promoted sweep lane: relay up, pin present", findings
    return (
        "FAIL",
        "promoted sweep lane cannot serve what its decision assumed "
        f"({'; '.join(f['detail'] for f in findings if not f['ok'])})",
        findings,
    )
