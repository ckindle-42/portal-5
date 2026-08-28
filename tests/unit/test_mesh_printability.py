from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from portal.modules.cad.tools.mesh_validator import check_printability

trimesh = pytest.importorskip("trimesh")

LIMITS = {
    "nozzle_diameter_mm": 0.4,
    "minimum_feature_nozzles": 2,
    "max_unsupported_overhang_deg": 45,
    "bed_size_mm": {"x": 220, "y": 220, "z": 250},
}


def _codes(warnings):
    return {warning["code"] for warning in warnings}


def test_thin_feature_reports_measured_value_and_limit():
    mesh = trimesh.creation.box(extents=(20, 20, 0.2))
    warning = next(
        warning
        for warning in check_printability(mesh, LIMITS)
        if warning["code"] == "minimum_feature_thickness"
    )
    assert warning["measured_mm"] == 0.2
    assert warning["limit_mm"] == 0.8


def test_seventy_degree_unsupported_overhang_is_flagged():
    normal_z = -np.sin(np.radians(70))
    mesh = SimpleNamespace(
        extents=np.array([20.0, 20.0, 20.0]),
        faces=np.array([[0, 1, 2]]),
        face_normals=np.array([[np.sqrt(1 - normal_z**2), 0, normal_z]]),
        triangles_center=np.array([[0.0, 0.0, 10.0]]),
        bounds=np.array([[0.0, 0.0, 0.0], [20.0, 20.0, 20.0]]),
    )
    warning = next(
        warning
        for warning in check_printability(mesh, LIMITS)
        if warning["code"] == "unsupported_overhang"
    )
    assert round(warning["measured_deg"]) == 70
    assert warning["limit_deg"] == 45


def test_oversize_part_is_flagged_per_axis():
    mesh = trimesh.creation.box(extents=(230, 20, 20))
    warning = next(
        warning for warning in check_printability(mesh, LIMITS) if warning["code"] == "bed_size_fit"
    )
    assert warning["axis"] == "x"
    assert warning["measured_mm"] == 230
    assert warning["limit_mm"] == 220


def test_clean_part_has_no_printability_warnings():
    assert check_printability(trimesh.creation.box(extents=(20, 20, 5)), LIMITS) == []
