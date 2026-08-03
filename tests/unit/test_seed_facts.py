"""Tests for portal/platform/wiki/adapters/seed_facts.py helpers."""

from __future__ import annotations

from portal.platform.wiki.adapters.seed_facts import _group_models


class TestGroupModelsUnion:
    """P5-FUT-013 B2: two backend entries can share one `group:` name
    (oMLX + Ollama both declaring `group: coding`, engine preference
    expressed via `priority:`). _group_models must union their models,
    not let the later entry clobber the earlier one's.
    """

    def test_two_backends_same_group_union_not_clobber(self):
        cfg = {
            "backends": [
                {"group": "coding", "id": "ollama-coding", "models": ["a", "b", "c"]},
                {"group": "coding", "id": "omlx-coding", "models": ["d", "e"]},
            ]
        }
        groups = _group_models(cfg)
        assert groups["coding"] == {"a", "b", "c", "d", "e"}

    def test_dict_form_models_union_across_same_group(self):
        cfg = {
            "backends": [
                {
                    "group": "coding",
                    "id": "ollama-coding",
                    "models": [{"id": "a", "supports_tools": True}],
                },
                {
                    "group": "coding",
                    "id": "omlx-coding",
                    "models": [{"id": "b", "supports_tools": True}],
                },
            ]
        }
        groups = _group_models(cfg)
        assert groups["coding"] == {"a", "b"}

    def test_distinct_groups_stay_separate(self):
        cfg = {
            "backends": [
                {"group": "coding", "id": "ollama-coding", "models": ["a"]},
                {"group": "vision", "id": "ollama-vision", "models": ["b"]},
            ]
        }
        groups = _group_models(cfg)
        assert groups == {"coding": {"a"}, "vision": {"b"}}
