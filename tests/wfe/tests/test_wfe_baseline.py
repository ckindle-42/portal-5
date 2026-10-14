"""Reusing another campaign's incumbent rows as a baseline (spec:
docs/WFE_ROOT_CAUSES_20261013.md)."""

from __future__ import annotations

import json

from tests.wfe import campaign as camp


class TestSameCampaignBaseline:
    """Reuse of another campaign's incumbent rows needs one instrument and one
    suite content; otherwise the incumbent is re-run."""

    @staticmethod
    def _campaign(root, name, fingerprint, suites):
        d = root / name
        (d / "rows").mkdir(parents=True)
        camp.save_manifest(
            d,
            {
                "campaign_id": name,
                "instrument": {"fingerprint": fingerprint},
                "env": {"fingerprint": "e"},
                "rows": [],
            },
        )
        (d / "controls_receipts.jsonl").write_text(
            json.dumps({"where": "open", "suites": suites}) + "\n"
        )
        return d

    def test_identical_instrument_and_suites_allow_reuse(self, tmp_path):
        a = self._campaign(tmp_path, "a", "fp1", {"s.jsonl": "d1"})
        b = self._campaign(tmp_path, "b", "fp1", {"s.jsonl": "d1"})
        ok, why = camp.baseline_reusable(a, b)
        assert ok and "same instrument" in why

    def test_a_different_instrument_forces_a_rerun(self, tmp_path):
        a = self._campaign(tmp_path, "a", "fp1", {"s.jsonl": "d1"})
        b = self._campaign(tmp_path, "b", "fp2", {"s.jsonl": "d1"})
        ok, why = camp.baseline_reusable(a, b)
        assert not ok and "instrument fingerprint" in why

    def test_changed_suite_content_forces_a_rerun(self, tmp_path):
        a = self._campaign(tmp_path, "a", "fp1", {"s.jsonl": "d1"})
        b = self._campaign(tmp_path, "b", "fp1", {"s.jsonl": "d2"})
        ok, why = camp.baseline_reusable(a, b)
        assert not ok and "suite content changed" in why

    def test_an_unrecorded_instrument_forces_a_rerun(self, tmp_path):
        a = self._campaign(tmp_path, "a", None, {"s.jsonl": "d1"})
        b = self._campaign(tmp_path, "b", "fp1", {"s.jsonl": "d1"})
        ok, _ = camp.baseline_reusable(a, b)
        assert not ok
