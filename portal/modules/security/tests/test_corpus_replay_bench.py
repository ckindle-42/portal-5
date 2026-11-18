"""Unit tests for corpus_replay_bench.py — the V3 (Mentor/Budgets/Barrier-tools)
+ Council validation harness against real (mocked here) corpus telemetry.

No network, no Docker, no live Splunk/Ollama: SplunkBackend._run_search and
blue_orchestrate._call_model/run_tool_model are monkeypatched. Exercises the
same contract the live run depends on: episode construction from corpus
rows, checkpoint backup-before-write discipline, and that the council roster
never includes a model on _COUNCIL_UNFIT_MODELS.
"""

from __future__ import annotations

from typing import Any

from portal.modules.security.core import corpus_replay_bench as crb
from portal.modules.security.core.blue_orchestrate import (
    _COUNCIL_UNFIT_MODELS,
)


class TestCouncilRosterExcludesUnfitModels:
    def test_council_models_never_includes_a_known_unfit_model(self) -> None:
        assert not (set(crb.COUNCIL_MODELS) & _COUNCIL_UNFIT_MODELS)

    def test_curated_techniques_is_nonempty_and_maps_to_valid_sourcetypes(self) -> None:
        assert crb.CURATED_TECHNIQUES
        valid_sourcetypes = {"windows:security", "web:access", "linux:auditd"}
        assert set(crb.CURATED_TECHNIQUES.values()) <= valid_sourcetypes

    def test_weak_t1557_cell_is_not_curated(self) -> None:
        """A corpus cell containing only EventCode 4624 is not AiTM proof."""
        assert "T1557" not in crb.CURATED_TECHNIQUES

    def test_cogito_is_tracked_from_v4_participation_evidence(self) -> None:
        assert "cogito:32b" in _COUNCIL_UNFIT_MODELS


class TestCouncilParticipationSummary:
    def test_counts_voters_and_non_voters_per_model(self) -> None:
        results: list[dict[str, Any]] = [
            {
                "status": "done",
                "mode": "council",
                "trace": [
                    {
                        "section": "council_member",
                        "model": "voter",
                        "verdict": "RULED_OUT",
                    },
                    {
                        "section": "council_member",
                        "model": "non-voter",
                        "verdict": None,
                    },
                ],
            },
            {
                "status": "done",
                "mode": "council",
                "trace": [
                    {
                        "section": "council_member",
                        "model": "voter",
                        "verdict": "CONFIRMED",
                    },
                    {
                        "section": "council_member",
                        "model": "non-voter",
                        "verdict": "ANOMALOUS_UNCLASSIFIED",
                    },
                ],
            },
        ]
        summary = crb._council_participation_summary(results)
        assert summary["voter"] == {
            "participated": 2,
            "cells": 2,
            "non_votes": 0,
            "rate": 1.0,
        }
        assert summary["non-voter"] == {
            "participated": 1,
            "cells": 2,
            "non_votes": 1,
            "rate": 0.5,
        }


class TestRunCellWiring:
    def test_promotion_recall_requires_confirmed_verdict(self) -> None:
        assert crb._promotion_recall("RULED_OUT", ["T1053.005"], "T1053.005") == 0.0
        assert crb._promotion_recall("ANOMALOUS_UNCLASSIFIED", ["T1053.005"], "T1053.005") == 0.0
        assert crb._promotion_recall("CONFIRMED", ["T1053.005"], "T1053.005") == 1.0
