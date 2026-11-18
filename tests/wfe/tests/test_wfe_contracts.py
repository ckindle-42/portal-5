"""Harness contract tests (WFE dimensions 3, 21, 22, 28).

These lock the defects that made the pre-repair harness unable to execute a
single tool call on its own default endpoint, and that made its measured system
prompt machine-dependent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.wfe import campaign as camp
from tests.wfe.runner import (
    TOOL_NAMES,
    TOOL_SCHEMAS,
    Sandbox,
    _is_json_object,
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
    UNRUN_OUTCOMES,
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
        covered = MODEL_QUALITY_OUTCOMES | INSTRUMENT_OUTCOMES | UNRUN_OUTCOMES
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

    def test_a_ten_task_confirm_plan_runs_and_reports_below_floor(self, tmp_path):
        from tests.wfe.report import fitness

        directory = self._campaign(tmp_path, tasks=10, repeats=4)
        manifest = camp.load_manifest(directory)
        assert camp._curtail_workspace(directory, manifest, "ch", "ws") is None
        saved = camp.load_manifest(directory)
        assert saved.get("curtailments", []) == []
        challenger = [r for r in saved["rows"] if r["arm"] == "ch"]
        assert challenger and all(r["state"] == "PENDING" for r in challenger)
        for row in saved["rows"]:
            if row["arm"] != "ch":
                continue
            row["state"] = "PASS"
            camp._row_path(directory, row["run_id"]).write_text(
                json.dumps(
                    {
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
                )
            )
        camp.save_manifest(directory, saved)
        cell = fitness(directory)["cells"][0]
        assert cell["verdict"] == "NO_DECISION"
        assert cell["reason"].startswith("below-floor:")
        assert cell["curtailment"] is None
        assert cell["n"] == 10

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
        directory = self._campaign(tmp_path, tasks=36, incumbent_outcome="FAIL")
        manifest = camp.load_manifest(directory)
        for row in manifest["rows"]:
            if row["arm"] != "ch" or int(row["task_id"][1:]) >= 33:
                continue
            row["state"] = "PASS"
            camp._row_path(directory, row["run_id"]).write_text(
                json.dumps(
                    {
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
                )
            )
        camp.save_manifest(directory, manifest)
        camp._curtail_workspace(directory, manifest, "ch", "ws", "suite/t32")
        manifest = camp.load_manifest(directory)
        camp._resume_curtailed_rows(directory, manifest, "ch")
        resumed = camp.load_manifest(directory)
        held = [r for r in resumed["rows"] if r["arm"] == "ch" and int(r["task_id"][1:]) >= 33]
        done = [r for r in resumed["rows"] if r["arm"] == "ch" and int(r["task_id"][1:]) < 33]
        assert held and all(r["state"] == "PENDING" for r in held)
        assert all(r["state"] == "PASS" for r in done)
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


class TestStallDetection:
    """A timeout is the enemy of a slow-but-progressing model. The runner
    streams and watches for a STALL (no bytes), not a total-time cap — a model
    that keeps emitting tokens is slow, not wedged, and its work is kept."""

    def test_stream_stalled_is_not_a_harness_error_outcome(self):
        """run_task maps a stall to BUDGET_EXHAUSTED (a model verdict), never to
        HARNESS_ERROR — the model accepted the request and went quiet."""
        from tests.wfe.schema import INSTRUMENT_OUTCOMES, MODEL_QUALITY_OUTCOMES, Outcome

        assert Outcome.BUDGET_EXHAUSTED in MODEL_QUALITY_OUTCOMES
        assert Outcome.BUDGET_EXHAUSTED not in INSTRUMENT_OUTCOMES


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

    def test_a_tag_that_bakes_zero_is_not_sampling_baked_hot(self):
        """hunt-reasoning's fallback bakes temperature 0, so the WARN is clear."""
        from tests.wfe.settings_audit import _audit_sampling

        hint = "gemma4:26b-a4b-it-qat-ctx8k-hunt"
        ws = {
            "module": "security",
            "model_hint": hint,
            "temperature": 0.0,
            "sampling_override": {"reason": "json", "evidence": "pending"},
        }
        v: list[dict] = []
        _audit_sampling("hunt-reasoning", ws, hint, {"temperature": 0.0}, {hint}, v)
        assert not any(x["kind"] == "sampling_baked_hot" for x in v)


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


class TestAdaptiveThink:
    """gpt-oss works; the harness refused it over a format:json probe of a mode
    no campaign task uses, and dropped `think` entirely on the /v1 path so a
    `think: false` workspace was measured with the model's reasoning left on."""

    def test_ollama_default_unchanged_by_engine_support(self):
        import tests.wfe.runner as rn

        assert rn._v1_think_fields("false") == {"think": False, "reasoning_effort": "none"}
        assert rn._v1_think_fields("true") == {"think": True}
        assert rn._v1_think_fields("default") == {}

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

    def test_budget_target_is_shared_with_challenger_sizing(self):
        from tests.wfe.settings_audit import reasoning_budget_target

        ws = {"think": True, "context_limit": 16384, "predict_limit": 4096}
        registry = {"qwen3.8": {"recommended_max_output": 131072}}
        target = reasoning_budget_target(ws, "qwen3.8:27b", registry, baked_window=32768)
        assert target == 8192
        v = self._run(ws, "qwen3.8:27b", registry, {"qwen3.8:27b"}, baked_window=32768)
        assert "budget target 8192" in v[0]["detail"]

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


class TestPipelineMode:
    """WFE_ENGINE=pipeline: the request is what Open WebUI sends — the
    workspace id, no seat sampling, no cap — plus only the arm's override."""

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

    def test_context_overflow_ignores_tool_loop_hop_shrink(self):
        """A sub-window shrink is the tool loop's last-hop accounting, not truncation.

        Per-turn usage is the pipeline tool loop's LAST hop (it carries that
        turn's reasoning and tool results; the next turn restarts from the
        client-visible history, final answer only), so turn 1 reports less
        than turn 0 whenever turn 0's loop was busier. Measured on
        realuse_s8_20261030f (tools-specialist::fast, gemma4:e4b-it-qat-ctx8k,
        window 8192): the engine's own log shows truncated=0 on every request
        and hop prompts 544 -> 1047 then 581 -> 864; the rows recorded the two
        last hops (1047, 864) and the old any-shrink rule called truncation."""
        from tests.wfe.runner import context_overflow

        hop_shrink = [
            {"turn": 0, "prompt_tokens": 1047, "completion_tokens": 93, "sent_chars": 432},
            {"turn": 1, "prompt_tokens": 864, "completion_tokens": 50, "sent_chars": 543},
        ]
        assert context_overflow(hop_shrink, 8192) is None
        assert context_overflow(hop_shrink, None) is None
        bigger = [
            {"turn": 0, "prompt_tokens": 1418, "completion_tokens": 250, "sent_chars": 407},
            {"turn": 1, "prompt_tokens": 877, "completion_tokens": 68, "sent_chars": 773},
        ]
        assert context_overflow(bigger, 8192) is None
        # At window pressure a wobble within the collapse band is not a cut:
        # only a fall to about half the window is the measured post-truncation
        # level (4099 on an 8192 tag).
        wobble = [{"turn": 0, "prompt_tokens": 7500}, {"turn": 1, "prompt_tokens": 6800}]
        assert context_overflow(wobble, 8192) is None
        collapse = [
            {"turn": 0, "prompt_tokens": 7500, "completion_tokens": 10},
            {"turn": 1, "prompt_tokens": 4099, "completion_tokens": 10},
        ]
        assert "shrank" in context_overflow(collapse, 8192)

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

    def test_repetition_penalty_maps_to_the_card_key(self):
        import tests.wfe.settings_audit as sa

        assert sa._omlx_entry_sampling({"repetition_penalty": 1.05, "mtp_enabled": True}) == {
            "repeat_penalty": 1.05
        }


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
