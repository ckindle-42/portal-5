"""Incumbent rows copied from an earlier campaign when the reuse key matches.

The key is the suite digest, task, repeat, served identity (backend, model,
content), sampling, tool surface, harness digest and the deployed build's portal
tree. The copy keeps the earlier grade and records reused_from. It is not re-graded.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.wfe import campaign
from tests.wfe import report as rep

WS = "auto-documents"
MODEL = "granite4.1:8b-ctx16k"
IDENT = {"backend": "ollama-general", "model": MODEL, "content": "content-abc"}
HARNESS = "h" * 16
PORTAL = "p" * 40
DIGEST = "d" * 16
DOCS = Path("/Users/chris/projects/portal-5/tests/wfe/results/campaigns")


@pytest.fixture(autouse=True)
def _pipeline(monkeypatch):
    monkeypatch.setattr(campaign, "ENGINE", "pipeline")


def _suite(tmp: Path) -> Path:
    path = tmp / "documents_production.jsonl"
    path.write_text(json.dumps({"id": "t1", "instruction": "do the task"}) + "\n")
    return path


def _stub(suite: Path, *, role: str = "incumbent", state: str = "PENDING", repeat: int = 0) -> dict:
    return {
        "run_id": f"{WS}|{MODEL}|documents_production|t1|r{repeat}",
        "workspace": WS,
        "arm": MODEL,
        "model": MODEL,
        "arm_role": role,
        "tier": "confirm",
        "suite": "documents_production",
        "suite_path": str(suite),
        "task_id": "t1",
        "repeat": repeat,
        "tool_mode": "production",
        "overrides": {"sampling": {"temperature": 0.0}},
        "state": state,
    }


def _receipt(d: Path, suite: Path, digest: str = DIGEST) -> None:
    (d / "controls_receipts.jsonl").write_text(
        json.dumps({"where": "open", "suites": {str(suite): digest}, "failures": []}) + "\n"
    )


def _instrument(fp: str) -> dict:
    return {
        "fingerprint": fp,
        "harness": HARNESS,
        "portal_tree": PORTAL,
        "engine": "pipeline",
    }


def _open(
    root: Path, name: str, suite: Path, rows: list[dict], *, fp: str, digest: str = DIGEST
) -> Path:
    d = root / name
    (d / "rows").mkdir(parents=True)
    campaign.save_manifest(
        d,
        {
            "campaign_id": name,
            "instrument": _instrument(fp),
            "env": {"fingerprint": fp},
            "identity_map": {f"{WS}|{MODEL}": dict(IDENT)},
            "rows": rows,
        },
    )
    _receipt(d, suite, digest)
    return d


def _source_row(suite: Path, surface: list, **over) -> dict:
    row = {
        **_stub(suite, state="PASS"),
        "outcome": "FAIL",
        "evidence": {"marker": 1},
        "notes": "kept",
        "identity": dict(IDENT),
        "sampling": campaign.expected_incumbent_sampling(_stub(suite)),
        "tool_surface": list(surface),
        "instrument": _instrument("old-fp"),
        "env": {"fingerprint": "old-env"},
        "campaign_id": "src",
    }
    row.update(over)
    return row


def _write_row(d: Path, row: dict) -> None:
    campaign._row_path(d, row["run_id"]).write_text(json.dumps(row))


def _pair(tmp: Path, monkeypatch):
    monkeypatch.setattr(campaign, "CAMPAIGNS", tmp)
    suite = _suite(tmp)
    surface = campaign.expected_incumbent_surface(_stub(suite))
    src_stub = _stub(suite, state="FAIL")
    src = _open(tmp, "src", suite, [src_stub], fp="old-fp")
    row = _source_row(suite, surface)
    _write_row(src, row)
    dst_stub = _stub(suite)
    dst = _open(tmp, "dst", suite, [dst_stub], fp="new-fp")
    return src, dst, dst_stub, row


class TestReuseKey:
    def test_an_exact_match_is_copied_and_not_regraded(self, tmp_path, monkeypatch):
        _src, dst, stub, src_row = _pair(tmp_path, monkeypatch)
        copied = campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub])
        assert copied == [stub["run_id"]]
        body = json.loads(campaign._row_path(dst, stub["run_id"]).read_text())
        assert body["reused_from"] == f"src/{src_row['run_id']}"
        assert body["outcome"] == "FAIL" and body["evidence"] == {"marker": 1}
        assert body["notes"] == "kept" and "rescore" not in body
        assert body["instrument"]["fingerprint"] == "old-fp"
        assert body["campaign_id"] == "dst" and body["run_id"] == stub["run_id"]
        saved = campaign.load_manifest(dst)
        assert saved["rows"][0]["state"] == "FAIL"
        assert saved["rows"][0]["reused_from"] == body["reused_from"]

    def test_a_copy_of_a_copy_keeps_the_original_provenance(self, tmp_path, monkeypatch):
        _src, dst, stub, _row = _pair(tmp_path, monkeypatch)
        src_path = campaign._row_path(tmp_path / "src", stub["run_id"])
        body = json.loads(src_path.read_text())
        body["reused_from"] = "older/the-row"
        src_path.write_text(json.dumps(body))
        campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub])
        copied = json.loads(campaign._row_path(dst, stub["run_id"]).read_text())
        assert copied["reused_from"] == "older/the-row"

    @pytest.mark.parametrize(
        "mutate",
        [
            "suite",
            "task",
            "repeat",
            "content",
            "sampling",
            "surface",
            "harness",
            "portal",
        ],
    )
    def test_any_one_field_off_is_not_copied(self, tmp_path, monkeypatch, mutate):
        _src, dst, stub, _row = _pair(tmp_path, monkeypatch)
        src_dir = tmp_path / "src"
        path = campaign._row_path(src_dir, stub["run_id"])
        body = json.loads(path.read_text())
        if mutate == "suite":
            _receipt(src_dir, Path(stub["suite_path"]), "other-digest")
        elif mutate == "task":
            body["task_id"] = "other"
            man = campaign.load_manifest(src_dir)
            man["rows"][0]["task_id"] = "other"
            campaign.save_manifest(src_dir, man)
        elif mutate == "repeat":
            body["repeat"] = 1
            man = campaign.load_manifest(src_dir)
            man["rows"][0]["repeat"] = 1
            campaign.save_manifest(src_dir, man)
        elif mutate == "content":
            body["identity"] = {**body["identity"], "content": "other-content"}
        elif mutate == "sampling":
            body["sampling"] = {**body["sampling"], "temperature": 0.7}
        elif mutate == "surface":
            body["tool_surface"] = ["read_pdf"]
        elif mutate == "harness":
            body["instrument"] = {**body["instrument"], "harness": "other-harness"}
        elif mutate == "portal":
            body["instrument"] = {**body["instrument"], "portal_tree": "other-tree"}
        path.write_text(json.dumps(body))
        assert campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub]) == []
        assert not campaign._row_path(dst, stub["run_id"]).exists()

    def test_unobserved_content_is_not_a_match(self, tmp_path, monkeypatch):
        _src, dst, stub, _row = _pair(tmp_path, monkeypatch)
        man = campaign.load_manifest(dst)
        man["identity_map"] = {}
        assert campaign.reuse_incumbent_rows(dst, man, [stub]) == []

    def test_a_challenger_row_is_not_a_source(self, tmp_path, monkeypatch):
        monkeypatch.setattr(campaign, "CAMPAIGNS", tmp_path)
        suite = _suite(tmp_path)
        surface = campaign.expected_incumbent_surface(_stub(suite))
        src_stub = _stub(suite, role="challenger", state="PASS")
        src = _open(tmp_path, "src", suite, [src_stub], fp="old-fp")
        _write_row(src, _source_row(suite, surface, arm_role="challenger"))
        dst_stub = _stub(suite)
        dst = _open(tmp_path, "dst", suite, [dst_stub], fp="new-fp")
        assert campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [dst_stub]) == []

    def test_a_blocked_source_is_not_copied(self, tmp_path, monkeypatch):
        _src, dst, stub, _row = _pair(tmp_path, monkeypatch)
        src_dir = tmp_path / "src"
        path = campaign._row_path(src_dir, stub["run_id"])
        body = json.loads(path.read_text())
        body["outcome"] = "BLOCKED"
        path.write_text(json.dumps(body))
        assert campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub]) == []

    def test_sources_that_disagree_are_not_copied(self, tmp_path, monkeypatch):
        _src, dst, stub, _row = _pair(tmp_path, monkeypatch)
        suite = Path(stub["suite_path"])
        surface = campaign.expected_incumbent_surface(stub)
        other_stub = _stub(suite, state="PASS")
        other = _open(tmp_path, "other", suite, [other_stub], fp="old-fp")
        _write_row(other, _source_row(suite, surface, outcome="PASS", campaign_id="other"))
        assert campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub]) == []
        assert not campaign._row_path(dst, stub["run_id"]).exists()

    def test_fresh_incumbent_releases_the_copy_and_does_not_reuse(self, tmp_path, monkeypatch):
        _src, dst, stub, _row = _pair(tmp_path, monkeypatch)
        campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub])
        man = campaign.load_manifest(dst)
        assert campaign.release_reused_incumbents(dst, man) == 1
        assert not campaign._row_path(dst, stub["run_id"]).exists()
        assert man["rows"][0]["state"] == "PENDING" and "reused_from" not in man["rows"][0]

        seen = {}

        def _rows(cd, manifest, *a):
            seen["state"] = manifest["rows"][0]["state"]
            seen["file"] = campaign._row_path(cd, stub["run_id"]).exists()
            return [], {"arm": MODEL, "ran": 0}

        monkeypatch.setattr(campaign, "_rows_to_run", _rows)
        # Put the copy back, then the flag must release it before any run.
        campaign.reuse_incumbent_rows(
            dst, campaign.load_manifest(dst), campaign.load_manifest(dst)["rows"]
        )
        out = campaign.execute_arm(dst, MODEL, 4, 60, None, False, False, fresh_incumbent=True)
        assert out["ran"] == 0 and seen["state"] == "PENDING" and seen["file"] is False

    def test_execute_arm_copies_then_does_not_run(self, tmp_path, monkeypatch):
        _src, dst, stub, _row = _pair(tmp_path, monkeypatch)

        def _rows(_cd, manifest, *_a):
            return [r for r in manifest["rows"] if r.get("state") == "PENDING"], None

        monkeypatch.setattr(campaign, "_rows_to_run", _rows)
        monkeypatch.setattr(
            campaign, "drain_others", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("ran"))
        )
        out = campaign.execute_arm(dst, MODEL, 4, 60, None, False, False)
        assert out["ran"] == 0 and out["reused"] == 1
        assert campaign.load_manifest(dst)["rows"][0]["state"] == "FAIL"


class TestPresent:
    def test_verify_complete_counts_a_reused_row(self, tmp_path, monkeypatch):
        _src, dst, stub, _row = _pair(tmp_path, monkeypatch)
        campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub])
        assert campaign.completion_problems(dst) == []
        assert campaign._cmd_verify_complete(dst) == 0

    def test_a_different_instrument_without_provenance_is_still_incomplete(self, tmp_path):
        suite = _suite(tmp_path)
        stub = _stub(suite, state="PASS")
        d = _open(tmp_path, "only", suite, [stub], fp="new-fp")
        row = _source_row(suite, ["read_pdf"], campaign_id="only")
        row["instrument"] = _instrument("other-fp")
        _write_row(d, row)
        assert campaign.completion_problems(d) == [
            f"{stub['run_id']}: measured under another instrument"
        ]

    def test_fitness_grades_a_reused_incumbent_with_the_new_campaign(self, tmp_path, monkeypatch):
        _src, dst, stub, _row = _pair(tmp_path, monkeypatch)
        cand = _stub(Path(stub["suite_path"]), role="challenger", state="PASS")
        cand["run_id"] = f"{WS}|cand|documents_production|t1|r0"
        cand["arm"] = "cand"
        cand["model"] = "cand"
        man = campaign.load_manifest(dst)
        man["rows"].append(cand)
        man["identity_map"][f"{WS}|cand"] = {
            "backend": "omlx-general",
            "model": "cand",
            "content": "cand-content",
        }
        campaign.save_manifest(dst, man)
        cand_row = {
            **cand,
            "outcome": "PASS",
            "identity": man["identity_map"][f"{WS}|cand"],
            "instrument": _instrument("new-fp"),
            "env": {"fingerprint": "new-env"},
        }
        _write_row(dst, cand_row)
        campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub])
        fit = rep.fitness(dst)
        (cell,) = fit["cells"]
        assert cell["n"] == 1 and cell["excluded"] == {}
        warnings = rep._collect_warnings(rep._load(dst)[1], campaign.load_manifest(dst), False)
        assert any("reused" in w for w in warnings)
        assert rep.build(dst)["not_run"] == []


def test_documents_g_to_h_incumbents_do_not_match():
    """Read-only proof against the recorded documents campaigns. g is the screen;
    h is the screen plus confirm. Nothing is written."""
    g, h = DOCS / "wfe_documents_20261017g", DOCS / "wfe_documents_20261017h"
    if not (g / "manifest.json").is_file() or not (h / "manifest.json").is_file():
        pytest.skip("documents campaigns g and h are not in this checkout")
    before = (h / "manifest.json").stat().st_mtime_ns
    report = campaign.incumbent_reuse_report(g, h)
    assert (h / "manifest.json").stat().st_mtime_ns == before
    counts: dict[tuple, int] = {}
    for row in report["rows"]:
        counts[tuple(row["diffs"])] = counts.get(tuple(row["diffs"]), 0) + 1
    assert report["matched"] == 0 and report["dst_incumbent_rows"] == 108
    assert counts[("no source row",)] == 96
    assert counts[("harness", "portal_tree")] == 12
