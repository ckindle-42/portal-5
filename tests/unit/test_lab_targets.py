"""Unit tests for lab targets catalog (Phase 0b)."""

from __future__ import annotations

import yaml


class TestLabTargetsCatalog:
    def test_catalog_parses(self):
        data = yaml.safe_load(open("config/lab_targets.yaml"))
        assert "targets" in data
        assert len(data["targets"]) >= 7

    def test_every_entry_has_source(self):
        data = yaml.safe_load(open("config/lab_targets.yaml"))
        for t in data["targets"]:
            assert "source" in t, f"entry {t.get('id', '?')} missing source"

    def test_preexisting_entries_marked(self):
        data = yaml.safe_load(open("config/lab_targets.yaml"))
        preexisting = [t for t in data["targets"] if t.get("preexisting")]
        assert len(preexisting) >= 4


class TestChallengeClasses:
    def test_classes_parse(self):
        data = yaml.safe_load(open("config/challenge_classes.yaml"))
        assert "classes" in data
        assert len(data["classes"]) >= 40  # expanded from 12

    def test_no_orphan_classes(self):
        data = yaml.safe_load(open("config/challenge_classes.yaml"))
        for c in data["classes"]:
            has_vulhub = len(c.get("vulhub", [])) > 0
            has_purpose = c.get("purpose_built") is not None
            assert has_vulhub or has_purpose, (
                f"class {c['id']} has no vulhub path or purpose_built dir"
            )

    def test_every_class_has_ground_truth(self):
        data = yaml.safe_load(open("config/challenge_classes.yaml"))
        for c in data["classes"]:
            assert "ground_truth" in c, f"class {c['id']} missing ground_truth"

    def test_every_class_has_source(self):
        data = yaml.safe_load(open("config/challenge_classes.yaml"))
        for c in data["classes"]:
            assert "source" in c, f"class {c['id']} missing provenance source"

    def test_ability_port_imports(self):
        from tests.benchmarks.bench_security.ability_port import ability_coverage

        cov = ability_coverage()
        assert cov["challenge_classes"] >= 40
        assert cov["ptai_probes_ported"] >= 20
        assert cov["vulhub_families_mapped"] >= 7
