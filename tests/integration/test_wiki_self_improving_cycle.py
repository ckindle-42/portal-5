"""Historical wiki writeback integration after P7 growth-loop retirement.

The former growth-loop hunting driver is replaced by Bully LOOP/HND and no
longer writes detections into the wiki. This retained historical-read test
keeps the independent investigation, bench, and gap adapters honest: their
proposals remain provenance-bearing and operator-confirmed.
"""

from portal.platform.wiki.adapters.writeback_bench import writeback_bench_result
from portal.platform.wiki.adapters.writeback_gap import writeback_gap_resolution
from portal.platform.wiki.adapters.writeback_investigation import (
    writeback_investigation_findings,
)
from portal.platform.wiki.store import reset_canonical_dir, set_canonical_dir
from portal.platform.wiki.writeback import list_proposed, reset_proposed_dir, set_proposed_dir


def test_retained_writeback_adapters_produce_provenance(tmp_path):
    set_proposed_dir(tmp_path / "proposed")
    set_canonical_dir(tmp_path / "canonical")
    try:
        writeback_investigation_findings(
            "case-test",
            [
                {
                    "technique_ids": ["T1190"],
                    "description": "test",
                    "evidence_refs": ["ev-001"],
                    "confidence": 0.9,
                }
            ],
        )
        writeback_bench_result("test-model", "exploit", "keep")
        writeback_gap_resolution("T1190", "COVERED")

        proposed = list_proposed()
        assert len(proposed) == 3
        assert all(unit.sources for unit in proposed)
    finally:
        reset_proposed_dir()
        reset_canonical_dir()
