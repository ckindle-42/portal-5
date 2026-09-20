"""HG/HH — the two checks that make abandonment cost something.

TASK_COMPLIANCE_PROVE_CIP_007_V1 §P6.1. Seven live harnesses were abandoned
because abandonment was free. These tests pin the two conditions that must FAIL
a push, and — just as importantly — the two that must not: a directory left
behind by a harness that never ran is not a run, and a run against a revision
that does not contain the module's latest change is not current.

Both checks are held at SKIP while `IN_SERVICE` is False, so the detection logic
and the pre-service gating are tested separately: the `_`-prefixed functions are
the detection, the registered `check_*` wrappers are the gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation import compliance_acceptance as check


def _run_dir(root: Path, rev: str, cells: list[dict] | None, planned: int = 0) -> Path:
    directory = root / rev
    directory.mkdir(parents=True)
    if cells is not None:
        (directory / "status.json").write_text(
            json.dumps({"git_head": rev, "updated_at": "2026-09-17T00:00:00Z", "cells": cells})
        )
    if planned:
        (directory / "manifest.json").write_text(
            json.dumps(
                {"cases": ["a"] * planned, "seats": ["s"], "adapters": ["reader"], "runs": 1}
            )
        )
    return directory


@pytest.fixture
def acceptance_root(tmp_path, monkeypatch):
    root = tmp_path / "acceptance"
    root.mkdir()
    monkeypatch.setattr(check, "ACCEPTANCE_ROOT", root)
    return root


class TestHGWhatCountsAsARun:
    def test_a_directory_with_no_status_is_not_a_run(self, acceptance_root) -> None:
        """Six of the seven abandoned harnesses left directories behind."""
        _run_dir(acceptance_root, "aaaa", None)
        assert check._acceptance_runs() == []

    def test_a_status_with_no_cells_is_not_a_run(self, acceptance_root) -> None:
        _run_dir(acceptance_root, "bbbb", [])
        assert check._acceptance_runs() == []

    def test_a_run_with_cells_counts_and_carries_its_pass_count(self, acceptance_root) -> None:
        _run_dir(
            acceptance_root,
            "cccc",
            [{"cell": "x", "passed": True}, {"cell": "y", "passed": False}],
        )
        (run,) = check._acceptance_runs()
        assert run["rev"] == "cccc"
        assert (run["cells"], run["passed"]) == (2, 1)


class TestHGCurrency:
    """These pin the underlying staleness detection (`_compliance_acceptance_currency`),
    which is unaffected by IN_SERVICE. The public `check_compliance_acceptance_currency`
    wrapper's IN_SERVICE downgrade is covered separately, below.
    """

    def test_no_run_at_all_fails_and_names_the_commit(self, acceptance_root, monkeypatch) -> None:
        monkeypatch.setattr(check, "_git", lambda *a: "deadbeefcafe0000")
        status, detail, _ = check._compliance_acceptance_currency()
        assert status == "FAIL"
        assert "deadbeefcafe" in detail
        assert "run_compliance_acceptance.sh" in detail

    def test_a_run_that_predates_the_change_fails(self, acceptance_root, monkeypatch) -> None:
        """The exact abandonment shape: a run exists, and the module moved
        after it. A check that only asked "is there a run" would pass here."""
        _run_dir(acceptance_root, "older", [{"cell": "x", "passed": True}])
        monkeypatch.setattr(check, "_git", lambda *a: "newer")
        monkeypatch.setattr(check, "_is_ancestor", lambda older, newer: False)
        status, detail, _ = check._compliance_acceptance_currency()
        assert status == "FAIL"
        assert "the module moved and nothing re-ran" in detail

    def test_a_run_containing_the_change_passes(self, acceptance_root, monkeypatch) -> None:
        _run_dir(acceptance_root, "newer", [{"cell": "x", "passed": True}], planned=1)
        monkeypatch.setattr(check, "_git", lambda *a: "older")
        monkeypatch.setattr(check, "_is_ancestor", lambda older, newer: True)
        status, _, _ = check.check_compliance_acceptance_currency()
        assert status == "PASS"

    def test_a_partial_run_is_not_currency(self, acceptance_root, monkeypatch) -> None:
        """Found by running the check: a campaign STOPPED after 5 of 18 cells
        satisfied it, because it asked "is there a run" and never "did it
        finish". An aborted run is precisely the shape the seven abandoned
        harnesses left behind."""
        _run_dir(
            acceptance_root,
            "newer",
            [{"cell": f"c{i}", "passed": True} for i in range(5)],
            planned=18,
        )
        monkeypatch.setattr(check, "_git", lambda *a: "older")
        monkeypatch.setattr(check, "_is_ancestor", lambda older, newer: True)
        status, detail, _ = check._compliance_acceptance_currency()
        assert status == "FAIL"
        assert "INCOMPLETE" in detail and "5 of 18" in detail

    def test_a_run_with_no_manifest_cannot_claim_completeness(
        self, acceptance_root, monkeypatch
    ) -> None:
        _run_dir(acceptance_root, "newer", [{"cell": "x", "passed": True}])
        monkeypatch.setattr(check, "_git", lambda *a: "older")
        monkeypatch.setattr(check, "_is_ancestor", lambda older, newer: True)
        status, _, _ = check._compliance_acceptance_currency()
        assert status == "FAIL"


class TestHGInServiceDowngrade:
    """While compliance is pre-service (IN_SERVICE=False), a stale/missing
    acceptance run must not block a push, and must not ask for one either: the
    public check downgrades FAIL to SKIP, and says why. A WARN was what kept
    the ~6-hour live suite being started on pushes that only touched the module
    in passing. Flip IN_SERVICE=True the day compliance ships, and this same
    stale state must go back to a hard-blocking FAIL.
    """

    def test_a_stale_run_skips_not_fails_while_pre_service(
        self, acceptance_root, monkeypatch
    ) -> None:
        monkeypatch.setattr(check, "_git", lambda *a: "deadbeefcafe0000")
        monkeypatch.setattr(check, "IN_SERVICE", False)
        status, detail, _ = check.check_compliance_acceptance_currency()
        assert status == "SKIP"
        assert "IN_SERVICE" in detail
        assert "deadbeefcafe" in detail

    def test_the_pre_service_skip_does_not_ask_for_a_live_run(
        self, acceptance_root, monkeypatch
    ) -> None:
        """The nag itself was the cost: naming the runner on every push is how
        a suite nothing depends on yet kept getting launched."""
        monkeypatch.setattr(check, "_git", lambda *a: "deadbeefcafe0000")
        monkeypatch.setattr(check, "IN_SERVICE", False)
        _, detail, _ = check.check_compliance_acceptance_currency()
        assert "no live run is asked for" in detail

    def test_the_same_stale_run_fails_once_in_service(self, acceptance_root, monkeypatch) -> None:
        monkeypatch.setattr(check, "_git", lambda *a: "deadbeefcafe0000")
        monkeypatch.setattr(check, "IN_SERVICE", True)
        status, _, _ = check.check_compliance_acceptance_currency()
        assert status == "FAIL"

    def test_a_passing_currency_check_is_unaffected_by_in_service(
        self, acceptance_root, monkeypatch
    ) -> None:
        _run_dir(acceptance_root, "newer", [{"cell": "x", "passed": True}], planned=1)
        monkeypatch.setattr(check, "_git", lambda *a: "older")
        monkeypatch.setattr(check, "_is_ancestor", lambda older, newer: True)
        monkeypatch.setattr(check, "IN_SERVICE", False)
        status, _, _ = check.check_compliance_acceptance_currency()
        assert status == "PASS"


class TestHHTemplateIdentity:
    """These pin the underlying template-drift detection, which is what runs
    once compliance is in service. The public wrapper's pre-service SKIP is
    covered by TestHHInServiceSkip.
    """

    def _pin(self, tmp_path, monkeypatch, sha: str) -> None:
        pin = tmp_path / "pin.json"
        pin.write_text(json.dumps({"seats": [{"seat": "seat-a", "template_sha": sha}]}))
        monkeypatch.setattr(check, "CAMPAIGN_PIN", pin)

    def test_a_matching_sha_passes(self, tmp_path, acceptance_root, monkeypatch) -> None:
        self._pin(tmp_path, monkeypatch, "aaaaaaaaaaaa")
        monkeypatch.setattr(
            "tests.wfe.settings_audit._template_sha", lambda tag: "aaaaaaaaaaaa", raising=True
        )
        monkeypatch.setattr(check, "IN_SERVICE", True)
        status, _, _ = check.check_compliance_seat_template_identity()
        assert status == "PASS"

    def test_a_moved_template_fails_and_names_both_shas(
        self, tmp_path, acceptance_root, monkeypatch
    ) -> None:
        """A chat template is not versioned, not announced, and changes on an
        `ollama pull`. Every result recorded against the old sha stops being
        comparable the moment it moves, and nothing else would notice."""
        self._pin(tmp_path, monkeypatch, "aaaaaaaaaaaa")
        monkeypatch.setattr(
            "tests.wfe.settings_audit._template_sha", lambda tag: "bbbbbbbbbbbb", raising=True
        )
        status, detail, _ = check._compliance_seat_template_identity()
        assert status == "FAIL"
        assert "aaaaaaaaaaaa" in detail and "bbbbbbbbbbbb" in detail

    def test_an_unreadable_live_template_fails_rather_than_passing_quietly(
        self, tmp_path, acceptance_root, monkeypatch
    ) -> None:
        self._pin(tmp_path, monkeypatch, "aaaaaaaaaaaa")
        monkeypatch.setattr(
            "tests.wfe.settings_audit._template_sha", lambda tag: None, raising=True
        )
        status, detail, _ = check._compliance_seat_template_identity()
        assert status == "FAIL"
        assert "unreadable" in detail

    def test_a_missing_pin_fails(self, tmp_path, acceptance_root, monkeypatch) -> None:
        monkeypatch.setattr(check, "CAMPAIGN_PIN", tmp_path / "absent.json")
        status, detail, _ = check._compliance_seat_template_identity()
        assert status == "FAIL"
        assert "compliance_preflight" in detail


class TestHHInServiceSkip:
    """HH's evidence is a live `/api/show` per seat, so pre-service it skips
    BEFORE probing rather than downgrading after — the point is not to spend
    the call. With the stack down or a seat tag uninstalled, that probe used to
    FAIL and block a push over a module nothing depends on yet.
    """

    def test_pre_service_skips_without_probing_ollama(
        self, tmp_path, acceptance_root, monkeypatch
    ) -> None:
        def _must_not_be_called(tag: str) -> str:
            raise AssertionError(f"probed {tag} while compliance is pre-service")

        monkeypatch.setattr(
            "tests.wfe.settings_audit._template_sha", _must_not_be_called, raising=True
        )
        monkeypatch.setattr(check, "IN_SERVICE", False)
        status, detail, _ = check.check_compliance_seat_template_identity()
        assert status == "SKIP"
        assert "IN_SERVICE" in detail

    def test_a_missing_pin_does_not_block_a_push_pre_service(
        self, tmp_path, acceptance_root, monkeypatch
    ) -> None:
        monkeypatch.setattr(check, "CAMPAIGN_PIN", tmp_path / "absent.json")
        monkeypatch.setattr(check, "IN_SERVICE", False)
        status, _, _ = check.check_compliance_seat_template_identity()
        assert status == "SKIP"

    def test_the_same_drift_fails_once_in_service(
        self, tmp_path, acceptance_root, monkeypatch
    ) -> None:
        pin = tmp_path / "pin.json"
        pin.write_text(json.dumps({"seats": [{"seat": "seat-a", "template_sha": "aaaaaaaaaaaa"}]}))
        monkeypatch.setattr(check, "CAMPAIGN_PIN", pin)
        monkeypatch.setattr(
            "tests.wfe.settings_audit._template_sha", lambda tag: "bbbbbbbbbbbb", raising=True
        )
        monkeypatch.setattr(check, "IN_SERVICE", True)
        status, _, _ = check.check_compliance_seat_template_identity()
        assert status == "FAIL"
