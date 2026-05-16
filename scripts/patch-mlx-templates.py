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

Fix:
  Read the chat_template.jinja content and write it as
  tokenizer_config.json["chat_template"]. This is the same content the
  tokenizer authors intended — the jinja file IS the authoritative template.

Run after any model download:
    python3 scripts/patch-mlx-templates.py

The script is idempotent — safe to re-run. It backs up each tokenizer_config.json
the first time it is patched (.bak suffix).
"""

import glob
import json
import os
import shutil
import sys

HF_CACHE = os.path.expanduser("~/.cache/huggingface/hub")


def patch_all(cache_dir: str = HF_CACHE) -> tuple[list[str], list[str], list[str]]:
    patched: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for jinja_path in sorted(glob.glob(f"{cache_dir}/**/chat_template.jinja", recursive=True)):
        snap_dir = os.path.dirname(jinja_path)
        cfg_path = os.path.join(snap_dir, "tokenizer_config.json")

        if not os.path.exists(cfg_path):
            continue

        try:
            with open(cfg_path) as f:
                cfg = json.load(f)

            if cfg.get("chat_template"):
                model_name = _model_name(snap_dir)
                skipped.append(model_name)
                continue

            with open(jinja_path) as f:
                template = f.read()

            bak_path = cfg_path + ".bak"
            if not os.path.exists(bak_path):
                shutil.copy(cfg_path, bak_path)

            cfg["chat_template"] = template
            with open(cfg_path, "w") as f:
                json.dump(cfg, f, indent=2)

            patched.append(_model_name(snap_dir))

        except Exception as exc:
            errors.append(f"{snap_dir}: {exc}")

    return patched, skipped, errors


def _model_name(snap_dir: str) -> str:
    try:
        return snap_dir.split("models--")[1].split("/snapshots")[0].replace("--", "/")
    except IndexError:
        return snap_dir


def main() -> None:
    patched, skipped, errors = patch_all()

    if patched:
        print(f"Patched {len(patched)} model(s):")
        for m in patched:
            print(f"  ✓ {m}")
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
    print(f"\n{total} model(s) checked — all have chat_template embedded.")


if __name__ == "__main__":
    main()
