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
    reset_ledger_path,
    set_ledger_path,
)


class TestProvenanceLedger:
    def test_append_and_read(self, tmp_path):
        set_ledger_path(tmp_path / "ledger.jsonl")
        try:
            append_entry(
                episode_id="ep-1",
                scenario="kerberoast_to_da",
                red_model="red-model",
                blue_model="blue-model",
                capability_verdict="PROVEN",
                evidence_refs=["results/captures/red/x.json"],
                wiki_units_written=["unit-T1558.003-signature"],
                event="purple_run",
            )
            entries = read_ledger()
            assert len(entries) == 1
            e = entries[0]
            assert e.episode_id == "ep-1"
            assert e.scenario == "kerberoast_to_da"
            assert e.capability_verdict == "PROVEN"
            assert e.evidence_refs == ["results/captures/red/x.json"]
            assert e.wiki_units_written == ["unit-T1558.003-signature"]
            assert e.library_version  # auto-filled from pyproject.toml
            assert e.timestamp > 0
        finally:
            reset_ledger_path()

    def test_append_only_never_overwrites(self, tmp_path):
        set_ledger_path(tmp_path / "ledger.jsonl")
        try:
            append_entry(episode_id="ep-1", scenario="a", event="purple_run")
            append_entry(episode_id="ep-2", scenario="b", event="write_back")
            append_entry(episode_id="ep-3", scenario="c", event="purple_run")

            entries = read_ledger()
            assert len(entries) == 3
            assert [e.episode_id for e in entries] == ["ep-1", "ep-2", "ep-3"]
        finally:
            reset_ledger_path()

    def test_read_ledger_empty_when_no_file(self, tmp_path):
        set_ledger_path(tmp_path / "does_not_exist.jsonl")
        try:
            assert read_ledger() == []
        finally:
            reset_ledger_path()

    def test_skips_malformed_lines(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        set_ledger_path(path)
        try:
            append_entry(episode_id="ep-1", scenario="a", event="purple_run")
            with path.open("a") as f:
                f.write("not valid json\n")
            append_entry(episode_id="ep-2", scenario="b", event="purple_run")

            entries = read_ledger()
            assert len(entries) == 2
            assert [e.episode_id for e in entries] == ["ep-1", "ep-2"]
        finally:
            reset_ledger_path()

    def test_confirm_unit_appends_ledger_entry(self, tmp_path):
        from portal.platform.wiki.store import reset_canonical_dir, set_canonical_dir
        from portal.platform.wiki.writeback import (
            confirm_unit,
            propose_unit,
            reset_proposed_dir,
            set_proposed_dir,
        )

        set_canonical_dir(tmp_path / "canonical")
        set_proposed_dir(tmp_path / "proposed")
        set_ledger_path(tmp_path / "ledger.jsonl")
        try:
            proposed = propose_unit(
                {
                    "title": "Test Unit",
                    "kind": "mixed",
                    "sources": [{"type": "scenario", "path": "test:source"}],
                    "body": "test body",
                },
                proposed_by="test",
            )
            confirm_unit(proposed.proposed_id)

            entries = read_ledger()
            assert len(entries) == 1
            assert entries[0].event == "write_back"
            assert proposed.unit_id in entries[0].wiki_units_written
            assert "test:source" in entries[0].evidence_refs
        finally:
            reset_canonical_dir()
            reset_proposed_dir()
            reset_ledger_path()
