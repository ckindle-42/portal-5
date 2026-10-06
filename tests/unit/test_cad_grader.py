"""Unit tests for the sealed gauntlet v2 grader (tests/benchmarks/cad_grader.py)."""

from __future__ import annotations

import pytest

trimesh = pytest.importorskip("trimesh")

from tests.benchmarks import cad_grader as g  # noqa: E402


@pytest.fixture
def truth(monkeypatch):
    monkeypatch.setitem(
        g.GAUNTLET_V2_TRUTH,
        "unit_box",
        {"bbox": [5.0, 10.0, 20.0], "volume": 1000.0, "vol_tol": 0.01, "genus": 0},
    )
    monkeypatch.setitem(
        g.GAUNTLET_V2_TRUTH,
        "unit_ring",
        {"bbox": [4.0, 20.0, 20.0], "volume": 0.0, "vol_tol": 1.0, "genus": 1},
    )


def _export(mesh, tmp_path, name):
    p = tmp_path / f"{name}.stl"
    mesh.export(p)
    return p


def test_pass_on_exact_box(truth, tmp_path):
    p = _export(trimesh.creation.box(extents=(20, 10, 5)), tmp_path, "box")
    r = g.grade_mesh("unit_box", p)
    assert r["verdict"] == "PASS" and r["score"] == 1.0


def test_bbox_is_orientation_agnostic(truth, tmp_path):
    p = _export(trimesh.creation.box(extents=(5, 20, 10)), tmp_path, "box_rot")
    assert g.grade_mesh("unit_box", p)["checks"]["bbox"] is True


def test_wrongsize_on_wrong_thickness(truth, tmp_path):
    p = _export(trimesh.creation.box(extents=(20, 10, 8)), tmp_path, "thick")
    r = g.grade_mesh("unit_box", p)
    assert r["verdict"] == "WRONGSIZE" and r["checks"]["bbox"] is False


def test_genus_counts_through_hole(truth, tmp_path):
    ring = trimesh.creation.annulus(r_min=4, r_max=10, height=4, sections=64)
    r = g.grade_mesh("unit_ring", _export(ring, tmp_path, "ring"))
    assert r["measured"]["genus"] == 1 and r["checks"]["genus"] is True


def test_invalid_on_two_bodies(truth, tmp_path):
    a = trimesh.creation.box(extents=(20, 10, 5))
    bb = trimesh.creation.box(extents=(20, 10, 5))
    bb.apply_translation((100, 0, 0))
    r = g.grade_mesh("unit_box", _export(trimesh.util.concatenate([a, bb]), tmp_path, "two"))
    assert r["verdict"] == "INVALID" and r["score"] == 0.0


def test_missing_and_unreadable(truth, tmp_path):
    assert g.grade_mesh("unit_box", None)["verdict"] == "MISSING"
    bad = tmp_path / "bad.stl"
    bad.write_text("not a mesh")
    assert g.grade_mesh("unit_box", bad)["verdict"] in ("INVALID", "MISSING")


def test_truth_table_covers_all_gauntlet_tasks():
    from tests.benchmarks.bench_cad_gauntlet_v2 import TASKS

    assert {t["id"] for t in TASKS} == {k for k in g.GAUNTLET_V2_TRUTH if not k.startswith("unit_")}
