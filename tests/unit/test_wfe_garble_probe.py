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


#: (backend, tag) pairs aliased onto granite-4.1-8b-mxfp8 with probe evidence (2026-10-17):
#: clean 10/10 with the lanes' own tool sets (tools-specialist, security-reviewer, auto-security).
#: Adding a pair needs a new `scripts/wfe_garble_probe.py` run and an update to the KNOWN_LIMITATIONS
#: unit unit-known-limitations-granite-8b-mxfp8-tool-garbling.
PROBED_ALIASES = {("omlx-general", "granite4.1:8b-ctx8k"), ("omlx-security", "granite4.1:8b-ctx8k")}


def test_no_unprobed_alias_onto_the_mxfp8_conversion():
    """With tools present the conversion emits U+200B in paths and mangled names; the
    granite4.1:8b-ctx16k seat (auto-documents/video/image) must not be shadowed onto it."""
    backends = yaml.safe_load((ROOT / "config" / "backends.yaml").read_text())["backends"]
    found = {
        (b["id"], tag)
        for b in backends
        for tag, target in (b.get("aliases") or {}).items()
        if target == "granite-4.1-8b-mxfp8"
    }
    assert found == PROBED_ALIASES, sorted(found ^ PROBED_ALIASES)
