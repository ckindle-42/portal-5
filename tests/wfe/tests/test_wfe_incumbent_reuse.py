"""Incumbent rows copied from an earlier campaign when the reuse key matches.

The key is the suite digest, task, repeat, model identity, engine and version,
delivered sampling, tool surface, the pipeline trees at the deployed sha, and
the tree of each offered tool module. The copy is re-graded with the current
checkers. original_outcome is the earlier grade; the regraded outcome counts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.wfe import campaign
from tests.wfe import report as rep

WS = "auto-documents"
MODEL = "granite4.1:8b-ctx16k"
IDENT = {"backend": "ollama-general", "model": MODEL, "content": "content-abc"}
DEPLOYED = "c" * 40
PIPE = "b" * 40
MOD = "d" * 40
VERSION = "0.40.5"
DOCS = (
    Path(os.environ.get("PORTAL_DATA_ROOT", str(Path.home() / "AI_Output" / "portal-data")))
    / "tests"
    / "wfe"
    / "results"
    / "campaigns"
)


@pytest.fixture(autouse=True)
def _pipeline(monkeypatch):
    monkeypatch.setattr(campaign, "ENGINE", "pipeline")


def _suite(tmp: Path, task: dict | None = None) -> Path:
    path = tmp / "documents_production.jsonl"
    path.write_text(
        json.dumps(
            task
            or {
                "id": "t1",
                "instruction": "do the task",
                "checkers": [{"type": "answer_contains", "patterns": ["TASK COMPLETE"]}],
            }
        )
        + "\n"
    )
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


def _receipt(d: Path, suite: Path, digest: str | None = None) -> None:
    from tests.wfe.controls import suite_digest

    if digest is None:
        digest = suite_digest(suite)
    (d / "controls_receipts.jsonl").write_text(
        json.dumps({"where": "open", "suites": {str(suite): digest}, "failures": []}) + "\n"
    )


def _instrument(fp: str, deployed: str = DEPLOYED) -> dict:
    return {
        "fingerprint": fp,
        "deployed": deployed,
        "engine": "pipeline",
        "harness": "harness-digest",
    }


def _env(fp: str, version: str = VERSION) -> dict:
    return {"fingerprint": fp, "engine": "pipeline", "ollama_version": version}


def _open(
    root: Path, name: str, suite: Path, rows: list[dict], *, fp: str, digest: str | None = None
) -> Path:
    d = root / name
    (d / "rows").mkdir(parents=True)
    campaign.save_manifest(
        d,
        {
            "campaign_id": name,
            "instrument": _instrument(fp),
            "env": _env(fp),
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
        "final_text": "TASK COMPLETE",
        "evidence": {"marker": 1},
        "notes": "kept",
        "identity": dict(IDENT),
        "sampling": campaign.expected_incumbent_sampling(_stub(suite)),
        "tool_surface": list(surface),
        "instrument": _instrument("old-fp"),
        "env": _env("old-env"),
        "campaign_id": "src",
    }
    row.update(over)
    return row


def _write_row(d: Path, row: dict) -> None:
    campaign._row_path(d, row["run_id"]).write_text(json.dumps(row))


class _Backend:
    def __init__(self, backend_id: str, engine: str, url: str):
        self.id = backend_id
        self.type = engine
        self.url = url


def _one_daemon(monkeypatch) -> None:
    """One Ollama daemon behind two group ids (doc: identity): the reuse key
    must treat the pair as one serving engine."""

    class _Reg:
        @staticmethod
        def list_backends():
            return [
                _Backend("ollama-general", "ollama", "http://daemon:11434"),
                _Backend("ollama-vision", "ollama", "http://daemon:11434"),
            ]

    monkeypatch.setattr(campaign, "_seat_registry", lambda: _Reg())


def _stub_trees(monkeypatch) -> None:
    """Synthetic trees. Real campaign proofs do not use this."""

    def pipeline(sha: str, _workspace: str = "") -> dict:
        if sha in (DEPLOYED, MOD):
            return {"inference": "inf", "config": "cfg"}
        if sha == PIPE:
            return {"inference": "inf", "config": "other-cfg"}
        return {}

    def modules(sha: str, _tools: list) -> dict | None:
        if sha in (DEPLOYED, PIPE):
            return {"portal/modules/documents": "mod"}
        if sha == MOD:
            return {"portal/modules/documents": "mod-other"}
        return None

    monkeypatch.setattr(campaign, "pipeline_at", pipeline)
    monkeypatch.setattr(campaign, "tool_module_trees", modules)


def _pair(tmp: Path, monkeypatch, task: dict | None = None):
    _stub_trees(monkeypatch)
    monkeypatch.setattr(campaign, "CAMPAIGNS", tmp)
    suite = _suite(tmp, task)
    surface = campaign.expected_incumbent_surface(_stub(suite))
    src_stub = _stub(suite, state="FAIL")
    src = _open(tmp, "src", suite, [src_stub], fp="old-fp")
    row = _source_row(suite, surface)
    _write_row(src, row)
    dst_stub = _stub(suite)
    dst = _open(tmp, "dst", suite, [dst_stub], fp="new-fp")
    return src, dst, dst_stub, row


def _scripted_pair(tmp: Path, monkeypatch, turns: list[dict], states: list[dict], outcome: str):
    task = {"id": "t1", "instruction": "do the task", "turns": turns}
    src, dst, stub, row = _pair(tmp, monkeypatch, task)
    row.update(outcome=outcome, tool_call_log=[], turn_results=states)
    _write_row(src, row)
    return dst, stub


class TestReuseKey:
    def test_an_exact_match_is_copied_and_regraded(self, tmp_path, monkeypatch):
        _src, dst, stub, src_row = _pair(tmp_path, monkeypatch)
        copied = campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub])
        assert copied == [stub["run_id"]]
        body = json.loads(campaign._row_path(dst, stub["run_id"]).read_text())
        assert body["reused_from"] == f"src/{src_row['run_id']}"
        assert body["original_outcome"] == "FAIL"
        assert body["regraded_outcome"] == "PASS" and body["outcome"] == "PASS"
        assert "checker re-grade" in body["notes"]
        assert body["instrument"]["fingerprint"] == "old-fp"
        assert body["campaign_id"] == "dst" and body["run_id"] == stub["run_id"]
        saved = campaign.load_manifest(dst)
        assert saved["rows"][0]["state"] == "PASS"
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

    def test_multiturn_tool_failure_stays_fail_after_regrade(self, tmp_path, monkeypatch):
        turns = [
            {
                "user": "Run the check",
                "checks": [
                    {"type": "answer_contains", "patterns": ["urgent 2"]},
                    {
                        "type": "tool_grounded",
                        "tools": ["execute_python"],
                        "evidence": ["urgent 2"],
                    },
                ],
                "expect_tools": ["execute_python"],
            },
            {
                "user": "Check the file",
                "checks": [{"type": "must_not_contain", "patterns": ["file is missing"]}],
            },
        ]
        states = [
            {
                "turn": 0,
                "final_text": "The result is urgent 2.",
                "assistant_texts": ["The result is urgent 2."],
                "tool_call_range": [0, 0],
                "finish_reason": "stop",
                "served": None,
            },
            {
                "turn": 1,
                "final_text": "The file is missing.",
                "assistant_texts": ["The file is missing."],
                "tool_call_range": [0, 0],
                "finish_reason": "stop",
                "served": None,
            },
        ]
        dst, stub = _scripted_pair(tmp_path, monkeypatch, turns, states, "FAIL")

        assert campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub]) == [
            stub["run_id"]
        ]
        body = json.loads(campaign._row_path(dst, stub["run_id"]).read_text())
        assert body["regraded_outcome"] == "FAIL" and body["outcome"] == "FAIL"

    def test_multiturn_refusal_stays_refused_after_regrade(self, tmp_path, monkeypatch):
        turns = [
            {
                "user": "Answer the question",
                "checks": [{"type": "answer_contains", "patterns": ["answer: 42"]}],
            }
        ]
        states = [
            {
                "turn": 0,
                "final_text": "I can't help with that.",
                "assistant_texts": ["I can't help with that."],
                "tool_call_range": [0, 0],
                "finish_reason": "stop",
                "served": None,
            }
        ]
        dst, stub = _scripted_pair(tmp_path, monkeypatch, turns, states, "REFUSED")

        assert campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub]) == [
            stub["run_id"]
        ]
        body = json.loads(campaign._row_path(dst, stub["run_id"]).read_text())
        assert body["regraded_outcome"] == "REFUSED" and body["outcome"] == "REFUSED"

    def test_scripted_row_without_saved_turn_evidence_is_not_reused(self, tmp_path, monkeypatch):
        turns = [{"user": "Answer", "checks": [{"type": "answer_contains", "patterns": ["42"]}]}]
        dst, stub = _scripted_pair(tmp_path, monkeypatch, turns, [], "FAIL")
        source = campaign._row_path(tmp_path / "src", stub["run_id"])
        row = json.loads(source.read_text())
        row.pop("turn_results")
        _write_row(tmp_path / "src", row)

        assert campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub]) == []
        assert stub["state"] == "PENDING"

    def test_grounded_scripted_row_without_tool_log_is_not_reused(self, tmp_path, monkeypatch):
        turns = [
            {
                "user": "Read the result",
                "checks": [{"type": "tool_grounded", "tools": ["file_read"], "evidence": ["42"]}],
            }
        ]
        states = [
            {
                "turn": 0,
                "final_text": "42",
                "assistant_texts": ["42"],
                "tool_call_range": [0, 0],
                "finish_reason": "stop",
                "served": None,
            }
        ]
        dst, stub = _scripted_pair(tmp_path, monkeypatch, turns, states, "PASS")
        source = campaign._row_path(tmp_path / "src", stub["run_id"])
        row = json.loads(source.read_text())
        row.pop("tool_call_log")
        _write_row(tmp_path / "src", row)

        assert campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub]) == []
        assert stub["state"] == "PENDING"

    @pytest.mark.parametrize(
        "mutate",
        [
            "suite",
            "task",
            "repeat",
            "backend",
            "model",
            "content",
            "engine",
            "version",
            "sampling",
            "surface",
            "pipeline",
            "modules",
            "harness",
        ],
    )
    def test_any_one_field_off_is_not_copied(self, tmp_path, monkeypatch, mutate):
        instrument_off = {
            "engine": {"engine": "other-engine"},
            "pipeline": {"deployed": PIPE},
            "modules": {"deployed": MOD},
            "harness": {"harness": "other-harness"},
        }
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
        elif mutate == "backend":
            body["identity"] = {**body["identity"], "backend": "other-backend"}
        elif mutate == "model":
            body["identity"] = {**body["identity"], "model": "other-model"}
        elif mutate == "content":
            body["identity"] = {**body["identity"], "content": "other-content"}
        elif mutate == "version":
            body["env"] = {**body["env"], "ollama_version": "9.9.9"}
        elif mutate == "sampling":
            body["sampling"] = {**body["sampling"], "temperature": 0.7}
        elif mutate == "surface":
            body["tool_surface"] = ["read_pdf"]
        elif mutate in instrument_off:
            body["instrument"] = {**body["instrument"], **instrument_off[mutate]}
        path.write_text(json.dumps(body))
        assert campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub]) == []
        assert not campaign._row_path(dst, stub["run_id"]).exists()

    def test_unobserved_content_is_not_a_match(self, tmp_path, monkeypatch):
        _src, dst, stub, _row = _pair(tmp_path, monkeypatch)
        man = campaign.load_manifest(dst)
        man["identity_map"] = {}
        assert campaign.reuse_incumbent_rows(dst, man, [stub]) == []

    def test_same_daemon_different_group_id_is_reused(self, tmp_path, monkeypatch):
        _one_daemon(monkeypatch)
        _src, dst, stub, src_row = _pair(tmp_path, monkeypatch)
        man = campaign.load_manifest(dst)
        man["identity_map"][f"{WS}|{MODEL}"] = {
            "backend": "ollama-vision",
            "model": MODEL,
            "content": IDENT["content"],
        }
        campaign.save_manifest(dst, man)
        copied = campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub])
        assert copied == [stub["run_id"]]
        body = json.loads(campaign._row_path(dst, stub["run_id"]).read_text())
        assert body["reused_from"] == f"src/{src_row['run_id']}"

    def test_same_daemon_different_content_is_not_reused(self, tmp_path, monkeypatch):
        _one_daemon(monkeypatch)
        _src, dst, stub, _row = _pair(tmp_path, monkeypatch)
        man = campaign.load_manifest(dst)
        man["identity_map"][f"{WS}|{MODEL}"] = {
            "backend": "ollama-vision",
            "model": MODEL,
            "content": "other-content",
        }
        campaign.save_manifest(dst, man)
        assert campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub]) == []
        assert not campaign._row_path(dst, stub["run_id"]).exists()

    def test_a_row_without_a_deployed_sha_is_not_copied(self, tmp_path, monkeypatch):
        _src, dst, stub, _row = _pair(tmp_path, monkeypatch)
        src_dir = tmp_path / "src"
        path = campaign._row_path(src_dir, stub["run_id"])
        body = json.loads(path.read_text())
        body["instrument"] = {k: v for k, v in body["instrument"].items() if k != "deployed"}
        path.write_text(json.dumps(body))
        assert campaign.reuse_incumbent_rows(dst, campaign.load_manifest(dst), [stub]) == []

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
        assert campaign.load_manifest(dst)["rows"][0]["state"] == "PASS"


class TestScreenReuse:
    def _pair(self, tmp_path, monkeypatch):
        _stub_trees(monkeypatch)
        monkeypatch.setattr(campaign, "CAMPAIGNS", tmp_path)
        suite = _suite(tmp_path)
        surface = campaign.expected_incumbent_surface(_stub(suite, role="challenger"))
        src_stub = _stub(suite, role="challenger", state="PASS")
        src = _open(tmp_path, "screen", suite, [src_stub], fp="old-fp")
        src_row = _source_row(suite, surface, arm_role="challenger", tier="screen")
        _write_row(src, src_row)
        dst_stub = _stub(suite, role="challenger")
        dst = _open(tmp_path, "confirm", suite, [dst_stub], fp="new-fp")
        manifest = campaign.load_manifest(dst)
        manifest["reuse_screen"] = ["screen"]
        campaign.save_manifest(dst, manifest)
        return src_row, dst, dst_stub

    def test_matching_screen_row_is_reused_with_source_provenance(self, tmp_path, monkeypatch):
        src_row, dst, stub = self._pair(tmp_path, monkeypatch)
        manifest = campaign.load_manifest(dst)
        copied = campaign.reuse_screen_rows(dst, manifest, [stub])
        assert copied == [stub["run_id"]]
        body = json.loads(campaign._row_path(dst, stub["run_id"]).read_text())
        assert body["reused_from"] == f"screen/{src_row['run_id']}"
        assert body["arm_role"] == "challenger"
        assert manifest["rows"][0]["reused_from"] == body["reused_from"]
        assert manifest["rows"][0]["state"] == "PASS"

    def test_fingerprint_mismatch_is_logged_and_not_reused(self, tmp_path, monkeypatch):
        _src_row, dst, stub = self._pair(tmp_path, monkeypatch)
        source_path = campaign._row_path(tmp_path / "screen", stub["run_id"])
        row = json.loads(source_path.read_text())
        row["sampling"] = {**row["sampling"], "temperature": 0.7}
        source_path.write_text(json.dumps(row))

        assert campaign.reuse_screen_rows(dst, campaign.load_manifest(dst), [stub]) == []
        assert not campaign._row_path(dst, stub["run_id"]).exists()
        log = (dst / "progress.log").read_text()
        assert "fingerprint mismatch ['sampling']" in log

    def test_source_is_recorded_in_manifest_and_cli_flag_is_repeatable(self, tmp_path, monkeypatch):
        _src_row, dst, _stub = self._pair(tmp_path, monkeypatch)
        plan = tmp_path / "plan.yaml"
        plan.write_text("workloads: {}\n")
        campaign.open_campaign("confirm", plan, [], append=False, reuse_screen=["older"])
        assert campaign.load_manifest(dst)["reuse_screen"] == ["screen", "older"]

        _parser, args = campaign._parse_args(
            ["--campaign-id", "confirm", "--reuse-screen", "screen", "--reuse-screen", "older"]
        )
        assert args.reuse_screen == ["screen", "older"]

    def test_report_lists_challenger_row_and_original_source(self, tmp_path):
        suite = _suite(tmp_path)
        row = _source_row(suite, ["read_pdf"], arm_role="challenger")
        row["run_id"] = "confirm/candidate/t1/r0"
        row["reused_from"] = "screen/original-run"
        reused = rep._reused_rows([row])
        assert reused == [
            {
                "run_id": "confirm/candidate/t1/r0",
                "arm_role": "challenger",
                "arm": MODEL,
                "workspace": WS,
                "suite": "documents_production",
                "task_id": "t1",
                "repeat": 0,
                "reused_from": "screen/original-run",
            }
        ]
        lines = []
        rep._sec_reused_rows(lines.append, {"reused_rows": reused})
        assert "confirm/candidate/t1/r0" in "\n".join(lines)
        assert "screen/original-run" in "\n".join(lines)
        warnings = rep._collect_warnings([row], {"rows": []}, False)
        assert any("1 row(s) reused" in warning for warning in warnings)


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
    assert counts[("pipeline", "tool_modules", "harness")] == 12


def test_math_b_to_d_auto_math_incumbents_do_not_match():
    """Read-only. b is the earlier auto-math confirm; d is the later one.
    Overlapping rows differ on the suite receipt and the pipeline trees."""
    b, d = DOCS / "wfe_math_20261018b", DOCS / "wfe_math_20261018d"
    if not (b / "manifest.json").is_file() or not (d / "manifest.json").is_file():
        pytest.skip("math campaigns b and d are not in this checkout")
    before = (d / "manifest.json").stat().st_mtime_ns
    report = campaign.incumbent_reuse_report(b, d)
    assert (d / "manifest.json").stat().st_mtime_ns == before
    by_id = {r["run_id"]: r for r in campaign.load_manifest(d)["rows"]}
    counts: dict[tuple, int] = {}
    n = 0
    for row in report["rows"]:
        if (by_id.get(row["run_id"]) or {}).get("workspace") != "auto-math":
            continue
        n += 1
        key = tuple(row["diffs"])
        counts[key] = counts.get(key, 0) + 1
    assert n == 108 and report["matched"] == 0
    assert counts[("no source row",)] == 72
    assert counts[("suite_digest", "pipeline", "harness")] == 36


def test_pipeline_digest_ignores_rebaseline_only_commits():
    """ad6e1342 only re-baselines the complexity budget and spine manifest: the
    serving digest must not move, or reuse is inert across every commit."""
    child, parent = "ad6e1342", "ad6e1342^"
    if not campaign.tree_at(child, "portal/platform/inference"):
        pytest.skip("history not available (shallow clone)")
    before = campaign.pipeline_at(campaign._git("rev-parse", parent).strip(), "auto-math")
    after = campaign.pipeline_at(campaign._git("rev-parse", child).strip(), "auto-math")
    assert before and before == after


def test_pipeline_digest_keys_on_the_rows_own_workspace_block():
    """538a38b7 reseated auto-math only: auto-math's digest moves, auto-documents' does not."""
    child = campaign._git("rev-parse", "538a38b7").strip()
    if not campaign.tree_at(child, "portal/platform/inference"):
        pytest.skip("history not available (shallow clone)")
    parent = campaign._git("rev-parse", "538a38b7^").strip()
    assert campaign.pipeline_at(parent, "auto-math") != campaign.pipeline_at(child, "auto-math")
    assert campaign.pipeline_at(parent, "auto-documents") == campaign.pipeline_at(
        child, "auto-documents"
    )


def test_variant_pipeline_digest_includes_base_and_variant_blocks(monkeypatch):
    import yaml

    base = {
        "engine": {
            "model_hint": "base-v1",
            "variants": {"math": {"temperature": 0.6}},
        }
    }
    variant_change = {
        "engine": {
            "model_hint": "base-v1",
            "variants": {"math": {"temperature": 0.7}},
        }
    }
    base_change = {
        "engine": {
            "model_hint": "base-v2",
            "variants": {"math": {"temperature": 0.6}},
        }
    }
    configs = {"a" * 40: base, "b" * 40: variant_change, "c" * 40: base_change}

    def fake_git(*args):
        if args[0] == "show":
            sha = args[1].split(":", 1)[0]
            return yaml.safe_dump({"workspaces": configs[sha]})
        return ""

    monkeypatch.setattr(campaign, "_git", fake_git)
    monkeypatch.setattr(campaign, "tree_at", lambda _sha, _path: "d" * 40)
    original = campaign.pipeline_at("a" * 40, "engine::math")

    assert original
    assert original != campaign.pipeline_at("b" * 40, "engine::math")
    assert original != campaign.pipeline_at("c" * 40, "engine::math")


def test_tool_index_places_route_served_and_async_tools(monkeypatch):
    """remember/recall are memory-server routes and execute_python is an async def; all
    three must place, and a route beats a same-named function in another module
    (field_journal's `def recall` used to claim the memory tool)."""
    sha = "a" * 40
    defs = "\n".join(
        [
            f"{sha}:portal/modules/coding/tools/code_sandbox_mcp.py:async def execute_python(",
            f"{sha}:portal/modules/security/core/field_journal.py:def recall(",
        ]
    )
    routes = "\n".join(
        [
            f'{sha}:portal/platform/memory/graph_memory.py:    mcp.custom_route("/tools/remember", methods=["POST"])(x)',
            f'{sha}:portal/platform/memory/graph_memory.py:    mcp.custom_route("/tools/recall", methods=["POST"])(x)',
        ]
    )

    def fake_git(*args: str) -> str:
        return routes if any("custom_route" in a for a in args) else defs

    monkeypatch.setattr(campaign, "_git", fake_git)
    monkeypatch.setattr(campaign, "_tool_index_cache", {})
    index = campaign._tool_index(sha)
    assert index["execute_python"] == "portal/modules/coding"
    assert index["remember"] == "portal/platform/memory"
    assert index["recall"] == "portal/platform/memory"


def test_tool_index_places_native_decorator_tools(monkeypatch):
    """A native `@mcp.tool()` in portal/platform places the tool and beats a same-named def."""
    sha = "b" * 40
    defs = f"{sha}:portal/modules/security/core/field_journal.py:def get_pipeline_status("
    native = "\n".join(
        [
            f"{sha}:portal/platform/mcp_host/pipeline_mcp.py:@mcp.tool()",
            f"{sha}:portal/platform/mcp_host/pipeline_mcp.py-async def get_pipeline_status(",
        ]
    )

    def fake_git(*args: str) -> str:
        if any("@mcp" in arg or "mcp\\.tool" in arg for arg in args):
            return native
        if any("custom_route" in arg for arg in args):
            return ""
        return defs

    monkeypatch.setattr(campaign, "_git", fake_git)
    monkeypatch.setattr(campaign, "_tool_index_cache", {})
    index = campaign._tool_index(sha)
    assert index["get_pipeline_status"] == "portal/platform/mcp_host"
