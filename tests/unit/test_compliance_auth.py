"""TASK_COMPLIANCE_REASONING_V2 P7 / F09 — local trusted-reviewer auth.

``decided_by`` in the pre-existing review flow was caller-supplied text with
nothing distinguishing a human operator's decision from a model inventing a
name. These tests cover ``core/auth.py`` in isolation (no LanceDB needed);
``test_compliance_mcp.py``-style integration of ``compliance_review_decide``
gating on this is covered where that module's fixtures already exist.
"""

from __future__ import annotations

import json

import pytest

from portal.modules.compliance.core.auth import (
    UnauthenticatedReviewError,
    reviewers_configured,
    verify_reviewer,
)


@pytest.fixture(autouse=True)
def _isolated_reviewers(tmp_path, monkeypatch):
    from portal.modules.compliance.core import auth as auth_mod

    monkeypatch.setattr(auth_mod, "REVIEWERS_PATH", tmp_path / "reviewers.json")
    yield


def test_empty_token_is_rejected():
    with pytest.raises(UnauthenticatedReviewError, match="no reviewer_token"):
        verify_reviewer("")


def test_no_reviewers_configured_rejects_every_token():
    assert reviewers_configured() is False
    with pytest.raises(UnauthenticatedReviewError, match="no reviewers configured"):
        verify_reviewer("any-token-at-all")


def test_valid_token_returns_the_configured_principal(tmp_path):
    from portal.modules.compliance.core import auth as auth_mod

    auth_mod.REVIEWERS_PATH.write_text(json.dumps({"tok-abc": "alice"}), encoding="utf-8")
    assert reviewers_configured() is True
    assert verify_reviewer("tok-abc") == "alice"


def test_wrong_token_is_rejected_even_when_reviewers_exist():
    from portal.modules.compliance.core import auth as auth_mod

    auth_mod.REVIEWERS_PATH.write_text(json.dumps({"tok-abc": "alice"}), encoding="utf-8")
    with pytest.raises(UnauthenticatedReviewError, match="does not match"):
        verify_reviewer("tok-wrong")


def test_malformed_reviewers_file_raises_not_silently_ignored():
    from portal.modules.compliance.core import auth as auth_mod

    auth_mod.REVIEWERS_PATH.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    with pytest.raises(UnauthenticatedReviewError, match="must contain"):
        verify_reviewer("anything")
