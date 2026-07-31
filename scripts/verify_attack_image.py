#!/usr/bin/env python3
"""Verify and fingerprint the lab-exercise attack image contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def verify(contract_path: Path) -> dict:
    raw = contract_path.read_bytes()
    contract = json.loads(raw)
    tools = {name: shutil.which(name) is not None for name in contract["tools"]}
    files = {name: Path(name).exists() for name in contract["files"]}
    return {
        "schema_version": contract["schema_version"],
        "mode": contract["mode"],
        "contract_sha256": hashlib.sha256(raw).hexdigest(),
        "tools": tools,
        "files": files,
        "ready": all(tools.values()) and all(files.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    result = verify(args.contract)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.manifest:
        args.manifest.write_text(rendered + "\n")
    print(rendered)
    if not result["ready"]:
        missing_tools = [name for name, present in result["tools"].items() if not present]
        missing_files = [name for name, present in result["files"].items() if not present]
        print(f"missing tools: {missing_tools}")
        print(f"missing files: {missing_files}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
