"""Launchd plists must not run serving jobs at Background priority.

macOS ran omlx-server at sched priority 4 with ProcessType Background,
dropping MoE decode ~56% (fixed in 3d17767ba: Standard).
"""

from __future__ import annotations

from pathlib import Path
from plistlib import load

import pytest

_LAUNCHD = Path("deploy/launchd")


@pytest.mark.parametrize("plist_path", sorted(_LAUNCHD.glob("*.plist")))
def test_no_background_on_serving_plists(plist_path: Path) -> None:
    dom = load(open(plist_path, "rb"))
    label: str = dom.get("Label", "")
    args: list[str] = dom.get("ProgramArguments", [])
    is_serving = label == "com.portal5.omlx" or any("serve" in a for a in args)

    if not is_serving:
        pytest.skip(f"{label}: maintenance job, allowed Background")

    process_type = dom.get("ProcessType", "not set")
    if process_type == "Background":
        pytest.fail(
            f"{plist_path.name} serves inference with ProcessType=Background: "
            "macOS lowers sched priority (MoE decode drops ~56%). Use Standard."
        )
