"""The surface audit's detectors, on small fixtures: each defect class it exists to find."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "wfe_surface_audit", ROOT / "scripts" / "wfe_surface_audit.py"
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def _fn(src: str):
    return ast.parse(src).body[0]


def test_signature_rows_flag_undefined_extra_and_missing_required():
    fn = _fn("def f(file_path, max_rows=5): pass")
    rows = audit.signature_rows("m / f", {"audio_path": {}, "max_rows": {}}, set(), fn)
    kinds = {(r[2], r[3].split(":")[0]) for r in rows}
    assert ("open", "manifest params not in the function") in kinds
    assert ("open", "function requires ['file_path'], manifest does not") in kinds


def test_shape_rows_flag_arrays_and_objects_with_no_keys():
    rows = audit.shape_rows(
        "m / f",
        {
            "slides": {"type": "array", "items": {"type": "object"}},
            "data": {"type": "array"},
            "opts": {"type": "object"},
            "ok": {"type": "array", "items": {"type": "object", "properties": {"a": {}}}},
        },
    )
    assert sorted(r[1] for r in rows) == ["m / f.data", "m / f.opts", "m / f.slides"]


def test_filtering_dispatcher_pattern_matches_the_whisper_shape():
    bad = "filtered = {k: v for k, v in arguments.items() if k in valid}"
    assert audit.FILTERING.search(bad)
    assert not audit.FILTERING.search("unknown = sorted(set(arguments) - valid)")


def test_no_dispatcher_silently_filters_unknown_arguments():
    assert audit.filtering_dispatchers() == []


def test_manifests_pass_the_integrity_classes_the_audit_closed():
    """required parameters are defined and match the functions, across every MCP manifest."""
    assert [r for r in audit.class2() if r[2] == "open"] == []
