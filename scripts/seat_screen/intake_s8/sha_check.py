#!/usr/bin/env python3
"""Read-only Gemma 4 26B-A4B check: installed blob vs the upstream checkpoint.

The verdict is taken from the identity a re-pull would change: the installed model-layer
blob digest against the registry's model layer for the tag's base build, with the manifest
digests as a fallback when a local build carries no model layer. The Hugging Face
``lastModified``/``sha`` are reported beside it (the checkpoint the build came from) and
the oMLX twin's repo is reported when the queue names one. Nothing is downloaded, written
or loaded; a missing engine or registry is ``unknown``, never ``stale``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote

import yaml

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import model_upstream as upstream  # noqa: E402

QUEUE = Path(__file__).resolve().parent / "queue.yaml"
EXIT = {"current": 0, "stale": 1, "unknown": 2}


def hf_model(repo: str, fetch: upstream.Fetch) -> dict | None:
    """The repo's current commit and lastModified, or None when upstream cannot be read."""
    url = f"https://huggingface.co/api/models/{quote(repo, safe='/')}"
    status, _headers, body = fetch("GET", url)
    if status != 200:
        return None
    try:
        payload = json.loads(body.decode())
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return {
        "repo": repo,
        "sha": str(payload.get("sha") or ""),
        "last_modified": str(payload.get("lastModified") or ""),
    }


def registry_state(tag: str, fetch: upstream.Fetch) -> tuple[str, str, int]:
    """(model-layer blob digest, manifest digest, HTTP status) for a tag's pullable build."""
    status, headers, body = fetch("GET", upstream.registry_manifest_url(tag))
    if status != 200:
        return "", str(headers.get("ollama-content-digest") or "").strip().lower(), status
    try:
        payload = json.loads(body.decode())
    except json.JSONDecodeError:
        payload = {}
    layers = payload.get("layers") if isinstance(payload, dict) else None
    blob = ""
    for layer in layers or []:
        if (
            isinstance(layer, dict)
            and layer.get("mediaType") == "application/vnd.ollama.image.model"
        ):
            blob = str(layer.get("digest") or "").removeprefix("sha256:").strip().lower()
            break
    manifest = str(headers.get("ollama-content-digest") or "").strip().lower()
    return blob, manifest, status


def check_tag(
    tag: str,
    models: Path,
    fetch: upstream.Fetch,
    run: upstream.Runner | None = None,
    binary: str = "ollama",
) -> dict:
    """One installed seat tag against the registry build it was pulled from."""
    split = upstream.split_derived(tag)
    base = split[0] if split else tag
    manifest = upstream.find_manifest(models, base)
    seat_manifest = upstream.find_manifest(models, tag)
    installed = ""
    if seat_manifest is not None:
        layer = upstream.model_layer(seat_manifest)
        installed = layer[0] if layer is not None else ""
    if not installed:
        installed = upstream.installed_model_sha(models, tag, run, binary)
    report = {
        "tag": tag,
        "base": base,
        "installed_blob": installed,
        "manifest": str(manifest) if manifest is not None else "",
    }
    if not installed and manifest is None and seat_manifest is None:
        return {**report, "verdict": "unknown", "reason": "not installed (no manifest)"}
    registry_blob, registry_manifest, status = registry_state(base, fetch)
    report.update(
        {
            "registry_blob": registry_blob,
            "registry_sha": registry_manifest,
            "registry_status": status,
        }
    )
    if installed and registry_blob:
        same = installed == registry_blob
        reason = "model layer matches the registry" if same else "model layer differs"
        return {**report, "verdict": "current" if same else "stale", "reason": reason}
    if manifest is not None and registry_manifest:
        same = upstream.file_sha256(manifest) == registry_manifest
        reason = "manifest digest matches the registry" if same else "manifest digest differs"
        return {**report, "verdict": "current" if same else "stale", "reason": reason}
    return {
        **report,
        "verdict": "unknown",
        "reason": f"upstream manifest unavailable (HTTP {status})",
    }


def _worst(verdicts: list[str]) -> str:
    for verdict in ("stale", "unknown"):
        if verdict in verdicts:
            return verdict
    return "current" if verdicts else "unknown"


def check_item(
    item: dict,
    models: Path,
    fetch: upstream.Fetch,
    run: upstream.Runner | None = None,
    binary: str = "ollama",
) -> dict:
    """Every tag in one queue item plus the upstream and twin repo metadata."""
    spec = item.get("maintenance") or {}
    tags = [check_tag(tag, models, fetch, run, binary) for tag in spec.get("tags") or []]
    upstream_repo = spec.get("upstream_repo")
    twin_repo = spec.get("omlx_twin_repo")
    return {
        "item": item.get("id", ""),
        "verdict": _worst([tag["verdict"] for tag in tags]),
        "tags": tags,
        "upstream": hf_model(upstream_repo, fetch) if upstream_repo else None,
        "omlx_twin": hf_model(twin_repo, fetch) if twin_repo else None,
    }


def _line(tag: dict) -> str:
    fields = [
        tag["verdict"],
        tag["tag"],
        f"base={tag['base']}",
        f"installed={tag.get('installed_blob') or '-'}",
        f"registry={tag.get('registry_blob') or tag.get('registry_sha') or '-'}",
    ]
    return " ".join(fields) + f" ({tag['reason']})"


def _repo_line(label: str, meta: dict | None) -> str | None:
    if not meta:
        return None
    return f"{label} {meta['repo']} sha={meta['sha'] or '-'} lastModified={meta['last_modified'] or '-'}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=QUEUE)
    parser.add_argument("--item", action="append", dest="items", help="queue item id (repeatable)")
    parser.add_argument("--models", type=Path, help="Ollama models dir (default: resolved)")
    parser.add_argument(
        "--no-ollama", action="store_true", help="skip `ollama show`; read manifests only"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    queue = yaml.safe_load(args.queue.read_text()) or {}
    items = [item for item in queue.get("items") or [] if item.get("kind") == "maintenance"]
    if args.items:
        wanted = set(args.items)
        items = [item for item in queue.get("items") or [] if item.get("id") in wanted]
    models = args.models or upstream.models_dir()
    run = None if args.no_ollama else upstream.default_run
    reports = [
        check_item(item, models, upstream.default_fetch, run, upstream.ollama_bin())
        for item in items
    ]
    if args.json:
        print(json.dumps(reports, indent=2, sort_keys=True))
    else:
        for report in reports:
            print(f"item {report['item']} verdict={report['verdict']}")
            for tag in report["tags"]:
                print(f"  {_line(tag)}")
            for label, meta in (("upstream", report["upstream"]), ("omlx", report["omlx_twin"])):
                line = _repo_line(label, meta)
                if line:
                    print(f"  {line}")
    if not reports:
        print("no maintenance item found", file=sys.stderr)
        return EXIT["unknown"]
    return EXIT[_worst([report["verdict"] for report in reports])]


if __name__ == "__main__":
    raise SystemExit(main())
