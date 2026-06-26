#!/usr/bin/env python3
"""Embed chat_template.jinja into tokenizer_config.json for MLX models.

Problem:
  Many mlx-community and third-party MLX model quantizations ship a
  chat_template.jinja file alongside tokenizer_config.json, but do NOT
  include the chat_template key inside tokenizer_config.json.

  mlx_lm.server (and transformers) loads the template from
  tokenizer_config.json["chat_template"]. When that key is missing,
  tokenizer.has_tool_calling = False, which causes two failure modes:

    1. Silent tool ignore: the model receives a request with `tools` in the
       body, the server skips tool formatting, and the model responds in plain
       text without ever emitting a tool_call token.

    2. Server disconnect: some models raise an unhandled exception when
       apply_chat_template is called with tools= but no template, causing
       the HTTP connection to drop with no response.

Fix 1 - Template embedding:
  Read the chat_template.jinja content and write it as
  tokenizer_config.json["chat_template"]. This is the same content the
  tokenizer authors intended -- the jinja file IS the authoritative template.

Fix 2 - Parser type correction:
  Some models ship with tool_parser_type=laguna but their chat templates use
  the GLM-style <arg_key>/<arg_value> XML format. The laguna parser expects
  JSON inside <tool_call> tags and fails silently for these models.
  We correct those models to use tool_parser_type=glm47, which handles the
  XML format correctly. Both parsers use identical tool_call_start/end tokens.

Run after any model download:
    python3 scripts/patch-mlx-templates.py

The script is idempotent -- safe to re-run. It backs up each tokenizer_config.json
the first time it is patched (.bak suffix).
"""

import glob
import json
import os
import shutil
import sys

HF_CACHE = os.path.expanduser("~/.cache/huggingface/hub")

# Models whose tool_parser_type=laguna is incorrect -- they use GLM XML format.
# The laguna parser expects JSON; the glm47 parser handles <arg_key>/<arg_value>.
_LAGUNA_TO_GLM47 = {
    "mlx-community/Laguna-XS.2-4bit",
    "mlx-community/Laguna-Small.4-4bit",
    "mlx-community/Laguna-Small.4-8bit",
}


def _model_name(snap_dir: str) -> str:
    try:
        return snap_dir.split("models--")[1].split("/snapshots")[0].replace("--", "/")
    except IndexError:
        return snap_dir


def _fix_parser_type(cfg: dict, model_name: str) -> bool:
    """Return True if a parser-type correction was made."""
    if cfg.get("tool_parser_type") != "laguna":
        return False
    ct = cfg.get("chat_template", "")
    # Correct laguna models that actually output GLM XML format
    if model_name in _LAGUNA_TO_GLM47 or "<arg_key>" in ct:
        cfg["tool_parser_type"] = "glm47"
        return True
    return False


def patch_all(cache_dir: str = HF_CACHE) -> tuple[list[str], list[str], list[str]]:
    patched: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    # Pass 1: embed chat templates (models with a .jinja file)
    for jinja_path in sorted(glob.glob(f"{cache_dir}/**/chat_template.jinja", recursive=True)):
        snap_dir = os.path.dirname(jinja_path)
        cfg_path = os.path.join(snap_dir, "tokenizer_config.json")

        if not os.path.exists(cfg_path):
            continue

        try:
            with open(cfg_path) as f:
                cfg = json.load(f)

            model_name = _model_name(snap_dir)
            changed = False

            if not cfg.get("chat_template"):
                with open(jinja_path) as f:
                    template = f.read()
                cfg["chat_template"] = template
                changed = True

            # TokenizersBackend is not a standard HF tokenizer class and is
            # not recognised by mlx_lm — models converted via mlx_lm.convert
            # from a huggingface_hub tokenizers-backed checkpoint inherit this
            # value and fail to load. PreTrainedTokenizerFast is the correct
            # class for BPE-based fast tokenizers.
            if cfg.get("tokenizer_class") == "TokenizersBackend":
                cfg["tokenizer_class"] = "PreTrainedTokenizerFast"
                cfg.pop("backend", None)
                cfg.pop("is_local", None)
                cfg.pop("local_files_only", None)
                changed = True

            if _fix_parser_type(cfg, model_name):
                changed = True

            if not changed:
                skipped.append(model_name)
                continue

            bak_path = cfg_path + ".bak"
            if not os.path.exists(bak_path):
                shutil.copy(cfg_path, bak_path)

            with open(cfg_path, "w") as f:
                json.dump(cfg, f, indent=2)

            patched.append(model_name)

        except Exception as exc:
            errors.append(f"{snap_dir}: {exc}")

    # Pass 2: fix parser type on models with already-embedded template (no .jinja file)
    for cfg_path in sorted(glob.glob(f"{cache_dir}/**/tokenizer_config.json", recursive=True)):
        snap_dir = os.path.dirname(cfg_path)
        jinja_path = os.path.join(snap_dir, "chat_template.jinja")
        if os.path.exists(jinja_path):
            continue  # already handled in Pass 1

        try:
            with open(cfg_path) as f:
                cfg = json.load(f)

            model_name = _model_name(snap_dir)
            if not _fix_parser_type(cfg, model_name):
                continue

            bak_path = cfg_path + ".bak"
            if not os.path.exists(bak_path):
                shutil.copy(cfg_path, bak_path)

            with open(cfg_path, "w") as f:
                json.dump(cfg, f, indent=2)

            patched.append(f"{model_name} [parser-fix]")

        except Exception as exc:
            errors.append(f"{snap_dir}: {exc}")

    return patched, skipped, errors


def main() -> None:
    patched, skipped, errors = patch_all()

    if patched:
        print(f"Patched {len(patched)} model(s):")
        for m in patched:
            print(f"  + {m}")
    else:
        print("No models needed patching.")

    if skipped:
        print(f"\nSkipped {len(skipped)} (already have embedded template):")
        for s in skipped:
            print(f"  - {s}")

    if errors:
        print(f"\nErrors ({len(errors)}):", file=sys.stderr)
        for e in errors:
            print(f"  ! {e}", file=sys.stderr)
        sys.exit(1)

    total = len(patched) + len(skipped)
    print(f"\n{total} model(s) checked -- all have chat_template embedded.")


if __name__ == "__main__":
    main()
