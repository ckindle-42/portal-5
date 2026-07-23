"""Tests for cite-or-drop FP control — Phase B.

Validates:
- Reported technique with no telemetry evidence is dropped
- The gate is LABEL-BLIND (2026-07-23 design review): it never sees ground
  truth, so a correct label faces exactly the same evidence bar as a wrong
  one, and the gate can run in production where no answer key exists
- A claim is kept only when its own cited evidence is grounded, its ID
  appears in telemetry, or a known event-ID marker is present
- Trigger-supplied tokens (host/scenario names) never count as citations
- False-positive count decreases after cite-or-drop
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tests" / "benchmarks"))

from portal.modules.security.core.blue import _cite_or_drop


class TestCiteOrDrop:
    """Cite-or-drop: never-invent applied to blue's own output."""

    def test_keeps_technique_with_grounded_evidence(self):
        """A technique whose cited evidence is actually grounded in real
        telemetry is kept."""
        reported = [{"technique_id": "T1558.003", "evidence": "EventCode=4769 seen"}]
        telemetry = {"T1558.003": {"telemetry": "EventCode=4769 some data", "source": "live"}}
        result = _cite_or_drop(reported, telemetry)
        assert len(result) == 1
        assert result[0]["technique_id"] == "T1558.003"

    def test_drops_correctly_labeled_technique_with_fabricated_evidence(self):
        """A CORE regression test: a technique whose OWN cited evidence is
        fabricated (never appears in real telemetry) must be dropped — the
        label being the corpus's right answer buys it nothing, because the
        gate never sees the answer key.

        Found live 2026-07-22 (GATE-D ablation Part II-A): a prior
        "matches ground truth -> keep" exemption let `vuln_fastjson_rce`'s
        Expert cite a fabricated log line ("GET /api/v1/data?param=..." /
        source_ip=203.0.113.45) for T1190 — neither string appears anywhere
        in the real telemetry, which contains only benign Tomcat startup
        logs and plain GET / 200s — and score a clean HIT purely because the
        label happened to be correct."""
        reported = [
            {
                "technique_id": "T1190",
                "evidence": '"GET /api/v1/data?param=abc HTTP/1.1" 200 1024; source_ip=203.0.113.45',
            }
        ]
        telemetry = {
            "web:access": {
                "telemetry": 'GET / HTTP/1.1" 200 11250 (benign startup traffic only)',
                "source": "live",
            }
        }
        result = _cite_or_drop(reported, telemetry)
        assert result == []

    def test_drops_hallucinated_technique(self):
        """Technique with no evidence is dropped (FP control)."""
        reported = [
            {"technique_id": "T1558.003", "evidence": "EventCode=4769 seen"},  # grounded
            {"technique_id": "T1078.001", "evidence": "nothing real"},  # hallucinated
        ]
        telemetry = {"T1558.003": {"telemetry": "EventCode=4769 some data", "source": "live"}}
        result = _cite_or_drop(reported, telemetry)
        assert len(result) == 1
        assert result[0]["technique_id"] == "T1558.003"

    def test_keeps_technique_with_telemetry_match(self):
        """Technique ID present in telemetry text is kept (this path doesn't
        require a per-detection evidence field — it checks the technique ID
        itself against the whole telemetry blob)."""
        reported = [{"technique_id": "T1558.003"}]
        telemetry = {"T1558.003": {"telemetry": "T1558.003 Kerberoasting data", "source": "live"}}
        result = _cite_or_drop(reported, telemetry)
        assert len(result) == 1

    def test_keeps_technique_with_event_id_match(self):
        """Technique with matching event ID in telemetry is kept."""
        reported = [{"technique_id": "T1558.003"}]
        telemetry = {
            "T1558.003": {"telemetry": "EventCode=4769 some Kerberos data", "source": "live"}
        }
        result = _cite_or_drop(reported, telemetry)
        assert len(result) == 1

    def test_drops_multiple_hallucinations(self):
        """Multiple hallucinated techniques are all dropped."""
        reported = [
            {"technique_id": "T1558.003", "evidence": "EventCode=4769 seen"},  # grounded
            {"technique_id": "T1078.001"},  # hallucinated
            {"technique_id": "T1021.003"},  # hallucinated
            {"technique_id": "T1059.007"},  # hallucinated
        ]
        telemetry = {"T1558.003": {"telemetry": "EventCode=4769 data", "source": "live"}}
        result = _cite_or_drop(reported, telemetry)
        assert len(result) == 1
        assert result[0]["technique_id"] == "T1558.003"

    def test_empty_reported(self):
        """Empty reported list returns empty."""
        assert _cite_or_drop([], {}) == []

    def test_keeps_technique_with_parent_id_in_telemetry(self):
        """Technique with parent ID in telemetry is kept."""
        reported = [{"technique_id": "T1558.003"}]
        telemetry = {"T1558.003": {"telemetry": "Some T1558 Kerberos data", "source": "live"}}
        result = _cite_or_drop(reported, telemetry)
        assert len(result) == 1

    def test_dcsync_event_id_match(self):
        """DCSync (T1003.006) kept when its own cited evidence names the
        4662 event that's actually present in telemetry."""
        reported = [{"technique_id": "T1003.006", "evidence": "EventCode=4662 replication seen"}]
        telemetry = {
            "T1003.006": {"telemetry": "EventCode=4662 Properties=*Replication*", "source": "live"}
        }
        result = _cite_or_drop(reported, telemetry)
        assert len(result) == 1

    def test_trigger_supplied_tokens_do_not_count_as_citations(self):
        """2026-07-23 design review: the trigger hands the model the target
        host and scenario name. Evidence whose only 'grounded' tokens are
        those trigger-echoed values is not a citation — the model was GIVEN
        them, it didn't retrieve them. Without context_text exclusion this
        fabricated narrative would pass grounding purely on the hostname."""
        trigger = (
            "An alert was triggered on webserver01 (scenario: vuln_fastjson_rce). "
            "Available telemetry sources for this host: web:access."
        )
        reported = [
            {
                "technique_id": "T1190",
                "evidence": "webserver01 received a crafted fastjson payload from the attacker",
            }
        ]
        # Real telemetry mentions the host (it usually does) but nothing else
        # from the cited evidence.
        telemetry = {
            "web:access": {
                "telemetry": "webserver01 GET / 200 (benign traffic)",
                "source": "live",
            }
        }
        assert _cite_or_drop(reported, telemetry, context_text=trigger) == []
        # Sanity: without the context exclusion the hostname echo would
        # (wrongly) ground it — this is exactly the hole being closed.
        assert len(_cite_or_drop(reported, telemetry)) == 1

    def test_grounded_evidence_survives_context_exclusion(self):
        """Context exclusion only removes trigger-echoed tokens — a claim
        citing a real, retrieved value still grounds normally."""
        trigger = "An alert was triggered on webserver01 (scenario: kerberoast)."
        reported = [{"technique_id": "T1558.003", "evidence": "EventCode=4769 on webserver01"}]
        telemetry = {
            "windows:security": {
                "telemetry": "webserver01 EventCode=4769 ticket request",
                "source": "live",
            }
        }
        result = _cite_or_drop(reported, telemetry, context_text=trigger)
        assert len(result) == 1
