"""Stamp and metrics: known values, and the failure modes each one exists to prevent."""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from portal.modules.security.core.review_eval import HARNESS_VERSION, metrics, stamp


def _stamp(**overrides: Any) -> stamp.Stamp:
    base: dict[str, Any] = {
        "repo": Path("."),
        "embedder_id": "emb-1",
        "model_digests": {"m": "d"},
        "config": {"a": 1},
        "corpus_snapshot": "real:snap-1",
        "policy": "p",
        "git": lambda _repo: ("deadbeef", False),
    }
    base.update(overrides)
    return stamp.build_stamp(**base)


# ── stamp ─────────────────────────────────────────────────────────────────────


def test_stamp_digest_is_stable_and_sensitive_to_every_input() -> None:
    a = _stamp()
    assert a.digest == _stamp().digest and a.harness_version == HARNESS_VERSION
    assert _stamp(embedder_id="emb-2").digest != a.digest
    assert _stamp(config={"a": 2}).digest != a.digest
    assert _stamp(git=lambda _r: ("cafe", False)).digest != a.digest
    assert _stamp(git=lambda _r: ("deadbeef", True)).digest != a.digest  # dirty is recorded


def test_incomplete_stamps_have_problems() -> None:
    assert _stamp().problems() == []
    bad = _stamp(embedder_id="", corpus_snapshot="", git=lambda _r: ("", False))
    assert {
        "stamp.commit is empty",
        "stamp.embedder_id is empty",
        "stamp.corpus_snapshot is empty",
    } <= set(bad.problems())


def test_git_state_uses_the_runner_and_reports_dirty() -> None:
    calls: list[list[str]] = []

    def run(cmd: list[str], **_kw: Any) -> Any:
        calls.append(cmd)
        return SimpleNamespace(stdout="abc123\n" if "rev-parse" in cmd else " M file.py\n")

    assert stamp.git_state(Path("/repo"), run) == ("abc123", True)
    assert len(calls) == 2


def test_service_identity_and_digest_helpers_are_offline_testable() -> None:
    get: dict[str, dict[str, Any]] = {
        "http://e/ready": {"identity": {"model": "google/embeddinggemma-2:768d"}},
        "http://o/api/tags": {"models": [{"name": "granite", "digest": "sha256:abc"}]},
    }
    assert (
        stamp.fetch_embedder_identity(lambda u: get[u], "http://e")
        == "google/embeddinggemma-2:768d"
    )
    digests = stamp.fetch_model_digests(lambda u: get[u], "http://o", ["granite", "missing"])
    assert digests == {"granite": "sha256:abc", "missing": "unlisted"}


# ── metrics ───────────────────────────────────────────────────────────────────


def test_auroc_known_values() -> None:
    assert metrics.auroc([3, 4], [1, 2]) == 1.0
    assert metrics.auroc([1, 2], [3, 4]) == 0.0
    assert metrics.auroc([1, 1], [1, 1]) == 0.5
    assert math.isnan(metrics.auroc([], [1.0]))


def test_ties_are_never_raised() -> None:
    assert metrics.recall_at_fpr([0.5, 0.5], [0.5] * 10, 0.05) == 0.0


def test_recall_at_fpr_and_curve() -> None:
    neg = [i / 100 for i in range(100)]
    pos = [0.995, 0.5, 2.0]
    assert metrics.recall_at_fpr(pos, neg, 0.01) == pytest.approx(
        2 / 3
    )  # 0.995 > 2nd-largest neg 0.98
    fpr, recall = metrics.recall_fpr_curve(pos, neg, [0.0, 0.5])[0]
    assert fpr == 0.0 and recall == pytest.approx(2 / 3)


def test_precision_at_n_and_false_raise_rate() -> None:
    assert metrics.precision_at_n([0.9, 0.8, 0.1], [True, False, True], 2) == 0.5
    assert metrics.false_raise_per_1k(3, 600) == pytest.approx(5.0)
    with pytest.raises(ValueError):
        metrics.false_raise_per_1k(0, 0)


def test_exact_mcnemar_known_values() -> None:
    assert metrics.exact_mcnemar_p(10, 0) == pytest.approx(2 / 1024)
    assert metrics.exact_mcnemar_p(5, 5) == 1.0
    assert metrics.exact_mcnemar_p(0, 0) == 1.0
    assert metrics.paired_discordant([True, True, False], [True, False, True]) == (1, 1)
    with pytest.raises(ValueError):
        metrics.paired_discordant([True], [True, False])


def test_bootstrap_is_seeded() -> None:
    values = [float(i % 7) for i in range(50)]
    assert metrics.bootstrap_ci(values, seed=1) == metrics.bootstrap_ci(values, seed=1)
    lo, hi = metrics.bootstrap_ci(values, seed=1)
    assert lo < sum(values) / len(values) < hi


def test_youden_point_respects_the_budget() -> None:
    points = [(0.01, 0.2), (0.05, 0.6), (0.2, 0.9)]
    assert metrics.youden_point(points, max_fpr=0.1) == (0.05, 0.6)
    assert metrics.youden_point(points, max_fpr=0.5) == (0.2, 0.9)
    with pytest.raises(ValueError):
        metrics.youden_point(points, max_fpr=0.001)


def test_twin_aware_hit() -> None:
    twins = {"a1": "g1", "a2": "g1", "b1": "g2"}
    assert metrics.twin_aware_hit("a2", {"a1"}, twins) is True
    assert metrics.twin_aware_hit("b1", {"a1"}, twins) is False
    assert metrics.twin_aware_hit("zz", {"zz"}, twins) is True


def test_a_corpus_must_declare_real_or_proxy() -> None:
    assert _stamp(corpus_snapshot="proxy:synthetic-universe").problems() == []
    assert any("real:' or 'proxy:" in p for p in _stamp(corpus_snapshot="snap-1").problems())
