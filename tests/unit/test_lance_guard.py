"""Regression tests for portal.platform.lance_guard.require_lance_dir
(TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2 A2).

The bug this guards: a previous run creates `/Volumes/<vol>/portal5_lance` on
the boot disk while `<vol>` is not mounted. The old implementation returned
success from a `p.is_dir()` short-circuit that ran *before* any mount check, and
also treated a plain `/Volumes/<vol>` directory as satisfying the guard. Both
are the exact state the module docstring says must fail.

A `tmp_path` test cannot place a path under a real unmounted `/Volumes/<vol>`,
so `os.path.ismount` / `Path.is_dir` are patched to reproduce the state
precisely: the tree exists on disk, the volume is not a mount.
"""

from __future__ import annotations

import os

import pytest

from portal.platform.lance_guard import LanceStoreUnavailableError, require_lance_dir


def _patch(monkeypatch, *, mounts: set[str], dirs: set[str]) -> None:
    monkeypatch.setattr(os.path, "ismount", lambda p: str(p) in mounts)
    import pathlib

    real_is_dir = pathlib.Path.is_dir
    monkeypatch.setattr(
        pathlib.Path,
        "is_dir",
        lambda self: str(self) in dirs or real_is_dir(self),
    )


def test_stray_tree_on_unmounted_volume_raises(monkeypatch):
    """The regression: lance dir AND volume dir both exist, volume not mounted."""
    _patch(
        monkeypatch,
        mounts=set(),
        dirs={"/Volumes/data01", "/Volumes/data01/portal5_lance"},
    )
    with pytest.raises(LanceStoreUnavailableError, match="is not mounted"):
        require_lance_dir("/Volumes/data01/portal5_lance")


def test_bare_volume_dir_on_boot_disk_raises(monkeypatch):
    """A plain /Volumes/<vol> directory (no mount) must not satisfy the guard."""
    _patch(monkeypatch, mounts=set(), dirs={"/Volumes/data01"})
    with pytest.raises(LanceStoreUnavailableError, match="is not mounted"):
        require_lance_dir("/Volumes/data01/portal5_lance")


def test_mounted_volume_passes(monkeypatch):
    _patch(
        monkeypatch,
        mounts={"/Volumes/data01"},
        dirs={"/Volumes/data01", "/Volumes/data01/portal5_lance"},
    )
    assert require_lance_dir("/Volumes/data01/portal5_lance") == "/Volumes/data01/portal5_lance"


def test_mounted_volume_store_dir_absent_but_parent_present(monkeypatch):
    _patch(monkeypatch, mounts={"/Volumes/data01"}, dirs={"/Volumes/data01"})
    assert require_lance_dir("/Volumes/data01/portal5_lance") == "/Volumes/data01/portal5_lance"


def test_local_path_existing_dir_passes(tmp_path):
    d = tmp_path / "portal5_lance"
    d.mkdir()
    assert require_lance_dir(str(d)) == str(d)


def test_local_path_missing_parent_raises(tmp_path):
    with pytest.raises(LanceStoreUnavailableError, match="does not exist"):
        require_lance_dir(str(tmp_path / "nope" / "portal5_lance"))
