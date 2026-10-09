"""The three pure observation-plane building blocks: the wall, calibration, content terms."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from portal.modules.security.core.review import calibration as cal
from portal.modules.security.core.review import content, wall

REVIEW_DIR = Path(__file__).parents[3] / "portal" / "modules" / "security" / "core" / "review"


# ── wall ──────────────────────────────────────────────────────────────────────


def test_assert_label_free_rejects_nested_label_keys() -> None:
    wall.assert_label_free({"host": "a", "fields": {"user": "b"}}, where="clean")
    with pytest.raises(wall.WallViolation):
        wall.assert_label_free({"host": "a", "fields": [{"Family": "kerberoast"}]}, where="x")


def test_scan_source_flags_code_not_docstrings() -> None:
    source = '''
"""Mentions family and technique in prose only."""

def f(record, scenario):
    return record.get("family"), record["technique_id"], record.truth
'''
    hits = wall.scan_source(source, filename="t.py")
    flagged = " ".join(hits)
    for name in ("scenario", "family", "technique_id", "truth"):
        assert name in flagged
    assert not wall.scan_source('"""family technique truth"""\nx = 1\n')


@pytest.mark.parametrize("stem", wall.OBSERVATION_PLANE)
def test_observation_plane_modules_never_mention_a_label(stem: str) -> None:
    path = REVIEW_DIR / f"{stem}.py"
    assert path.is_file(), f"observation-plane module {stem}.py is missing"
    assert wall.scan_source(path.read_text(encoding="utf-8"), filename=path.name) == []


# ── calibration ───────────────────────────────────────────────────────────────


def test_required_n_and_insufficient() -> None:
    assert cal.required_n(0.05) == 19
    assert cal.required_n(0.01) == 99
    with pytest.raises(cal.CalibrationInsufficient):
        cal.conformal_threshold([0.1] * 18, 0.05)
    assert cal.conformal_threshold([float(i) for i in range(99)], 0.01) == 98.0


def test_realized_false_raise_rate_respects_alpha() -> None:
    rng = random.Random(7)
    alpha = 0.05
    null = [rng.random() for _ in range(400)]
    threshold = cal.conformal_threshold(null, alpha)
    fresh = [rng.random() for _ in range(20000)]
    rate = sum(1 for s in fresh if s > threshold) / len(fresh)
    sd = (alpha * (1 - alpha) / len(fresh)) ** 0.5
    assert rate <= alpha + 3 * sd


def test_empirical_p_monotone_and_never_zero() -> None:
    null = sorted(random.Random(1).random() for _ in range(50))
    assert cal.empirical_p(null, 10.0) == pytest.approx(1 / 51)
    assert cal.empirical_p(null, -1.0) == 1.0
    assert cal.empirical_p(null, 0.3) >= cal.empirical_p(null, 0.7)


def test_calibration_set_roundtrip_and_staleness() -> None:
    rng = random.Random(3)
    scores = [rng.random() for _ in range(60)]
    a = cal.fit_calibration("unusual", "L2_ENTITY", scores, 0.05, basis="benign_slice")
    b = cal.fit_calibration(
        "known_similar", "L2_ENTITY", scores, 0.05, basis="benign_slice", embedder_id="emb-1"
    )
    cset = cal.CalibrationSet()
    cset.put(a)
    cset.put(b)
    again = cal.CalibrationSet.from_json(cset.to_json())
    assert again.ids() == cset.ids()
    assert again.get("unusual", "L2_ENTITY") == a
    assert cset.stale_for("emb-1") == []
    assert cset.stale_for("emb-2") == ["known_similar|L2_ENTITY"]  # embedder-free ones never stale
    assert a.exceeds(a.threshold) is False
    assert a.exceeds(a.threshold + 1e-9) is True


def test_calibration_id_changes_with_inputs() -> None:
    scores = [float(i) for i in range(40)]
    one = cal.fit_calibration("unusual", "L2_ENTITY", scores, 0.05, basis="benign_slice")
    two = cal.fit_calibration("unusual", "L2_ENTITY", scores, 0.1, basis="benign_slice")
    assert one.calibration_id != two.calibration_id


# ── content ───────────────────────────────────────────────────────────────────


def test_content_terms_use_roles_not_field_names() -> None:
    roles = {"weird_col_7": "PAYLOAD", "host": "ENTITY", "ts": "TIMESTAMP"}
    records = [
        {"ts": "2026-10-01T00:00:00Z", "host": "WKS01", "weird_col_7": "certutil -urlcache -f"},
        {"ts": "2026-10-01T00:00:01Z", "host": "WKS01", "weird_col_7": "whoami /all"},
    ]
    terms = content.content_terms(records, roles)
    assert "certutil -urlcache -f" in terms and "whoami /all" in terms
    assert not any("weird_col_7" in t or "WKS01" in t for t in terms)


def test_content_terms_mask_environment_identity() -> None:
    roles = {"cmd": "ACTION"}
    records = [
        {
            "cmd": "copy x \\\\10.1.2.3\\c$\\a1b2c3d4e5f60718.bin {3F2504E0-4F89-11D3-9A0C-0305E82C3301}"
        }
    ]
    (term,) = content.content_terms(records, roles)
    assert "10.1.2.3" not in term and "3F2504E0" not in term.upper()


def test_content_terms_rarest_first_and_per_field_cap() -> None:
    roles = {"a": "ACTION", "b": "PAYLOAD"}
    records = [{"a": "common", "b": f"rare-{i}"} for i in range(1)] + [
        {"a": "common", "b": "x"} for _ in range(5)
    ]
    terms = content.content_terms(records, roles, limit=10, per_field_cap=1)
    assert terms[0].startswith("rare-0")  # occurs once, before the commoner terms
    assert len([t for t in terms if t in {"common"}]) <= 1
    assert content.content_terms(records, {"a": "ENTITY"}) == []
