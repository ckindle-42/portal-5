"""Tests for validate_capture_signals — the capture-quality gate that decides
whether a saved capture actually contains evidence of its own labeled ground
truth, so it can be trusted as replayable telemetry for blue/purple.

Found live 2026-07-22 (GATE-D ablation Part II-A, prompted directly by a user
architecture question about capture/replay trustworthiness): a "broader
attack evidence" fallback credited EVERY missing/unchecked technique as
"found" whenever ANY of ~35 generic words ("error", "failed", "denied"...)
appeared anywhere in the capture, regardless of relevance. 352/422 (83.4%) of
on-disk captures showed coverage=1.0 under that logic — a rubber stamp, not a
real quality signal. This file locks in the corrected behavior: technique
credit requires that technique's own specific EXPECTED_SIGNALS keywords, and
techniques with no EXPECTED_SIGNALS entry are `unchecked`, never silently
credited either way.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tests" / "benchmarks"))

from portal.modules.security.core.siem.capture_enrichment import validate_capture_signals


class TestValidateCaptureSignals:
    def test_finds_technique_with_specific_signal(self):
        """Real, technique-specific EventCode/field content -> found."""
        telemetry = {
            "windows:security": [
                "EventCode=4625 Account=user01 WorkstationName=WKSTN01 IpAddress=10.0.0.50 Status=0xc000006d",
            ]
        }
        result = validate_capture_signals("meta3_ssh_brute", telemetry)
        assert "T1110.003" in result["found"]
        assert "T1110.003" not in result["missing"]

    def test_generic_noise_words_alone_do_not_credit_a_technique(self):
        """The core regression: a capture with only generic failure/error
        vocabulary (no technique-specific signal) must NOT credit ANY ground
        truth technique — this mirrors the real meta3_ssh_brute capture that
        was wrongly certified coverage=1.0 off a single FTP '530' failure
        line matching "denied"/"failed"."""
        telemetry = {
            "ftp:access": [
                "10.0.0.25 - 10.10.11.13 21 user :) 331 0 0 abc -",
                "10.0.0.25 - 10.10.11.13 21 pass *** 530 1326 41 abc -",
            ],
            "web:access": [
                "10.10.11.13 GET / - 80 - 10.0.0.25 curl 200 0 995 375",
            ],
        }
        result = validate_capture_signals("meta3_ssh_brute", telemetry)
        assert result["found"] == []
        assert set(result["missing"]) >= {"T1110.003", "T1078", "T1059"}
        assert result["coverage"] == 0.0
        assert result["valid"] is False

    def test_technique_without_expected_signals_entry_is_unchecked(self):
        """A GT technique with no EXPECTED_SIGNALS entry (e.g. T1078.004,
        Cloud Accounts) must be `unchecked`, never silently `found` (the old
        bug) and never unfairly counted as `missing` either."""
        telemetry = {"web:access": ["irrelevant noise line"]}
        result = validate_capture_signals("cloud_breach", telemetry)
        assert "T1078.004" in result["unchecked"]
        assert "T1078.004" not in result["found"]
        assert "T1078.004" not in result["missing"]

    def test_coverage_excludes_unchecked_techniques(self):
        """coverage is computed over the checkable subset only — an
        all-unchecked ground truth (no signal table coverage at all) must
        not silently read as coverage=1.0 (falsely "fully valid") or divide
        by zero; it's an honest 0.0/not-valid, distinct from a real miss."""
        telemetry = {"web:access": ["nothing relevant here"]}
        result = validate_capture_signals("cloud_breach", telemetry)
        assert result["coverage"] == 0.0
        assert result["valid"] is False
        assert result["found"] == []
        assert result["missing"] == []
        assert len(result["unchecked"]) == 3  # T1552.005, T1078.004, T1537

    def test_partial_signal_yields_partial_coverage_not_full_credit(self):
        """One of three checkable techniques present -> coverage reflects
        exactly that fraction, not rounded up to full via the old fallback.
        Uses T1110.003's REAL EXPECTED_SIGNALS example line verbatim — safe
        from colliding with T1078's/T1059's own examples now that matching
        requires a whole example line's fields together (AND within a line),
        not any single pooled token (the 2026-07-23 fix, found live on the
        first scenario of the post-fix recapture run: a bare shared token like
        "Account=administrator" or "EventCode=4662" alone used to false-match
        an unrelated technique's real telemetry)."""
        telemetry = {
            "windows:security": [
                "EventCode=4625 Account=user01 WorkstationName=WKSTN01 IpAddress=10.0.0.50 Status=0xc000006d",
            ],
            "web:access": ["some unrelated 500 error line here"],  # generic noise, must not help
        }
        result = validate_capture_signals("meta3_ssh_brute", telemetry)
        assert result["found"] == ["T1110.003"]
        assert set(result["missing"]) == {"T1078", "T1059"}
        assert result["coverage"] == round(1 / 3, 3)
        assert result["valid"] is False

    def test_unknown_scenario_returns_empty_unchecked_result(self):
        result = validate_capture_signals("not_a_real_scenario", {})
        assert result["valid"] is False
        assert result["coverage"] == 0.0
        assert result["found"] == []
        assert result["unchecked"] == []

    def test_stray_generic_token_from_a_different_technique_does_not_false_match(self):
        """Regression: found live 2026-07-23 on the first scenario of the
        post-fix recapture run (kerberoast_to_da). A real capture had ONLY
        genuine Kerberoasting evidence (T1558.003, EventCode=4769 with
        TicketEncryptionType=0x17) — the red chain stalled before ever
        attempting DCSync or scheduled-task persistence. But the (then-)
        current validator credited ALL THREE ground-truth techniques
        (T1558.003, T1003.006 DCSync, T1053.005 Scheduled Task) as "found",
        because pooling every field=value token across every technique's
        examples let a bare, generic token from an unrelated technique's
        example — T1053.005's "Account=administrator" — coincidentally
        substring-match the real Kerberoasting event's own
        "Account=administrator@PORTAL.LAB" field, and a bare "EventCode=4662"
        (Windows' general object-access audit event, used for many unrelated
        operations) false-matched T1003.006 without its actually-discriminating
        "Properties=Replication-Dir-Replication-Right" value ever appearing.

        Fixed by requiring a whole example line's fields together (AND within
        the line), not any single token pooled across every example (OR
        across lines only, never across techniques or partial lines)."""
        telemetry = {
            "windows:security": [
                # Genuine Kerberoasting evidence only.
                "EventCode=4769 TicketEncryptionType=0x17 ServiceName=svc_backup Account=administrator@PORTAL.LAB",
                # A generic EventCode=4662 for an UNRELATED object access, and
                # a coincidental "Account=administrator" mention elsewhere —
                # neither is real DCSync/Scheduled-Task evidence.
                "EventCode=4662 Properties=Control Access Account=WIN-MVQO0PT39IO$",
                "EventCode=4624 LogonType=3 Account=administrator WorkstationName=WKSTN02",
            ]
        }
        result = validate_capture_signals("kerberoast_to_da", telemetry)
        assert result["found"] == ["T1558.003"]
        assert set(result["missing"]) == {"T1003.006", "T1053.005"}
        assert result["valid"] is False
