"""Query-level tool-schema preselection (P5-FUT-TOOL-PRESELECT).

See README.md in this directory for the full design. Feature-flagged
off by default (PORTAL5_TOOL_PRESELECT=0); requires per-workspace
opt-in in config/portal.yaml even when the global flag is on.
"""

from __future__ import annotations
