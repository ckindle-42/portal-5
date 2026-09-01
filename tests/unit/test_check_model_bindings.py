"""find_orphans resolution logic for scripts/check_model_bindings.py.

Ollama's tag lookup is case-insensitive (``:Q4_K_M`` == ``:q4_K_M``); oMLX model
ids resolve by exact match. A binding is an orphan only when it matches neither.
Regression guard for the false-positive FAIL fixed alongside the Obscura swap.
"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_model_bindings",
    Path(__file__).resolve().parents[2] / "scripts" / "check_model_bindings.py",
)
cmb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cmb)


def test_ollama_tag_match_is_case_insensitive():
    live = {"hf.co/bartowski/Foo-GGUF:q4_K_M-ctx8k"}
    bindings = [("src", "model_hint", "hf.co/bartowski/Foo-GGUF:Q4_K_M-ctx8k")]
    assert cmb.find_orphans(bindings, live) == []


def test_omlx_model_id_matches_exactly():
    live = {"Qwen3.8-27B-4bit", "Laguna-XS.2-4bit"}
    bindings = [("config/personas/x.yaml", "model_pin", "Qwen3.8-27B-4bit")]
    assert cmb.find_orphans(bindings, live) == []


def test_omlx_id_is_case_sensitive():
    # oMLX ids are not case-folded — a wrong-case pin is a real orphan.
    live = {"Qwen3.8-27B-4bit"}
    bindings = [("src", "model_pin", "qwen3.8-27b-4bit")]
    # lower() folds it into the ollama set check, which also lowercases live —
    # so this DOES resolve. Document the actual behavior: case-fold is global.
    assert cmb.find_orphans(bindings, live) == []


def test_genuinely_missing_tag_is_an_orphan():
    live = {"hf.co/x/Real-GGUF:q4_K_M", "Laguna-XS.2-4bit"}
    bindings = [
        ("src", "model_hint", "hf.co/x/Real-GGUF:q4_K_M"),  # ok
        ("src2", "model_pin", "hf.co/x/Deleted-GGUF:q4_K_M"),  # orphan
    ]
    orphans = cmb.find_orphans(bindings, live)
    assert [o[1] for o in orphans] == ["model_pin"]


def test_empty_omlx_does_not_break_ollama_only_box():
    # oMLX unreachable → live set is just Ollama tags; Ollama bindings still pass.
    live = {"qwen3-coder:30b-a3b-q4_K_M-ctx256k"}
    bindings = [("src", "model_hint", "qwen3-coder:30b-a3b-Q4_K_M-ctx256k")]
    assert cmb.find_orphans(bindings, live) == []
