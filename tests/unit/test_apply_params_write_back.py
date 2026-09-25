"""`portal models apply-params` write-back: base workspaces and variants."""

from __future__ import annotations

from portal.platform.inference import config as cfg_mod
from portal.platform.inference.cli.models import _write_back_model_hints

YAML = """\
workspaces:
  auto-coding:
    module: coding
    model_hint: base:tag
    variants:
      laguna:
        name: L
        model_hint: lag:tag
        context_limit: 131072
      fast-repair:
        model_hint: kat:tag
  auto-other:
    model_hint: other:tag
    variants:
      laguna:
        model_hint: untouched:tag
"""


def _run(tmp_path, monkeypatch, updates):
    p = tmp_path / "portal.yaml"
    p.write_text(YAML)
    monkeypatch.setattr(cfg_mod, "PORTAL_YAML", p)
    _write_back_model_hints(updates)
    return p.read_text()


def test_variant_hint_rewritten_only_in_its_workspace(tmp_path, monkeypatch):
    out = _run(tmp_path, monkeypatch, {"auto-coding::laguna": "lag:tag-ctx128k"})
    assert "        model_hint: lag:tag-ctx128k\n" in out
    assert "model_hint: untouched:tag" in out
    assert "    model_hint: base:tag\n" in out
    assert "model_hint: kat:tag" in out


def test_base_and_variant_together(tmp_path, monkeypatch):
    out = _run(
        tmp_path,
        monkeypatch,
        {"auto-coding": "base:tag-ctx8k", "auto-coding::fast-repair": "kat:tag-ctx32k"},
    )
    assert "    model_hint: base:tag-ctx8k\n" in out
    assert "        model_hint: kat:tag-ctx32k\n" in out
    assert "        model_hint: lag:tag\n" in out
    assert "    model_hint: other:tag\n" in out
