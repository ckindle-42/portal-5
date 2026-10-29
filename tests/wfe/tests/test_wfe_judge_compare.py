"""Tests for tests/wfe/judge_compare.py — all mock, no network."""

from __future__ import annotations

import json
from io import StringIO

from tests.wfe import judge_compare as compare


def _make_campaign(tmp_path, store):
    campaign = tmp_path / "camp"
    campaign.mkdir()
    (campaign / "manifest.json").write_text(json.dumps({"rows": []}))
    judgements = campaign / "judgements"
    for profile, recs in store.items():
        d = judgements / profile
        d.mkdir(parents=True)
        for key, rec in recs.items():
            (d / f"{key}.json").write_text(json.dumps(rec))
    return campaign


def _rec(pref=None, reason="by design", key="sha1234567890"):
    out = {
        "key": key,
        "workspace": "ws",
        "lane": "home",
        "suite": "realuse",
        "arm": "inc:tag",
        "incumbent": "chall:tag",
        "reason": reason,
    }
    if pref is not None:
        out["preference"] = pref
        out["winner"] = pref
    return out


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


class TestMainAgreement:
    def test_fully_agreed_outputs_agreement_pct(self, tmp_path, monkeypatch):
        camp = _make_campaign(
            tmp_path,
            {
                "local": {"k1": _rec("A")},
                "cloud": {"k1": _rec("A")},
            },
        )
        out = StringIO()
        monkeypatch.setattr("sys.stdout", out)
        compare.main(["--campaign", str(camp.name), "--campaigns-root", str(tmp_path)])
        text = out.getvalue()
        assert "Agreement: 1/1 = 100.00%" in text

    def test_fully_disagreed_outputs_disagreement_table(self, tmp_path, monkeypatch):
        camp = _make_campaign(
            tmp_path,
            {
                "local": {"k1": _rec("A")},
                "cloud": {"k1": _rec("B")},
            },
        )
        out = StringIO()
        monkeypatch.setattr("sys.stdout", out)
        compare.main(["--campaign", str(camp.name), "--campaigns-root", str(tmp_path)])
        text = out.getvalue()
        assert "Disagreements (1):" in text
        assert "by design" in text

    def test_no_shared_keys_returns_early(self, tmp_path, monkeypatch):
        camp = _make_campaign(
            tmp_path,
            {
                "local": {"k1": _rec("A", key="key-a")},
                "cloud": {"k2": _rec("B", key="key-b")},
            },
        )
        out = StringIO()
        monkeypatch.setattr("sys.stdout", out)
        rc = compare.main(["--campaign", str(camp.name), "--campaigns-root", str(tmp_path)])
        assert rc == 0
        text = out.getvalue()
        assert "Pairs with all profiles: 0" in text
        assert "Agreement:" not in text

    def test_records_with_errors_are_excluded(self, tmp_path, monkeypatch):
        # local has no error; cloud's record has error, so they are not paired.
        camp = _make_campaign(
            tmp_path,
            {
                "local": {"k1": _rec("A")},
                "cloud": {
                    "k1": {
                        "key": "k1",
                        "workspace": "ws",
                        "lane": "home",
                        "suite": "realuse",
                        "arm": "inc:tag",
                        "incumbent": "chall:tag",
                        "error": "boom",
                        "preference": "B",
                    }
                },
            },
        )
        out = StringIO()
        monkeypatch.setattr("sys.stdout", out)
        rc = compare.main(["--campaign", str(camp.name), "--campaigns-root", str(tmp_path)])
        assert rc == 0
        text = out.getvalue()
        assert "Pairs with all profiles: 0" in text
        assert "Agreement:" not in text

    def test_missing_profile_directory_is_treated_as_empty(self, tmp_path, monkeypatch):
        camp = _make_campaign(
            tmp_path,
            {
                "local": {"k1": _rec("A")},
            },
        )
        out = StringIO()
        monkeypatch.setattr("sys.stdout", out)
        rc = compare.main(["--campaign", str(camp.name), "--campaigns-root", str(tmp_path)])
        assert rc == 0
        text = out.getvalue()
        assert "Pairs with all profiles: 0" in text
        assert "Agreement:" not in text

    def test_partial_profile_comparison(self, tmp_path, monkeypatch):
        """When some profiles share keys but not all, only shared keys are used."""
        camp = _make_campaign(
            tmp_path,
            {
                "local": {"k1": _rec("A"), "k2": _rec("B")},
                "cloud": {"k1": _rec("A"), "k3": _rec("B")},
            },
        )
        out = StringIO()
        monkeypatch.setattr("sys.stdout", out)
        compare.main(
            [
                "--campaign",
                str(camp.name),
                "--campaigns-root",
                str(tmp_path),
                "--profiles",
                "local",
                "cloud",
            ]
        )
        text = out.getvalue()
        # Only k1 is shared; both agree.
        assert "Agreement: 1/1 = 100.00%" in text
        # k2 and k3 are not paired — not printed as disagreements.
        assert "No disagreements." in text


def test_local_profile_reads_the_flat_directory_and_not_cloud(tmp_path):
    from tests.wfe.judge import judgements_dir

    base = tmp_path / "c" / "judgements"
    (base / "cloud").mkdir(parents=True)
    (base / "l.json").write_text(json.dumps({"key": "local"}))
    (base / "cloud" / "c.json").write_text(json.dumps({"key": "cloud"}))
    assert set(compare._load(judgements_dir(tmp_path / "c", "local"))) == {"local"}
    assert set(compare._load(judgements_dir(tmp_path / "c", "cloud"))) == {"cloud"}
