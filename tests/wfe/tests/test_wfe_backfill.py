"""The closeout disposition backfill: every item classified; a removal is
restorable only when a registry still serves it, and verified only when the
registry's layers include the digest the register recorded (spec:
docs/WFE_ROOT_CAUSES_20261013.md, "Decisions at risk").

The registry is faked here; P1R's live phase asks the real ones."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
QUEUE = REPO / "tests" / "wfe" / "candidate_queue.yaml"
RECEIPT = REPO / "docs" / "WFE_DISPOSITION_BACKFILL_20261014.json"


def _load():
    spec = importlib.util.spec_from_file_location(
        "wfe_disposition_backfill", REPO / "scripts" / "wfe_disposition_backfill.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


bf = _load()
D1, D2 = "sha256:" + "1" * 64, "sha256:" + "2" * 64


def _item(**kw):
    base = {
        "item_id": "i",
        "exact_identity": "t:1",
        "kind": "ollama_manifest",
        "final_disposition": "REMOVED_CLOSED",
        "observed_present": True,
        "model_layer_digests": [D1],
    }
    return {**base, **kw}


def _registry(served: dict):
    """A fake registry: tag -> layer digests; anything else is absent."""

    def lookup(tag):
        return ("found", set(served[tag])) if tag in served else ("absent (HTTP 404)", set())

    return lookup


class TestClassify:
    def test_in_service_and_retained_identities_have_nothing_to_restore(self):
        assert bf.classify(_item(final_disposition="INTEGRATED"))["class"] == "integrated"
        assert bf.classify(_item(final_disposition="RETAINED_FOR_PURPOSE"))["restorable"] == "n/a"

    def test_a_removal_the_registry_serves_with_the_recorded_digest_is_verified(self):
        v = bf.classify(
            _item(exact_identity="granite4.1:8b-q8_0"), _registry({"granite4.1:8b-q8_0": [D1, D2]})
        )
        assert (v["class"], v["restorable"]) == ("removed_restorable", "verified")
        assert v["recipe"] == "ollama pull granite4.1:8b-q8_0"

    def test_absence_at_closeout_does_not_make_a_library_tag_unrestorable(self):
        """command-r:35b and granite4.2:30b were marked unrestorable only because
        they were not installed at closeout. The registry decides, not the store."""
        item = _item(exact_identity="command-r:35b-08-2024-q4_K_M", observed_present=False)
        v = bf.classify(item, _registry({"command-r:35b-08-2024-q4_K_M": [D1]}))
        assert v["restorable"] == "verified"

    def test_a_registry_build_other_than_the_measured_one_is_flagged(self):
        v = bf.classify(_item(), _registry({"t:1": [D2]}))
        assert (v["class"], v["restorable"]) == ("removed_restorable", "differs")

    def test_a_tag_with_no_recorded_digest_is_unrecorded_not_verified(self):
        item = _item(kind="historical_absent_ollama_tag", model_layer_digests=None)
        assert bf.classify(item, _registry({"t:1": [D1]}))["restorable"] == "unrecorded"

    def test_a_ctx_variant_pulls_its_base_and_recreates_the_variant(self):
        """`-ctxNk` tags are made locally by `models apply-params`; pulling the
        variant itself fails, which is what the first backfill told the reader to do."""
        item = _item(exact_identity="granite4.1:8b-q8_0-ctx16k")
        asked = []

        def lookup(tag):
            asked.append(tag)
            return "found", {D1}

        v = bf.classify(item, lookup)
        assert asked == ["granite4.1:8b-q8_0"]
        assert v["restorable"] == "verified"
        assert v["recipe"].startswith(
            "ollama pull granite4.1:8b-q8_0 && printf 'FROM granite4.1:8b-q8_0"
        )
        assert "PARAMETER num_ctx 16384" in v["recipe"]
        assert v["recipe"].endswith(
            "ollama create granite4.1:8b-q8_0-ctx16k -f /tmp/granite4.1_8b-q8_0-ctx16k.Modelfile"
        )

    def test_a_local_portal5_tag_no_registry_serves_is_unrestorable(self):
        item = _item(exact_identity="portal5/xyz-aquila-mini:q4_k_m-ctx16k")
        v = bf.classify(item, _registry({}))
        assert (v["class"], v["restorable"]) == ("removed_unrestorable", "unrestorable")
        assert "portal5/xyz-aquila-mini/manifests/q4_k_m" in v["verification"]

    def test_a_restore_source_is_verified_like_any_other(self, monkeypatch):
        monkeypatch.setitem(bf.RESTORE_SOURCES, "portal5/x:q4-ctx16k", "hf.co/u/x-GGUF:Q4")
        item = _item(exact_identity="portal5/x:q4-ctx16k")
        assert bf.classify(item, _registry({"hf.co/u/x-GGUF:Q4": [D1]}))["restorable"] == "verified"
        assert bf.classify(item, _registry({"hf.co/u/x-GGUF:Q4": [D2]}))["restorable"] == "differs"

    def test_an_omlx_directory_without_a_source_is_unrestorable_without_asking(self):
        def never(tag):
            raise AssertionError("an oMLX directory has no registry tag to ask about")

        v = bf.classify(_item(kind="omlx_entry", exact_identity="Laguna-XS.2-4bit"), never)
        assert v["restorable"] == "unrestorable"

    def test_an_unreachable_registry_leaves_the_removal_unverified(self):
        v = bf.classify(_item(), lambda tag: ("unreachable (DNS)", set()))
        assert (v["class"], v["restorable"]) == ("removed_unverified", "unverified")
        assert bf.classify(_item())["restorable"] == "unverified"  # never asked


class TestRegistry:
    def test_manifest_urls(self):
        assert bf.manifest_url("granite4.1:8b-q8_0") == (
            "https://registry.ollama.ai/v2/library/granite4.1/manifests/8b-q8_0"
        )
        assert bf.manifest_url("portal5/cadmium:Q4_K_M") == (
            "https://registry.ollama.ai/v2/portal5/cadmium/manifests/Q4_K_M"
        )
        assert bf.manifest_url("hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M") == (
            "https://hf.co/v2/bartowski/Qwen_Qwen3.6-27B-GGUF/manifests/Q4_K_M"
        )
        assert bf.manifest_url("llama3").endswith("/library/llama3/manifests/latest")

    @pytest.mark.parametrize(
        ("code", "state"),
        [(404, "absent"), (401, "absent"), (403, "unreachable"), (500, "unreachable")],
    )
    def test_http_errors_are_classified_without_guessing(self, code, state):
        def opener(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, None)

        assert bf.registry_layers("t:1", opener)[0].startswith(state)

    def test_a_manifest_yields_its_layer_digests(self):
        doc = {"layers": [{"digest": D1}, {"digest": D2}, {"mediaType": "x"}]}

        def opener(req, timeout=None):
            assert req.headers["Accept"].startswith("application/vnd.docker")
            return io.BytesIO(json.dumps(doc).encode())

        assert bf.registry_layers("t:1", opener) == ("found", {D1, D2})


class TestRegister:
    def test_every_item_is_classified_into_exactly_one_class(self):
        report = bf.backfill(_registry({}))
        assert report["item_count"] == 203
        assert sum(report["classes"].values()) == 203
        assert set(report["classes"]) <= set(bf.CLASSES)

    def test_the_five_measurement_based_removals_are_found(self):
        first = bf.backfill()["at_risk_first"]
        assert sorted(r["item_id"] for r in first) == sorted(bf.AT_RISK)

    def test_when_every_registry_answers_nothing_is_unverified(self):
        served = {}
        for item in json.loads(bf.CLOSEOUT.read_text())["items"]:
            pull, _ = bf.pull_plan(str(item.get("exact_identity")))
            served[pull] = set(item.get("model_layer_digests") or []) | served.get(pull, set())
        report = bf.backfill(_registry(served))
        assert not report["unverified"]
        assert report["restorability"].get("verified", 0) > 0

    def test_the_committed_receipt_and_queue_agree(self):
        """P5-B1 resolution (b): the queue holds live candidates only — it carries no
        closeout row — while the frozen 2026-10-14 receipt keeps the historical record
        of the 28 unrestorable removals."""
        receipt = json.loads(RECEIPT.read_text())
        models = (yaml.safe_load(QUEUE.read_text()) or {}).get("models") or {}
        owned = {m for m, e in models.items() if (e or {}).get("removed_at_closeout")}
        assert owned == set()
        assert all((e or {}).get("available") is True for e in models.values())
        unrestorable = {
            str(r["exact_identity"] or r["item_id"])
            for r in receipt["rows"]
            if r["restorable"] == "unrestorable"
        }
        assert len(unrestorable) == 28


class TestWriting:
    def test_write_refuses_while_anything_is_unverified(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["bf", "--write"])
        monkeypatch.setattr(bf, "RECEIPT", Path("/nonexistent/receipt.json"))
        assert bf.main() == 1
        assert "refusing to write" in capsys.readouterr().out

    def test_merge_drops_restorable_entries_and_keeps_the_operators(self, tmp_path):
        q = tmp_path / "queue.yaml"
        q.write_text(
            yaml.safe_dump(
                {
                    "models": {
                        "now-restorable:tag": {"available": False, "removed_at_closeout": True},
                        "operator:tag": {"available": True, "intended": ["auto-coding"]},
                    }
                }
            )
        )
        added, dropped = bf.merge_queue(
            {"gone:tag": {"available": False, "removed_at_closeout": True}}, q
        )
        models = yaml.safe_load(q.read_text())["models"]
        assert (added, dropped) == (1, 1)
        assert set(models) == {"gone:tag", "operator:tag"}

    def test_the_doc_section_is_rewritten_in_place(self, tmp_path):
        doc = tmp_path / "doc.md"
        doc.write_text("# T\n\n## Decisions at risk\n\nold text\n## Next\n\nkept\n")
        report = bf.backfill(_registry({}))
        report["verified_utc"] = "2026-10-15T00:00:00Z"
        bf.write_doc_section(report, doc)
        text = doc.read_text()
        assert "old text" not in text and text.endswith("## Next\n\nkept\n")
        assert text.count("## Decisions at risk") == 1
        assert "| `ollama:portal5/xyz-aquila-mini:q4_k_m-ctx16k` |" in text
