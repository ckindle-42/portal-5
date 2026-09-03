"""T2 P1 — the CAD render GL→matplotlib fallback actually works.

O1: `matplotlib` was imported inside `_render_mesh_to_png`'s CPU fallback but
undeclared in `pyproject.toml`, so the fallback raised `ImportError` at exactly
the moment the GL path had failed and it was needed. This test forces the GL
path to fail and confirms the fallback reaches a PNG — the only way to prove
this class of fix, and the reason the original grep missed it.
"""

from __future__ import annotations

import numpy as np
import pytest

from portal.modules.cad.tools.cad_render_mcp import _render_mesh_to_png

trimesh = pytest.importorskip("trimesh")
pytest.importorskip("matplotlib")


@pytest.fixture
def cube_stl(tmp_path):
    p = tmp_path / "cube.stl"
    trimesh.creation.box(extents=(1, 1, 1)).export(str(p))
    return p


def test_gl_failure_falls_back_to_matplotlib(cube_stl, tmp_path, monkeypatch):
    # force every GL offscreen attempt to raise, the headless-container case
    monkeypatch.setattr(
        trimesh.Scene,
        "save_image",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no GL context")),
    )
    png = tmp_path / "out.png"
    note = _render_mesh_to_png(cube_stl, png, resolution=256)
    assert "matplotlib CPU fallback" in note
    assert png.is_file() and png.stat().st_size > 0
    # a real PNG signature, not a placeholder
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_gl_path_used_when_it_succeeds(cube_stl, tmp_path, monkeypatch):
    monkeypatch.setattr(
        trimesh.Scene, "save_image", lambda *a, **k: b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    )
    png = tmp_path / "out.png"
    note = _render_mesh_to_png(cube_stl, png, resolution=256)
    assert note == "rendered via trimesh offscreen GL"
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_numpy_import_is_available_for_stl_path():
    # numpy-stl ships as `stl`; the render path and mesh_validator both need it
    import stl  # noqa: F401

    assert np.__version__
