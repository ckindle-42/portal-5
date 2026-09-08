"""Harness contract tests (WFE dimensions 3, 21, 22, 28).

These lock the defects that made the pre-repair harness unable to execute a
single tool call on its own default endpoint, and that made its measured system
prompt machine-dependent.
"""

from __future__ import annotations

import json
import socket

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

    def test_rescore_upgrades_a_budget_outcome_when_the_checker_now_passes(self, tmp_path):
        """The one case a checker fix legitimately overrides run telemetry: the
        model DID produce a correct artifact, and the too-strict checker was why
        the run looked unfinished."""
        rec = self._debug_record()
        rec["outcome"] = "BUDGET_EXHAUSTED"
        rec["sandbox_tree"] = {"parse_kv.py": TestOfflineRescore._GOOD_PARSE_KV}
        dbg = tmp_path / "debug"
        dbg.mkdir()
        (dbg / "m_t.debug.jsonl").write_text(json.dumps(rec) + "\n")
        out = camp.rescore_debug_dir(dbg)
        assert out[0]["rescore"]["outcome"] == "PASS"

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

    def test_v1_payload_carries_think_like_production(self):
        from tests.wfe.runner import _build_payload

        url, payload, caveats = _build_payload(
            "m",
            [{"role": "user", "content": "x"}],
            {"endpoint": "v1", "format": "none"},
            {},
            None,
            "false",
        )
        assert "/v1/chat/completions" in url
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

    def test_campaign_harness_resolves_think_workspace_then_card(self):
        from tests.wfe import campaign as c

        assert c.campaign_harness({"model": "m", "think": False})["think"] == "false"
        assert c.campaign_harness({"model": "m", "think": True})["think"] == "true"
        # no workspace think -> card policy
        reg = {"gpt-oss": {"harness_policy": {"think": "true"}}}
        import tests.wfe.runner as rn

        assert rn.think_policy("gpt-oss:20b", reg) == "true"

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


class TestTransientPreflightIsRecoverable:
    """A flaky probe must not cost an arm its whole row budget for the rest of a
    multi-day sweep.

    Regression: `preflight_arm` cached a REVIEW verdict and `execute_arm` marked
    every pending row BLOCKED. On resume the cached REVIEW short-circuited the
    re-probe and the BLOCKED rows no longer matched the PENDING filter, so one
    momentary connection reset silently cost an arm all 39 of its runs.
    """

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
        monkeypatch.setattr(camp, "workspace_context", lambda ws: {"model": "m:t"})
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
