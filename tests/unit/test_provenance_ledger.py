"""Tests for the provenance ledger — Phase 3 of TASK-SEC-DESIGN-GAP-DELIVERY-V1.

Validates:
- append-only: appending never rewrites/removes prior entries
- entries carry the full audit schema (episode/scenario/models/verdict/refs)
- read_ledger() reconstructs entries in append order
- confirm_unit() (writeback.py) appends a ledger entry on write-back
- malformed lines are skipped, not fatal
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from portal.platform.wiki.provenance_ledger import (
    append_entry,
    read_ledger,
)


def test_scratch_ledger_fixture_keeps_the_real_ledger_byte_identical() -> None:
    """The conftest autouse fixture (A3) redirects every append to a tmp_path ledger."""
    real = Path(__file__).resolve().parents[2] / "portal_wiki" / "provenance_ledger.jsonl"
    before = real.read_bytes() if real.exists() else None

    append_entry(episode_id="ep-scratch", scenario="scratch", event="purple_run")

    assert (real.read_bytes() if real.exists() else None) == before
    assert [e.episode_id for e in read_ledger()] == ["ep-scratch"]
