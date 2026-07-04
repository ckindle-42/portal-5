"""Tests for wiki write-back API — Phase P1.

Validates:
- propose_unit with provenance succeeds
- propose_unit without provenance is rejected
- confirm_unit promotes to canonical
- Idempotent: re-proposing same source updates
- list_proposed / reject_unit work
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from portal_wiki.core.store import load_unit, reset_canonical_dir, set_canonical_dir
from portal_wiki.core.writeback import (
    confirm_unit,
    list_proposed,
    propose_unit,
    reject_unit,
    reset_proposed_dir,
    set_proposed_dir,
)


class TestWritebackAPI:
    """Confirm-gated write-back API."""

    def test_propose_with_provenance(self, tmp_path):
        set_proposed_dir(tmp_path / "proposed")
        set_canonical_dir(tmp_path / "canonical")
        try:
            proposed = propose_unit(
                {
                    "title": "Test Unit",
                    "kind": "what",
                    "sources": [{"type": "code", "path": "test.py"}],
                    "body": "test body",
                },
                proposed_by="test-loop",
            )
            assert proposed.status == "proposed"
            assert proposed.unit_id
            assert proposed.proposed_by == "test-loop"
        finally:
            reset_proposed_dir()
            reset_canonical_dir()

    def test_reject_no_provenance(self, tmp_path):
        set_proposed_dir(tmp_path / "proposed")
        try:
            import pytest

            with pytest.raises(ValueError, match="must cite its source"):
                propose_unit({"title": "Bad", "kind": "what", "sources": []})
        finally:
            reset_proposed_dir()

    def test_reject_invalid_kind(self, tmp_path):
        set_proposed_dir(tmp_path / "proposed")
        try:
            import pytest

            with pytest.raises(ValueError, match="Invalid kind"):
                propose_unit(
                    {
                        "title": "Bad",
                        "kind": "invalid",
                        "sources": [{"type": "code", "path": "x.py"}],
                    }
                )
        finally:
            reset_proposed_dir()

    def test_confirm_promotes_to_canonical(self, tmp_path):
        set_proposed_dir(tmp_path / "proposed")
        set_canonical_dir(tmp_path / "canonical")
        try:
            proposed = propose_unit(
                {
                    "title": "Confirm Test",
                    "kind": "mixed",
                    "sources": [{"type": "spl", "path": "T1190"}],
                    "body": "confirmed body",
                },
            )
            assert proposed.status == "proposed"

            confirmed = confirm_unit(proposed.proposed_id)
            assert confirmed.status == "confirmed"

            # Now in canonical store
            unit = load_unit(confirmed.unit_id)
            assert unit is not None
            assert unit.title == "Confirm Test"
            assert unit.body == "confirmed body"
        finally:
            reset_proposed_dir()
            reset_canonical_dir()

    def test_auto_confirm(self, tmp_path):
        set_proposed_dir(tmp_path / "proposed")
        set_canonical_dir(tmp_path / "canonical")
        try:
            proposed = propose_unit(
                {
                    "title": "Auto Confirm",
                    "kind": "what",
                    "sources": [{"type": "code", "path": "x.py"}],
                    "body": "auto",
                },
                auto_confirm=True,
            )
            assert proposed.status == "confirmed"
            unit = load_unit(proposed.unit_id)
            assert unit is not None
        finally:
            reset_proposed_dir()
            reset_canonical_dir()

    def test_list_proposed(self, tmp_path):
        set_proposed_dir(tmp_path / "proposed")
        try:
            propose_unit(
                {"title": "P1", "kind": "what", "sources": [{"type": "code", "path": "a.py"}]}
            )
            propose_unit(
                {"title": "P2", "kind": "what", "sources": [{"type": "code", "path": "b.py"}]}
            )
            proposed = list_proposed()
            assert len(proposed) == 2
        finally:
            reset_proposed_dir()

    def test_reject_unit(self, tmp_path):
        set_proposed_dir(tmp_path / "proposed")
        try:
            proposed = propose_unit(
                {
                    "title": "Reject Me",
                    "kind": "what",
                    "sources": [{"type": "code", "path": "x.py"}],
                }
            )
            rejected = reject_unit(proposed.proposed_id)
            assert rejected.status == "rejected"
            assert len(list_proposed("proposed")) == 0
            assert len(list_proposed("rejected")) == 1
        finally:
            reset_proposed_dir()

    def test_confirm_idempotent(self, tmp_path):
        set_proposed_dir(tmp_path / "proposed")
        set_canonical_dir(tmp_path / "canonical")
        try:
            proposed = propose_unit(
                {
                    "title": "Idem",
                    "kind": "what",
                    "sources": [{"type": "code", "path": "x.py"}],
                    "body": "idem",
                }
            )
            c1 = confirm_unit(proposed.proposed_id)
            c2 = confirm_unit(proposed.proposed_id)
            assert c1.status == c2.status == "confirmed"
        finally:
            reset_proposed_dir()
            reset_canonical_dir()
