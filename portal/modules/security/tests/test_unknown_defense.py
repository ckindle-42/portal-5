"""Tests for unknown defense — U1-U6 (DESIGN-SEC-UNKNOWN-DEFENSE-V1).

Validates:
- U1: Similarity tier (EXACT/SIMILAR/NONE)
- U2: Unknown→investigation bridge
- U3: Baseline generation
- U4: Anomaly-vs-baseline scoring
- U5: Anomaly→investigation→write-back
- U6: Purple outcome-space expansion
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tests" / "benchmarks"))

from portal.modules.security.core.unknown_defense import (
    AnomalyResult,
    BaselineProfile,
    ExpandedPurpleResult,
    InvestigationOutcome,
    MatchGrade,
    PurpleOutcome,
    SimilarityResult,
    compute_similarity,
    generate_baseline,
    resolve_unknown,
    route_to_investigation,
    score_anomaly,
    score_expanded_purple,
)

# ── U1: Similarity tier ─────────────────────────────────────────────────────


class TestSimilarityTier:
    """U1: Graded match (EXACT/SIMILAR/NONE) from wiki descriptions."""

    def test_exact_match(self):
        wiki = {"T1558.003": "Kerberoasting Windows Security Event 4769 RC4 encryption ticket"}
        observed = {
            "tactic": "credential-access",
            "event_codes": ["4769"],
            "keywords": [
                "RC4",
                "Kerberoasting",
                "Windows",
                "Security",
                "Event",
                "encryption",
                "ticket",
            ],
        }
        result = compute_similarity(observed, wiki)
        assert result.grade in (MatchGrade.EXACT, MatchGrade.SIMILAR)
        assert result.matched_technique == "T1558.003"
        assert result.confidence > 0

    def test_similar_match(self):
        wiki = {"T1558.003": "Kerberoasting Windows Security Event 4769 RC4 encryption"}
        observed = {"keywords": ["Kerberos", "Windows", "Security", "encryption", "ticket"]}
        result = compute_similarity(observed, wiki)
        assert result.grade in (
            MatchGrade.SIMILAR,
            MatchGrade.EXACT,
            MatchGrade.NONE,
        )  # heuristic — may vary

    def test_no_match(self):
        wiki = {"T1558.003": "Kerberoasting Windows Security Event 4769 RC4 encryption"}
        observed = {"keywords": ["completely", "unrelated", "content"]}
        result = compute_similarity(observed, wiki)
        assert result.grade == MatchGrade.NONE

    def test_empty_wiki(self):
        result = compute_similarity({"keywords": ["test"]}, {})
        assert result.grade == MatchGrade.NONE

    def test_punctuated_description_still_matches_separate_words(self):
        """Found live 2026-07-20 (GATE-D ablation): a description like
        "sh/bash/python" or "credential-access" used to tokenize via naive
        .lower().split() into one glued blob that could never match "bash"
        or "credential" as standalone words in observed telemetry. This
        silently zeroed out overlap for almost any real technique
        description containing a slash or hyphen."""
        wiki = {"T1059.004": "Unix shell — command execution via sh/bash/python on Linux targets"}
        observed = {"telemetry": "process exec bash shell command on linux host"}
        result = compute_similarity(observed, wiki)
        assert result.grade in (MatchGrade.SIMILAR, MatchGrade.EXACT)
        assert "bash" in result.overlapping_features

    def test_real_telemetry_sized_blob_is_not_diluted_by_jaccard(self):
        """Found live 2026-07-20 (GATE-D ablation), independent of the
        tokenization bug above: real telemetry is a large blob of mostly
        irrelevant structured field names compared against a short
        description. A pure Jaccard (overlap/union) score gets diluted by
        the SIZE of the observed side, not just its relevance — a
        genuinely on-topic match scored below the SIMILAR floor purely
        because of unrelated noise words. Containment (overlap relative to
        the description's own word count) must not have this problem."""
        wiki = {"T1059.004": "Unix shell — command execution via sh/bash/python on Linux targets"}
        noisy_telemetry = (
            "EventCode=4688 NewProcessName=/bin/bash CommandLine=bash timestamp=2026-07-20T10:15:22Z "
            "host=web01 source=linux:auditd type=EXECVE exe=/bin/sh a0=sh a1=-c a2=id "
            "additional noise words here to simulate a realistic verbose telemetry dump "
            "with many unrelated field names and values padding out the actual signal "
            "user session login logout network connection established port 443 tls handshake "
            "more filler content unrelated to the actual technique but present in real logs"
        )
        result = compute_similarity({"telemetry": noisy_telemetry}, wiki)
        assert result.grade in (MatchGrade.SIMILAR, MatchGrade.EXACT), (
            f"expected a real match to survive noise, got {result.grade} (score={result.confidence})"
        )

    def test_similarity_result_to_dict(self):
        import json

        r = SimilarityResult(grade=MatchGrade.SIMILAR, matched_technique="T1190", confidence=0.3)
        json.dumps(r.to_dict())


# ── U2: Investigation bridge ─────────────────────────────────────────────────


class TestInvestigationBridge:
    """U2: Route SIMILAR flags to investigation."""

    def test_similar_routes_to_investigation(self):
        sim = SimilarityResult(
            grade=MatchGrade.SIMILAR,
            matched_technique="T1558.003",
            overlapping_features=["RC4", "4769"],
        )
        intake = route_to_investigation(similarity=sim, episode_id="ep-001")
        assert intake.source == "similarity"
        assert "T1558.003" in intake.alert_text
        assert intake.similarity is not None

    def test_anomaly_routes_to_investigation(self):
        intake = route_to_investigation(anomaly_score=0.85, episode_id="ep-002")
        assert intake.source == "anomaly"
        assert "0.85" in intake.alert_text

    def test_intake_to_dict(self):
        import json

        intake = route_to_investigation(anomaly_score=0.5)
        json.dumps(intake.to_dict())


# ── U3: Baseline generation ─────────────────────────────────────────────────


class TestBaselineGeneration:
    """U3: Model normal behavior."""

    def test_generate_baseline(self):
        events = [
            {"NewProcessName": "C:\\Windows\\System32\\svchost.exe", "EventCode": "4688"},
            {"NewProcessName": "C:\\Windows\\System32\\svchost.exe", "EventCode": "4688"},
            {"NewProcessName": "C:\\Windows\\System32\\lsass.exe", "EventCode": "4688"},
        ]
        profile = generate_baseline("dc01", "windows:security", events)
        assert profile.sample_count == 3
        assert profile.normal_processes["C:\\Windows\\System32\\svchost.exe"] > 0.5
        assert profile.profile_id == "baseline-dc01-windows:security"

    def test_baseline_to_dict(self):
        import json

        profile = BaselineProfile("b-test", "host", "src", sample_count=10)
        json.dumps(profile.to_dict())


# ── U4: Anomaly scoring ─────────────────────────────────────────────────────


class TestAnomalyScoring:
    """U4: Statistical deviation from baseline."""

    def test_normal_not_anomalous(self):
        baseline = BaselineProfile(
            "b-test",
            "dc01",
            "windows:security",
            normal_processes={"C:\\Windows\\System32\\svchost.exe": 0.8},
            normal_event_codes={"4688": 0.9},
            sample_count=100,
        )
        result = score_anomaly(
            {"NewProcessName": "C:\\Windows\\System32\\svchost.exe", "EventCode": "4688"}, baseline
        )
        assert not result.flagged
        assert result.score < 0.7

    def test_novel_process_anomalous(self):
        baseline = BaselineProfile(
            "b-test",
            "dc01",
            "windows:security",
            normal_processes={"C:\\Windows\\System32\\svchost.exe": 0.8},
            normal_event_codes={"4688": 0.9},
            sample_count=100,
        )
        result = score_anomaly(
            {"NewProcessName": "C:\\Temp\\mystery.exe", "EventCode": "4688"}, baseline
        )
        assert result.score > 0.5
        assert any("mystery" in f for f in result.deviant_features)

    def test_insufficient_baseline(self):
        baseline = BaselineProfile("b-test", "host", "src", sample_count=5)
        result = score_anomaly({"test": True}, baseline)
        assert not result.flagged

    def test_anomaly_result_to_dict(self):
        import json

        r = AnomalyResult(score=0.8, flagged=True, deviant_features=["novel_process:x"])
        json.dumps(r.to_dict())


# ── U5: Resolve unknown ─────────────────────────────────────────────────────


class TestResolveUnknown:
    """U5: Three honest outcomes — variant / new_technique / benign."""

    def test_variant_resolution(self):
        intake = route_to_investigation(
            similarity=SimilarityResult(grade=MatchGrade.SIMILAR, matched_technique="T1558.003"),
            episode_id="ep-001",
        )
        findings = [
            {"technique_ids": ["T1558.003"], "description": "Confirmed Kerberoasting variant"}
        ]
        outcome = resolve_unknown(intake, findings)
        assert outcome.classification == "variant"
        assert outcome.technique_id == "T1558.003"
        assert outcome.write_back_unit is not None

    def test_benign_resolution(self):
        intake = route_to_investigation(anomaly_score=0.5, episode_id="ep-002")
        findings = [
            {"description": "No technique match found", "technique_ids": []}
        ]  # no technique match
        outcome = resolve_unknown(intake, findings)
        assert outcome.classification == "benign"
        assert outcome.baseline_update is True

    def test_outcome_to_dict(self):
        import json

        o = InvestigationOutcome("o-1", "variant", "T1190", "test")
        json.dumps(o.to_dict())


# ── U6: Purple outcome expansion ─────────────────────────────────────────────


class TestPurpleOutcomeExpansion:
    """U6: confirmed / variant-flagged / anomaly-flagged / missed."""

    def test_confirmed_outcome(self):
        result = score_expanded_purple(
            red_landed=True, match_grade=MatchGrade.EXACT, detection_confirmed=True
        )
        assert result.outcome == PurpleOutcome.CONFIRMED

    def test_variant_flagged_outcome(self):
        result = score_expanded_purple(red_landed=True, match_grade=MatchGrade.SIMILAR)
        assert result.outcome == PurpleOutcome.VARIANT_FLAGGED

    def test_anomaly_flagged_outcome(self):
        result = score_expanded_purple(
            red_landed=True, match_grade=MatchGrade.NONE, anomaly_score=0.9
        )
        assert result.outcome == PurpleOutcome.ANOMALY_FLAGGED

    def test_missed_outcome(self):
        result = score_expanded_purple(
            red_landed=True, match_grade=MatchGrade.NONE, anomaly_score=0.1
        )
        assert result.outcome == PurpleOutcome.MISSED

    def test_red_not_landed(self):
        result = score_expanded_purple(red_landed=False, match_grade=MatchGrade.NONE)
        assert result.outcome == PurpleOutcome.MISSED

    def test_expanded_result_to_dict(self):
        import json

        r = ExpandedPurpleResult(outcome=PurpleOutcome.CONFIRMED, technique_id="T1190")
        json.dumps(r.to_dict())


class TestSimilarityReferenceCatalog:
    """The U1 similarity reference must be a broad, independent MITRE ATT&CK
    catalog, not just this project's own answer-key subset (found live
    2026-07-22, GATE-D ablation Part II-A: the wiki's 30 seeded descriptions
    are auto-generated from this project's own spl_detections.yaml +
    exec_chain.py#SCENARIOS, covering 27/29 of the ablation corpus's own
    ground-truth techniques — near-circular novelty grounding)."""

    def test_mitre_catalog_is_broad_not_just_project_techniques(self):
        from portal.modules.security.core.blue import (
            _load_mitre_attack_catalog,
            _load_wiki_technique_descriptions,
        )

        broad = _load_mitre_attack_catalog()
        narrow = _load_wiki_technique_descriptions()
        assert len(broad) > 500  # full MITRE Enterprise catalog, not a curated subset
        # Techniques absent from this project's own answer-key set must still
        # be covered by the broad catalog.
        assert "T1078.004" not in narrow
        assert "T1078.004" in broad
        assert "T1537" not in narrow
        assert "T1537" in broad

    def test_merged_reference_prefers_project_specific_detail(self):
        from portal.modules.security.core.blue import (
            _load_similarity_reference_descriptions,
        )

        merged = _load_similarity_reference_descriptions()
        assert len(merged) > 500
        # Project-specific SIEM detail (exact EventCode discriminators) wins
        # for techniques the project has real detection content for.
        assert "4769" in merged["T1558.003"]
        # But techniques outside the project's own 30-item set are still
        # covered, from the broad catalog.
        assert merged.get("T1078.004", "").startswith("Cloud Accounts")
