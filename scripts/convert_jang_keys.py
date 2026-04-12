#!/usr/bin/env python3
"""
Convert JANG model safetensors key names to mlx_vlm-compatible format.

The JANG model has format:mlx metadata (so mlx_vlm skips sanitize) but
uses PyTorch-style keys with model. prefix. This script remaps the headers:
  model.language_model.X  ->  language_model.model.X
  model.vision_tower.X    ->  vision_tower.X
  model.embed_vision.X    ->  embed_vision.X

Only headers are rewritten; tensor data bytes are streamed unchanged.
"""

import glob
import json
import os
import struct
import sys


def remap_key(key: str) -> str:
    if key == "__metadata__":
        return key
    # Strip model. prefix
    if key.startswith("model."):
        key = key[len("model."):]
    # language_model.X -> language_model.model.X (but not language_model.model.X)
    if key.startswith("language_model.") and not key.startswith("language_model.model."):
        key = "language_model.model." + key[len("language_model."):]
    return key


def convert_file(path: str) -> None:
    print(f"  Converting: {os.path.basename(path)}")
    with open(path, "rb") as f:
        header_len_bytes = f.read(8)
        header_len = struct.unpack("<Q", header_len_bytes)[0]
        header_bytes = f.read(header_len)
        tensor_data = f.read()  # stream rest unchanged

    header = json.loads(header_bytes)

    # Check if already converted
    sample = next((k for k in header if k != "__metadata__"), None)
    if sample and not sample.startswith("model."):
        print(f"    Already converted, skipping.")
        return

    new_header = {remap_key(k): v for k, v in header.items()}

    new_header_bytes = json.dumps(new_header, separators=(",", ":")).encode("utf-8")
    new_header_len = len(new_header_bytes)

    tmp_path = path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(struct.pack("<Q", new_header_len))
        f.write(new_header_bytes)
        f.write(tensor_data)

    os.replace(tmp_path, path)
    print(f"    Done. Header: {header_len} -> {new_header_len} bytes, "
          f"tensor data: {len(tensor_data):,} bytes")


def main() -> None:
    model_dir = os.path.expanduser(
        "~/.cache/huggingface/hub/models--dealignai--Gemma-4-31B-JANG_4M-CRACK"
    )
    snapshots = glob.glob(os.path.join(model_dir, "snapshots", "*"))
    if not snapshots:
        print(f"No snapshots found in {model_dir}", file=sys.stderr)
        sys.exit(1)

    snap = snapshots[0]
    files = sorted(glob.glob(os.path.join(snap, "*.safetensors")))
    if not files:
        print(f"No safetensors files found in {snap}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(files)} safetensors file(s) in:\n  {snap}\n")
    for f in files:
        convert_file(f)

    # Also remap model.safetensors.index.json if present
    index_path = os.path.join(snap, "model.safetensors.index.json")
    if os.path.exists(index_path):
        print(f"\n  Updating index: model.safetensors.index.json")
        with open(index_path) as f:
            index = json.load(f)
        old_map = index.get("weight_map", {})
        new_map = {remap_key(k): v for k, v in old_map.items()}
        index["weight_map"] = new_map
        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)
        print(f"    Done. {len(old_map)} -> {len(new_map)} entries")

    print("\nConversion complete.")


if __name__ == "__main__":
    main()
