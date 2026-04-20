#!/usr/bin/env python3
"""
Convert JANG model safetensors key names to mlx_vlm-compatible format.

The JANG model has format:mlx metadata (so mlx_vlm skips sanitize) but
uses PyTorch-style keys with model. prefix. This script remaps the headers:
  model.language_model.X  ->  language_model.model.X
  model.vision_tower.X    ->  vision_tower.X
  model.embed_vision.X    ->  embed_vision.X

Only headers are rewritten; tensor data bytes are streamed unchanged.

Also patches config.json to set audio_config: null. mlx_vlm 0.4.4 calls
config.setdefault("audio_config", {}) unconditionally, which creates an
AudioEncoder with default weights — but JANG has no audio tower weights.
Setting audio_config explicitly to null (JSON null) prevents setdefault from
injecting the empty dict, keeping audio_tower=None and skipping the 752
missing-parameter error.
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
        print("    Already converted, skipping.")
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
        print("\n  Updating index: model.safetensors.index.json")
        with open(index_path) as f:
            index = json.load(f)
        old_map = index.get("weight_map", {})
        new_map = {remap_key(k): v for k, v in old_map.items()}
        index["weight_map"] = new_map
        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)
        print(f"    Done. {len(old_map)} -> {len(new_map)} entries")

    # Patch config.json with two fixes:
    #
    # Fix 1: audio_config: null
    #   mlx_vlm 0.4.4 calls config.setdefault("audio_config", {}) unconditionally,
    #   which creates an AudioEncoder with all-default weights. JANG has no audio tower
    #   weights, causing 752 missing-parameter errors on load_weights(). Setting the
    #   key explicitly to null prevents setdefault from injecting the empty dict.
    #
    # Fix 2: quantization.bits = 8 (not 4)
    #   The JANG weights are stored as U32 with pack_factor=4 (4 bytes per U32 =
    #   8-bit quantization). The config.json incorrectly declares bits=4 (pack_factor=8),
    #   which makes mlx expect weight shape (out, in//8) instead of (out, in//4),
    #   causing shape mismatches on every attention/MLP projection.
    cfg_path = os.path.join(snap, "config.json")
    if os.path.exists(cfg_path):
        print("\n  Patching config.json")
        with open(cfg_path) as f:
            cfg = json.load(f)
        changed = False
        if cfg.get("audio_config") is not None:
            cfg["audio_config"] = None
            changed = True
            print("    audio_config set to null")
        else:
            print("    audio_config already null")
        q = cfg.get("quantization", {})
        # Fix 2b: mixed-precision — attention layers use 8-bit packing (pack_factor=4),
        # embed/MLP use 4-bit (pack_factor=8). Set default bits=4 and add override.
        if q.get("bits") != 4:
            cfg.setdefault("quantization", {})["bits"] = 4
            changed = True
            print(f"    quantization.bits: {q.get('bits')} -> 4 (embed/MLP)")
        else:
            print("    quantization.bits already 4")
        if cfg.get("quantization_bits_per_layer_type", {}).get("self_attn") != 8:
            cfg["quantization_bits_per_layer_type"] = {"self_attn": 8}
            changed = True
            print("    quantization_bits_per_layer_type: {self_attn: 8} (attention override)")
        else:
            print("    quantization_bits_per_layer_type already set")
        if changed:
            with open(cfg_path, "w") as f:
                json.dump(cfg, f, indent=2)
            print("    Written.")

    print("\nConversion complete.")


if __name__ == "__main__":
    main()
