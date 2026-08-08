"""Single-sourced JSON data-file loader.

Collapses the ~60 byte-identical per-module ``_load_data``/``_load_catalog``
copies that differed only in their data root (config/security,
config/inference, tests/data, tests/data/uat_catalog_*) — Q004 of
TASK_PORTAL_QUALITY_V1.

Pure stdlib (no portal imports) so MCP servers can use it without pulling
in ``portal.platform.inference`` (Rule 3). ``routing.py`` keeps its own
env/container-aware variant — the data root there is not repo-relative.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]


def load_data(rel_dir: str, name: str) -> Any:
    """Load ``<repo>/<rel_dir>/<name>.json`` as JSON.

    ``name`` is the full filename stem (the uat_catalog caller passes
    ``"uat_catalog_<group>"`` to reach ``tests/data/uat_catalog_<group>.json``).
    """
    path = _REPO_ROOT / rel_dir / f"{name}.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)
