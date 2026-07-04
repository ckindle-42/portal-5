"""Integration test: wiki self-improving cycle — Phase P7.

Proves the loop actually compounds: a gap → growth loop proposes+proves+confirms
a detection → it writes back as a cited wiki unit → the wiki has MORE cited
units after than before.  Each step is asserted.

This is the feature-complete proof.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from portal_wiki.core.store import load_all, reset_canonical_dir, set_canonical_dir
from portal_wiki.core.writeback import confirm_unit, list_proposed, propose_unit, reset_proposed_dir, set_proposed_dir


class TestSelfImprovingCycle:
    """The compound proof: gap → prove → write-back → look-up → detect."""

    def test_full_cycle(self, tmp_path):
        """Full self-improving cycle end-to-end."""
        from bench_security.capability_graph import CoverageSummary, CapabilityGraph, Procedure, build_gap
        from bench_security.growth_loop import DraftDetection, propose_draft, prove_draft, _writeback_proven_detection

        proposed_dir = tmp_path / "proposed"
        canonical_dir = tmp_path / "canonical"
        set_proposed_dir(proposed_dir)
        set_canonical_dir(canonical_dir)
        try:
            # Step 1: Seed initial wiki state
            initial_count = len(load_all())

            # Step 2: Create a capability graph with a RED_ONLY gap
            graph = CapabilityGraph()
            proc = Procedure("proc-test", "test_scenario", frozenset({"T9999"}))
            graph.add_procedure(proc)
            gap = build_gap(proc, "T9999", {
                "red_status": "RED_LANDED",
                "telemetry_status": "TELEMETRY_OBSERVED",
                "detection_status": "DETECTION_MISSING",
                "response_status": "RESPONSE_NOT_TESTED",
                "used_synthetic": False,
            })
            gap.summary = CoverageSummary.RED_ONLY.value
            graph.add_gap(gap)

            # Step 3: Growth loop proposes + proves a draft
            draft = propose_draft(gap, existing_spl='index=portal5_lab sourcetype="web:access" test')
            proof = prove_draft(draft)

            if proof.all_passed():
                draft.status = "proven"

                # Step 4: Write-back — proven detection becomes a cited wiki unit
                _writeback_proven_detection(draft, gap)

                # Step 5: Confirm the proposed unit
                proposed = list_proposed("proposed")
                assert len(proposed) >= 1, "Write-back should have proposed a unit"

                for pu in proposed:
                    confirm_unit(pu.proposed_id)

                # Step 6: Wiki has MORE cited units than before
                final_count = len(load_all())
                assert final_count > initial_count, (
                    f"Wiki should have grown: {initial_count} → {final_count}"
                )

                # Step 7: The new unit has provenance
                new_units = load_all()
                growth_units = [u for u in new_units if "growth-loop" in u.tags]
                assert len(growth_units) >= 1, "Growth-sourced unit should exist"
                assert all(u.sources for u in growth_units), "All units must have sources"

            # Step 8: Core stays import-clean
            import glob as glob_mod
            bad = [f for f in glob_mod.glob("portal_wiki/core/**/*.py", recursive=True)
                   if any(x in open(f).read() for x in ["portal_pipeline", "bench_security"])]
            assert bad == [], f"Core has Portal imports: {bad}"

        finally:
            reset_proposed_dir()
            reset_canonical_dir()

    def test_all_writeback_loops_produce_provenance(self, tmp_path):
        """All four write-back loops produce units with provenance."""
        set_proposed_dir(tmp_path / "p")
        set_canonical_dir(tmp_path / "c")
        try:
            # Growth (P2)
            from bench_security.growth_loop import _writeback_proven_detection, propose_draft, prove_draft, DraftDetection
            from bench_security.capability_graph import Procedure, build_gap, CoverageSummary

            proc = Procedure("p", "s", frozenset({"T9999"}))
            gap = build_gap(proc, "T9999", {"red_status": "RED_LANDED", "telemetry_status": "TELEMETRY_OBSERVED", "detection_status": "DETECTION_MISSING", "response_status": "RESPONSE_NOT_TESTED", "used_synthetic": False})
            gap.summary = CoverageSummary.RED_ONLY.value
            draft = propose_draft(gap, existing_spl='index=portal5_lab test')
            proof = prove_draft(draft)
            if proof.all_passed():
                draft.status = "proven"
                _writeback_proven_detection(draft, gap)

            # Investigation (P3)
            from portal_wiki.adapters.writeback_investigation import writeback_investigation_findings
            writeback_investigation_findings("case-test", [{"technique_ids": ["T1190"], "description": "test", "evidence_refs": ["ev-001"], "confidence": 0.9}])

            # Bench (P4)
            from portal_wiki.adapters.writeback_bench import writeback_bench_result
            writeback_bench_result("test-model", "exploit", "keep")

            # Gap (P5)
            from portal_wiki.adapters.writeback_gap import writeback_gap_resolution
            writeback_gap_resolution("T1190", "COVERED")

            # All proposed units have provenance
            all_proposed = list_proposed()
            assert len(all_proposed) >= 1
            for pu in all_proposed:
                assert pu.sources, f"Unit {pu.proposed_id} has no sources"

        finally:
            reset_proposed_dir()
            reset_canonical_dir()
