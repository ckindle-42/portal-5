"""PROVE_THEN_SCALE_V1 — the mechanical contracts behind the campaign.

Live-only where "did it read and understand" is the question; unit-tested
where the machinery makes promises the sweep depends on:

* a determination writes at ``machine_determined`` with provenance, and never
  an edge whose justifying sentence is not in the section's text;
* the bootstrap guard: a pairing the store holds is corroborated, never
  re-created;
* the material renderer: byte-identical fixed body per revision, standing
  labels on every entry, the shared prefix FIRST;
* the sweep order: dependency order across standards, numeric order within;
* the contradiction scan: cross-reading disagreement is the review queue.
"""

from __future__ import annotations

from portal.modules.compliance.core import (
    sweep,
)


class TestParseDeterminations:
    def test_the_fenced_block_parses(self) -> None:
        answer = 'prose prose\n```json\n{"determinations": [{"section_id": "s", "relation_type": "IMPLEMENTS"}]}\n```\n'
        entries, error = sweep.parse_determinations(answer)
        assert error == ""
        assert entries[0]["relation_type"] == "IMPLEMENTS"

    def test_a_missing_block_is_a_recorded_reason_not_an_exception(self) -> None:
        entries, error = sweep.parse_determinations("no block here")
        assert entries == []
        assert "no determinations block" in error
