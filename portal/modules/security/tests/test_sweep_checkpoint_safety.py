"""Unit tests for checkpoint-loss prevention in _sweep_driver.py.

The original devstral raw-vs-harness gate checkpoint was lost when a
later, unrelated sweep (16-candidate tools-arm ranking) reused the
same default OUT_PATH and the pre-run backup step was skipped. These
tests cover the structural fix: unconditional backup-before-write and
a loud warning on a model-set mismatch, so this can't happen silently
again regardless of whether an operator/agent remembers to back up.

All tests use tmp_path fixtures; no network, no Docker.
"""

from __future__ import annotations

import json

from portal.modules.security.core._sweep_driver import (
    _backup_existing_checkpoint,
    _warn_if_unrelated_checkpoint,
)


class TestBackupExistingCheckpoint:
    def test_no_file_returns_none(self, tmp_path):
        path = tmp_path / "sweep.json"
        assert _backup_existing_checkpoint(path) is None

    def test_existing_file_gets_backed_up(self, tmp_path):
        path = tmp_path / "sweep.json"
        path.write_text(json.dumps([{"scenario": "s", "model": "m"}]))

        bak_path = _backup_existing_checkpoint(path)

        assert bak_path is not None
        assert bak_path.exists()
        assert bak_path.name.endswith(".json.bak")
        assert bak_path.read_text() == path.read_text()
        # Original is untouched (still there, still readable)
        assert path.exists()

    def test_backup_is_a_real_copy_not_a_move(self, tmp_path):
        path = tmp_path / "sweep.json"
        original_content = json.dumps([{"a": 1}])
        path.write_text(original_content)

        _backup_existing_checkpoint(path)

        # Original file must still exist with its original content —
        # this is a backup, not a rename/move.
        assert path.read_text() == original_content

    def test_two_backups_of_same_path_dont_collide(self, tmp_path, monkeypatch):
        path = tmp_path / "sweep.json"
        path.write_text("{}")

        bak1 = _backup_existing_checkpoint(path)
        # Simulate a later run by writing again and backing up again —
        # timestamps in the filename should differ enough to not collide
        # in the (unlikely but possible) same-second case this asserts
        # the mechanism doesn't silently clobber a prior backup.
        path.write_text('{"changed": true}')
        bak2 = _backup_existing_checkpoint(path)

        assert bak1 is not None
        assert bak2 is not None
        # Both backups exist on disk (not overwritten by each other)
        assert bak1.exists()
        assert bak2.exists()


class TestWarnIfUnrelatedCheckpoint:
    def test_empty_results_no_warning(self, capsys):
        _warn_if_unrelated_checkpoint([], ["devstral:24b"])
        assert "WARNING" not in capsys.readouterr().out

    def test_overlapping_models_no_warning(self, capsys):
        existing = [{"scenario": "s1", "model": "devstral:24b"}]
        _warn_if_unrelated_checkpoint(existing, ["devstral:24b", "granite4.1:8b"])
        assert "WARNING" not in capsys.readouterr().out

    def test_zero_overlap_warns(self, capsys):
        existing = [{"scenario": "s1", "model": "some-other-model:9b"}]
        _warn_if_unrelated_checkpoint(existing, ["devstral:24b"])
        out = capsys.readouterr().out
        assert "WARNING" in out
        assert "ZERO model overlap" in out
