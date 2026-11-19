"""Section — the operator's OWUI preset-drift check run against the live Open WebUI."""

from __future__ import annotations

import sys

from .context import TraceContext, run_cmd
from .model import Hop, Status, short


def run(ctx: TraceContext, portal: dict[str, object]) -> list[Hop]:
    """Seeded workspace/persona presets must still match the repo; seed skips existing ones."""
    script = ctx.repo_root / "scripts" / "check_owui_preset_drift.py"
    done = run_cmd([sys.executable, str(script)], timeout=120.0)
    out = (done.stdout or done.stderr).strip()
    if "nothing to compare" in out:
        return [Hop("owui preset sync", Status.WARN, short(out, 70), "presets compared")]
    ok = done.ok and out.endswith("preset drift: none")
    last = short(out.splitlines()[-1] if out else done.error, 70)
    detail = "" if ok else short(out, 90)
    return [Hop("owui preset sync", Status.PASS if ok else Status.FAIL, last, "no drift", detail)]
