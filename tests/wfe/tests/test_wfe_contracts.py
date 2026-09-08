"""Harness contract tests (WFE dimensions 3, 21, 22, 28).

These lock the defects that made the pre-repair harness unable to execute a
single tool call on its own default endpoint, and that made its measured system
prompt machine-dependent.
"""

from __future__ import annotations

import json

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
    Outcome,
    intervals_overlap,
    wilson,
)


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
