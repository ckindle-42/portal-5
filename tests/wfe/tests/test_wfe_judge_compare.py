"""Tests for tests/wfe/judge_compare.py — all mock, no network."""

from __future__ import annotations

import json
from io import StringIO

from tests.wfe import judge_compare as compare
from tests.wfe.judge import judgements_dir


class TestLoad:
    def test_loads_all_json_files_in_a_profile(self, tmp_path):
        d = tmp_path / "p" / "judgements" / "local"
        d.mkdir(parents=True)
        (d / "abc.json").write_text(json.dumps({"key": "a1"}))
        (d / "def.json").write_text(json.dumps({"key": "a2"}))
        res = compare._load(d)
        assert res["a1"]["key"] == "a1"
        assert res["a2"]["key"] == "a2"

    def test_missing_profile_returns_empty(self, tmp_path):
        assert compare._load(tmp_path / "does_not_exist") == {}

    def test_broken_json_is_skipped(self, tmp_path):
        d = tmp_path / "p"
        d.mkdir(parents=True)
        (d / "bad.json").write_text("{not json")
        assert compare._load(d) == {}


class TestKappa:
    def test_no_data_returns_none(self):
        assert compare._kappa([]) is None

    def test_perfect_agreement_is_one(self):
        pairs = [("A", "A"), ("B", "B"), ("A", "A")]
        k = compare._kappa(pairs)
        assert k is not None
        assert abs(k - 1.0) < 1e-9

    def test_chance_agreement_gives_negative_kappa(self):
        # All pairs are cross — max disagreement.
        pairs = [("A", "B"), ("B", "A"), ("A", "B"), ("B", "A")]
        k = compare._kappa(pairs)
        assert k is not None
        assert k < 0


def test_council_profiles_report_checker_agreement(tmp_path, monkeypatch):
    from tests.wfe.judge import pair_key

    campaign = tmp_path / "camp"
    (campaign / "rows").mkdir(parents=True)
    key = pair_key("ws", "realuse", "t1", 0, "inc", "cand")
    arms = {"A": "inc", "B": "cand"}
    for profile, pref in (("local", "A"), ("cloud", "B"), ("council", "A")):
        path = judgements_dir(campaign, profile) / "k.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "key": key,
                    "preference": pref,
                    "winner": arms[pref],
                    "arms": arms,
                    "workspace": "ws",
                    "suite": "realuse",
                    "task_id": "t1",
                    "repeat": 0,
                    "reason": "by design",
                    "excluded": None,
                }
            )
        )
    (campaign / "rows" / "a.json").write_text(
        json.dumps(
            {
                "workspace": "ws",
                "suite": "realuse",
                "task_id": "t1",
                "repeat": 0,
                "arm": "inc",
                "outcome": "PASS",
            }
        )
    )
    (campaign / "rows" / "b.json").write_text(
        json.dumps(
            {
                "workspace": "ws",
                "suite": "realuse",
                "task_id": "t1",
                "repeat": 0,
                "arm": "cand",
                "outcome": "FAIL",
            }
        )
    )
    out = StringIO()
    monkeypatch.setattr("sys.stdout", out)
    compare.main(
        [
            "--campaign",
            campaign.name,
            "--campaigns-root",
            str(tmp_path),
            "--profiles",
            "local",
            "cloud",
            "council",
        ]
    )
    text = out.getvalue()
    assert "Council vs checker (exactly one arm passed): 1/1 = 100.00%" in text
    assert "council" in text


def test_local_profile_reads_the_flat_directory_and_not_cloud(tmp_path):

    base = tmp_path / "c" / "judgements"
    (base / "cloud").mkdir(parents=True)
    (base / "l.json").write_text(json.dumps({"key": "local"}))
    (base / "cloud" / "c.json").write_text(json.dumps({"key": "cloud"}))
    assert set(compare._load(judgements_dir(tmp_path / "c", "local"))) == {"local"}
    assert set(compare._load(judgements_dir(tmp_path / "c", "cloud"))) == {"cloud"}
