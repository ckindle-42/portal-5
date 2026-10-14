"""The closeout disposition backfill: every item classified, every removal either
restorable with a recipe or marked unrestorable and unavailable
(spec: docs/WFE_ROOT_CAUSES_20261013.md, "Decisions at risk")."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
QUEUE = REPO / "tests" / "wfe" / "candidate_queue.yaml"


def _load():
    spec = importlib.util.spec_from_file_location(
        "wfe_disposition_backfill", REPO / "scripts" / "wfe_disposition_backfill.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


bf = _load()


def _item(**kw):
    base = {"item_id": "i", "exact_identity": "t:1", "kind": "ollama_manifest"}
    return {**base, **kw}


class TestClassify:
    def test_an_integrated_identity_has_nothing_to_restore(self):
        cls, restorable, recipe = bf.classify(_item(final_disposition="INTEGRATED"))
        assert (cls, restorable) == ("integrated", "n/a") and "in service" in recipe

    def test_a_retained_identity_has_nothing_to_restore(self):
        cls, _r, _recipe = bf.classify(_item(final_disposition="RETAINED_FOR_PURPOSE"))
        assert cls == "retained_for_purpose"

    def test_a_present_ollama_removal_is_restorable_by_pull(self):
        cls, restorable, recipe = bf.classify(
            _item(
                final_disposition="REMOVED_CLOSED",
                observed_present=True,
                model_layer_digests=["sha256:abc"],
            )
        )
        assert (cls, restorable) == ("removed_restorable", "restorable")
        assert recipe.startswith("ollama pull t:1") and "1 layer" in recipe

    def test_an_absent_removal_is_unrestorable(self):
        cls, restorable, recipe = bf.classify(
            _item(final_disposition="REMOVED_CLOSED", observed_present=False)
        )
        assert (cls, restorable) == ("removed_unrestorable", "unrestorable")
        assert "absent from the store" in recipe

    def test_a_present_omlx_removal_is_unrestorable_without_an_upstream_source(self):
        cls, restorable, recipe = bf.classify(
            _item(
                final_disposition="REMOVED_CLOSED",
                observed_present=True,
                kind="omlx_entry",
            )
        )
        assert (cls, restorable) == ("removed_unrestorable", "unrestorable")
        assert "omlx_entry" in recipe


class TestTheRegister:
    def test_every_item_is_classified_into_exactly_one_class(self):
        report = bf.backfill()
        assert report["item_count"] == 203
        assert sum(report["classes"].values()) == report["item_count"]
        assert set(report["classes"]) <= set(bf.CLASSES)

    def test_the_five_measurement_based_removals_are_found(self):
        first = bf.backfill()["at_risk_first"]
        assert len(first) == 5
        probes = [r["at_risk"] for r in first]
        assert sum("judgment probe v6" in p for p in probes) == 4
        assert sum("research probe" in p for p in probes) == 1
        assert all(r["disposition"] == "REMOVED_CLOSED" for r in first)

    def test_every_unrestorable_removal_is_in_the_queue_unavailable(self):
        """An unrestorable removal's cells must be MISSING, which needs
        `available: false` in the queue — otherwise the decision rule would read
        its absence as an unmeasured-but-reachable model."""
        report = bf.backfill()
        models = (yaml.safe_load(QUEUE.read_text()) or {}).get("models") or {}
        for row in report["unrestorable"]:
            identity = str(row["exact_identity"] or row["item_id"])
            assert identity in models, f"{identity} is missing from the queue"
            assert models[identity]["available"] is False
            assert models[identity]["intended"] == []

    def test_no_restorable_removal_is_marked_unavailable(self):
        report = bf.backfill()
        models = (yaml.safe_load(QUEUE.read_text()) or {}).get("models") or {}
        for row in report["rows"]:
            if row["restorable"] != "restorable":
                continue
            entry = models.get(str(row["exact_identity"]))
            if entry is not None:
                assert entry.get("available") is not False
