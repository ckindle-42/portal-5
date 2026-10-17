"""The oMLX granite-8b shadow is gone for the auto-documents lane, and the probe that found why
(U+200B inside paths, mangled tool names) recognises each kind of corruption."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "wfe_garble_probe", ROOT / "scripts" / "wfe_garble_probe.py"
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def test_probe_flags_zwsp_bad_names_and_dotdot():
    names = {"read_excel"}
    assert probe.corruption("Download: /app/​data", [], names) == ["zwsp-text"]
    assert probe.corruption("", [{"name": "create_ powerpoint", "arguments": "{}"}], names) == [
        "bad-name:'create_ powerpoint'"
    ]
    assert probe.corruption(
        "", [{"name": "read_excel", "arguments": '{"file_path": "v..xlsx"}'}], names
    ) == ["dotdot-args"]
    assert (
        probe.corruption(
            "fine", [{"name": "read_excel", "arguments": '{"file_path": "v.xlsx"}'}], names
        )
        == []
    )


def test_the_documents_seat_is_not_shadowed_onto_the_mxfp8_conversion():
    """auto-documents routes to general+coding; in omlx-general the ctx16k seat tag must not be
    aliased to granite-4.1-8b-mxfp8 (U+200B in paths whenever tools are in the request)."""
    backends = yaml.safe_load((ROOT / "config" / "backends.yaml").read_text())["backends"]
    general = next(b for b in backends if b["id"] == "omlx-general")
    assert "granite4.1:8b-ctx16k" not in (general.get("aliases") or {})
    assert general["aliases"]["granite4.1:8b-ctx8k"] == "granite-4.1-8b-mxfp8"  # fan-out lane kept
