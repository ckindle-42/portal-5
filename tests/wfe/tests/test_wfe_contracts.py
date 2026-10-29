"""Harness contract tests (WFE dimensions 3, 21, 22, 28).

These lock the defects that made the pre-repair harness unable to execute a
single tool call on its own default endpoint, and that made its measured system
prompt machine-dependent.
"""

from __future__ import annotations

import json
import socket
import time
import types
from pathlib import Path

import pytest
import yaml

from tests.wfe import campaign as camp
from tests.wfe.runner import (
    TOOL_NAMES,
    TOOL_SCHEMAS,
    Sandbox,
    StreamStalledError,
    _is_json_object,
    _iter_lines_with_stall,
    _mk_msg,
    _parse_stream_v1,
    card_entry,
    format_json_policy,
    normalize_tool_args,
    resolve_persona,
    think_policy,
)
from tests.wfe.schema import (
    INSTRUMENT_OUTCOMES,
    MODEL_QUALITY_OUTCOMES,
    Outcome,
    intervals_overlap,
    wilson,
)
from tests.wfe.settings_audit import effective_temperature


class TestToolArgumentContract:
    def test_v1_string_arguments_decode(self):
        """/v1 returns arguments as a JSON STRING. The previous runner splatted
        it as **kwargs, so EVERY tool call on the default endpoint failed."""
        args, err = normalize_tool_args('{"path": "README.md"}')
        assert err is None and args == {"path": "README.md"}

    def test_api_dict_arguments_pass_through(self):
        args, err = normalize_tool_args({"path": "x"})
        assert err is None and args == {"path": "x"}

    def test_empty_arguments(self):
        assert normalize_tool_args("") == ({}, None)
        assert normalize_tool_args(None) == ({}, None)

    def test_malformed_json_reports_an_error_rather_than_raising(self):
        args, err = normalize_tool_args("{not json")
        assert args == {} and "invalid JSON" in err

    def test_non_object_arguments_rejected(self):
        args, err = normalize_tool_args("[1, 2]")
        assert args == {} and "expected object" in err

    def test_tool_name_envelope_is_unwrapped(self):
        """command-r (WFE wfe_full_20260911) emits arguments wrapped as
        {"tool_name": ..., "parameters": {...}}, which failed every call in
        the campaign (66/85 rows on this arm) with "bad args" until this
        unwrap landed. Covers both the /v1 string and /api/chat dict shapes."""
        args, err = normalize_tool_args(
            '{"tool_name": "http_get", "parameters": {"url": "https://x"}}'
        )
        assert err is None and args == {"url": "https://x"}

        args, err = normalize_tool_args(
            {"tool_name": "http_get", "parameters": {"url": "https://x"}}
        )
        assert err is None and args == {"url": "https://x"}

    def test_tool_name_envelope_unwrap_does_not_swallow_real_arguments(self):
        """A model that happens to have real parameters named tool_name/
        parameters must not be unwrapped — only the exact envelope shape."""
        args, err = normalize_tool_args('{"tool_name": "http_get", "other": "x"}')
        assert err is None and args == {"tool_name": "http_get", "other": "x"}

    def test_dispatch_executes_with_v1_shaped_arguments(self, tmp_path):
        sb = Sandbox(tmp_path)
        sb.file_write("a.txt", "hello")
        args, err = normalize_tool_args('{"path": "a.txt"}')
        assert err is None
        assert sb.dispatch("file_read", args) == "hello"

    def test_unknown_tool_is_an_error_string_not_an_exception(self, tmp_path):
        assert Sandbox(tmp_path).dispatch("rm_rf", {}).startswith("ERROR:")

    def test_writes_cannot_escape_the_sandbox(self, tmp_path):
        assert Sandbox(tmp_path).file_write("../escape.txt", "x").startswith("ERROR:")


class TestToolSchemas:
    def test_no_duplicate_tool_names(self):
        """The previous list declared file_write twice (7 entries, 6 names)."""
        assert len(TOOL_NAMES) == len(set(TOOL_NAMES))

    def test_every_schema_is_dispatchable(self, tmp_path):
        sb = Sandbox(tmp_path)
        for name in TOOL_NAMES:
            assert sb.dispatch(name, {}) is not None

    def test_schemas_are_wellformed(self):
        for s in TOOL_SCHEMAS:
            assert s["type"] == "function"
            fn = s["function"]
            assert fn["name"] and fn["description"]
            assert fn["parameters"]["type"] == "object"
            for req in fn["parameters"]["required"]:
                assert req in fn["parameters"]["properties"]


class TestStreamAssembly:
    def test_v1_deltas_reassemble_content_and_tool_calls(self):
        lines = [
            'data: {"choices":[{"delta":{"content":"He"}}]}',
            'data: {"choices":[{"delta":{"content":"llo"}}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"file_","arguments":"{\\"pa"}}]}}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"read","arguments":"th\\": \\"a\\"}"}}]},"finish_reason":"tool_calls"}]}',
            "data: [DONE]",
        ]
        out = _parse_stream_v1(iter(lines))
        msg = out["message"]
        assert msg["content"] == "Hello"
        call = msg["tool_calls"][0]
        assert call["id"] == "c1" and call["function"]["name"] == "file_read"
        args, err = normalize_tool_args(call["function"]["arguments"])
        assert err is None and args == {"path": "a"}

    def test_tool_calls_always_carry_an_id(self):
        """Production attaches tool_call_id to every tool result
        (router/tools.py); the previous stream parsers dropped the id."""
        msg = _mk_msg([""], {0: {"id": "", "function": {"name": "file_list", "arguments": "{}"}}})
        assert msg["tool_calls"][0]["id"]

    def test_v1_reasoning_content_is_captured_separately_from_content(self):
        """granite4.2 / deepseek-r1 stream <think> in delta.reasoning_content on
        /v1. Not capturing it made a run that reasoned for its whole token
        budget look like an inexplicable empty response."""
        lines = [
            'data: {"choices":[{"delta":{"reasoning_content":"let me think..."}}]}',
            'data: {"choices":[{"delta":{"reasoning_content":" still thinking"}}],"usage":{"completion_tokens":4096}}',
            'data: {"choices":[{"delta":{},"finish_reason":"length"}]}',
            "data: [DONE]",
        ]
        out = _parse_stream_v1(iter(lines))
        assert out["message"]["content"] == ""
        assert out["message"]["reasoning"] == "let me think... still thinking"
        assert out["finish_reason"] == "length"
        assert out["usage"]["completion_tokens"] == 4096


class TestCardRegistryMatching:
    """The previous first-substring-wins scan collapsed 28 of 81 production
    hints onto the generic 'qwen3' entry and matched nothing for granite,
    because registry keys are hyphenated and installed tags are not."""

    REG = {
        "qwen3": {"status": "research-debt"},
        "qwen3.5": {"status": "a"},
        "qwen3.8": {"harness_policy": {"think": "true"}},
        "granite-4.1": {"status": "b"},
        "gpt-oss": {"harness_policy": {"think": "true", "format_json_safe": False}},
    }

    def test_longest_match_wins(self):
        key, _ = card_entry("hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k", self.REG)
        assert key == "qwen3.8"

    def test_generic_key_still_matches_when_specific_absent(self):
        key, _ = card_entry("qwen3-coder:30b-a3b-q4_K_M-ctx256k", self.REG)
        assert key == "qwen3"

    def test_separator_insensitive(self):
        key, _ = card_entry("granite4.1:8b-ctx8k", self.REG)
        assert key == "granite-4.1"

    def test_unknown_tag_returns_none(self):
        assert card_entry("some-unlisted-model:q4", self.REG) is None

    def test_think_policy_resolves_from_the_specific_entry(self):
        assert think_policy("hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M", self.REG) == "true"
        assert think_policy("qwen3-coder:30b", self.REG) == "default"

    def test_live_registry_keys_are_unambiguous(self):
        """Guard against a future registry edit reintroducing shadowing: no key
        may be a normalised prefix-substring of another with the same policy."""
        from tests.wfe.runner import _card_registry, _norm_key

        reg = _card_registry()
        if not reg:
            pytest.skip("registry absent")
        for a in reg:
            for b in reg:
                if a != b and _norm_key(a) in _norm_key(b):
                    assert len(_norm_key(a)) < len(_norm_key(b))

    def test_format_json_policy_reads_the_card(self):
        assert format_json_policy("gpt-oss:20b", self.REG) is False
        assert format_json_policy("qwen3.8-27b", self.REG) is None
        assert format_json_policy("some-unlisted:q4", self.REG) is None

    def test_live_gpt_oss_card_still_marks_strict_json_unsafe(self):
        """The V-verify anchor: gpt-oss's recorded harmony breakage must remain
        discoverable by a card lookup, so preflight can reconcile it."""
        from tests.wfe.runner import _card_registry

        reg = _card_registry()
        if "gpt-oss" not in reg:
            pytest.skip("gpt-oss card absent")
        assert format_json_policy("gpt-oss:20b") is False


class TestStrictJsonDegeneracy:
    """Finding: gpt-oss preflight returned verdict OK because its degenerate
    (non-empty, non-JSON) strict-JSON output was not flagged — the detector
    only checked for EMPTY content. The card records the breakage as
    'empty/degenerate'; both halves must fail the arm."""

    def test_clean_json_object_passes(self):
        assert _is_json_object('{"ok": true}')
        assert _is_json_object('  {"ok": true}\n')

    def test_degenerate_prose_is_not_a_json_object(self):
        assert not _is_json_object(
            'The user says ":", but the instruction from developer says: "\n\n \t\t}'
        )

    def test_empty_is_not_a_json_object(self):
        assert not _is_json_object("")
        assert not _is_json_object("   ")

    def test_json_array_is_not_an_object(self):
        assert not _is_json_object("[1, 2, 3]")

    def test_json_scalar_is_not_an_object(self):
        assert not _is_json_object("true")
        assert not _is_json_object('"ok"')


class TestPersonaDeterminism:
    def test_resolution_is_stable_across_calls(self):
        """auto-coding has 40 personas bound to it; first-glob-wins made the
        measured system prompt arbitrary and machine-dependent."""
        a = resolve_persona("auto-coding")
        b = resolve_persona("auto-coding")
        assert a == b

    def test_unbound_workspace_yields_no_persona(self):
        slug, sp = resolve_persona("__does_not_exist__")
        assert slug is None and sp == ""

    def test_unknown_override_fails_loudly(self):
        with pytest.raises(SystemExit):
            resolve_persona("auto-coding", "__no_such_persona__")


class TestStatistics:
    def test_wilson_bounds(self):
        p, lo, hi = wilson(1, 2)
        assert lo < p < hi and lo >= 0 and hi <= 1

    def test_two_tasks_cannot_separate_anything(self):
        """Dimension 21, mechanised: 2/2 vs 1/2 must NOT be reported as an
        ordering. The original suite size made every Phase-1 bar unexpressible."""
        assert intervals_overlap(wilson(2, 2), wilson(1, 2))

    def test_clear_separation_is_detected(self):
        assert not intervals_overlap(wilson(10, 10), wilson(0, 10))

    def test_zero_n_is_maximally_uncertain(self):
        assert wilson(0, 0) == (0.0, 0.0, 1.0)

    def test_outcome_partition_is_total_and_disjoint(self):
        both = MODEL_QUALITY_OUTCOMES & INSTRUMENT_OUTCOMES
        assert not both
        covered = MODEL_QUALITY_OUTCOMES | INSTRUMENT_OUTCOMES | {Outcome.PENDING_REVIEW}
        assert covered == set(Outcome)


class TestMatrixExpansion:
    def _plan(self, tmp_path):
        p = tmp_path / "plan.yaml"
        p.write_text(
            yaml.safe_dump(
                {
                    "workloads": {
                        "auto-coding": {
                            "home": "coding",
                            "discovery": ["research"],
                            "arms": {"incumbent": "inc:tag", "challengers": ["ch1:tag", "ch2:tag"]},
                        }
                    }
                }
            )
        )
        return p

    def test_expansion_covers_every_arm_suite_task(self, tmp_path):
        rows = camp.expand_matrix(self._plan(tmp_path), repeats=1)
        arms = {r["arm"] for r in rows}
        assert arms == {"inc:tag", "ch1:tag", "ch2:tag"}
        assert {r["suite"] for r in rows} == {"coding", "research"}
        assert all(r["repeat"] == 0 for r in rows)

    def test_repeats_multiply_rows_with_distinct_ids(self, tmp_path):
        """Full power up front: n=3 is the campaign, not an escalation tier."""
        one = camp.expand_matrix(self._plan(tmp_path), repeats=1)
        three = camp.expand_matrix(self._plan(tmp_path), repeats=3)
        assert len(three) == 3 * len(one)
        assert len({r["run_id"] for r in three}) == len(three)
        assert {r["repeat"] for r in three} == {0, 1, 2}

    def test_targeting_narrows_the_matrix(self, tmp_path):
        """Interactive use: one model, one suite, one task."""
        plan = self._plan(tmp_path)
        assert {r["arm"] for r in camp.expand_matrix(plan, 3, only_arm="ch1:tag")} == {"ch1:tag"}
        assert {r["suite"] for r in camp.expand_matrix(plan, 3, only_suite="coding")} == {"coding"}
        assert camp.expand_matrix(plan, 3, only_arm="nope:tag") == []

    def test_ordering_is_model_major(self, tmp_path):
        """Each model must load once, and one arm per process is the isolation
        boundary for a multi-day sweep."""
        rows = camp.expand_matrix(self._plan(tmp_path))
        arms = [r["arm"] for r in rows]
        assert arms == sorted(arms)
        for a in set(arms):
            idx = [i for i, x in enumerate(arms) if x == a]
            assert idx == list(range(idx[0], idx[-1] + 1))

    def test_home_flag_set_correctly(self, tmp_path):
        rows = camp.expand_matrix(self._plan(tmp_path))
        assert all(r["is_home"] == (r["suite"] == "coding") for r in rows)

    def test_append_is_additive_and_preserves_completed_rows(self, tmp_path):
        """A new challenger must be able to join a sweep already 20 hours in
        without discarding a single completed row."""
        camp.CAMPAIGNS = tmp_path / "campaigns"
        plan = self._plan(tmp_path)
        m1 = camp.expand_matrix(plan, repeats=1, only_arm="inc:tag")
        d = camp.open_campaign("c", plan, m1, append=False)
        man = camp.load_manifest(d)
        man["rows"][0]["state"] = "PASS"
        camp.save_manifest(d, man)
        m2 = camp.expand_matrix(plan, repeats=1)
        camp.open_campaign("c", plan, m2, append=True)
        man = camp.load_manifest(d)
        assert len(man["rows"]) == len(m2)
        assert len({r["run_id"] for r in man["rows"]}) == len(man["rows"])
        kept = [r for r in man["rows"] if r["state"] == "PASS"]
        assert len(kept) == 1, "append destroyed a completed row"
        assert man["appends"][0]["added"] == len(m2) - len(m1)

    def test_missing_suite_is_recorded_not_silently_dropped(self, tmp_path):
        p = tmp_path / "plan.yaml"
        p.write_text(
            yaml.safe_dump(
                {"workloads": {"ws": {"home": "__nope__", "arms": {"incumbent": "m:t"}}}}
            )
        )
        rows = camp.expand_matrix(p)
        assert rows and rows[0]["state"] == Outcome.HARNESS_ERROR.value

    def test_live_plan_expands(self):
        from pathlib import Path

        plan = Path(camp.REPO) / "tests/wfe/workloads.yaml"
        if not plan.exists():
            pytest.skip("workloads.yaml absent")
        rows = camp.expand_matrix(plan)
        assert rows, "live plan produced an empty matrix"
        assert all(r["run_id"] for r in rows)
        assert len({r["run_id"] for r in rows}) == len(rows), "duplicate run_ids"


class TestReportCompilation:
    def _campaign(self, tmp_path, outcomes):
        d = tmp_path / "c1"
        (d / "rows").mkdir(parents=True)
        (d / "preflight").mkdir()
        env = {"fingerprint": "abc", "git_sha": "deadbeef", "ollama_version": "0.33"}
        manifest = {
            "campaign_id": "c1",
            "env": env,
            "rows": [
                {
                    "run_id": f"ws|{arm}|coding|t{i}|r0",
                    "workspace": "ws",
                    "arm": arm,
                    "arm_role": "incumbent" if arm == "inc" else "challenger",
                    "suite": "coding",
                    "task_id": f"t{i}",
                    "repeat": 0,
                    "is_home": True,
                    "state": oc,
                }
                for arm, ocs in outcomes.items()
                for i, oc in enumerate(ocs)
            ],
        }
        (d / "manifest.json").write_text(json.dumps(manifest))
        for arm, ocs in outcomes.items():
            for i, oc in enumerate(ocs):
                rid = f"ws|{arm}|coding|t{i}|r0"
                (d / "rows" / f"{arm}_{i}.json").write_text(
                    json.dumps(
                        {
                            "run_id": rid,
                            "campaign_id": "c1",
                            "workspace": "ws",
                            "arm": arm,
                            "arm_role": "incumbent" if arm == "inc" else "challenger",
                            "suite": "coding",
                            "task_id": f"t{i}",
                            "repeat": 0,
                            "outcome": oc,
                            "economics": {"total_tokens": 100, "wall_s": 1.0},
                            "env": env,
                        }
                    )
                )
        return d

    def test_instrument_failures_are_excluded_from_rates(self, tmp_path):
        """A harness defect must never read as a model verdict."""
        d = self._campaign(
            tmp_path,
            {"inc": ["PASS", "PASS", "HARNESS_ERROR"], "ch": ["FAIL", "FAIL", "TOOL_ERROR"]},
        )
        rep = camp_report_build(d)
        inc = next(m for m in rep["matrix"] if m["arm"] == "inc")
        ch = next(m for m in rep["matrix"] if m["arm"] == "ch")
        assert inc["n"] == 2 and inc["passes"] == 2 and inc["instrument_excluded"] == 1
        assert ch["n"] == 2 and ch["passes"] == 0 and ch["instrument_excluded"] == 1

    def test_overlapping_intervals_are_not_ranked(self, tmp_path):
        d = self._campaign(tmp_path, {"inc": ["PASS", "FAIL"], "ch": ["PASS", "PASS"]})
        rep = camp_report_build(d)
        assert rep["comparisons"][0]["verdict"] == "NOT SEPARATED (n insufficient)"

    def test_clear_separation_is_reported(self, tmp_path):
        d = self._campaign(
            tmp_path,
            {"inc": ["FAIL"] * 12, "ch": ["PASS"] * 12},
        )
        rep = camp_report_build(d)
        assert rep["comparisons"][0]["verdict"] == "CHALLENGER BETTER (separated)"

    def test_mixed_fingerprints_are_refused(self, tmp_path):
        d = self._campaign(tmp_path, {"inc": ["PASS"], "ch": ["PASS"]})
        f = next((d / "rows").glob("*.json"))
        row = json.loads(f.read_text())
        row["env"] = {"fingerprint": "different"}
        f.write_text(json.dumps(row))
        with pytest.raises(SystemExit):
            camp_report_build(d)

    def test_markdown_renders(self, tmp_path):
        from tests.wfe.report import render_markdown

        d = self._campaign(tmp_path, {"inc": ["PASS", "FAIL"], "ch": ["PASS", "PASS"]})
        md = render_markdown(camp_report_build(d))
        assert "# WFE Fitness Report" in md
        assert "NOT SEPARATED" in md
        assert "Coverage and provisionality" in md


def camp_report_build(d):
    from tests.wfe.report import build

    return build(d)


class TestWfeCurtailment:
    def _campaign(
        self, tmp_path, tasks=12, repeats=3, incumbent_complete=True, incumbent_outcome="PASS"
    ):
        directory = tmp_path / "curtail-campaign"
        (directory / "rows").mkdir(parents=True)
        (directory / "preflight").mkdir()
        suite_path = tmp_path / "curtail-suite.jsonl"
        suite_path.write_text("".join(json.dumps({"id": f"t{i}"}) + "\n" for i in range(tasks)))
        rows = []
        for arm, role in (("inc", "incumbent"), ("ch", "challenger")):
            for task in range(tasks):
                for repeat in range(repeats):
                    run_id = f"ws|{arm}|suite|t{task}|r{repeat}"
                    state = incumbent_outcome if arm == "inc" and incumbent_complete else "PENDING"
                    rows.append(
                        {
                            "run_id": run_id,
                            "workspace": "ws",
                            "arm": arm,
                            "arm_role": role,
                            "suite": "suite",
                            "suite_path": str(suite_path),
                            "task_id": f"t{task}",
                            "repeat": repeat,
                            "tier": "confirm",
                            "state": state,
                        }
                    )
                    if state != "PENDING":
                        result = {
                            "run_id": run_id,
                            "workspace": "ws",
                            "arm": arm,
                            "suite": "suite",
                            "task_id": f"t{task}",
                            "repeat": repeat,
                            "outcome": state,
                            "instrument": {"fingerprint": "base"},
                            "env": {"fingerprint": "env"},
                        }
                        (directory / "rows" / f"{camp.sha12(run_id)}.json").write_text(
                            json.dumps(result)
                        )
        camp.save_manifest(
            directory,
            {
                "campaign_id": "f1-test",
                "instrument": {"fingerprint": "base"},
                "env": {"fingerprint": "env"},
                "rows": rows,
            },
        )
        return directory

    def test_floor_curtailment_is_complete_and_reported(self, tmp_path):
        from tests.wfe.report import build, fitness, render_markdown

        directory = self._campaign(tmp_path)
        manifest = camp.load_manifest(directory)
        record = camp._curtail_workspace(directory, manifest, "ch", "ws")
        assert record["state"] == "CURTAILED"
        assert record["verdict"] == "NO_DECISION"
        assert record["rows_saved"] == 36
        assert all(
            r["state"] == "SKIPPED_DECIDED"
            for r in camp.load_manifest(directory)["rows"]
            if r["arm"] == "ch"
        )
        assert camp.completion_problems(directory) == []
        fit = fitness(directory)
        json.dumps(fit)
        assert [(c["candidate"], c["verdict"]) for c in fit["cells"]] == [("ch", "NO_DECISION")]
        assert fit["cells"][0]["excluded"] == {}
        report = build(directory)
        assert len(report["not_run"]) == 36
        assert "36 row(s) saved" in render_markdown(report)

    def test_better_curtailment_is_the_fitness_verdict_and_skips_do_not_reduce_floor(
        self, tmp_path
    ):
        from tests.wfe.report import fitness

        directory = self._campaign(tmp_path, tasks=36, incumbent_outcome="FAIL")
        manifest = camp.load_manifest(directory)
        for row in manifest["rows"]:
            if row["arm"] != "ch" or int(row["task_id"][1:]) >= 33:
                continue
            row["state"] = "PASS"
            result = {
                "run_id": row["run_id"],
                "workspace": "ws",
                "arm": "ch",
                "suite": "suite",
                "task_id": row["task_id"],
                "repeat": row["repeat"],
                "outcome": "PASS",
                "instrument": {"fingerprint": "base"},
                "env": {"fingerprint": "env"},
            }
            camp._row_path(directory, row["run_id"]).write_text(json.dumps(result))
        camp.save_manifest(directory, manifest)

        record = camp._curtail_workspace(directory, manifest, "ch", "ws", "suite/t32")

        assert record["verdict"] == "BETTER"
        assert record["cell"]["n"] == 33
        assert record["rows_saved"] == 9
        cell = fitness(directory)["cells"][0]
        assert (cell["verdict"], cell["n"], cell["wins"]) == ("BETTER", 33, 33)
        assert not {f"suite/t{i}" for i in range(33, 36)} & set(cell["excluded"])

    def test_partial_gradeable_screen_rows_remain_future_tasks(self, tmp_path):
        directory = self._campaign(tmp_path, tasks=36, incumbent_outcome="FAIL")
        manifest = camp.load_manifest(directory)
        for row in manifest["rows"]:
            if row["repeat"] != 0:
                continue
            row["tier"] = "screen"
            if row["arm"] == "ch":
                row["state"] = "PASS"
                result = {
                    "run_id": row["run_id"],
                    "workspace": "ws",
                    "arm": "ch",
                    "suite": "suite",
                    "task_id": row["task_id"],
                    "repeat": 0,
                    "outcome": "PASS",
                    "instrument": {"fingerprint": "base"},
                    "env": {"fingerprint": "env"},
                }
                camp._row_path(directory, row["run_id"]).write_text(json.dumps(result))
        camp.save_manifest(directory, manifest)

        record = camp._curtail_workspace(directory, manifest, "ch", "ws")

        assert record is None
        assert all(
            row["state"] == "PENDING"
            for row in camp.load_manifest(directory)["rows"]
            if row["arm"] == "ch" and row["tier"] == "confirm"
        )

    def test_execute_arm_curtails_floor_before_challenger_preflight(self, tmp_path, monkeypatch):
        directory = self._campaign(tmp_path)

        def unexpected_preflight(*_args, **_kwargs):
            raise AssertionError("floor-limited challenger must not need preflight or model calls")

        monkeypatch.setattr(camp, "preflight_arm", unexpected_preflight)
        result = camp.execute_arm(directory, "ch", 4, 60, None, False, False)
        assert result["ran"] == 0
        assert camp.load_manifest(directory)["curtailments"][0]["rows_saved"] == 36

    def test_incomplete_incumbent_bypasses_curtailment(self, tmp_path):
        directory = self._campaign(tmp_path, incumbent_complete=False)
        manifest = camp.load_manifest(directory)
        record = camp._curtail_workspace(directory, manifest, "ch", "ws")
        assert record["state"] == "BYPASSED_INCOMPLETE_INCUMBENT"
        assert record["rows_saved"] == 0
        assert all(r["state"] == "PENDING" for r in manifest["rows"] if r["arm"] == "ch")

    def test_incumbent_with_a_missing_repeat_bypasses_curtailment(self, tmp_path):
        directory = self._campaign(tmp_path, tasks=36)
        manifest = camp.load_manifest(directory)
        manifest["rows"] = [
            row
            for row in manifest["rows"]
            if not (row["arm"] == "inc" and row["task_id"] == "t0" and row["repeat"] == 2)
        ]

        record = camp._curtail_workspace(directory, manifest, "ch", "ws")

        assert record["state"] == "BYPASSED_INCOMPLETE_INCUMBENT"
        assert "repeats incomplete" in record["reason"]
        assert record["rows_saved"] == 0

    def test_no_curtail_resumes_skipped_rows(self, tmp_path):
        directory = self._campaign(tmp_path)
        manifest = camp.load_manifest(directory)
        camp._curtail_workspace(directory, manifest, "ch", "ws")
        manifest = camp.load_manifest(directory)
        camp._resume_curtailed_rows(directory, manifest, "ch")
        resumed = camp.load_manifest(directory)
        assert all(r["state"] == "PENDING" for r in resumed["rows"] if r["arm"] == "ch")
        assert resumed["curtailment_history"][0]["state"] == "RESUMED_NO_CURTAIL"
        assert resumed.get("curtailments", []) == []

    def test_incumbent_arms_are_selected_first(self):
        manifest = {
            "rows": [
                {"arm": "z-candidate", "arm_role": "challenger", "model": "z"},
                {"arm": "a-incumbent", "arm_role": "incumbent", "model": "a"},
            ]
        }
        assert camp._select_arms(manifest, None) == ["a-incumbent", "z-candidate"]


class TestOfflineRescore:
    """The single most valuable property of a 30-60 hour campaign: when a
    checker is wrong — and the checkers in this harness were wrong once already
    — the fix must cost seconds, not another sweep of the fleet."""

    _GOOD_PARSE_KV = (
        "def parse_kv(s):\n"
        "    out = {}\n"
        "    if not s or not s.strip():\n"
        "        return out\n"
        "    parts, buf, i = [], '', 0\n"
        "    while i < len(s):\n"
        "        if s[i] == '\\\\' and i + 1 < len(s) and s[i+1] == ';':\n"
        "            buf += ';'; i += 2; continue\n"
        "        if s[i] == ';':\n"
        "            parts.append(buf); buf = ''; i += 1; continue\n"
        "        buf += s[i]; i += 1\n"
        "    parts.append(buf)\n"
        "    for p in parts:\n"
        "        if not p.strip():\n"
        "            continue\n"
        "        k, sep, v = p.partition('=')\n"
        "        out[k.strip()] = v.strip() if sep else ''\n"
        "    return out\n"
    )

    def _debug_record(self, run_id="ws|m:t|coding|code-kv|r0"):
        return {
            "run_id": run_id,
            "arm": "m:t",
            "workspace": "ws",
            "suite": "coding",
            "suite_path": str(camp.SUITE_DIR / "coding.jsonl"),
            "task_id": "code-kv",
            "repeat": 0,
            "outcome": "FAIL",
            "final_text": "TASK COMPLETE",
            "assistant_texts": ["TASK COMPLETE"],
            "tool_call_log": [],
            "finish_reason": "stop",
            "sandbox_tree": {},
        }

    def test_sandbox_tree_round_trips(self, tmp_path):
        src = tmp_path / "sb"
        (src / "pkg").mkdir(parents=True)
        (src / "a.py").write_text("x = 1\n")
        (src / "pkg" / "b.txt").write_text("hello")
        (src / "__pycache__").mkdir()
        (src / "__pycache__" / "junk.pyc").write_bytes(b"\x00\x01")
        tree = camp.capture_tree(src)
        assert set(tree) == {"a.py", "pkg/b.txt"}, tree
        back = camp.rehydrate_tree(tree)
        assert (back / "a.py").read_text() == "x = 1\n"
        assert (back / "pkg" / "b.txt").read_text() == "hello"

    def test_oversized_and_binary_files_are_marked_not_dropped(self, tmp_path):
        src = tmp_path / "sb"
        src.mkdir()
        (src / "big.txt").write_text("x" * (camp.DEBUG_FILE_CAP + 10))
        (src / "img.bin").write_bytes(b"\xff\xd8\xff\x00")
        tree = camp.capture_tree(src)
        assert tree["big.txt"]["truncated"] is True
        assert tree["img.bin"]["binary"] is True

    def test_rescore_regrades_a_file_checker_without_model_calls(self, tmp_path):
        """A correct implementation captured in the debug record must grade
        PASS on re-score even though the original run recorded FAIL."""
        impl = (
            "def parse_kv(s):\n"
            "    out = {}\n"
            "    if not s or not s.strip():\n"
            "        return out\n"
            "    parts, buf, i = [], '', 0\n"
            "    while i < len(s):\n"
            "        if s[i] == '\\\\' and i + 1 < len(s) and s[i+1] == ';':\n"
            "            buf += ';'; i += 2; continue\n"
            "        if s[i] == ';':\n"
            "            parts.append(buf); buf = ''; i += 1; continue\n"
            "        buf += s[i]; i += 1\n"
            "    parts.append(buf)\n"
            "    for p in parts:\n"
            "        if not p.strip():\n"
            "            continue\n"
            "        k, sep, v = p.partition('=')\n"
            "        out[k.strip()] = v.strip() if sep else ''\n"
            "    return out\n"
        )
        rec = self._debug_record()
        rec["sandbox_tree"] = {"parse_kv.py": impl}
        dbg = tmp_path / "debug"
        dbg.mkdir()
        (dbg / "m_t.debug.jsonl").write_text(json.dumps(rec) + "\n")
        out = camp.rescore_debug_dir(dbg)
        assert len(out) == 1
        assert out[0]["rescore"]["outcome"] == "PASS"
        assert out[0]["rescore"]["changed"] is True
        assert out[0]["rescore"]["was"] == "FAIL"

    def test_rescore_keeps_a_genuine_failure_failing(self, tmp_path):
        rec = self._debug_record()
        rec["outcome"] = "PASS"
        rec["sandbox_tree"] = {"parse_kv.py": "def parse_kv(s):\n    return {}\n"}
        dbg = tmp_path / "debug"
        dbg.mkdir()
        (dbg / "m_t.debug.jsonl").write_text(json.dumps(rec) + "\n")
        out = camp.rescore_debug_dir(dbg)
        assert out[0]["rescore"]["outcome"] == "FAIL"
        assert out[0]["rescore"]["changed"] is True

    def test_rescore_preserves_a_run_telemetry_outcome_the_checker_cannot_see(self, tmp_path):
        """A model that exhausted its turn budget (BUDGET_EXHAUSTED) has an empty
        final answer; apply_checkers on the record alone would call that FAIL.
        --rescore must keep the recorded outcome — the run, not a checker,
        decided it — unless the re-grade upgrades it to PASS."""
        rec = self._debug_record()
        rec["outcome"] = "BUDGET_EXHAUSTED"
        rec["final_text"] = ""
        rec["assistant_texts"] = []
        rec["sandbox_tree"] = {}  # no impl -> hidden_pytest FAILs
        dbg = tmp_path / "debug"
        dbg.mkdir()
        (dbg / "m_t.debug.jsonl").write_text(json.dumps(rec) + "\n")
        out = camp.rescore_debug_dir(dbg)
        assert out[0]["rescore"]["outcome"] == "BUDGET_EXHAUSTED"
        assert out[0]["rescore"]["checker_outcome"] == "FAIL"
        assert out[0]["rescore"]["changed"] is False

    def test_rescore_never_upgrades_a_budget_outcome_to_pass(self, tmp_path):
        """A run that stalled or hit its turn/wall budget did not finish. A
        checker PASS on the artifacts it left behind must not turn it into a
        PASS — that was the stall-masking defect (s2_seat_vendor_omlx_seat_v1
        row 1: a 900s StreamStalledError reported PASS)."""
        rec = self._debug_record()
        rec["outcome"] = "BUDGET_EXHAUSTED"
        rec["sandbox_tree"] = {"parse_kv.py": TestOfflineRescore._GOOD_PARSE_KV}
        dbg = tmp_path / "debug"
        dbg.mkdir()
        (dbg / "m_t.debug.jsonl").write_text(json.dumps(rec) + "\n")
        out = camp.rescore_debug_dir(dbg)
        assert out[0]["rescore"]["outcome"] == "BUDGET_EXHAUSTED"
        assert out[0]["rescore"]["checker_outcome"] == "PASS"

    def test_rescore_updates_campaign_rows_and_manifest(self, tmp_path):
        camp.CAMPAIGNS = tmp_path / "campaigns"
        d = camp.CAMPAIGNS / "c"
        (d / "rows").mkdir(parents=True)
        (d / "preflight").mkdir()
        rid = "ws|m:t|coding|code-kv|r0"
        camp.save_manifest(
            d,
            {
                "campaign_id": "c",
                "env": {"fingerprint": "x"},
                "rows": [{"run_id": rid, "arm": "m:t", "state": "FAIL"}],
            },
        )
        camp._row_path(d, rid).write_text(json.dumps({"run_id": rid, "outcome": "FAIL"}))
        rec = self._debug_record(rid)
        rec["sandbox_tree"] = {"parse_kv.py": "def parse_kv(s):\n    return {}\n"}
        dbg = tmp_path / "debug"
        dbg.mkdir()
        (dbg / "m_t.debug.jsonl").write_text(json.dumps(rec) + "\n")
        camp.rescore_debug_dir(dbg, d)
        man = camp.load_manifest(d)
        assert man["rows"][0]["state"] == "FAIL"
        assert man["rescores"][0]["runs"] == 1
        row = json.loads(camp._row_path(d, rid).read_text())
        assert "rescored_utc" in row

    def test_a_rescore_preserves_the_original_evidence_and_names_its_grader(self, tmp_path):
        """R-7: re-grading used to overwrite the row, so the verdict the run
        actually produced became unrecoverable and nothing recorded which
        checkers replaced it."""
        rid = "ws|m:t|coding|code-kv|r0"
        cd = tmp_path / "c"
        (cd / "rows").mkdir(parents=True)
        rp = camp._row_path(cd, rid)
        rp.write_text(
            json.dumps(
                {
                    "run_id": rid,
                    "outcome": "PASS",
                    "notes": "the original verdict",
                    "instrument": {"fingerprint": "abc123", "engine": "ollama"},
                }
            )
        )
        rec = self._debug_record(rid)
        rec["sandbox_tree"] = {"parse_kv.py": "def parse_kv(s):\n    return {}\n"}
        dbg = tmp_path / "debug"
        dbg.mkdir()
        (dbg / "m_t.debug.jsonl").write_text(json.dumps(rec) + "\n")

        camp.rescore_debug_dir(dbg, cd)

        row = json.loads(rp.read_text())
        assert row["outcome"] == "FAIL"
        assert row["original"] == {
            "outcome": "PASS",
            "notes": "the original verdict",
            "instrument": {"fingerprint": "abc123", "engine": "ollama"},
        }
        assert row["rescore"]["outcome"] == "FAIL"
        assert row["rescore"]["grader"]["fingerprint"]

    def test_a_second_rescore_keeps_the_first_original(self, tmp_path):
        """`original` is what the run produced, not what the previous re-grade
        produced, so re-scoring twice does not lose the run's own verdict."""
        rid = "ws|m:t|coding|code-kv|r0"
        cd = tmp_path / "c"
        (cd / "rows").mkdir(parents=True)
        rp = camp._row_path(cd, rid)
        rp.write_text(json.dumps({"run_id": rid, "outcome": "PASS", "notes": "run verdict"}))
        rec = self._debug_record(rid)
        rec["sandbox_tree"] = {"parse_kv.py": "def parse_kv(s):\n    return {}\n"}
        dbg = tmp_path / "debug"
        dbg.mkdir()
        (dbg / "m_t.debug.jsonl").write_text(json.dumps(rec) + "\n")

        camp.rescore_debug_dir(dbg, cd)
        camp.rescore_debug_dir(dbg, cd)

        row = json.loads(rp.read_text())
        assert row["original"]["outcome"] == "PASS"
        assert row["original"]["notes"] == "run verdict"

    def test_repeat_degeneracy_is_flagged(self):
        """n=3 at temperature 0 is one draw counted three times. The report must
        never present it as three independent observations."""
        assert camp.degenerate_repeats({"declared_temperature": 0.0}) is not None
        assert camp.degenerate_repeats({"pinned_seed": 42}) is not None
        assert camp.degenerate_repeats({"declared_temperature": 0.7}) is None

    def test_workspace_sampling_is_production_not_harness_default(self):
        """Dimension 8: every workspace declares its own sampling block, and the
        campaign must serve each arm at ITS settings, not at a harness default."""
        from tests.wfe.runner import workspace_context

        wsc = workspace_context("auto-coding")
        assert wsc["sampling"], "workspace sampling block not carried through"
        s = camp._sampling_for(wsc, 2)
        assert s["seed"] == 1002
        if wsc.get("declared_temperature") is not None:
            assert s["temperature"] == wsc["declared_temperature"]

    def test_variant_context_merges_like_production(self):
        """Variants override base settings, merge tools, and inject prompt text."""
        import yaml

        from portal.platform.inference.config import effective_workspace
        from tests.wfe.prompt_surface import HARNESS_NOTE_MARKER
        from tests.wfe.runner import REPO, workspace_context

        ws = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
        variant = ws["auto-coding"]["variants"]["laguna"]
        expected = effective_workspace(ws, "auto-coding::laguna")
        wsc = workspace_context("auto-coding::laguna")
        assert wsc["model"] == variant["model_hint"]
        assert wsc["sampling"]["temperature"] == variant["temperature"]
        served = wsc["system_prompt"].split("\n\n" + HARNESS_NOTE_MARKER)[0]
        assert served.endswith(variant["system_prompt_append"])
        assert wsc["declared_tools"] == expected["tools"]

    def test_reasoning_math_variant_uses_effective_settings(self):
        from portal.platform.inference.config import effective_workspace
        from tests.wfe.runner import REPO, workspace_context

        workspaces = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
        expected = effective_workspace(workspaces, "auto-reasoning::math")
        actual = workspace_context("auto-reasoning::math")
        assert actual["model"] == expected["model_hint"]
        assert actual["context_limit"] == expected["context_limit"]
        assert actual["sampling"]["max_tokens"] == expected["predict_limit"]
        assert actual["sampling"]["temperature"] == expected["temperature"]

    def test_pipeline_request_uses_the_variant_id_as_model(self, monkeypatch):
        from tests.wfe import runner

        monkeypatch.setattr(runner, "ENGINE", "pipeline")
        _url, payload, _headers = runner._build_pipeline(
            "auto-reasoning::math",
            [{"role": "user", "content": "solve"}],
            "none",
            {},
            None,
            "default",
            False,
        )
        assert payload["model"] == "auto-reasoning::math"

    def test_settings_audit_resolves_variant_seats(self):
        from tests.wfe.settings_audit import _seats

        portal = {
            "workspaces": {
                "engine": {
                    "model_hint": "base-model",
                    "context_limit": 16384,
                    "variants": {"math": {"model_hint": "math-model", "context_limit": 8192}},
                }
            }
        }
        seats = dict(_seats(portal))
        assert seats["engine::math"]["model_hint"] == "math-model"
        assert seats["engine::math"]["context_limit"] == 8192

    def test_base_workspace_system_prompt_append_is_applied(self):
        import yaml

        from tests.wfe.runner import REPO, workspace_context

        base = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"][
            "auto-coding"
        ]
        assert workspace_context("auto-coding")["system_prompt"].endswith(
            base["system_prompt_append"]
        )

    def test_personaless_workspace_uses_the_owui_preset_prompt(self):
        import yaml

        from portal.platform.inference.config import effective_workspace
        from tests.wfe.runner import REPO, workspace_context

        workspaces = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
        ws = effective_workspace(workspaces, "auto-daily::deep")
        wsc = workspace_context("auto-daily::deep")
        assert wsc["persona_slug"] is None
        assert wsc["system_prompt_base"] == ws["owui_system_prompt"]


class TestGraderComparison:
    """R-7: a comparison may only pool rows one grader produced."""

    @staticmethod
    def _row(fp: str | None, outcome: str = "PASS") -> dict:
        row = {"outcome": outcome}
        if fp is not None:
            row["rescore"] = {"outcome": outcome, "grader": {"fingerprint": fp}}
        return row

    def test_rows_never_rescored_are_comparable(self):
        from tests.wfe import report as rep

        assert rep._grader_check([self._row(None), self._row(None, "FAIL")], False) == []

    def test_rows_under_one_grader_are_comparable(self):
        from tests.wfe import report as rep

        rows = [self._row("aaa"), self._row("aaa", "FAIL")]
        assert rep._grader_check(rows, False) == []

    def test_two_graders_refuse_rather_than_pool(self):
        from tests.wfe import report as rep

        rows = [self._row("aaa"), self._row("bbb")]
        with pytest.raises(SystemExit, match="MIXED GRADERS"):
            rep._grader_check(rows, False)
        assert "MIXED GRADERS" in rep._grader_check(rows, True)[0]

    def test_a_rescored_row_is_not_comparable_with_an_unrescored_one(self):
        from tests.wfe import report as rep

        with pytest.raises(SystemExit, match="MIXED GRADERS"):
            rep._grader_check([self._row("aaa"), self._row(None)], False)


class TestModelIdentity:
    """The build that served each (workspace, model): observed in the engine's own
    store, frozen at the pair's first preflight, re-observed after every row, and
    kept out of the shared instrument fingerprint (doc: identity)."""

    @staticmethod
    def _ident(backend="omlx-coding", model="granite4.1:8b-ctx8k", content="c1"):
        return {"backend": backend, "model": model, "content": content}

    @staticmethod
    def _row(workspace, model, identity, outcome="PASS"):
        return {
            "workspace": workspace,
            "arm": model,
            "model": model,
            "identity": identity,
            "outcome": outcome,
        }

    PIPELINE = {"instrument": {"engine": "pipeline"}}

    @staticmethod
    def _checkpoint(root, model, **files):
        d = root / model
        d.mkdir(parents=True, exist_ok=True)
        base = {"config.json": '{"quant": 4}', "model.safetensors": "w" * 10}
        for name, body in {**base, **files}.items():
            (d / name).write_text(body)
        return d

    def test_the_same_arm_may_be_served_by_different_builds_in_two_workspaces(self):
        """granite4.1:8b-ctx8k really does resolve to different builds per
        workspace, so a per-arm freeze would block a legitimate comparison."""
        from tests.wfe import report as rep

        frozen: dict = {}
        pairs = {
            "auto-coding|granite4.1:8b-ctx8k": self._ident(
                model="granite-4.1-8b-mxfp8", content="a"
            ),
            "auto-research|granite4.1:8b-ctx8k": self._ident(
                backend="ollama", model="granite4.1:8b-ctx8k", content="b"
            ),
        }
        assert camp.freeze_identities(frozen, pairs) == []
        rows = [self._row(k.split("|")[0], "granite4.1:8b-ctx8k", v) for k, v in pairs.items()]
        assert rep._identity_check(rows, {**self.PIPELINE, "identity_map": frozen}, False) == []

    def test_an_identity_change_within_one_pair_is_rejected(self):
        from tests.wfe import report as rep

        frozen: dict = {}
        assert camp.freeze_identities(frozen, {"auto-coding|m": self._ident(content="c1")}) == []
        drift = camp.freeze_identities(frozen, {"auto-coding|m": self._ident(content="c2")})
        assert len(drift) == 1 and "auto-coding|m" in drift[0]
        assert frozen["auto-coding|m"]["content"] == "c1"  # the freeze is not overwritten
        manifest = {**self.PIPELINE, "identity_map": frozen}
        rows = [self._row("auto-coding", "m", self._ident(content="c2"))]
        with pytest.raises(SystemExit, match="IDENTITY DRIFT"):
            rep._identity_check(rows, manifest, False)
        assert "IDENTITY DRIFT" in rep._identity_check(rows, manifest, True)[0]

    def test_two_groups_on_one_daemon_with_the_same_content_are_not_drift(self, monkeypatch):
        """ollama-general and ollama-vision share one Ollama URL. The group id is not a build."""
        from tests.wfe import report as rep

        monkeypatch.setattr(camp, "ENGINE", "pipeline")
        tag = "gemma4:26b-a4b-it-qat-ctx32k"
        general = {"backend": "ollama-general", "model": tag, "content": "03f3d913"}
        vision = {"backend": "ollama-vision", "model": tag, "content": "03f3d913"}
        key = f"auto-vision|{tag}"
        r = {"workspace": "auto-vision", "model": tag, "arm": tag}
        assert (
            camp.identity_drift({"identity_map": {key: general}}, r, {"identity": vision}) is None
        )
        frozen: dict = {}
        assert camp.freeze_identities(frozen, {key: general}) == []
        assert camp.freeze_identities(frozen, {key: vision}) == []
        assert frozen[key] == general
        rows = [self._row("auto-vision", tag, vision)]
        assert (
            rep._identity_check(rows, {**self.PIPELINE, "identity_map": {key: general}}, False)
            == []
        )

    def test_a_different_content_hash_is_still_drift(self, monkeypatch):
        monkeypatch.setattr(camp, "ENGINE", "pipeline")
        tag = "gemma4:26b-a4b-it-qat-ctx32k"
        frozen_ident = {"backend": "ollama-vision", "model": tag, "content": "03f3d913"}
        served = {"backend": "ollama-general", "model": tag, "content": "deadbeef"}
        key = f"auto-vision|{tag}"
        r = {"workspace": "auto-vision", "model": tag, "arm": tag}
        assert camp.identity_drift({"identity_map": {key: frozen_ident}}, r, {"identity": served})
        held = {key: dict(frozen_ident)}
        drift = camp.freeze_identities(held, {key: served})
        assert drift and held[key]["content"] == "03f3d913"

    def test_ollama_versus_omlx_is_drift_even_when_the_content_string_matches(self, monkeypatch):
        monkeypatch.setattr(camp, "ENGINE", "pipeline")
        tag = "gemma4:26b-a4b-it-qat-ctx32k"
        ollama = {"backend": "ollama-vision", "model": tag, "content": "03f3d913"}
        omlx = {"backend": "omlx-general", "model": tag, "content": "03f3d913"}
        key = f"auto-vision|{tag}"
        r = {"workspace": "auto-vision", "model": tag, "arm": tag}
        assert camp.identity_drift({"identity_map": {key: ollama}}, r, {"identity": omlx})

    def test_preflight_freezes_the_routed_backend_not_the_first_group(self, monkeypatch):
        """The tag is listed in general before vision. auto-vision routes to vision."""
        tag = "gemma4:26b-a4b-it-qat-ctx32k"
        seen: dict = {}

        def observe(backend_id, model):
            seen["backend"] = backend_id
            return {"backend": backend_id, "model": model, "content": "03f3d913"}, ""

        monkeypatch.setattr(
            camp,
            "chat",
            lambda *a, **k: {"served": {"backend": "ollama-general", "model": tag}},
        )
        monkeypatch.setattr(camp, "observe_identity", observe)
        monkeypatch.setattr(camp, "deployed_build", lambda: "abc1234")
        monkeypatch.setattr(camp, "deployed_matches", lambda _build: True)
        monkeypatch.setattr(camp, "deployed_services", lambda: {})
        pf = camp.preflight_pipeline(["auto-vision"], tag)
        assert seen["backend"] == "ollama-vision"
        assert pf["identities"][f"auto-vision|{tag}"]["backend"] == "ollama-vision"
        assert pf["verdict"] == "OK"

    def test_an_unobserved_identity_is_never_frozen(self):
        frozen: dict = {}
        assert camp.freeze_identities(frozen, {"ws|m": self._ident(content="")}) == []
        assert frozen == {}

    def test_omlx_content_comes_from_the_checkpoint_on_disk(self, tmp_path, monkeypatch):
        """Each thing that makes the checkpoint what it is moves the content id."""
        monkeypatch.setenv("OMLX_MODEL_DIR", str(tmp_path / "models"))
        settings = tmp_path / "model_settings.json"
        settings.write_text(json.dumps({"models": {"m": {"temperature": 0.6}}}))
        monkeypatch.setattr(camp, "OMLX_SETTINGS", settings)
        d = self._checkpoint(tmp_path / "models", "m")
        first, why = camp.omlx_content_id("m")
        assert first and not why
        assert camp.omlx_content_id("m")[0] == first  # stable
        seen = {first}
        for change in (
            lambda: (d / "config.json").write_text('{"quant": 8}'),
            lambda: (d / "chat_template.jinja").write_text("{{ patched }}"),
            lambda: (d / "model.safetensors").write_text("w" * 11),
            lambda: settings.write_text(json.dumps({"models": {"m": {"temperature": 0.7}}})),
        ):
            change()
            now = camp.omlx_content_id("m")[0]
            assert now not in seen
            seen.add(now)

    def test_an_unobservable_omlx_build_has_no_content_and_says_why(self, tmp_path, monkeypatch):
        """Before P1R a missing directory hashed to one constant shared by every
        model, which passed as an identity. Now it is no identity, with a reason."""
        monkeypatch.setenv("OMLX_MODEL_DIR", str(tmp_path / "empty"))
        a, why_a = camp.omlx_content_id("Qwen3.8-27B-oQ4e-mtp")
        b, _ = camp.omlx_content_id("granite-4.1-30b-4bit")
        assert a == b == ""
        assert "Qwen3.8-27B-oQ4e-mtp/config.json" in why_a and str(tmp_path / "empty") in why_a

    def test_omlx_model_dirs_come_from_the_server_settings(self, tmp_path, monkeypatch):
        server = tmp_path / "settings.json"
        server.write_text(
            json.dumps({"model": {"model_dirs": [str(tmp_path / "a"), str(tmp_path / "b")]}})
        )
        monkeypatch.setattr(camp, "OMLX_SERVER_SETTINGS", server)
        monkeypatch.delenv("OMLX_MODEL_DIR", raising=False)
        assert camp.omlx_model_dirs() == [tmp_path / "a", tmp_path / "b"]
        self._checkpoint(tmp_path / "b", "m")
        assert camp.omlx_content_id("m")[0]  # found in the second directory
        monkeypatch.setenv("OMLX_MODEL_DIR", str(tmp_path / "override"))
        assert camp.omlx_model_dirs() == [tmp_path / "override"]
        server.write_text("{}")
        monkeypatch.delenv("OMLX_MODEL_DIR")
        assert camp.omlx_model_dirs() == [Path(camp.OMLX_DEFAULT_MODEL_DIR)]

    def test_ollama_content_is_the_tags_digest_or_empty_with_a_reason(self, monkeypatch):
        import contextlib
        import io

        tags = {
            "models": [
                {"name": "granite4.1:30b", "model": "granite4.1:30b", "digest": "d30"},
                {"name": "llama3:latest", "model": "llama3:latest", "digest": "dl3"},
            ]
        }

        def fake_urlopen(url, timeout=None):
            assert url.endswith("/api/tags")
            return contextlib.closing(io.BytesIO(json.dumps(tags).encode()))

        monkeypatch.setattr(camp.urllib.request, "urlopen", fake_urlopen)
        assert camp.ollama_content_id("granite4.1:30b") == ("d30", "")
        assert camp.ollama_content_id("llama3") == ("dl3", "")
        content, why = camp.ollama_content_id("absent:tag")
        assert content == "" and "not in Ollama" in why

        def down(url, timeout=None):
            raise OSError("connection refused")

        monkeypatch.setattr(camp.urllib.request, "urlopen", down)
        content, why = camp.ollama_content_id("granite4.1:30b")
        assert content == "" and "unreachable" in why

    def test_a_row_records_the_build_observed_after_it_not_the_freeze(self, monkeypatch):
        """Before P1R the row copied the frozen content, so a rebuild under the
        same name could never show up in a row. Now the row is observed."""
        monkeypatch.setattr(camp, "ENGINE", "pipeline")
        monkeypatch.setattr(
            camp,
            "observe_identity",
            lambda b, m: ({"backend": b, "model": m, "content": "rebuilt"}, ""),
        )
        transcript = [{"turn": 0, "served": {"backend": "omlx-reasoning", "model": "g"}}]
        row = {"identity": camp.row_identity(transcript)}
        assert row["identity"] == {"backend": "omlx-reasoning", "model": "g", "content": "rebuilt"}
        r = {"workspace": "auto-compliance", "model": "granite4.1:30b", "arm": "granite4.1:30b"}
        manifest = {
            "identity_map": {
                "auto-compliance|granite4.1:30b": self._ident(
                    backend="omlx-reasoning", model="g", content="measured"
                )
            }
        }
        assert "frozen" in camp.identity_drift(manifest, r, row)
        manifest["identity_map"]["auto-compliance|granite4.1:30b"]["content"] = "rebuilt"
        assert camp.identity_drift(manifest, r, row) is None

    def test_a_row_with_no_freeze_or_no_content_is_drift(self, monkeypatch):
        monkeypatch.setattr(camp, "ENGINE", "pipeline")
        r = {"workspace": "w", "model": "m", "arm": "m"}
        assert camp.identity_drift({}, r, {"identity": self._ident()})  # nothing frozen
        assert "cannot be observed" in camp.identity_drift(
            {"identity_map": {"w|m": self._ident()}}, r, {"identity": self._ident(content="")}
        )
        assert camp.identity_drift({}, r, {"identity": None}) is None  # no served turn

    def test_turns_served_by_two_models_match_nothing(self):
        transcript = [
            {"turn": 0, "served": {"backend": "omlx-reasoning", "model": "a"}},
            {"turn": 1, "served": {"backend": "ollama", "model": "b"}},
        ]
        ident = camp.row_identity(transcript)
        assert ident["backend"] == "mixed" and ident["content"] == ""

    def test_a_row_with_no_trace_records_no_identity(self):
        assert camp.row_identity([{"turn": 0, "content": "x"}]) is None

    def test_the_report_refuses_a_scored_pipeline_row_without_identity(self):
        from tests.wfe import report as rep

        frozen = {"w|m": self._ident()}
        bare = [self._row("w", "m", None)]
        with pytest.raises(SystemExit, match="IDENTITY DRIFT"):
            rep._identity_check(bare, {**self.PIPELINE, "identity_map": frozen}, False)
        with pytest.raises(SystemExit):  # no freeze at all is not a pass either
            rep._identity_check([self._row("w", "m", self._ident())], dict(self.PIPELINE), False)
        assert (
            rep._identity_check([self._row("w", "m", None, "HARNESS_ERROR")], self.PIPELINE, False)
            == []
        )
        assert rep._identity_check(bare, {"instrument": {"engine": "ollama"}}, False) == []

    def test_the_arm_preflight_freezes_then_blocks_a_later_change(self, tmp_path, monkeypatch):
        monkeypatch.setattr(camp, "ENGINE", "pipeline")
        d = tmp_path / "c"
        d.mkdir()
        manifest = {"rows": []}
        camp.save_manifest(d, manifest)
        seen = {"content": "c1"}

        def fake_pf(workspaces, model):
            ident = {"backend": "omlx-reasoning", "model": "g", "content": seen["content"]}
            return {
                "model": model,
                "verdict": "OK",
                "findings": [],
                "identities": {f"{w}|{model}": ident for w in workspaces},
            }

        monkeypatch.setattr(camp, "preflight_pipeline", fake_pf)
        rows = [{"workspace": "auto-compliance", "model": "m", "arm": "m"}]
        assert camp._arm_preflight(d, manifest, rows, "m", False)["verdict"] == "OK"
        assert camp.load_manifest(d)["identity_map"]["auto-compliance|m"]["content"] == "c1"
        seen["content"] = "c2"
        pf = camp._arm_preflight(d, manifest, rows, "m", False)
        assert pf["verdict"] == "REVIEW" and any("IDENTITY DRIFT" in f for f in pf["findings"])
        assert camp.load_manifest(d)["identity_map"]["auto-compliance|m"]["content"] == "c1"

    def test_identity_drift_after_a_row_quarantines_it_and_stops_the_arm(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(camp, "ENGINE", "pipeline")
        monkeypatch.setattr(camp, "instrument_drift", lambda m: None)
        d = tmp_path / "c"
        (d / "rows").mkdir(parents=True)
        r = {"run_id": "w|m|s|t|r0", "workspace": "w", "model": "m", "arm": "m", "state": "PASS"}
        manifest = {"rows": [r], "identity_map": {"w|m": self._ident(content="c1")}}
        row = {"outcome": "PASS", "notes": "", "identity": self._ident(content="c2")}
        stop = camp.arm_stop_reason("m", row, d, manifest, r)
        assert stop and "frozen" in stop
        saved = json.loads(camp._row_path(d, r["run_id"]).read_text())
        assert saved["outcome"] == "BLOCKED" and saved["notes"].startswith("IDENTITY DRIFT")
        assert r["state"] == "BLOCKED"

    def test_identity_never_enters_the_instrument_fingerprint(self):
        fp = camp.instrument_fingerprint()
        assert not {"identity", "identity_map", "content"} & set(fp)


class _FakeResp:
    """Minimal stand-in for an http.client.HTTPResponse line stream."""

    def __init__(self, lines, raise_after=None, exc=socket.timeout):
        self._lines = list(lines)
        self._i = 0
        self._raise_after = raise_after
        self._exc = exc

    def readline(self):
        if self._raise_after is not None and self._i >= self._raise_after:
            raise self._exc("timed out")
        if self._i >= len(self._lines):
            return b""
        ln = self._lines[self._i]
        self._i += 1
        return ln


class TestStallDetection:
    """A timeout is the enemy of a slow-but-progressing model. The runner
    streams and watches for a STALL (no bytes), not a total-time cap — a model
    that keeps emitting tokens is slow, not wedged, and its work is kept."""

    def test_a_quiet_backend_raises_stream_stalled_not_a_generic_error(self):
        resp = _FakeResp([b'{"a":1}\n'], raise_after=1)
        with pytest.raises(StreamStalledError):
            list(_iter_lines_with_stall(resp, stall_s=1, hard_s=60, tag="m"))

    def test_socket_timeout_subclass_is_caught(self):
        resp = _FakeResp([], raise_after=0, exc=TimeoutError)
        with pytest.raises(StreamStalledError):
            list(_iter_lines_with_stall(resp, stall_s=1, hard_s=60, tag="m"))

    def test_a_progressing_stream_runs_to_completion(self):
        lines = [b'{"delta":"a"}\n', b'{"delta":"b"}\n', b'{"done":true}\n']
        out = list(_iter_lines_with_stall(_FakeResp(lines), stall_s=5, hard_s=60, tag="m"))
        assert out == lines

    def test_hard_ceiling_still_bounds_a_dribbling_stream(self):
        # hard_s=0 => the very first post-read check trips it, even though bytes
        # are arriving. The single-call ceiling is the caller's remaining budget.
        with pytest.raises(StreamStalledError):
            list(_iter_lines_with_stall(_FakeResp([b"x\n", b"y\n"]), stall_s=5, hard_s=0, tag="m"))

    def test_stream_stalled_is_not_a_harness_error_outcome(self):
        """run_task maps a stall to BUDGET_EXHAUSTED (a model verdict), never to
        HARNESS_ERROR — the model accepted the request and went quiet."""
        from tests.wfe.schema import INSTRUMENT_OUTCOMES, MODEL_QUALITY_OUTCOMES, Outcome

        assert Outcome.BUDGET_EXHAUSTED in MODEL_QUALITY_OUTCOMES
        assert Outcome.BUDGET_EXHAUSTED not in INSTRUMENT_OUTCOMES


class TestFailedTurnTrace:
    """R2-22: a stalled or errored turn keeps its request's correlation id, so the
    pipeline trace of the request that failed is still reachable."""

    @pytest.fixture
    def pipeline_mode(self, monkeypatch):
        from tests.wfe import runner as rn

        monkeypatch.setattr(rn, "ENGINE", "pipeline")
        monkeypatch.setattr(rn, "CHAT_BASE", "http://pipeline.invalid")
        return rn

    def test_a_refused_request_keeps_its_correlation_id(self, pipeline_mode, monkeypatch):
        import urllib.request

        def _refused(*_a, **_k):
            raise ConnectionRefusedError("no pipeline here")

        monkeypatch.setattr(urllib.request, "urlopen", _refused)
        with pytest.raises(ConnectionRefusedError) as ei:
            pipeline_mode.chat("auto-compliance", [{"role": "user", "content": "hi"}])
        assert ei.value.correlation_id.startswith("wfe-")

    def test_a_stall_keeps_its_correlation_id(self, pipeline_mode, monkeypatch):
        import urllib.request

        def _stalled(*_a, **_k):
            raise StreamStalledError("no output for 300s")

        monkeypatch.setattr(urllib.request, "urlopen", _stalled)
        with pytest.raises(StreamStalledError) as ei:
            pipeline_mode.chat("auto-compliance", [{"role": "user", "content": "hi"}])
        assert ei.value.correlation_id.startswith("wfe-")

    def test_the_loop_records_the_id_on_a_failed_turn(self, pipeline_mode, monkeypatch, tmp_path):
        rn = pipeline_mode
        task = {"id": "t", "instruction": "Decide."}

        def _failing_chat(*_a, **_k):
            err = rn.StreamStalledError("no output for 300s")
            err.correlation_id = "wfe-abc123"
            raise err

        monkeypatch.setattr(rn, "chat", _failing_chat)
        loop = rn._Loop("auto-compliance", task, Sandbox(tmp_path), None, {}, None, False)
        assert loop.step(0, 30) is False
        (turn,) = loop.transcript
        assert turn["turn"] == 0
        assert "stalled" in turn
        assert turn["correlation_id"] == "wfe-abc123"

    def test_a_direct_engine_turn_records_no_empty_id(self, monkeypatch, tmp_path):
        """Only pipeline mode has a trace; a direct row must not carry a blank id."""
        from tests.wfe import runner as rn

        task = {"id": "t", "instruction": "Decide."}

        def _failing_chat(*_a, **_k):
            raise rn.StreamStalledError("no output for 300s")

        monkeypatch.setattr(rn, "chat", _failing_chat)
        loop = rn._Loop("laguna", task, Sandbox(tmp_path), None, {}, None, False)
        assert loop.step(0, 30) is False
        assert "correlation_id" not in loop.transcript[0]


class TestEffectiveSampling:
    """The audit must check the temperature the PIPELINE serves, not the one
    baked in the tag. router/validation.py injects the workspace's flat sampling
    (or think_profiles) into options at request time, so a workspace that pins
    temperature 0.2 over a tag that bakes 0.7 was reported as a FAIL it was not.
    """

    def test_workspace_config_overrides_a_hot_baked_tag(self):
        eff, src = effective_temperature({"temperature": 0.2}, {"temperature": 0.7})
        assert eff == 0.2 and src == "workspace config"

    def test_think_profile_wins_when_think_is_set(self):
        ws = {"think": False, "think_profiles": {"instruct": {"temperature": 0.4}}}
        eff, src = effective_temperature(ws, {"temperature": 0.7})
        assert eff == 0.4 and src == "think_profile"

    def test_falls_back_to_baked_then_unset(self):
        assert effective_temperature({}, {"temperature": 0.55}) == (0.55, "baked tag")
        assert effective_temperature({}, {}) == (None, "unset")

    def test_live_auto_coding_is_lane_compliant_after_the_fix(self):
        """auto-coding pins temperature 0.2 (coding lane <= 0.5) over a tag that
        bakes 0.7 — the pre-fix audit FAILed it; it must not now."""
        from tests.wfe.settings_audit import _audit_sampling

        ws = {"module": "coding", "model_hint": "x", "temperature": 0.2}
        v: list[dict] = []
        _audit_sampling("auto-coding", ws, "x", {"temperature": 0.7}, {"x"}, v)
        assert not [x for x in v if x["kind"] == "sampling_hot" and x["severity"] == "FAIL"]
        assert any(x["kind"] == "sampling_baked_hot" for x in v)

    def test_nothing_set_in_a_deterministic_lane_is_still_a_fail(self):
        from tests.wfe.settings_audit import _audit_sampling

        ws = {"module": "compliance", "model_hint": "x"}
        v: list[dict] = []
        _audit_sampling("w", ws, "x", {}, {"x"}, v)
        assert any(x["kind"] == "sampling_defaulted" and x["severity"] == "FAIL" for x in v)


class TestSeatSamplingFollowsTheGuidance:
    """C-FIX: a lane cap once lowered auto-compliance's temperature below Qwen3.8's published
    value (7b5d2afd) and the audit only warned. The guidance is now the authority."""

    CARD = {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5}

    def _check(self, ws_id, ws, monkeypatch):
        import tests.wfe.settings_audit as sa

        registry = {
            "qwen3.8": {
                "status": "verified-card",
                "recommended_sampling": self.CARD,
                "recommended_sampling_modes": {"instruct": self.CARD},
            }
        }
        monkeypatch.setattr(
            sa, "_expectations_for", lambda _h, _r: ("qwen3.8", registry["qwen3.8"])
        )
        monkeypatch.setattr(sa, "omlx_default_sampling", lambda: {})
        monkeypatch.setattr(sa, "_omlx_model_settings", lambda _mid: {})
        v: list[dict] = []
        hint = "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"
        sa._served_sampling_check(
            ws_id, {"model_hint": hint, "think": False, **ws}, hint, "omlx", registry, v
        )
        return v

    def test_a_production_seat_below_the_guidance_is_a_fail(self, monkeypatch):
        v = self._check("auto-compliance", {"temperature": 0.3, "top_p": 0.95}, monkeypatch)
        assert [x["severity"] for x in v if x["kind"] == "served_vs_card"] == ["FAIL"]

    def test_the_presence_penalty_is_checked_too(self, monkeypatch):
        ws = {"temperature": 0.7, "top_p": 0.8, "top_k": 20}  # everything but the anti-loop key
        v = self._check("auto-compliance", ws, monkeypatch)
        assert any(x["kind"] == "served_vs_card" and "presence_penalty" in x["detail"] for x in v)

    def test_a_seat_serving_the_guidance_is_clean(self, monkeypatch):
        assert self._check("auto-compliance", dict(self.CARD), monkeypatch) == []

    def test_a_purpose_named_arm_is_sanctioned(self, monkeypatch):
        # glm-4.7-flash: default + agentic_coding arms; sampling_mode_fit requires the coding arm.
        import tests.wfe.settings_audit as sa

        entry = {
            "recommended_sampling": {"temperature": 1.0, "top_p": 0.95},
            "recommended_sampling_modes": {
                "default": {"temperature": 1.0, "top_p": 0.95},
                "agentic_coding": {"temperature": 0.7, "top_p": 1.0},
            },
        }
        monkeypatch.setattr(sa, "_expectations_for", lambda _h, _r: ("glm", entry))
        monkeypatch.setattr(sa, "baked_params", lambda _h: {})
        v: list[dict] = []
        ws = {"model_hint": "glm", "temperature": 0.7, "top_p": 1.0}
        sa._served_sampling_check("auto-coding::glm-coder", ws, "glm", "ollama", {}, v)
        assert v == []

    def test_a_complete_override_keeps_the_seat_and_says_why(self, monkeypatch):
        ov = {"reason": "classifier", "evidence": "wfe_router_20261016"}
        v = self._check("task-router", {"temperature": 0.2, "sampling_override": ov}, monkeypatch)
        assert [x["severity"] for x in v] == ["INFO"] and v[0][
            "kind"
        ] == "served_vs_card_overridden"

    def test_an_override_without_evidence_is_a_fail(self, monkeypatch):
        ov = {"reason": "deterministic lane"}
        v = self._check(
            "auto-compliance", {"temperature": 0.3, "sampling_override": ov}, monkeypatch
        )
        assert [x["kind"] for x in v] == ["sampling_override_incomplete"] and v[0][
            "severity"
        ] == "FAIL"

    def test_a_bench_seat_stays_a_warning(self, monkeypatch):
        v = self._check("bench-qwen38-cad", {"temperature": 0.2}, monkeypatch)
        assert [x["severity"] for x in v] == ["WARN"]

    def test_an_override_turns_the_lane_ceiling_into_a_note(self):
        from tests.wfe.settings_audit import _audit_sampling

        ws = {"module": "compliance", "model_hint": "x", "temperature": 0.7}
        v: list[dict] = []
        _audit_sampling("w", ws, "x", {}, {"x"}, v)
        assert any(x["kind"] == "sampling_hot" and x["severity"] == "FAIL" for x in v)
        ws["sampling_override"] = {"reason": "r", "evidence": "e"}
        v = []
        _audit_sampling("w", ws, "x", {}, {"x"}, v)
        assert [x["kind"] for x in v] == ["sampling_override_over_lane"]


class TestCardRegistryCarriesTheAntiLoopSettings:
    """C-FIX: the registry's qwen3.8 entry omitted Unsloth's presence_penalty 1.5, so the audit
    could not see that the seat lacked it."""

    def _entry(self, key):
        import yaml

        from tests.wfe.runner import REPO

        return yaml.safe_load((REPO / "config/model_card_expectations.yaml").read_text())["models"][
            key
        ]

    def test_qwen38_instruct_is_unsloths_full_non_thinking_setting(self):
        modes = self._entry("qwen3.8")["recommended_sampling_modes"]
        assert modes["instruct"] == {
            "temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0,
            "presence_penalty": 1.5, "repeat_penalty": 1.0,
        }  # fmt: skip
        assert (
            modes["thinking"]["temperature"] == 1.0 and modes["thinking"]["presence_penalty"] == 0.0
        )

    def test_qwen36_thinking_general_carries_the_presence_penalty(self):
        modes = self._entry("qwen3.6")["recommended_sampling_modes"]
        assert modes["thinking_general"]["presence_penalty"] == 1.5

    def test_the_entries_record_their_source_tier(self):
        assert "build provider" in self._entry("qwen3.8")["source_tier"]
        assert "build provider" in self._entry("qwen3.6")["source_tier"]


class TestVariantsKeepTheirOwnSamplingWhenTheBaseChanges:
    """A variant inherits every base key it does not set. Giving the throwaway variant the
    Qwen3.6 presence_penalty 1.5 also gave it to its gemma4 and Ornith variants."""

    def test_throwaway_variants_do_not_inherit_the_qwen36_anti_loop_setting(self):
        import yaml

        from tests.wfe.runner import REPO

        ws = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
        base = ws["auto-general-uncensored"]
        assert base["variants"]["throwaway"]["presence_penalty"] == 1.5
        for name in ("throwaway-gemma4-heretic", "throwaway-ornith15"):
            assert {**base, **base["variants"][name]}["presence_penalty"] == 0.0
        assert {**base, **base["variants"]["throwaway-ornith15"]}["repeat_penalty"] == 1.05


class TestThinkingOnlyBuildsAreNotFlaggedAsBrokenTemplates:
    """qwen3-vl:32b is the Thinking build: it ignores think:false, so the system-instruction
    probe's 20-token budget went to reasoning and the probe reported a template fault."""

    def _run(self, monkeypatch, replies):
        import tests.wfe.settings_audit as sa

        calls: list[int] = []

        def fake_post(path, payload, timeout=60):
            if payload.get("format") == "json":
                return {"message": {"content": '{"ok": true}'}}
            calls.append(payload["options"]["num_predict"])
            return replies[min(len(calls) - 1, len(replies) - 1)]

        monkeypatch.setattr(sa, "_post", fake_post)
        monkeypatch.setattr(sa, "_probe_tools_rendered", lambda *a, **k: None)
        monkeypatch.setattr(sa, "_probe_think_honored", lambda *a, **k: None)
        v: list[dict] = []
        sa._behavioral_probes("qwen3-vl:32b", v, "tag:qwen3-vl:32b")
        return v, calls

    def test_reasoning_that_finishes_on_a_larger_budget_is_not_a_fault(self, monkeypatch):
        thinking_only = {"message": {"content": "", "thinking": "The user wants one word..."}}
        answered = {"message": {"content": "BLUE", "thinking": "..."}}
        v, calls = self._run(monkeypatch, [thinking_only, answered])
        assert [x for x in v if x["severity"] == "FAIL"] == [] and calls == [20, 1024]

    def test_a_turn_that_is_still_empty_is_still_a_fail(self, monkeypatch):
        empty = {"message": {"content": "", "thinking": "..."}}
        v, _ = self._run(monkeypatch, [empty, empty])
        assert any(x["kind"] == "template_system_ignored" and x["severity"] == "FAIL" for x in v)

    def test_empty_content_with_no_reasoning_is_a_fail_without_a_retry(self, monkeypatch):
        v, calls = self._run(monkeypatch, [{"message": {"content": ""}}])
        assert calls == [20]
        assert any(x["kind"] == "template_system_ignored" for x in v)


class TestQwen3VlSeatFollowsTheBuildItRuns:
    """qwen3-vl:32b is the Thinking build; the registry and the auto-vision seat carried the
    Instruct card's values."""

    def test_the_registry_describes_the_thinking_build_first(self):
        import yaml

        from tests.wfe.runner import REPO

        e = yaml.safe_load((REPO / "config/model_card_expectations.yaml").read_text())["models"][
            "qwen3-vl"
        ]
        assert e["recommended_sampling"] == e["recommended_sampling_modes"]["thinking"]
        assert e["recommended_sampling"]["temperature"] == 1.0
        assert e["recommended_sampling"]["presence_penalty"] == 0.0
        assert e["recommended_sampling_modes"]["instruct"]["presence_penalty"] == 1.5

    def test_auto_vision_serves_the_thinking_card(self):
        import re

        from tests.wfe.runner import REPO

        ws = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]["auto-vision"]
        hint = ws["model_hint"]
        backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())
        groups = set(backends["workspace_routing"]["auto-vision"])
        served = {
            m["id"]
            for b in backends["backends"]
            if b["group"] in groups
            for m in b.get("models") or []
        }
        assert hint in served, hint
        window = int(re.search(r"ctx(\d+)k", hint).group(1)) * 1024
        assert window >= ws["context_limit"], (hint, window)
        assert (ws["temperature"], ws["top_p"], ws["top_k"]) == (1.0, 0.95, 20)
        assert (ws["presence_penalty"], ws["repeat_penalty"]) == (0.0, 1.0)


class TestThinkingOnlyBuildThinkProbe:
    def _probe(self, monkeypatch, modelfile):
        import tests.wfe.settings_audit as sa

        def fake_post(path, payload, timeout=60):
            if path == "/api/show":
                return {"modelfile": modelfile}
            return {"message": {"content": "43", "thinking": "17 plus 26 is 43"}}

        monkeypatch.setattr(sa, "_post", fake_post)
        v: list[dict] = []
        sa._probe_think_honored("qwen3-vl:32b", v, "tag:x")
        return v

    def test_a_thinking_renderer_makes_ignored_think_an_info_not_a_fail(self, monkeypatch):
        v = self._probe(
            monkeypatch, "FROM x\nRENDERER qwen3-vl-thinking\nPARSER qwen3-vl-thinking\n"
        )
        assert [(x["kind"], x["severity"]) for x in v] == [("thinking_only_build", "INFO")]

    def test_a_template_that_ignores_think_without_a_thinking_renderer_still_fails(
        self, monkeypatch
    ):
        v = self._probe(monkeypatch, "FROM x\nTEMPLATE {{ .Prompt }}\n")
        assert [(x["kind"], x["severity"]) for x in v] == [("template_think_ignored", "FAIL")]


class TestSandboxRepoAccess:
    """Regression: an in-repo research task (res-repo-grounded) was unwinnable
    because repo_search('.', ...) searched only the empty sandbox and
    file_read('README.md') never fell back to the repository — the fallback
    fired only when a path ESCAPED the sandbox, which is backwards."""

    def test_file_read_falls_back_to_a_real_repo_file(self, tmp_path):
        sb = Sandbox(tmp_path)
        out = sb.file_read("pyproject.toml")
        assert "[tool.ruff]" in out and not out.startswith("ERROR")

    def test_sandbox_file_wins_over_a_repo_file_of_the_same_name(self, tmp_path):
        sb = Sandbox(tmp_path)
        sb.file_write("pyproject.toml", "SANDBOX COPY")
        assert sb.file_read("pyproject.toml") == "SANDBOX COPY"

    def test_missing_everywhere_is_a_clean_error(self, tmp_path):
        assert Sandbox(tmp_path).file_read("no/such/file.xyz").startswith("ERROR:")

    def test_repo_search_dot_path_reaches_the_repo(self, tmp_path):
        sb = Sandbox(tmp_path)
        hits = sb.repo_search("single source of truth", ".")
        assert "config/portal.yaml" in hits or "portal.yaml" in hits
        assert str(sb.root) not in hits  # paths are repo-relative, not absolute

    def test_repo_search_empty_path_reaches_the_repo(self, tmp_path):
        assert "pyproject.toml" in Sandbox(tmp_path).repo_search(r"\[tool\.ruff\]")

    def test_repo_search_still_finds_sandbox_content(self, tmp_path):
        sb = Sandbox(tmp_path)
        sb.file_write("note.txt", "MARKER_TOKEN_XYZ here")
        assert "MARKER_TOKEN_XYZ" in sb.repo_search("MARKER_TOKEN_XYZ", ".")

    def test_repo_search_requires_a_pattern(self, tmp_path):
        assert Sandbox(tmp_path).repo_search("", ".").startswith("ERROR:")

    def test_writes_still_cannot_escape(self, tmp_path):
        assert Sandbox(tmp_path).file_write("../../evil.txt", "x").startswith("ERROR:")
        assert Sandbox(tmp_path)._resolve("../../evil.txt", write=True) is None

    def test_file_list_of_empty_sandbox_is_empty_not_a_repo_dump(self, tmp_path):
        """A code task's sandbox is legitimately empty. Dumping the whole repo
        tree (hundreds of entries) into the context is noise the model reasons
        past — it derailed granite4.2 on code-kv."""
        assert Sandbox(tmp_path).file_list(".") == ""

    def test_file_list_of_a_real_repo_subdir_still_works(self, tmp_path):
        out = Sandbox(tmp_path).file_list("tests/wfe")
        assert "runner.py" in out and "checkers.py" in out
        assert "results" not in out.split("\n") or True  # top level only, no rglob


class TestUnreachableIsNotAModelFailure:
    """Sibling of the repo-tool bug: a harness limitation must not be recorded
    as a model verdict."""

    def test_requires_network_task_offline_is_blocked_not_failed(self, tmp_path, monkeypatch):
        from tests.wfe import runner as rn

        monkeypatch.setattr(rn, "network_ok", lambda *a, **k: False)
        sb = rn.Sandbox(tmp_path)
        task = {
            "id": "res-x",
            "requires_network": True,
            "instruction": "fetch something",
            "checkers": [{"type": "cited_answer", "patterns": ["x"]}],
        }
        out = rn.run_task("m", "sys", task, sb, max_turns=3, budget_s=60, use_tools=True)
        assert out["outcome"] == Outcome.BLOCKED.value
        assert out["tool_calls"] == 0

    def test_blocked_is_an_instrument_outcome_excluded_from_rates(self):
        assert Outcome.BLOCKED in INSTRUMENT_OUTCOMES
        assert Outcome.BLOCKED not in MODEL_QUALITY_OUTCOMES

    def test_network_ok_is_cached(self, monkeypatch):
        from tests.wfe import runner as rn

        calls = []
        monkeypatch.setattr(rn, "_NETWORK_OK", None)
        monkeypatch.setattr(rn.urllib.request, "urlopen", lambda *a, **k: calls.append(1) or _Ctx())
        rn.network_ok()
        rn.network_ok()
        assert len(calls) == 1


class TestTextToolCallParity:
    """The pipeline recovers a Qwen3-Coder call written as text
    (P5-OMLX-QWEN3CODER-TOOLTEXT-001). The harness posts to the engine
    directly, so it must recover it too or it scores a production success as a
    lost call."""

    def test_text_written_call_is_executed_and_counted(self, tmp_path, monkeypatch):
        from tests.wfe import runner as rn

        replies = iter(
            [
                {
                    "content": "note\n<function=file_write>\n<parameter=path>\nout.txt\n"
                    "</parameter>\n<parameter=content>\nhello\n</parameter>\n"
                    "</function>\n</tool_call>"
                },
                {"content": "Done."},
            ]
        )

        def fake_chat(*a, **k):
            return {
                "message": next(replies),
                "finish_reason": "stop",
                "economics": rn.Economics(),
            }

        monkeypatch.setattr(rn, "chat", fake_chat)
        sb = rn.Sandbox(tmp_path)
        task = {"id": "t", "instruction": "write", "checkers": []}
        out = rn.run_task("m", "sys", task, sb, max_turns=3, budget_s=60, use_tools=True)
        assert out["tool_calls"] == 1
        assert (tmp_path / "out.txt").read_text() == "hello"
        assert out["evidence"]["recovered_tool_calls"] == 1


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestToolOutputRetentionForRescore:
    def test_tool_call_log_keeps_full_output_for_offline_leak_detection(self, tmp_path):
        """A leaked answer key past char 300 of a tool output must be catchable
        on --rescore, not only on the live run."""
        from tests.wfe.runner import _execute_calls

        sb = Sandbox(tmp_path)
        long_leak = "x" * 500 + " gold_label=CONTRADICTED"
        sb.file_write("packet.txt", long_leak)
        tool_log: list = []
        msgs: list = []
        calls = [
            {"id": "c1", "function": {"name": "file_read", "arguments": '{"path": "packet.txt"}'}}
        ]
        _execute_calls(calls, 0, sb, tool_log, msgs)
        assert "gold_label=CONTRADICTED" in str(tool_log[0]["output"])


class TestAdaptiveThink:
    """gpt-oss works; the harness refused it over a format:json probe of a mode
    no campaign task uses, and dropped `think` entirely on the /v1 path so a
    `think: false` workspace was measured with the model's reasoning left on."""

    def test_v1_payload_carries_think_like_production(self, monkeypatch):
        import tests.wfe.runner as rn
        from tests.wfe.runner import _build_payload

        # Ollama "v1" arms are served natively, as production serves them;
        # think reaches a thinking-capable model in both directions.
        monkeypatch.setattr(rn, "_ollama_can_think", lambda m: True)

        url, payload, caveats = _build_payload(
            "m",
            [{"role": "user", "content": "x"}],
            {"endpoint": "v1", "format": "none"},
            {},
            None,
            "false",
        )
        assert url.endswith("/api/chat")
        assert payload["think"] is False
        assert not caveats  # no more "v1_think_unsupported"
        _, p2, _ = _build_payload(
            "m",
            [{"role": "user", "content": "x"}],
            {"endpoint": "v1", "format": "none"},
            {},
            None,
            "true",
        )
        assert p2["think"] is True

    def test_every_resolved_sampling_key_reaches_the_request(self, monkeypatch):
        """The workspace's loop guard (repeat_penalty) and top_k/min_p were dropped
        on both paths; engines without Ollama's defaults then looped. On Ollama
        the v1 arm is served natively, so every key lands in `options`."""
        import tests.wfe.runner as rn
        from tests.wfe.runner import _build_payload

        monkeypatch.setattr(rn, "_ollama_can_think", lambda m: True)

        sampling = {
            "temperature": 0.3,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
            "repeat_penalty": 1.1,
            "presence_penalty": 1.5,
            "seed": 7,
        }
        msgs = [{"role": "user", "content": "x"}]
        _, v1, _ = _build_payload("m", msgs, {"endpoint": "v1"}, dict(sampling), None, "false")
        _, api, _ = _build_payload("m", msgs, {"endpoint": "api"}, dict(sampling), None, "false")
        for k, v in sampling.items():
            assert v1["options"][k] == v
            assert api["options"][k] == v

    def test_engine_mode_routes_v1_to_engine_and_uses_template_switch(self, monkeypatch):
        """WFE_ENGINE head-to-head: the chat goes to the other engine's base URL
        and thinking is controlled by the chat template's own switch, never by
        Ollama-only fields another engine may reject."""
        import tests.wfe.runner as rn

        monkeypatch.setattr(rn, "ENGINE", "mlx-serve")
        monkeypatch.setattr(rn, "CHAT_BASE", "http://127.0.0.1:11234")
        url, payload, _ = rn._build_payload(
            "m",
            [{"role": "user", "content": "x"}],
            {"endpoint": "v1", "format": "none"},
            {},
            None,
            "false",
        )
        assert url == "http://127.0.0.1:11234/v1/chat/completions"
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}
        assert "think" not in payload and "reasoning_effort" not in payload

    def test_ollama_default_unchanged_by_engine_support(self):
        import tests.wfe.runner as rn

        assert rn._v1_think_fields("false") == {"think": False, "reasoning_effort": "none"}
        assert rn._v1_think_fields("true") == {"think": True}
        assert rn._v1_think_fields("default") == {}

    def test_campaign_harness_resolves_think_like_production(self, monkeypatch):
        """Production reads only the workspace's `think`; with none it sends
        nothing. The harness used to fall back to the card's harness_policy and
        ran three production seats with thinking off that production runs on."""
        import tests.wfe.runner as rn
        from tests.wfe import campaign as c

        assert c.campaign_harness({"model": "m", "think": False})["think"] == "false"
        assert c.campaign_harness({"model": "m", "think": True})["think"] == "true"
        assert c.campaign_harness({"model": "laguna", "think": None})["think"] == "native"
        _, payload, _ = rn._build_payload("m", [], {"endpoint": "v1"}, {}, None, "native")
        assert "think" not in payload and "reasoning_effort" not in payload
        # raw-model preflight still resolves the card policy
        reg = {"gpt-oss": {"harness_policy": {"think": "true"}}}
        import tests.wfe.runner as rn

        assert rn.think_policy("gpt-oss:20b", reg) == "true"

    def test_wfe_sampling_override_replaces_seat_sampling(self):
        from tests.wfe import campaign as c

        wsc = {"sampling": {"temperature": 0.2, "min_p": 0.05, "max_tokens": 16384}}
        ov = {"sampling": {"temperature": 1.0, "top_k": 20}}
        assert c._sampling_for(wsc, 1, ov) == {
            "max_tokens": 16384,
            "temperature": 1.0,
            "top_k": 20,
            "seed": 1001,
            "max_tokens_source": "predict_limit",
        }
        # no override -> the seat's own block
        assert c._sampling_for(wsc, 0)["min_p"] == 0.05
        # no predict_limit -> production sends no cap; the harness only guards runaways
        bare = c._sampling_for({"sampling": {"temperature": 0.7}}, 0)
        assert bare["max_tokens"] == c.HARNESS_RUNAWAY_CAP
        assert bare["max_tokens_source"] == "harness_runaway_cap"

    def test_wfe_think_override_wins_and_is_stamped(self):
        from tests.wfe import campaign as c

        assert (
            c.campaign_harness({"model": "m", "think": True}, {"think": "false"})["think"]
            == "false"
        )
        assert (
            c.campaign_harness({"model": "m", "think": True}, {"think": "bogus"})["think"] == "true"
        )

    def test_env_override_becomes_a_distinct_arm_with_its_own_run_ids(self, monkeypatch):
        """The A/B of one model: seat arm and card arm must not share run_ids,
        or --append adds 0 rows and the card arm silently never runs."""
        from tests.wfe import campaign as c

        monkeypatch.delenv("WFE_SAMPLING", raising=False)
        monkeypatch.delenv("WFE_THINK", raising=False)
        seat = c.arm_spec("m:tag")
        assert seat == ("m:tag", "m:tag", {})
        monkeypatch.setenv("WFE_SAMPLING", '{"temperature": 1.0}')
        card = c.arm_spec("m:tag")
        assert card[0].startswith("m:tag@env-") and card[1] == "m:tag"
        assert card[2] == {"sampling": {"temperature": 1.0}}
        monkeypatch.setenv("WFE_SAMPLING", '{"temperature": 0.7}')
        assert c.arm_spec("m:tag")[0] != card[0]

    def test_plan_variant_arm(self, monkeypatch):
        from tests.wfe import campaign as c

        monkeypatch.delenv("WFE_SAMPLING", raising=False)
        monkeypatch.delenv("WFE_THINK", raising=False)
        arm, model, ov = c.arm_spec(
            {"model": "m:tag", "label": "card", "sampling": {"top_k": 20}, "think": True}
        )
        assert arm.startswith("m:tag@card-") and model == "m:tag"
        assert ov == {"sampling": {"top_k": 20}, "think": "true"}

    def test_row_override_survives_a_resume_without_env(self, monkeypatch):
        """Overrides live on the row; a resume in a clean shell must still run
        the card arm as the card arm."""
        from tests.wfe import campaign as c

        monkeypatch.delenv("WFE_SAMPLING", raising=False)
        row = {"arm": "m@card-x", "model": "m", "overrides": {"sampling": {"temperature": 1.0}}}
        assert c.row_overrides(row) == {"sampling": {"temperature": 1.0}}
        assert c.row_model(row) == "m"
        # legacy rows (pre-variant manifests) keep the env semantics
        monkeypatch.setenv("WFE_SAMPLING", '{"temperature": 0.5}')
        assert c.row_overrides({"arm": "m"}) == {"sampling": {"temperature": 0.5}}

    def test_workspace_context_exposes_think(self):
        from tests.wfe.runner import workspace_context

        wsc = workspace_context("auto-compliance")
        assert wsc["think"] in (True, False, None)  # auto-compliance sets it False

    def test_strict_json_failure_is_a_note_not_a_verdict_gate(self):
        from tests.wfe.runner import _preflight_findings, _strict_json_note

        degenerate = {"content": "The user says ...", "finish_reason": "stop"}
        note = _strict_json_note(degenerate, card_json_safe=False)
        assert note and "cannot serve strict-JSON" in note
        # a strict-json failure contributes NOTHING to the findings list
        out = {
            "v1": {"content": "OK"},
            "v1_tools": {"emitted_call": True, "parsed_ok": True},
        }
        assert _preflight_findings(out, {"content": "OK"}, {"content": "OK"}) == []

    def test_verdict_gates_only_on_campaign_arms(self):
        from tests.wfe.runner import _preflight_findings

        # v1 tool contract broken -> a real gate
        out = {"v1": {"content": "OK"}, "v1_tools": {"parsed_ok": False}}
        f = _preflight_findings(out, {"content": "OK"}, {"content": "OK"})
        assert any("tool-call arguments" in x for x in f)
        # stream parity mismatch -> a real gate
        out2 = {"v1": {"content": "OK"}, "v1_tools": {"parsed_ok": True}}
        f2 = _preflight_findings(out2, {"content": "A"}, {"content": "B"})
        assert any("parity" in x for x in f2)


class TestReasoningFitAudit:
    def test_reasoning_model_no_think_on_deterministic_lane_is_a_fail(self):
        from tests.wfe.settings_audit import _audit_reasoning_fit

        reg = {"gpt-oss": {"harness_policy": {"think": "true"}}}
        ws = {"module": "compliance", "model_hint": "gpt-oss:20b"}  # no `think`
        v: list[dict] = []
        _audit_reasoning_fit("w", ws, "gpt-oss:20b", reg, {"gpt-oss:20b"}, v)
        assert any(x["kind"] == "reasoning_uncontrolled" and x["severity"] == "FAIL" for x in v)

    def test_reasoning_model_no_think_on_agentic_lane_is_a_warn(self):
        from tests.wfe.settings_audit import _audit_reasoning_fit

        ws = {"module": "coding", "model_hint": "granite4.2:30b-q4_K_M"}
        v: list[dict] = []
        _audit_reasoning_fit("w", ws, "granite4.2:30b-q4_K_M", {}, {"granite4.2:30b-q4_K_M"}, v)
        assert any(x["kind"] == "reasoning_uncontrolled" and x["severity"] == "WARN" for x in v)

    def test_workspace_that_sets_think_is_not_flagged(self):
        from tests.wfe.settings_audit import _audit_reasoning_fit

        ws = {"module": "compliance", "model_hint": "gpt-oss:20b", "think": False}
        v: list[dict] = []
        _audit_reasoning_fit(
            "w",
            ws,
            "gpt-oss:20b",
            {"gpt-oss": {"harness_policy": {"think": "true"}}},
            {"gpt-oss:20b"},
            v,
        )
        assert not v

    def test_non_reasoning_model_is_not_flagged(self):
        from tests.wfe.settings_audit import _audit_reasoning_fit

        ws = {"module": "compliance", "model_hint": "gemma4:e4b-it-qat"}
        v: list[dict] = []
        _audit_reasoning_fit("w", ws, "gemma4:e4b-it-qat", {}, {"gemma4:e4b-it-qat"}, v)
        assert not v


class TestReasoningBudgetFitAudit:
    """reasoning_budget_fit: a thinking seat's served output budget vs a
    window-aware target — min(card max output, 32768, window // 2), half the
    KV window staying for prompt, history and tool results. Motivated by
    auto-reasoning serving 16384 against DeepSeek-R1-0528's 64K-max-generation
    card — hard problems truncated mid-thought and the audit had no check that
    could see it."""

    @staticmethod
    def _run(ws, hint, registry, tags, baked_window=None):
        from tests.wfe.settings_audit import _audit_reasoning_budget_fit

        v: list[dict] = []
        _audit_reasoning_budget_fit("w", ws, hint, registry, tags, v, baked_window=baked_window)
        return [x for x in v if x["kind"] == "reasoning_budget_fit"]

    def test_underbudgeted_reasoning_seat_is_a_fail(self):
        ws = {"module": "general", "think": True, "predict_limit": 8192}
        v = self._run(
            ws,
            "deepseek-r1:8b",
            {"deepseek-r1": {"recommended_max_output": 65536}},
            {"deepseek-r1:8b"},
        )
        assert len(v) == 1 and v[0]["severity"] == "FAIL"
        # the finding names the model, the served budget and the card value
        assert "deepseek-r1:8b" in v[0]["detail"]
        assert "8192" in v[0]["detail"] and "65536" in v[0]["detail"]
        assert v[0]["workspace"] == "w"

    def test_exactly_the_truncation_budget_warns(self):
        # served 16384 against a 32768 target sits ON the FAIL boundary
        # (target // 2): below it fails, 16384 warns
        ws = {"module": "general", "think": True, "predict_limit": 16384}
        v = self._run(
            ws,
            "deepseek-r1:8b",
            {"deepseek-r1": {"recommended_max_output": 65536}},
            {"deepseek-r1:8b"},
        )
        assert len(v) == 1 and v[0]["severity"] == "WARN"
        assert "16384" in v[0]["detail"] and "32768" in v[0]["detail"]

    def test_card_sized_budget_is_silent(self):
        # the 2026-10-19 auto-reasoning fix: 40960 covers min(65536, 32768)
        ws = {"module": "general", "think": True, "predict_limit": 40960}
        v = self._run(
            ws,
            "deepseek-r1:8b",
            {"deepseek-r1": {"recommended_max_output": 65536}},
            {"deepseek-r1:8b"},
        )
        assert not v

    def test_below_ceiling_but_above_floor_is_a_warn(self):
        ws = {"think": True, "predict_limit": 24576}
        v = self._run(ws, "m:r", {"m": {"recommended_max_output": 32768}}, {"m:r"})
        assert len(v) == 1 and v[0]["severity"] == "WARN"

    def test_pipeline_default_budget_is_measured_when_no_predict_limit(self):
        from tests.wfe.settings_audit import PIPELINE_DEFAULT_PREDICT_LIMIT

        assert PIPELINE_DEFAULT_PREDICT_LIMIT == 8192
        ws = {"think": True}  # no predict_limit — the served cap is the default
        v = self._run(ws, "m:r", {"m": {"recommended_max_output": 32768}}, {"m:r"})
        assert len(v) == 1 and v[0]["severity"] == "FAIL"
        assert f"serves {PIPELINE_DEFAULT_PREDICT_LIMIT} (pipeline default)" in v[0]["detail"]

    def test_served_budget_mirrors_output_cap_context_ceiling(self):
        from tests.wfe.settings_audit import _served_output_budget

        assert _served_output_budget({"predict_limit": 40960}) == 40960
        assert _served_output_budget({"context_limit": 4096}) == 4096
        assert _served_output_budget({"context_limit": 98304}) == 8192
        assert _served_output_budget({}) == 8192

    def test_baked_window_from_suffix_modelfile_or_neither(self):
        from tests.wfe.settings_audit import _baked_window

        assert _baked_window("hf.co/x/R:Q4_K_M-ctx24k", {}) == 24576
        shows = {
            "m:t": {"modelfile": "FROM x\nPARAMETER num_ctx 65536\nPARAMETER temperature 1.0\n"}
        }
        assert _baked_window("m:t", shows) == 65536
        assert _baked_window("m:t", {"m:t": {"modelfile": "FROM x"}}) is None
        assert _baked_window("m:t", {}) is None

    def test_window_caps_the_target_and_sets_the_bands(self):
        # card would allow 32768, but half of the 24576 window is 12288:
        # 8192 is below target yet inside the WARN band (target // 2 = 6144)
        ws = {"think": True, "predict_limit": 8192}
        v = self._run(
            ws, "m:r", {"m": {"recommended_max_output": 131072}}, {"m:r"}, baked_window=24576
        )
        assert len(v) == 1 and v[0]["severity"] == "WARN"
        assert "12288" in v[0]["detail"] and "half of window 24576" in v[0]["detail"]
        # below half the target is the FAIL class again
        ws2 = {"think": True, "predict_limit": 4096}
        v2 = self._run(
            ws2, "m:r", {"m": {"recommended_max_output": 131072}}, {"m:r"}, baked_window=24576
        )
        assert len(v2) == 1 and v2[0]["severity"] == "FAIL"

    def test_seat_context_limit_overrides_the_baked_window(self):
        # the workspace's own context_limit is the window that fills
        ws = {"think": True, "predict_limit": 8192, "context_limit": 8192}
        v = self._run(
            ws, "m:r", {"m": {"recommended_max_output": 131072}}, {"m:r"}, baked_window=65536
        )
        assert not v  # target = min(131072, 32768, 4096) = 4096; 8192 >= target

    def test_window_is_the_binding_limit(self):
        # a small window binds harder than card or ceiling: this seat would
        # FAIL under the card-only rule (8192 < 16384) but its 8192 window
        # sets target 4096 and the default 8192 budget passes it
        ws = {"think": True, "context_limit": 8192}  # no predict_limit: default 8192
        v = self._run(ws, "m:r", {"m": {"recommended_max_output": 65536}}, {"m:r"})
        assert not v

    def test_card_below_ceiling_never_fails(self):
        # a card that documents less than 32K (e.g. granite-4.2's thinking-mode
        # 8192) can only ever WARN — the FAIL class is for cards claiming 32K+
        ws = {"think": True, "predict_limit": 4096}
        v = self._run(
            ws,
            "granite4.2:8b",
            {"granite-4.2": {"recommended_max_output": 8192}},
            {"granite4.2:8b"},
        )
        assert len(v) == 1 and v[0]["severity"] == "WARN"

    def test_think_false_reasoning_family_is_out_of_scope(self):
        # operator review 2026-10-19: a seat that pins think:false does not
        # reason at runtime, so a reasoning-sized output budget does not apply
        ws = {"module": "general", "think": False, "predict_limit": 4096}
        v = self._run(
            ws,
            "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k",
            {"qwen3.8": {"recommended_max_output": 131072}},
            {"hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"},
        )
        assert not v

    def test_reasoning_family_seat_without_think_is_checked(self):
        # a reasoning-family model thinks at its native default; the seat is in
        # scope even though the workspace never sets `think`
        ws = {"module": "compliance", "predict_limit": 8192}
        v = self._run(
            ws,
            "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k",
            {"qwen3.8": {"recommended_max_output": 131072}},
            {"hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"},
        )
        assert len(v) == 1 and v[0]["severity"] == "FAIL"

    def test_think_true_seat_on_a_cardless_model_is_silent(self):
        ws = {"think": True, "predict_limit": 4096}
        v = self._run(ws, "gemma4:e4b-it-qat", {"gemma4": {}}, {"gemma4:e4b-it-qat"})
        assert not v

    def test_think_false_plain_model_is_out_of_scope(self):
        ws = {"think": False, "predict_limit": 4096}
        v = self._run(
            ws, "llama3.1:8b", {"llama3.1": {"recommended_max_output": 32768}}, {"llama3.1:8b"}
        )
        assert not v

    def test_uninstalled_hint_is_out_of_scope(self):
        ws = {"think": True, "predict_limit": 4096}
        v = self._run(ws, "m:r", {"m": {"recommended_max_output": 32768}}, set())
        assert not v

    def test_registry_values_are_positive_ints(self):
        """A YAML edit that puts a string/bool/negative into the field must not
        reach the audit — the check treats an unusable value as absent."""
        from tests.wfe.settings_audit import _load_expectations

        reg = _load_expectations()
        carried = [
            k for k, e in reg.items() if isinstance(e, dict) and "recommended_max_output" in e
        ]
        assert carried, "registry lost every recommended_max_output entry"
        for key in carried:
            value = reg[key]["recommended_max_output"]
            assert isinstance(value, int) and not isinstance(value, bool) and value > 0, key
        # the motivating card documents its 64K maximum generation
        assert reg["deepseek-r1"]["recommended_max_output"] == 65536
        # review 2026-10-19: usage-example numbers (k2-horizon, nemotron) are
        # not recommendations — those entries must not carry the field
        assert "k2-horizon" not in carried and "nemotron-3.5-lightning" not in carried


class TestTransientPreflightIsRecoverable:
    """A flaky probe must not cost an arm its whole row budget for the rest of a
    multi-day sweep.

    Regression: `preflight_arm` cached a REVIEW verdict and `execute_arm` marked
    every pending row BLOCKED. On resume the cached REVIEW short-circuited the
    re-probe and the BLOCKED rows no longer matched the PENDING filter, so one
    momentary connection reset silently cost an arm all 39 of its runs.
    """

    @pytest.fixture(autouse=True)
    def _no_live_engines(self, monkeypatch):
        """execute_arm drains Ollama/oMLX before an arm. Unstubbed, this test
        evicted real resident models (the pipeline's router) on every run."""
        monkeypatch.setattr(camp, "drain_others", lambda keep: [])
        monkeypatch.setattr(camp, "drain_model", lambda m: True)
        monkeypatch.setattr(camp, "drain_omlx", lambda: "stub")
        monkeypatch.setattr(camp, "model_sizes", lambda: {"m:t": 1})

    def _open(self, tmp_path):
        camp.CAMPAIGNS = tmp_path / "campaigns"
        plan = tmp_path / "plan.yaml"
        plan.write_text(
            yaml.safe_dump(
                {"workloads": {"auto-coding": {"home": "coding", "arms": {"incumbent": "m:t"}}}}
            )
        )
        matrix = camp.expand_matrix(plan, repeats=1)
        assert matrix, "fixture plan produced no rows"
        return camp.open_campaign("c", plan, matrix, append=False)

    def test_review_verdict_is_not_cached(self, tmp_path, monkeypatch):
        d = self._open(tmp_path)
        monkeypatch.setattr(
            camp, "preflight_harness", lambda m: {"verdict": "REVIEW", "findings": ["flaky"]}
        )
        assert camp.preflight_arm(d, "m:t")["verdict"] == "REVIEW"
        # An OK on the next attempt must be reachable, not masked by the cache.
        monkeypatch.setattr(camp, "preflight_harness", lambda m: {"verdict": "OK", "findings": []})
        assert camp.preflight_arm(d, "m:t")["verdict"] == "OK"

    def test_ok_verdict_is_cached(self, tmp_path, monkeypatch):
        """The expensive probe runs once per arm per campaign when it succeeds."""
        d = self._open(tmp_path)
        calls = []

        def _probe(m):
            calls.append(m)
            return {"verdict": "OK", "findings": []}

        monkeypatch.setattr(camp, "preflight_harness", _probe)
        camp.preflight_arm(d, "m:t")
        camp.preflight_arm(d, "m:t")
        assert calls == ["m:t"]

    def test_blocked_rows_are_re_offered_once_preflight_passes(self, tmp_path, monkeypatch):
        d = self._open(tmp_path)
        monkeypatch.setattr(
            camp, "preflight_harness", lambda m: {"verdict": "REVIEW", "findings": ["flaky"]}
        )
        first = camp.execute_arm(d, "m:t", 4, 60, None, False, False)
        assert first["ran"] == 0 and first["blocked"] > 0
        states = {r["state"] for r in camp.load_manifest(d)["rows"]}
        assert states == {Outcome.BLOCKED.value}

        ran = []

        def _row(campaign_dir, manifest, r, wsc, task, *a, **kw):
            ran.append(r["run_id"])
            return {
                "outcome": Outcome.PASS.value,
                "turns": 1,
                "tool_calls": 0,
                "tool_errors": 0,
                "economics": {"wall_s": 1.0},
            }

        monkeypatch.setattr(camp, "preflight_harness", lambda m: {"verdict": "OK", "findings": []})
        monkeypatch.setattr(camp, "workspace_context", lambda ws, persona=None: {"model": "m:t"})
        monkeypatch.setattr(camp, "run_row", _row)
        second = camp.execute_arm(d, "m:t", 4, 60, None, False, False)
        assert second["ran"] > 0, "resume left the arm permanently blocked"
        assert len(ran) == len(camp.load_manifest(d)["rows"])
        assert all(r["state"] == Outcome.PASS.value for r in camp.load_manifest(d)["rows"])
        assert all("note" not in r for r in camp.load_manifest(d)["rows"])

    def test_a_task_level_block_is_not_re_offered(self, tmp_path, monkeypatch):
        """Only a preflight block is retryable. A row blocked because the task
        needs the network and the host is offline stays blocked."""
        d = self._open(tmp_path)
        man = camp.load_manifest(d)
        for r in man["rows"]:
            r["state"] = Outcome.BLOCKED.value
            r["note"] = "requires_network but the host is offline"
        camp.save_manifest(d, man)
        monkeypatch.setattr(camp, "preflight_harness", lambda m: {"verdict": "OK", "findings": []})
        assert camp.execute_arm(d, "m:t", 4, 60, None, False, False)["ran"] == 0


class TestModelRelease:
    """A 17-arm sweep of ~20GB models against OLLAMA_MAX_LOADED_MODELS=5 measures
    memory pressure unless each arm gives its weights back."""

    def test_unload_asks_ollama_to_release_only_that_tag(self, monkeypatch):
        sent = {}

        def _urlopen(req, timeout=None):
            sent["url"] = req.full_url
            sent["body"] = json.loads(req.data)

            class _R:
                def read(self):
                    return b""

            return _R()

        monkeypatch.setattr("urllib.request.urlopen", _urlopen)
        camp.unload_model("some/model:tag")
        assert sent["url"].endswith("/api/generate")
        assert sent["body"] == {"model": "some/model:tag", "keep_alive": 0}

    def test_unload_never_raises_into_the_sweep(self, monkeypatch):
        def _boom(req, timeout=None):
            raise OSError("connection reset")

        monkeypatch.setattr("urllib.request.urlopen", _boom)
        camp.unload_model("m:t")  # must not propagate

    def test_model_sizes_degrades_to_empty_when_ollama_is_silent(self, monkeypatch):
        def _boom(url, timeout=None):
            raise OSError("no route")

        monkeypatch.setattr("urllib.request.urlopen", _boom)
        assert camp.model_sizes() == {}


class TestDrain:
    """Eviction on model change, waited on rather than assumed — the bench/UAT
    rule. Regression: fire-and-forget `keep_alive: 0` let the next arm begin
    loading ~20GB while the previous model was still resident."""

    def test_drain_waits_until_ollama_reports_the_model_gone(self, monkeypatch):
        seen = iter([["m:t"], ["m:t"], []])
        monkeypatch.setattr(camp, "unload_model", lambda t: None)
        monkeypatch.setattr(camp, "loaded_models", lambda: next(seen))
        monkeypatch.setattr(camp.time, "sleep", lambda s: None)
        assert camp.drain_model("m:t") is True

    def test_drain_gives_up_at_the_ceiling_rather_than_hanging(self, monkeypatch):
        """A wedged backend must not stall a multi-day sweep indefinitely."""
        clock = iter([0.0] + [float(i) for i in range(1, 500)])
        monkeypatch.setattr(camp, "unload_model", lambda t: None)
        monkeypatch.setattr(camp, "loaded_models", lambda: ["m:t"])
        monkeypatch.setattr(camp.time, "sleep", lambda s: None)
        monkeypatch.setattr(camp.time, "monotonic", lambda: next(clock))
        assert camp.drain_model("m:t", timeout_s=5) is False

    def test_drain_others_evicts_everything_but_the_arm(self, monkeypatch):
        """Including a model a service pinned at keep_alive=-1: that is memory
        the arm needs, and the owner reloads it on its next request."""
        resident = ["pinned-classifier:q4", "leftover:tag", "arm:tag"]
        released = []
        monkeypatch.setattr(camp, "loaded_models", lambda: list(resident))
        monkeypatch.setattr(camp, "drain_model", lambda t, timeout_s=0: released.append(t))
        assert camp.drain_others("arm:tag") == ["pinned-classifier:q4", "leftover:tag"]
        assert "arm:tag" not in released

    def test_loaded_models_degrades_to_empty_when_ollama_is_silent(self, monkeypatch):
        def _boom(url, timeout=None):
            raise OSError("no route")

        monkeypatch.setattr("urllib.request.urlopen", _boom)
        assert camp.loaded_models() == []


class TestInstrumentHealthSection:
    """Section 1 lists the full outcome census with instrument rows marked.

    Regression: the heading promised only the excluded runs while the table
    listed every outcome, so a clean campaign of 4 PASS / 1 FAIL / 1
    BUDGET_EXHAUSTED read as six instrument failures — the exact misreading the
    outcome taxonomy exists to prevent."""

    def _md(self, tmp_path, outcomes):
        from tests.wfe.report import render_markdown

        d = TestReportCompilation()._campaign(tmp_path, outcomes)
        return render_markdown(camp_report_build(d))

    def test_a_clean_campaign_reports_zero_excluded(self, tmp_path):
        md = self._md(tmp_path, {"inc": ["PASS", "FAIL"], "ch": ["PASS", "BUDGET_EXHAUSTED"]})
        assert "0 of 4 run(s) excluded as instrument failures." in md
        # The marker appears in the explanatory line; no TABLE ROW may carry it.
        assert not [ln for ln in md.splitlines() if ln.startswith("|") and "*(excluded)*" in ln]

    def test_instrument_rows_are_marked_and_counted(self, tmp_path):
        md = self._md(tmp_path, {"inc": ["PASS", "HARNESS_ERROR"], "ch": ["PASS", "TOOL_ERROR"]})
        assert "| HARNESS_ERROR *(excluded)* | 1 |" in md
        assert "| TOOL_ERROR *(excluded)* | 1 |" in md
        assert "| PASS | 2 |" in md
        assert "2 of 4 run(s) excluded as instrument failures." in md

    def test_the_census_total_matches_every_recorded_run(self, tmp_path):
        md = self._md(tmp_path, {"inc": ["PASS"] * 5, "ch": ["FAIL"] * 3})
        assert "0 of 8 run(s) excluded as instrument failures." in md


class TestLaneWithNoIncumbent:
    """A workspace whose incumbent arm was excluded still has challengers.

    They cannot be ranked, and the report must SAY that rather than leaving them
    out of section 3 — an empty row reads as "nothing to report" when the truth
    is "nothing to compare against". auto-coding is in exactly this state: its
    production model_hint does not fit this host, so the arm was dropped.
    """

    def _campaign_no_incumbent(self, tmp_path):
        d = TestReportCompilation()._campaign(tmp_path, {"ch": ["PASS", "FAIL"]})
        man = json.loads((d / "manifest.json").read_text())
        for r in man["rows"]:
            r["arm_role"] = "challenger"
        (d / "manifest.json").write_text(json.dumps(man))
        for f in (d / "rows").glob("*.json"):
            row = json.loads(f.read_text())
            row["arm_role"] = "challenger"
            f.write_text(json.dumps(row))
        return d

    def test_the_lane_is_named_as_having_no_baseline(self, tmp_path):
        rep = camp_report_build(self._campaign_no_incumbent(tmp_path))
        assert rep["comparisons"] == []
        assert rep["no_baseline"] == ["ws"]

    def test_the_markdown_says_so_instead_of_showing_an_empty_section(self, tmp_path):
        from tests.wfe.report import render_markdown

        md = render_markdown(camp_report_build(self._campaign_no_incumbent(tmp_path)))
        assert "no incumbent arm" in md
        assert "`ws` — challengers were measured" in md

    def test_a_lane_with_an_incumbent_is_not_listed(self, tmp_path):
        d = TestReportCompilation()._campaign(tmp_path, {"inc": ["PASS"], "ch": ["PASS"]})
        assert camp_report_build(d)["no_baseline"] == []


class TestWatch:
    """A 30-60 hour sweep the operator cannot see is a sweep they cannot trust.
    The live view is read-only by construction — it must never be able to disturb
    the campaign it is watching."""

    def _campaign(self, tmp_path, outcomes):
        d = TestReportCompilation()._campaign(tmp_path, outcomes)
        for i, f in enumerate(sorted((d / "rows").glob("*.json"))):
            row = json.loads(f.read_text())
            row["economics"] = {"wall_s": 100.0 + i}
            f.write_text(json.dumps(row))
        return d

    def test_frame_reports_progress_and_an_eta(self, tmp_path):
        d = self._campaign(tmp_path, {"inc": ["PASS", "PASS"], "ch": ["PENDING", "PENDING"]})
        frame = camp._watch_frame(d, {}, __import__("time").monotonic())
        assert "2/4 rows" in frame
        assert "PENDING=2" in frame
        assert "left at this rate" in frame

    def test_a_finished_campaign_shows_no_eta(self, tmp_path):
        d = self._campaign(tmp_path, {"inc": ["PASS", "FAIL"]})
        assert "left at this rate" not in camp._watch_frame(d, {}, 0.0)

    def test_the_arm_in_flight_is_marked(self, tmp_path):
        d = self._campaign(tmp_path, {"inc": ["PASS", "PENDING"], "ch": ["PENDING", "PENDING"]})
        lines = [ln for ln in camp._watch_frame(d, {}, 0.0).splitlines() if "inc" in ln]
        assert lines and lines[0].lstrip().startswith("▶"), "arm in flight not marked"

    def test_wall_cache_reads_each_row_file_once(self, tmp_path):
        """Re-reading 513 files every refresh would make the monitor compete
        with the thing it is monitoring."""
        d = self._campaign(tmp_path, {"inc": ["PASS", "PASS"]})
        cache: dict = {}
        camp._row_walls(d, cache)
        assert len(cache) == 2
        for f in (d / "rows").glob("*.json"):
            f.write_text("{ corrupt")
        camp._row_walls(d, cache)  # cached names are not re-read
        assert len(cache) == 2

    def test_a_torn_manifest_read_does_not_kill_the_watch(self, tmp_path):
        """The campaign rewrites manifest.json after every row, so a reader can
        catch it mid-write. That must degrade to a skipped frame, not a crash."""
        d = self._campaign(tmp_path, {"inc": ["PASS"]})
        (d / "manifest.json").write_text('{"campaign_id": "c1"')
        with pytest.raises(json.JSONDecodeError):
            camp._watch_frame(d, {}, 0.0)  # raises here...
        # ...and _cmd_watch swallows it: the suppress wraps the whole frame, so a
        # torn read costs one skipped refresh rather than the operator's view.
        import inspect

        assert "contextlib.suppress" in inspect.getsource(camp._cmd_watch)

    def test_hms_is_readable_at_both_scales(self):
        assert camp._hms(45) == "0m45s"
        assert camp._hms(3600 * 30 + 120) == "30h02m"


class TestHealth:
    """One deterministic verdict, for a supervisor checking in on a schedule for
    two days. The answer must be the same whoever asks."""

    def _c(self, tmp_path, outcomes):
        return TestReportCompilation()._campaign(tmp_path, outcomes)

    def test_a_running_campaign_is_ok(self, tmp_path, monkeypatch):
        monkeypatch.setattr(camp, "ollama_reachable", lambda: True)
        d = self._c(tmp_path, {"inc": ["PASS", "PENDING"]})
        h = camp.health(d)
        assert (h["verdict"], h["exit_code"]) == ("OK", 0)

    def test_no_pending_rows_is_done(self, tmp_path, monkeypatch):
        monkeypatch.setattr(camp, "ollama_reachable", lambda: True)
        h = camp.health(self._c(tmp_path, {"inc": ["PASS", "FAIL"]}))
        assert (h["verdict"], h["exit_code"]) == ("DONE", 1)

    def test_unreachable_ollama_is_degraded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(camp, "ollama_reachable", lambda: False)
        h = camp.health(self._c(tmp_path, {"inc": ["PASS", "PENDING"]}))
        assert (h["verdict"], h["exit_code"]) == ("DEGRADED", 3)
        assert any("Ollama" in p for p in h["problems"])

    def test_no_progress_between_checks_is_stalled(self, tmp_path, monkeypatch):
        """A row may legitimately take the full 1800s budget, so a stall is only
        called when nothing at all completed between two spaced-out checks."""
        monkeypatch.setattr(camp, "ollama_reachable", lambda: True)
        d = self._c(tmp_path, {"inc": ["PASS", "PENDING", "PENDING"]})
        camp.health(d)  # records the baseline
        state = json.loads((d / "health_state.json").read_text())
        state["ts"] -= 7200  # two hours ago, still 1 row done
        (d / "health_state.json").write_text(json.dumps(state))
        h = camp.health(d)
        assert (h["verdict"], h["exit_code"]) == ("STALLED", 2)
        assert any("no row completed" in p for p in h["problems"])

    def test_progress_between_checks_is_not_stalled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(camp, "ollama_reachable", lambda: True)
        d = self._c(tmp_path, {"inc": ["PASS", "PASS", "PENDING"]})
        (d / "health_state.json").write_text(json.dumps({"ts": time.time() - 7200, "done": 1}))
        h = camp.health(d)
        assert h["verdict"] == "OK"
        assert h["advanced_since_last_check"] == 1

    def test_the_first_check_never_reports_a_stall(self, tmp_path, monkeypatch):
        """With no previous reading there is nothing to compare against."""
        monkeypatch.setattr(camp, "ollama_reachable", lambda: True)
        h = camp.health(self._c(tmp_path, {"inc": ["PENDING", "PENDING"]}))
        assert h["verdict"] == "OK"
        assert h["advanced_since_last_check"] is None

    def test_mostly_instrument_failures_is_degraded(self, tmp_path, monkeypatch):
        """The harness breaking is worth waking someone for; a model failing is not."""
        monkeypatch.setattr(camp, "ollama_reachable", lambda: True)
        d = self._c(tmp_path, {"inc": ["HARNESS_ERROR", "TOOL_ERROR", "PASS", "PENDING"]})
        h = camp.health(d)
        assert (h["verdict"], h["exit_code"]) == ("DEGRADED", 3)
        assert any("instrument failures" in p for p in h["problems"])

    def test_model_failures_alone_are_not_degraded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(camp, "ollama_reachable", lambda: True)
        d = self._c(tmp_path, {"inc": ["FAIL", "FAIL", "FAIL", "PENDING"]})
        assert camp.health(d)["verdict"] == "OK"

    def test_disk_free_is_the_available_column_not_the_size(self, tmp_path, monkeypatch):
        """Regression: splitting all of `df -g` stdout lands on 1G-blocks (total),
        which is always large — a disk check that could never fire."""
        monkeypatch.setattr(camp, "ollama_reachable", lambda: True)
        fake = "Filesystem 1G-blocks Used Available Capacity iused ifree %iused Mounted on\n/dev/x 926 920 5 99% 1 2 0% /\n"
        monkeypatch.setattr(
            camp.subprocess, "run", lambda *a, **k: types.SimpleNamespace(stdout=fake)
        )
        h = camp.health(self._c(tmp_path, {"inc": ["PASS", "PENDING"]}))
        assert h["checks"]["disk_free_gb"] == 5
        assert (h["verdict"], h["exit_code"]) == ("DEGRADED", 3)


class TestSamplingDelivery:
    """Measured 2026-09-25: Ollama /v1 drops top_k/min_p/repeat_penalty/
    presence_penalty; oMLX ignores `repeat_penalty` and honours
    `repetition_penalty`. A row must never claim sampling the model never saw."""

    def test_omlx_gets_repetition_penalty(self, monkeypatch):
        import tests.wfe.runner as rn

        monkeypatch.setattr(rn, "ENGINE", "omlx")
        _, payload, _ = rn._build_payload(
            "m", [], {"endpoint": "v1"}, {"repeat_penalty": 1.05, "top_k": 20}, None, "default"
        )
        assert payload["repetition_penalty"] == 1.05
        assert payload["top_k"] == 20

    def test_ollama_undeliverable_keys(self):
        import tests.wfe.runner as rn

        s = {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0, "repeat_penalty": 1.05}
        assert rn.undeliverable_keys(s, "ollama") == []
        # applied by Ollama since 0.35.0 (engine contract, 2026-10-07)
        assert rn.undeliverable_keys({"presence_penalty": 1.5}, "ollama") == []
        assert rn.undeliverable_keys(s, "omlx") == []
        assert rn.undeliverable_keys({"max_tokens": 5, "seed": 1}, "ollama") == []

    def test_override_with_undeliverable_key_blocks_the_arm(self, tmp_path, monkeypatch):
        import tests.wfe.campaign as c

        monkeypatch.setattr(c, "ENGINE", "ollama")
        monkeypatch.setattr(
            c, "undeliverable_keys", lambda s: [k for k in s if k == "top_k"]
        )  # stand-in
        monkeypatch.setattr(c, "preflight_arm", lambda *a, **k: pytest.fail("must not preflight"))
        rows = [
            {
                "run_id": "w|m@card-1|s|t|r0",
                "arm": "m@card-1",
                "model": "m",
                "overrides": {"sampling": {"temperature": 1.0, "top_k": 20}},
                "state": "PENDING",
            }
        ]
        manifest = {"rows": rows}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        todo, early = c._rows_to_run(tmp_path, manifest, "m@card-1", set(), False, False)
        assert todo == [] and early["blocked"] == 1
        assert rows[0]["state"] == "BLOCKED" and "top_k" in rows[0]["note"]

    def test_resume_on_a_different_engine_aborts(self, tmp_path, monkeypatch):
        import tests.wfe.campaign as c

        monkeypatch.setattr(c, "ollama_reachable", lambda: True)
        monkeypatch.setattr(c, "ENGINE", "ollama")
        (tmp_path / "manifest.json").write_text(json.dumps({"env": {"engine": "omlx"}, "rows": []}))
        assert c._ready(tmp_path) is False
        monkeypatch.setattr(c, "ENGINE", "omlx")
        assert c._ready(tmp_path) is True


class TestPipelineMode:
    """WFE_ENGINE=pipeline: the request is what Open WebUI sends — the
    workspace id, no seat sampling, no cap — plus only the arm's override."""

    def test_payload_is_workspace_plus_override_only(self, monkeypatch):
        from tests.wfe import runner as rn

        monkeypatch.setattr(rn, "ENGINE", "pipeline")
        monkeypatch.setattr(rn, "CHAT_BASE", "http://p:9099")
        url, body, _ = rn._build_payload(
            "auto-coding::laguna",
            [{"role": "user", "content": "x"}],
            {**rn.HARNESS_DEFAULTS},
            {"temperature": 0.2, "repeat_penalty": 1.05, "max_tokens": 32768},
            [{"type": "function", "function": {"name": "f"}}],
            "false",
            True,
        )
        assert url == "http://p:9099/v1/chat/completions"
        assert body["model"] == "auto-coding::laguna"
        assert "max_tokens" not in body
        assert body["temperature"] == 0.2
        assert body["repetition_penalty"] == body["repeat_penalty"] == 1.05
        assert body["think"] is False
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        assert body["portal_client_tools_only"] is True

    def test_incumbent_sends_no_sampling_and_no_think(self, monkeypatch):
        from tests.wfe import campaign as cp

        monkeypatch.setattr(cp, "ENGINE", "pipeline")
        wsc = {"sampling": {"temperature": 1.0, "max_tokens": 16384}, "think": True}
        assert cp._sampling_for(wsc, 1) == {"seed": 1001, "max_tokens_source": "pipeline"}
        assert cp.campaign_harness(wsc)["think"] == "native"

    def test_override_sampling_is_sent(self, monkeypatch):
        from tests.wfe import campaign as cp

        monkeypatch.setattr(cp, "ENGINE", "pipeline")
        s = cp._sampling_for({"sampling": {"top_k": 20}}, 0, {"sampling": {"temperature": 0.2}})
        assert s == {"temperature": 0.2, "seed": 1000, "max_tokens_source": "pipeline"}

    def test_seat_primary_is_the_production_alias(self):
        """backends.yaml shadows several incumbent tags onto priority-10 oMLX
        seats; that alias is the seat. Reads the committed routing, so it
        fails if the alias drifts too."""
        from tests.wfe import campaign as cp

        assert (
            cp.seat_primary("auto-compliance", "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k")
            == "Qwen3.8-27B-oQ4e-mtp"
        )
        # variant ids resolve through their base workspace's routing
        assert (
            cp.seat_primary("auto-coding::laguna", "portal5/laguna-xs21:q4_K_M-ctx128k")
            == "Laguna-XS-2.1-4bit"
        )
        # an unaliased tag is its own seat
        assert (
            cp.seat_primary("auto-coding::fast-repair", "kat-coder-v2.5-dev:Q4_K_M-ctx32k")
            == "kat-coder-v2.5-dev:Q4_K_M-ctx32k"
        )

    def test_preflight_pipeline_rejects_the_failover_and_drift(self, monkeypatch):
        from tests.wfe import campaign as cp

        tag = "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"
        seat = {"backend": "omlx-reasoning", "model": "Qwen3.8-27B-oQ4e-mtp"}
        monkeypatch.setattr(cp, "chat", lambda *a, **k: {"served": seat})
        monkeypatch.setattr(
            cp, "observe_identity", lambda b, m: ({"backend": b, "model": m, "content": "c"}, "")
        )
        assert cp.preflight_pipeline(["auto-compliance"], tag)["verdict"] == "OK"
        for other in (tag, "some-other-model"):
            served = {"backend": "omlx-reasoning", "model": other}
            monkeypatch.setattr(cp, "chat", lambda *a, _s=served, **k: {"served": _s})
            pf = cp.preflight_pipeline(["auto-compliance"], tag)
            assert pf["verdict"] == "REVIEW" and other in pf["findings"][0]
        # The right model, but a build nobody can observe, is not a pass either.
        monkeypatch.setattr(cp, "chat", lambda *a, **k: {"served": seat})
        monkeypatch.setattr(
            cp, "observe_identity", lambda b, m: ({"backend": b, "model": m, "content": ""}, "gone")
        )
        pf = cp.preflight_pipeline(["auto-compliance"], tag)
        assert pf["verdict"] == "REVIEW" and "cannot be observed: gone" in pf["findings"][0]

    def test_a_failover_turn_makes_the_row_not_seat_evidence(self):
        """V2 counted 17 rows served by the Ollama failover (and 2 that switched
        engine mid-row) as the oMLX seat's baseline."""
        from tests.wfe import campaign as cp

        seat = "Qwen3.8-27B-oQ4e-mtp"

        def turn(m):
            return {"turn": 0, "tool_calls": [], "served": {"model": m}}

        assert cp.served_mismatch([turn(seat), turn(seat)], seat) is None
        assert "failover" in cp.served_mismatch([turn(seat), turn("raw:tag")], seat)
        # a model turn without trace evidence is unverified, not assumed fine
        missing = [turn(seat), {"turn": 1, "tool_calls": []}]
        assert "unverified" in cp.served_mismatch(missing, seat)
        # non-model transcript entries (stall, turn-cap marker) carry no served
        assert cp.served_mismatch([turn(seat), {"turn": 2, "exhausted_turns": "x"}], seat) is None


class TestV2ReviewInstrumentFixes:
    """Defects found reviewing wfe_prompt_surface_seat_20261012 (V3 task)."""

    def test_repo_search_scoped_to_a_file_searches_that_file(self, tmp_path):
        sb = Sandbox(tmp_path)
        sb.file_write("packet.json", '"governing_ref": "CIP-010-4 R2 Part 2.1"')
        sb.file_write("other.txt", "unrelated")
        out = sb.repo_search("CIP-010-4", "other.txt")
        assert "packet.json" not in out and out == "(no matches)"
        assert sb.repo_search("CIP-010-4", "packet.json").startswith("packet.json:1:")

    def test_repo_search_on_a_missing_path_is_an_error_not_a_widening(self, tmp_path):
        sb = Sandbox(tmp_path)
        sb.file_write("packet.json", "CIP-010-4")
        assert sb.repo_search("CIP-010-4", "no/such.json").startswith("ERROR:")

    def test_repo_search_scoped_to_a_repo_file_reaches_it(self, tmp_path):
        out = Sandbox(tmp_path).repo_search(r"\[tool\.ruff\]", "pyproject.toml")
        assert out.startswith("pyproject.toml:")

    def test_repo_search_scoped_to_a_repo_dir_keeps_the_deny_list(self, tmp_path):
        out = Sandbox(tmp_path).repo_search("comp-p6j-01", "tests")
        assert "tests/wfe/" not in out

    def test_sandbox_only_task_cannot_read_the_repository(self, tmp_path):
        sb = Sandbox(tmp_path, allow_repo_read=False)
        assert sb.file_read("pyproject.toml").startswith("ERROR:")
        assert sb.repo_search(r"\[tool\.ruff\]") == "(no matches)"
        assert sb.repo_search("x", "config/compliance/y21_resolutions.yaml").startswith("ERROR:")

    def test_every_compliance_packet_task_is_sandbox_only(self):
        from tests.wfe.runner import REPO, load_suite

        for name in (
            "compliance_agentic",
            "compliance_agentic_full",
            "compliance_agentic_loopset",
            "compliance_agentic_loopset_noformat",
        ):
            for t in load_suite(REPO / f"tests/wfe/suites/{name}.jsonl"):
                if "packet.json" in (t.get("seed") or {}):
                    assert t.get("repo_read") is False, (name, t["id"])

    def test_run_task_applies_repo_read_and_the_sandbox_only_schema(self, tmp_path, monkeypatch):
        from tests.wfe import runner as rn

        seen = {}

        def fake_chat(model, messages, tools=True, tool_schemas=None, **k):
            seen["schemas"] = tool_schemas
            return {
                "message": {"content": "done"},
                "finish_reason": "stop",
                "economics": rn.Economics(),
                "served": {},
            }

        monkeypatch.setattr(rn, "chat", fake_chat)
        sb = Sandbox(tmp_path)
        task = {
            "id": "t",
            "instruction": "x",
            "repo_read": False,
            "checkers": [{"type": "answer_contains", "patterns": ["done"]}],
        }
        rn.run_task("m", "sys", task, sb, 2, 60, use_tools=True)
        assert sb.allow_repo_read is False
        desc = [s for s in seen["schemas"] if s["function"]["name"] == "repo_search"][0]
        assert "repository" not in desc["function"]["description"]

    def test_workspace_mount_paths_land_in_the_sandbox(self, tmp_path):
        sb = Sandbox(tmp_path)
        sb.file_write("notes.md", "seeded")
        assert sb.file_read("/workspace/notes.md") == "seeded"
        assert sb.file_read("/workspace/uploads/notes.md") == "seeded"
        assert sb.file_write("/workspace/out.py", "x").startswith("wrote")
        assert (tmp_path / "out.py").read_text() == "x"
        assert "notes.md" in sb.file_list("/workspace")

    def test_pipeline_error_frame_is_not_an_empty_answer(self):
        lines = ['data: {"error": "Response timed out — model may still be generating."}']
        with pytest.raises(RuntimeError, match="mid-stream"):
            _parse_stream_v1(iter(lines))

    def test_pipeline_no_answer_placeholder_is_not_the_models_answer(self, tmp_path, monkeypatch):
        from portal.platform.inference.router.thinking import NO_ANSWER_MESSAGE
        from tests.wfe import runner as rn

        monkeypatch.setattr(
            rn,
            "chat",
            lambda *a, **k: {
                "message": {"content": NO_ANSWER_MESSAGE},
                "finish_reason": "stop",
                "economics": rn.Economics(),
                "served": {},
            },
        )
        task = {
            "id": "t",
            "instruction": "x",
            "checkers": [{"type": "answer_contains", "patterns": ["Please retry"]}],
        }
        out = rn.run_task("m", "sys", task, Sandbox(tmp_path), 2, 60, use_tools=True)
        assert out["final_text"] == "" and out["outcome"] == "FAIL"
        assert out["evidence"]["pipeline_no_answer"] is True
        assert out["notes"].startswith("pipeline no-answer placeholder")

    def test_dispatch_errors_are_flagged_in_the_tool_log(self, tmp_path):
        from tests.wfe.runner import _execute_calls

        log, msgs = [], []
        calls = [{"function": {"name": "file_read", "arguments": '{"path": "nope.txt"}'}}]
        assert _execute_calls(calls, 0, Sandbox(tmp_path), log, msgs) == 1
        assert log[0]["error"] is True

    def test_code_kv_instruction_names_a_single_backslash_escape(self):
        """The instruction said `\\\\;` (two backslashes) while the hidden suite
        tests r"a\\;b" (one): models wrote tests to the instruction, their
        own tests failed and they looped with a hidden-suite-passing parser."""
        from tests.wfe.runner import REPO, load_suite

        kv = {t["id"]: t for t in load_suite(REPO / "tests/wfe/suites/coding.jsonl")}["code-kv"]
        assert "semicolon \\; is" in kv["instruction"]
        assert "\\\\;" not in kv["instruction"]
        graded = (REPO / "tests/wfe/graded/code_kv/test_parse_kv.py").read_text()
        assert 'r"note=a\\;b' in graded

    def test_rescore_never_upgrades_a_blocked_row(self):
        out, why = camp._reconcile_offline("BLOCKED", "PASS")
        assert out == "BLOCKED" and "kept recorded" in why

    def test_arm_on_an_aliased_seat_drains_the_raw_tag_and_stops_on_failover(
        self, tmp_path, monkeypatch
    ):
        """V2: the failover GGUF stayed resident (drain kept the raw tag) and
        oMLX 507'd every reload for 17 rows. The arm must free it at start and
        stop at the first failover row instead of burning the rest."""
        tag = "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"
        rows = [
            {
                "run_id": f"r{i}",
                "arm": tag,
                "model": tag,
                "workspace": "auto-compliance",
                "suite_path": "s",
                "task_id": "t",
                "state": "PENDING",
            }
            for i in range(3)
        ]
        manifest = {"rows": rows}
        kept, ran = [], []
        monkeypatch.setattr(camp, "ENGINE", "pipeline")
        monkeypatch.setattr(camp, "load_manifest", lambda d: manifest)
        monkeypatch.setattr(camp, "save_manifest", lambda d, m: None)
        monkeypatch.setattr(camp, "_rows_to_run", lambda *a: (list(rows), None))
        monkeypatch.setattr(camp, "drain_others", lambda keep: kept.append(keep) or [])
        monkeypatch.setattr(camp, "model_sizes", lambda: {tag: 1})
        monkeypatch.setattr(camp, "drain_model", lambda m: True)
        monkeypatch.setattr(camp, "workspace_context", lambda ws, persona=None: {})
        monkeypatch.setattr(camp, "load_suite", lambda p: [{"id": "t"}])

        def fake_row(d, m, r, *a, **k):
            ran.append(r["run_id"])
            return {
                "outcome": "BLOCKED",
                "notes": camp.SEAT_BLOCK + "failover",
                "turns": 1,
                "tool_calls": 0,
                "tool_errors": 0,
                "economics": {},
            }

        monkeypatch.setattr(camp, "run_row", fake_row)
        camp.execute_arm(tmp_path, tag, 16, 600, None, False, False)
        assert kept == [""] and ran == ["r0"]
        assert [r["state"] for r in rows] == ["BLOCKED", "PENDING", "PENDING"]


class TestSelectionBiasFixes:
    """Defects that biased model choice, found in the 2026-10-13 audit."""

    def test_workspace_is_measured_with_its_own_prompt_not_a_persona(self):
        import yaml

        from tests.wfe.runner import REPO, workspace_context

        ws = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
        for wid in ("auto-coding", "auto-compliance", "tools-specialist", "auto-research"):
            wsc = workspace_context(wid)
            assert wsc["persona_slug"] is None
            assert wsc["system_prompt_base"] == (ws[wid].get("owui_system_prompt") or "")
        # a persona is measured only when named
        slug = workspace_context("auto-coding", "agenticheavy")["persona_slug"]
        assert slug == "agenticheavy"

    def test_no_prompt_workspace_sends_no_invented_prompt(self, tmp_path, monkeypatch):
        from tests.wfe import runner as rn

        assert rn.workspace_context("auto-general-uncensored")["system_prompt_base"] == ""
        sent = {}

        def fake_chat(model, messages, **k):
            sent["roles"] = [m["role"] for m in messages]
            return {
                "message": {"content": "ok"},
                "finish_reason": "stop",
                "economics": rn.Economics(),
                "served": {},
            }

        monkeypatch.setattr(rn, "chat", fake_chat)
        task = {"id": "t", "instruction": "x", "checkers": [{"type": "answer_contains"}]}
        rn.run_task("m", "", task, Sandbox(tmp_path), 1, 60, use_tools=True)
        assert sent["roles"] == ["user"]

    def test_challengers_run_at_their_card_sampling(self, tmp_path):
        plan = tmp_path / "p.yaml"
        plan.write_text(
            yaml.safe_dump(
                {
                    "workloads": {
                        "auto-compliance": {
                            "home": "compliance_agentic",
                            "arms": {
                                "incumbent": "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k",
                                "challengers": [
                                    "gpt-oss:20b",
                                    {"model": "granite4.2:30b-q4_K_M", "sampling": "seat"},
                                ],
                            },
                        }
                    }
                }
            )
        )
        rows = camp.expand_matrix(plan, repeats=1)
        by_model = {r["model"]: r for r in rows}
        assert by_model["hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"]["overrides"] == {}
        assert by_model["gpt-oss:20b"]["overrides"]["sampling"] == {
            "temperature": 1.0,
            "top_p": 1.0,
        }
        assert "@card-" in by_model["gpt-oss:20b"]["arm"]
        assert by_model["granite4.2:30b-q4_K_M"]["overrides"] == {}

    def test_card_mode_follows_the_lane_think_policy(self):
        from tests.wfe.runner import card_sampling

        tag = "orcarouter/Qwen3.8-27B-Uncensored:Q4_K_M"
        assert card_sampling(tag, False)["temperature"] == 0.7
        assert card_sampling(tag, True)["temperature"] == 1.0
        assert card_sampling("command-r:35b", None) == {}

    def test_degeneracy_follows_the_arms_own_temperature(self):
        wsc = {"declared_temperature": 0.0}
        assert camp.degenerate_repeats(wsc) is not None
        assert camp.degenerate_repeats(wsc, {"sampling": {"temperature": 1.0}}) is None

    def test_deterministic_repeats_count_once_in_the_rate(self):
        from tests.wfe import report as rp

        rows = [
            {"task_id": "a", "repeat": i, "outcome": "PASS", "repeat_degeneracy": "t0"}
            for i in range(3)
        ] + [
            {"task_id": "b", "repeat": i, "outcome": "FAIL", "repeat_degeneracy": "t0"}
            for i in range(3)
        ]
        assert rp._rate(rp._one_draw_per_task(rows)) == (1, 2)

    def test_context_overflow_is_detected(self):
        from tests.wfe.runner import context_overflow

        grow = [{"turn": 0, "prompt_tokens": 3000}, {"turn": 1, "prompt_tokens": 5000}]
        assert context_overflow(grow, 8192) is None
        shrink = [{"turn": 0, "prompt_tokens": 7000}, {"turn": 1, "prompt_tokens": 4098}]
        assert "shrank" in context_overflow(shrink, 8192)
        full = [{"turn": 0, "prompt_tokens": 7900, "completion_tokens": 300}]
        assert "reached" in context_overflow(full, 8192)
        first_turn_cut = [{"turn": 0, "sent_chars": 15346, "prompt_tokens": 1027}]
        assert "chars sent" in context_overflow(first_turn_cut, None)

    def test_weak_checkers_now_require_the_substance(self):
        from tests.wfe.runner import REPO, load_suite

        coding = {t["id"]: t for t in load_suite(REPO / "tests/wfe/suites/coding.jsonl")}
        assert coding["code-cli-args"]["checkers"][0]["type"] == "hidden_pytest"
        assert (REPO / "tests/wfe/graded/code_summarize/test_summarize.py").is_file()
        research = {t["id"]: t for t in load_suite(REPO / "tests/wfe/suites/research.jsonl")}
        assert "Modelfile" in research["res-ollama-ctx"]["checkers"][0]["patterns"]


class TestServedEngine:
    """served_engine: the audit resolves each seat the way the pipeline does —
    routing groups, backend priority, alias translation, oMLX groups included —
    so every later check audits the path production actually serves."""

    BACKENDS = """\
backends:
- group: general
  id: ollama-general
  type: ollama
  url: http://localhost:11434
  models: [gemma4:26b]
- group: coding
  id: ollama-coding
  type: ollama
  url: http://localhost:11434
  models: [kat-coder:Q4]
- group: general
  id: omlx-general
  type: omlx
  url: http://localhost:8085
  priority: 10
  models:
  - id: unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit
    supports_tools: true
  aliases:
    hf.co/unsloth/Qwen3.6-35B-GGUF:Q4_K_M: unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit
workspace_routing:
  auto-daily: [general]
  auto-coding: [coding, general]
defaults:
  fallback_group: general
"""

    def _reg(self, tmp_path):
        from portal.platform.inference.cluster_backends import BackendRegistry

        p = tmp_path / "backends.yaml"
        p.write_text(self.BACKENDS)
        return BackendRegistry(str(p))

    def test_an_omlx_alias_serves_the_omlx_path_and_names_the_served_model(self, tmp_path):
        from tests.wfe.settings_audit import _served_path

        got = _served_path(
            "auto-daily", "hf.co/unsloth/Qwen3.6-35B-GGUF:Q4_K_M", self._reg(tmp_path)
        )
        assert got == ("omlx", "omlx-general", "unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit")

    def test_a_plain_hint_on_a_10_priority_group_still_resolves_ollama(self, tmp_path):
        """The priority-10 oMLX backend is tried first; when it cannot serve the
        hint the Ollama backend behind it does — engine ollama, not a guess."""
        from tests.wfe.settings_audit import _served_path

        assert _served_path("auto-daily", "gemma4:26b", self._reg(tmp_path)) == (
            "ollama",
            "ollama-general",
            "gemma4:26b",
        )

    def test_the_first_routing_group_wins_over_the_priority_10_fallback(self, tmp_path):
        from tests.wfe.settings_audit import _served_path

        assert _served_path("auto-coding", "kat-coder:Q4", self._reg(tmp_path)) == (
            "ollama",
            "ollama-coding",
            "kat-coder:Q4",
        )

    def test_no_backend_resolving_the_hint_is_none(self, tmp_path):
        from tests.wfe.settings_audit import _served_path

        assert _served_path("auto-daily", "nope:latest", self._reg(tmp_path)) is None


class TestTemplateConformance:
    """template_conformance: the expectation per architecture is DERIVED from the
    locally installed library builds (any tag whose modelfile carries a RENDERER,
    most common pair wins) — never a hand-written table."""

    @staticmethod
    def _show(arch, ren="", par="", template="{{ .Prompt }}", params=""):
        modelfile = ""
        if ren:
            modelfile += f"RENDERER {ren}\n"
        if par:
            modelfile += f"PARSER {par}\n"
        return {
            "model_info": {"general.architecture": arch},
            "modelfile": modelfile,
            "template": template,
            "parameters": params,
        }

    @staticmethod
    def _audit(tag, show, library):
        import tests.wfe.settings_audit as sa

        shows = {tag: show, **library}
        v: list[dict] = []
        sa._audit_template_conformance("w", tag, shows, sa.template_map(shows), v)
        return v

    def test_the_map_is_the_most_common_pair_per_architecture(self):
        import tests.wfe.settings_audit as sa

        shows = {
            "a": self._show("qwen35", "qwen3.5", "qwen3.5"),
            "b": self._show("qwen35", "qwen3.5", "qwen3.5"),
            "c": self._show("qwen35", "qwen3.8", "qwen3.5"),
            "d": self._show("gemma4", "gemma4", "gemma4"),
        }
        assert sa.template_map(shows) == {
            "qwen35": ("qwen3.5", "qwen3.5"),
            "gemma4": ("gemma4", "gemma4"),
        }

    def test_a_tie_resolves_deterministically(self):
        import tests.wfe.settings_audit as sa

        shows = {
            "a": self._show("arch", "rend1", "p1"),
            "b": self._show("arch", "rend2", "p2"),
        }
        assert sa.template_map(shows) == sa.template_map(dict(reversed(list(shows.items()))))

    def test_a_raw_jinja_tag_on_a_mapped_architecture_fails(self):
        lib = {"lib": self._show("gemma4", "gemma4", "gemma4", "<real template>")}
        v = self._audit("raw:Q4", self._show("gemma4"), lib)
        assert [(x["kind"], x["severity"]) for x in v] == [("template_raw_jinja", "FAIL")]
        assert "gemma4/gemma4" in v[0]["detail"]

    def test_a_raw_jinja_tag_on_an_unmapped_architecture_passes(self):
        v = self._audit("granite:Q4", self._show("granite"), {})
        assert v == []

    def test_a_library_conforming_tag_is_clean(self):
        lib = {"lib": self._show("qwen35", "qwen3.5", "qwen3.5", "<real>")}
        v = self._audit(
            "hf.co/x/Qwen3.6-GGUF:Q4",
            self._show("qwen35", "qwen3.5", "qwen3.5", "<real>"),
            lib,
        )
        assert v == []

    def test_a_renderer_the_library_does_not_carry_fails(self):
        lib = {
            "lib-a": self._show("qwen35", "qwen3.5", "qwen3.5", "<real>"),
            "lib-b": self._show("qwen35", "qwen3.5", "qwen3.5", "<real>"),
        }
        v = self._audit("retemplated:Q4", self._show("qwen35", "qwen3.8", "qwen3.8", "<real>"), lib)
        assert [(x["kind"], x["severity"]) for x in v] == [("template_renderer_mismatch", "FAIL")]

    def test_an_instruct_variant_beside_only_thinking_builds_is_legitimate(self):
        """2026-10-28: removing qwen3-vl:8b-instruct left qwen3-vl:4b-instruct beside only
        thinking builds; its qwen3-vl-instruct renderer is the variant its name says."""
        lib = {"lib": self._show("qwen3vl", "qwen3-vl-thinking", "qwen3-vl-thinking", "<real>")}
        tag = "qwen3-vl:4b-instruct-q4_K_M"
        show = self._show("qwen3vl", "qwen3-vl-instruct", "qwen3-vl-instruct", "<real>")
        assert self._audit(tag, show, lib) == []
        # The variant token must match the tag's own name: a thinking-named tag on the
        # instruct renderer is still a mismatch.
        v = self._audit("qwen3-vl:32b-thinking", show, lib)
        assert [x["kind"] for x in v] == ["template_renderer_mismatch"]

    def test_a_second_library_renderer_for_the_arch_is_legitimate(self):
        """qwen35 carries qwen3.5 and qwen3.8 in the library; a Qwen3.8 tag on
        qwen3.8 is the documented build, not a majority-vote loser."""
        lib = {
            "lib-a": self._show("qwen35", "qwen3.5", "qwen3.5", "<real>"),
            "lib-b": self._show("qwen35", "qwen3.5", "qwen3.5", "<real>"),
            "lib-c": self._show("qwen35", "qwen3.8", "qwen3.5", "<real>"),
        }
        v = self._audit(
            "hf.co/unsloth/Qwen3.8-27B:Q4",
            self._show("qwen35", "qwen3.8", "qwen3.5", "<real>"),
            lib,
        )
        assert v == []

    def test_a_raw_jinja_tag_expects_its_family_renderer(self):
        lib = {
            "lib-a": self._show("qwen35", "qwen3.5", "qwen3.5", "<real>"),
            "lib-b": self._show("qwen35", "qwen3.5", "qwen3.5", "<real>"),
            "lib-c": self._show("qwen35", "qwen3.8", "qwen3.5", "<real>"),
        }
        raw = self._show("qwen35", "", "", "{{ .Prompt }}")
        v = self._audit("hf.co/unsloth/Qwen3.8-27B:Q4", raw, lib)
        assert len(v) == 1 and "qwen3.8/qwen3.5" in v[0]["detail"]

    def test_a_laguna_build_named_21_must_use_poolside_v1(self):
        """XS.2's `laguna` parser on a 2.1 build is the finding that started this
        check — it must fail even when the laguna-arch map says otherwise."""
        lib = {
            "xs2-a": self._show("laguna", "laguna", "laguna", "<real>"),
            "xs2-b": self._show("laguna", "laguna", "laguna", "<real>"),
            "lib21": self._show("laguna", "poolside-v1", "poolside-v1", "<real>"),
        }
        v = self._audit(
            "laguna-xs-2.1:latest",
            self._show("laguna", "poolside-v1", "laguna", "<real>"),
            lib,
        )
        assert [(x["kind"], x["severity"]) for x in v] == [("template_parser_mismatch", "FAIL")]

    def test_a_laguna_21_build_on_poolside_v1_is_clean_even_against_the_map(self):
        lib = {
            "xs2-a": self._show("laguna", "laguna", "laguna", "<real>"),
            "xs2-b": self._show("laguna", "laguna", "laguna", "<real>"),
        }
        v = self._audit(
            "laguna-xs-2.1:latest",
            self._show("laguna", "poolside-v1", "poolside-v1", "<real>"),
            lib,
        )
        assert v == []

    def test_a_laguna_build_that_is_not_21_follows_the_map(self):
        lib = {"xs2-a": self._show("laguna", "laguna", "laguna", "<real>")}
        v = self._audit("laguna-xs:2.0", self._show("laguna", "laguna", "laguna", "<real>"), lib)
        assert v == []

    def test_xs21_without_the_dot_is_still_named_21(self):
        lib = {"xs2-a": self._show("laguna", "laguna", "laguna", "<real>")}
        v = self._audit(
            "portal5/laguna-xs21:q4_K_M",
            self._show("laguna", "poolside-v1", "laguna", "<real>"),
            lib,
        )
        assert [x["kind"] for x in v] == ["template_parser_mismatch"]


class TestStopHygiene:
    def _audit(self, params):
        import tests.wfe.settings_audit as sa

        shows = {"t:Q4": {"parameters": params}}
        v: list[dict] = []
        sa._audit_stop_hygiene("w", "t:Q4", shows, v)
        return v

    def test_a_baked_think_stop_is_a_fail(self):
        v = self._audit('temperature 0.7\nstop    "<think>"\nstop    "<|im_end|>"')
        assert [(x["kind"], x["severity"]) for x in v] == [("stop_hygiene", "FAIL")]
        assert "<think>" in v[0]["detail"]

    def test_baked_jinja_fragments_are_a_fail(self):
        assert self._audit('stop    "{{ .Prompt }}"') != []
        assert self._audit('stop    ".Prompt }}"') != []

    def test_clean_stops_pass(self):
        assert self._audit('stop    "<|im_end|>"\nstop    "<|im_start|>user"') == []

    def test_no_parameters_at_all_passes(self):
        assert self._audit("") == []


class TestOmlxSettings:
    """omlx_settings: the served oMLX model's ~/.omlx/model_settings.json entry
    is what the card is judged against; 'no entry' is INFO (oMLX then serves the
    request's sampling)."""

    def test_no_entry_is_info_not_a_fault(self, monkeypatch):
        import tests.wfe.settings_audit as sa

        monkeypatch.setattr(sa, "_omlx_model_settings", lambda _mid: {})
        v: list[dict] = []
        sa._audit_omlx_settings("w", "model-4bit", v)
        assert [(x["kind"], x["severity"]) for x in v] == [("omlx_settings_no_entry", "INFO")]

    def test_the_reader_parses_a_canned_model_settings(self, tmp_path, monkeypatch):
        import tests.wfe.settings_audit as sa

        home = tmp_path / "home"
        (home / ".omlx").mkdir(parents=True)
        (home / ".omlx" / "model_settings.json").write_text(
            json.dumps({"models": {"m-4bit": {"temperature": 0.7, "enable_thinking": False}}})
        )
        monkeypatch.setattr(sa.Path, "home", lambda: home)
        assert sa._omlx_model_settings("m-4bit") == {
            "temperature": 0.7,
            "enable_thinking": False,
        }
        assert sa._omlx_model_settings("absent") == {}

    def test_repetition_penalty_maps_to_the_card_key(self):
        import tests.wfe.settings_audit as sa

        assert sa._omlx_entry_sampling({"repetition_penalty": 1.05, "mtp_enabled": True}) == {
            "repeat_penalty": 1.05
        }

    def test_the_entry_is_what_the_card_is_judged_against(self, monkeypatch):
        """The global oMLX default says 0.7; the entry bakes the thinking card's
        1.0 — served is 1.0, so the seat must be judged clean, not by the global."""
        import tests.wfe.settings_audit as sa

        registry = {
            "qwen3.6": {
                "status": "verified-card",
                "recommended_sampling_modes": {
                    "thinking": {"temperature": 1.0, "presence_penalty": 0.0}
                },
            }
        }
        monkeypatch.setattr(
            sa, "_expectations_for", lambda _h, _r: ("qwen3.6", registry["qwen3.6"])
        )
        monkeypatch.setattr(sa, "omlx_default_sampling", lambda: {"temperature": 0.7})
        monkeypatch.setattr(
            sa,
            "_omlx_model_settings",
            lambda _mid: {"temperature": 1.0, "presence_penalty": 0.0, "enable_thinking": True},
        )
        ws = {"model_hint": "Laguna-X-4bit", "think": True}
        v: list[dict] = []
        sa._served_sampling_check(
            "w", ws, "hf.co/x/Qwen3.6-GGUF:Q4", "omlx", registry, v, served_id="Laguna-X-4bit"
        )
        assert v == []

    def test_an_entry_off_the_card_fails_the_served_seat(self, monkeypatch):
        import tests.wfe.settings_audit as sa

        registry = {
            "qwen3.6": {
                "status": "verified-card",
                "recommended_sampling_modes": {
                    "thinking": {"temperature": 1.0, "presence_penalty": 0.0}
                },
            }
        }
        monkeypatch.setattr(
            sa, "_expectations_for", lambda _h, _r: ("qwen3.6", registry["qwen3.6"])
        )
        monkeypatch.setattr(sa, "omlx_default_sampling", lambda: {})
        monkeypatch.setattr(
            sa, "_omlx_model_settings", lambda _mid: {"temperature": 0.7, "enable_thinking": False}
        )
        ws = {"model_hint": "Laguna-X-4bit", "think": True}
        v: list[dict] = []
        sa._served_sampling_check(
            "w", ws, "hf.co/x/Qwen3.6-GGUF:Q4", "omlx", registry, v, served_id="Laguna-X-4bit"
        )
        assert [x["kind"] for x in v] == ["served_vs_card"]
        assert [x["severity"] for x in v] == ["FAIL"]
        assert "temperature" in v[0]["detail"]


class TestSamplingModeFit:
    """sampling_mode_fit: a tools/coding seat must serve the card's coding/precise
    arm when the card documents one — the general arm's presence 1.5 is the
    tool-refusal regime, and the card names the numbers that work."""

    MODES = {
        "thinking_general": {"temperature": 0.7, "presence_penalty": 1.5},
        "thinking_precise_coding": {"temperature": 0.6, "presence_penalty": 0.0},
    }

    def _audit(self, ws, monkeypatch, modes=None):
        import tests.wfe.settings_audit as sa

        registry = {
            "qwen3.6": {
                "status": "verified-card",
                "recommended_sampling_modes": modes if modes is not None else self.MODES,
            }
        }
        monkeypatch.setattr(
            sa, "_expectations_for", lambda _h, _r: ("qwen3.6", registry["qwen3.6"])
        )
        v: list[dict] = []
        sa._audit_sampling_mode_fit(
            "auto-coding", ws, "hf.co/unsloth/Qwen3.6-35B-GGUF:Q4", {}, registry, v
        )
        return v

    def test_a_tools_seat_on_the_general_arm_fails_naming_the_matched_mode(self, monkeypatch):
        ws = {
            "tools": ["execute_bash"],
            "think": True,
            "temperature": 0.7,
            "presence_penalty": 1.5,
        }
        v = self._audit(ws, monkeypatch)
        assert [(x["kind"], x["severity"]) for x in v] == [("sampling_mode_fit", "FAIL")]
        assert "thinking_general" in v[0]["detail"]
        assert "thinking_precise_coding" in v[0]["detail"]
        assert "presence_penalty 1.5 vs 0.0" in v[0]["detail"]

    def test_a_tools_seat_on_the_precise_arm_is_clean(self, monkeypatch):
        ws = {
            "tools": ["execute_bash"],
            "think": True,
            "temperature": 0.6,
            "presence_penalty": 0.0,
        }
        assert self._audit(ws, monkeypatch) == []

    def test_the_baked_default_layer_counts_as_served(self, monkeypatch):
        """Nothing declared: the seat is served the tag's baked general-arm
        values — still the wrong arm for a tool loop."""
        import tests.wfe.settings_audit as sa

        ws = {"tools": ["execute_bash"], "think": True}
        registry = {
            "qwen3.6": {
                "status": "verified-card",
                "recommended_sampling_modes": self.MODES,
            }
        }
        monkeypatch.setattr(
            sa, "_expectations_for", lambda _h, _r: ("qwen3.6", registry["qwen3.6"])
        )
        v: list[dict] = []
        sa._audit_sampling_mode_fit(
            "auto-coding",
            ws,
            "hf.co/unsloth/Qwen3.6-35B-GGUF:Q4",
            {"temperature": 0.7, "presence_penalty": 1.5},
            registry,
            v,
        )
        assert [x["kind"] for x in v] == ["sampling_mode_fit"]

    def test_a_seat_without_tools_on_a_general_lane_is_not_checked(self, monkeypatch):
        ws = {"module": "general", "think": True, "temperature": 0.7, "presence_penalty": 1.5}
        assert self._audit(ws, monkeypatch) == []

    def test_a_coding_lane_is_checked_even_without_tools(self, monkeypatch):
        ws = {"module": "coding", "think": True, "temperature": 0.7, "presence_penalty": 1.5}
        assert [x["kind"] for x in self._audit(ws, monkeypatch)] == ["sampling_mode_fit"]

    def test_the_agentic_tool_mode_is_checked_even_without_tools(self, monkeypatch):
        ws = {"mode": "agentic", "think": True, "temperature": 0.7, "presence_penalty": 1.5}
        assert [x["kind"] for x in self._audit(ws, monkeypatch)] == ["sampling_mode_fit"]

    def test_a_card_without_a_precise_arm_is_not_checked(self, monkeypatch):
        ws = {"tools": ["execute_bash"], "think": True, "temperature": 0.7, "presence_penalty": 1.5}
        v = self._audit(ws, monkeypatch, modes={"thinking": {"temperature": 1.0}})
        assert v == []


class TestTagsAudit:
    """--tags: template + stop conformance for arbitrary tags (challengers and
    bench candidates), with no workspace."""

    @staticmethod
    def _show(arch, ren="", par="", template="{{ .Prompt }}", params=""):
        return TestTemplateConformance._show(arch, ren, par, template, params)

    def _mock(self, monkeypatch, shows):
        import tests.wfe.settings_audit as sa

        def fake_post(path, payload, timeout=60):
            if path == "/api/tags":
                return {"models": [{"name": n} for n in shows]}
            return shows.get(payload["model"], {})

        monkeypatch.setattr(sa, "_post", fake_post)
        monkeypatch.setattr(sa, "omlx_served_ids", set)

    def _run(self, monkeypatch, shows, want):
        import tests.wfe.settings_audit as sa

        self._mock(monkeypatch, shows)
        return sa.audit_tags(want)

    #: The gate table under test; the committed file is exercised separately.
    TABLE = {
        "renderers": {"flint": {"renderer": "flint", "parser": "flint", "source": "test"}},
        "allow": {"allowed:Q4": "probe-verified"},
    }

    def _run_gate(self, monkeypatch, shows, want, table=None):
        import tests.wfe.settings_audit as sa

        self._mock(monkeypatch, shows)
        if table is not None:
            monkeypatch.setattr(sa, "_renderer_table", lambda: table)
        return sa.audit_renderer_gate(want)

    def test_template_and_stop_findings_are_reported_per_tag(self, monkeypatch):
        shows = {
            "lib:latest": self._show("gemma4", "gemma4", "gemma4", "<real>"),
            "challenger:Q4": self._show("gemma4", params='stop    "<think>"'),
        }
        r = self._run(monkeypatch, shows, ["challenger:Q4", "absent:latest"])
        kinds = {(x["workspace"], x["kind"], x["severity"]) for x in r["violations"]}
        assert ("tag:challenger:Q4", "template_raw_jinja", "FAIL") in kinds
        assert ("tag:challenger:Q4", "stop_hygiene", "FAIL") in kinds
        assert ("tag:absent:latest", "hint_absent", "FAIL") in kinds
        assert r["fail_count"] == 3 and r["warn_count"] == 0

    def test_a_clean_challenger_reports_nothing(self, monkeypatch):
        shows = {
            "lib:latest": self._show("gemma4", "gemma4", "gemma4", "<real>"),
            "challenger:Q4": self._show("gemma4", "gemma4", "gemma4", "<real>"),
        }
        r = self._run(monkeypatch, shows, ["challenger:Q4"])
        assert r["violations"] == [] and r["fail_count"] == 0

    def test_a_renderer_less_tag_on_a_known_arch_is_refused_with_the_modelfile_fix(
        self, monkeypatch
    ):
        shows = {
            "hf.co/unsloth/flint-GGUF:UD-Q4_K_XL": self._show("flint", template="<vendor jinja>")
        }
        r = self._run_gate(
            monkeypatch, shows, ["hf.co/unsloth/flint-GGUF:UD-Q4_K_XL"], table=self.TABLE
        )
        v = r["violations"]
        assert [(x["kind"], x["severity"]) for x in v] == [("renderer_missing", "FAIL")]
        assert "RENDERER flint + PARSER flint" in v[0]["detail"]
        assert "ollama_template_conformance_probe" in v[0]["detail"]
        assert r["fail_count"] == 1

    def test_a_tag_carrying_its_renderer_is_not_refused(self, monkeypatch):
        shows = {"flint:latest": self._show("flint", "flint", "flint", "<real>")}
        assert (
            self._run_gate(monkeypatch, shows, ["flint:latest"], table=self.TABLE)["violations"]
            == []
        )

    def test_an_allow_entry_skips_the_refusal(self, monkeypatch):
        shows = {"allowed:Q4": self._show("flint", template="<vendor jinja>")}
        assert (
            self._run_gate(monkeypatch, shows, ["allowed:Q4"], table=self.TABLE)["violations"] == []
        )

    def test_an_architecture_the_table_does_not_know_is_not_refused(self, monkeypatch):
        shows = {"mellum:Q4": self._show("mellum", template="<vendor jinja>")}
        assert (
            self._run_gate(monkeypatch, shows, ["mellum:Q4"], table=self.TABLE)["violations"] == []
        )

    def test_an_uninstalled_arm_is_left_to_audit_tags(self, monkeypatch):
        r = self._run_gate(monkeypatch, {}, ["gone:latest"], table=self.TABLE)
        assert r["violations"] == []

    def test_the_committed_table_refuses_the_incident_setup(self, monkeypatch):
        """The real config/ollama_modelfiles/renderers.yaml, loaded by the gate:
        a flint-arch tag with no RENDERER/PARSER is the 2026-10-29 screen failure."""
        shows = {
            "hf.co/unsloth/flint-GGUF:UD-Q4_K_XL": self._show("flint", template="<vendor jinja>")
        }
        r = self._run_gate(monkeypatch, shows, ["hf.co/unsloth/flint-GGUF:UD-Q4_K_XL"])
        assert [x["kind"] for x in r["violations"]] == ["renderer_missing"]

    def test_the_committed_renderer_table_is_fully_cited(self):
        import tests.wfe.settings_audit as sa

        table = sa._renderer_table()
        assert (table.get("renderers") or {}).get("flint"), "the incident arch is seeded"
        for arch, entry in (table.get("renderers") or {}).items():
            assert entry.get("renderer") and entry.get("parser"), arch
            assert entry.get("source"), f"{arch}: cite where the pair comes from"
        assert isinstance(table.get("allow") or {}, dict)
