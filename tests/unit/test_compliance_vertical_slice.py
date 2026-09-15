"""END_TO_END Phase 7 — the compound CIP-007 R2 analysis plan.

Under test: one shared immutable context (source/corpus/index/both clocks/
model config pinned once), a deterministic seven-operation plan that keyword
routing cannot drop components from, and plan execution that records every
operation id and refuses to compose answers from steps that did not run.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core import vertical_slice as vs

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

LIVE_STORE = pytest.importorskip(
    "portal.modules.compliance.core.repository"
)  # the plan pins the live corpus snapshot

REQUIREMENT = "CIP-007-6 R2"


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    return vs.build_context(REQUIREMENT, valid_at="2026-09-14")


class TestSharedContext:
    def test_context_pins_all_four_parts_and_bundles(self, ctx):
        assert ctx.part_ids == [
            "CIP-007-6 R2 Part 2.1",
            "CIP-007-6 R2 Part 2.2",
            "CIP-007-6 R2 Part 2.3",
            "CIP-007-6 R2 Part 2.4",
        ]
        assert set(ctx.bundle_fingerprints) == set(ctx.part_ids)
        assert len(set(ctx.bundle_fingerprints.values())) == 4  # per-Part bundles

    def test_one_snapshot_and_clocks_for_everything(self, ctx):
        assert ctx.snapshot_fingerprint
        assert ctx.snapshot_id.startswith("snap-")
        assert ctx.valid_at == "2026-09-14"
        assert ctx.revision_before == "CIP-007-6" and ctx.revision_after == "CIP-007-7.1"
        # the production reader identity is recorded, never assumed
        assert "seats" in ctx.model_config

    def test_defective_bundle_never_builds_a_plan(self, monkeypatch):
        from portal.modules.compliance.core.regulatory_bundle import SourceBundleIncompleteError

        def _resolve(requirement_id, **kwargs):
            raise SourceBundleIncompleteError(
                ref=requirement_id, failures=[{"component": "measures", "detail": "missing"}]
            )

        monkeypatch.setattr(vs, "resolve_part_ids", lambda req: ["X R1 Part 1.1"])
        monkeypatch.setattr(
            "portal.modules.compliance.core.assessment_source.resolve_governing_bundle",
            _resolve,
        )
        monkeypatch.setattr(
            "portal.modules.compliance.core.assessment_source.build_corpus_snapshot",
            lambda kb_id: type(
                "S", (), {"fingerprint": "f", "snapshot_id": "s", "index_generation": "i"}
            )(),
        )
        with pytest.raises(SourceBundleIncompleteError):
            vs.build_context("X R1", valid_at="2026-09-14")


class TestCompoundPlan:
    def test_dry_run_contains_all_seven_operations(self, ctx):
        plan = vs.dry_run(ctx)
        assert plan["n_operations"] == 7
        ops = [op["op"] for op in plan["operations"]]
        assert ops == [
            "requirement_duties",
            "implementing_clauses",
            "alignment",
            "gaps",
            "evidence_connections",
            "temporal_diff",
            "scenario",
        ]
        # every operation carries the SAME shared context ids
        for op in plan["operations"]:
            assert op["args"]["snapshot_id"] == ctx.snapshot_id
            assert op["args"]["snapshot_fingerprint"] == ctx.snapshot_fingerprint
            assert op["args"]["valid_at"] == ctx.valid_at
            assert op["args"]["known_at"] == ctx.known_at
            assert op["args"]["kb_id"] == ctx.kb_id

    def test_plan_is_deterministic_no_keyword_routing(self, ctx):
        """The plan is identical regardless of any free-text question phrasing
        — routing cannot drop alignment/gap/trace/temporal/impact/scenario."""
        a = [op.to_dict() for op in vs.seven_question_plan(ctx)]
        b = [op.to_dict() for op in vs.seven_question_plan(ctx)]
        assert a == b
        assert not any("route" in op["op"] or "intent" in op["op"] for op in a)

    def test_scenario_op_supplies_overlay_at_execution(self, ctx):
        plan = vs.seven_question_plan(ctx)
        scenario = plan[-1]
        assert scenario.op == "scenario"
        assert scenario.args["overlay"] is None


class TestExecutePlan:
    def test_missing_implementation_is_recorded_never_composed(self, ctx):
        result = vs.execute_plan(
            ctx,
            op_impls={"requirement_duties": lambda **kwargs: {"duties": 4}},
            run_id="run-x",
        )
        ops = result["operations"]
        assert ops[0]["ran"] is True
        assert "error" in ops[1] and "no implementation" in ops[1]["error"]
        assert result["answers"] == {"requirement_duties": {"duties": 4}}
        assert result["run_id"] == "run-x"

    def test_every_result_carries_operation_ids(self, ctx):
        impls = {
            name: (lambda **kwargs: {"ok": True})
            for name in (
                "requirement_duties",
                "implementing_clauses",
                "alignment",
                "gaps",
                "evidence_connections",
                "temporal_diff",
                "scenario",
            )
        }
        result = vs.execute_plan(ctx, op_impls=impls, run_id="run-y")
        assert len(result["answers"]) == 7
        for index, op in enumerate(result["operations"]):
            assert op["operation_id"] == f"run-y#{index + 1}:{op['op']}"
            assert op["ran"] is True

    def test_scenario_overlay_forwarded(self, ctx):
        seen = {}

        def scenario(**kwargs):
            seen.update(kwargs)
            return {"reassessed": True}

        vs.execute_plan(
            ctx,
            op_impls={"scenario": scenario},
            run_id="run-z",
            scenario_overlay={"edits": [{"operation": "ADD"}]},
        )
        assert seen["overlay"] == {"edits": [{"operation": "ADD"}]}
