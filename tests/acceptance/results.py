"""Backwards-compat shim — canonical home is tests/lib/results.py.

Existing acceptance section modules import from this path. New code
should import directly from tests.lib.results.
"""

from tests.lib.results import *  # noqa: F401, F403
from tests.lib.results import (  # noqa: F401 — explicit for static checkers
    _ICON,
    _PROGRESS_LOG,
    _ROUTING_LOG,
    R,
    _blocked,
    _classify,
    _emit,
    _git_sha,
    _load_prior_results,
    _log,
    _print_routing_summary,
    _verbose,
    _write_results,
    record,
)
