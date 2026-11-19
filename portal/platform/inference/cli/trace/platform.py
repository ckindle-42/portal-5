"""Section — the operator's OWUI preset-drift check run against the live Open WebUI."""

from __future__ import annotations

import sys

from .context import TraceContext, run_cmd
from .model import Hop, Status, short


def drift_presets(out: str) -> dict[str, list[str]]:
    """`DRIFT <preset>` blocks from the checker's stdout: one entry per drifted preset."""
    drifts: dict[str, list[str]] = {}
    current = ""
    for line in out.splitlines():
        if line.startswith("DRIFT "):
            current = line[6:].strip()
            drifts[current] = []
        elif current and line.startswith("    "):
            drifts[current].append(line.strip())
    return drifts


def run(ctx: TraceContext, portal: dict[str, object]) -> list[Hop]:
    """Seeded workspace/persona presets must still match the repo; seed skips existing ones."""
    script = ctx.repo_root / "scripts" / "check_owui_preset_drift.py"
    done = run_cmd([sys.executable, str(script)], timeout=120.0)
    out = (done.stdout or done.stderr).strip()
    if "nothing to compare" in out:
        return [Hop("owui preset sync", Status.WARN, short(out, 70), "presets compared")]
    drifts = drift_presets(out)
    if done.ok and not drifts and out.endswith("preset drift: none"):
        return [Hop("owui preset sync", Status.PASS, out.splitlines()[-1], "no drift")]
    hops = [
        Hop(f"drift {name}", Status.FAIL, "differs from the repo", "matches", " | ".join(lines))
        for name, lines in sorted(drifts.items())
    ]
    return hops or [
        Hop(
            "owui preset sync",
            Status.FAIL,
            short(out.splitlines()[-1] if out else done.error, 70),
            "no drift",
            short(out, 90),
        )
    ]
