"""Y.6 -- `_parse_raw_kv` must recover JSON-shaped `_raw` text, not just
`key=value` text. Discovered live during the Y.6 re-run: `universe.py`'s
generated events ship as JSON objects (HEC/Splunk store `_raw` as their JSON
text), so the pre-existing `key=value`-only regex silently dropped every
synthetic record's real payload -- including the injected implant identity
-- leaving entity resolution to run on incidental Splunk metadata instead.
See docs/DESIGN_BULLY_TRUTH_ACCEPTANCE_V1.md."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bully_loop_milestone_run as r6  # noqa: E402


def test_flat_json_raw_is_recovered():
    rec = {"_raw": '{"event.kind": "4519", "actor.id": "adv8370", "pod.id": "id-280"}'}
    parsed = r6._parse_raw_kv(rec)
    assert parsed["actor.id"] == "adv8370"
    assert parsed["event.kind"] == "4519"


def test_nested_json_raw_is_flattened_and_leaf_name_also_exposed():
    rec = {"_raw": '{"detail": {"src_id": "adv5738", "req_name": "HrtgmAuth"}}'}
    parsed = r6._parse_raw_kv(rec)
    assert parsed["detail.src_id"] == "adv5738"
    assert parsed["src_id"] == "adv5738"  # bare leaf name, for identity_field matching


def test_real_kv_raw_text_still_parses_unchanged():
    rec = {"_raw": r"EventCode=4624 Account=AR-WIN-3\Administrator LogonType=3"}
    parsed = r6._parse_raw_kv(rec)
    assert parsed["EventCode"] == "4624"
    assert parsed["Account"] == r"AR-WIN-3\Administrator"
    assert parsed["LogonType"] == "3"


def test_seeded_violation_regex_alone_cannot_recover_json():
    """Proves the gate is load-bearing: the old KV-only regex finds nothing
    in JSON `_raw` text."""
    rec = {"_raw": '{"actor.id": "adv8370"}'}
    matches = list(r6._RAW_KV.finditer(rec["_raw"]))
    assert matches == []


def test_malformed_raw_falls_back_without_raising():
    rec = {"_raw": "{not valid json"}
    parsed = r6._parse_raw_kv(rec)
    assert parsed["_raw"] == "{not valid json"


def test_non_string_json_values_are_skipped_not_stringified():
    rec = {"_raw": '{"count": 4, "tags": ["a", "b"], "name": "svc1"}'}
    parsed = r6._parse_raw_kv(rec)
    assert parsed["name"] == "svc1"
    assert "count" not in parsed
    assert "tags" not in parsed
