from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_security_corpus_contract_separates_sources_and_hides_answer_keys():
    contract = yaml.safe_load((ROOT / "config" / "security_corpus.yaml").read_text())
    assert contract["answer_key_visibility"] == "scorer_only"
    assert contract["sources"]["portal_live"]["scenario_proof"] is True
    assert contract["sources"]["public_labeled"]["scenario_proof"] is False
    assert contract["gates"]["allow_external_scenario_substitution"] is False
    assert all(source["data_mode"] != "theory" for source in contract["sources"].values())
