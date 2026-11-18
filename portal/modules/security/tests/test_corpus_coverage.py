"""Combined red-corpus coverage stays provenance- and mode-aware."""

from __future__ import annotations

from portal.modules.security.core import corpus_coverage as coverage


def test_source_contract_keeps_theory_out_of_capture_modes() -> None:
    contract = coverage.load_source_contract()
    assert contract["answer_key_visibility"] == "scorer_only"
    assert all(source["data_mode"] != "theory" for source in contract["sources"].values())
    assert contract["gates"]["allow_external_scenario_substitution"] is False
