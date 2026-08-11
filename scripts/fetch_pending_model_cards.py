#!/usr/bin/env python3
"""Fetch model cards for every pending-verdict tag; cache locally so the
analysis report can compare 'what the card advertises' against 'what
portal.yaml says we slotted it for'.

Why this exists: TPS-and-quality bench numbers don't tell us whether we
tested the model for what it's actually built to do. A CUA model benched
as general chat wasn't really evaluated. A security tooling model benched
against a chat scorer wasn't really evaluated. Without the card claims in
hand, we can't tell whether a decline verdict is fair or premature.

Cache layout:
    reports/model_cards/<sha256(tag)[:16]>.card.md     raw fetched text
    reports/model_cards/<sha256(tag)[:16]>.meta.json   fetch metadata

Idempotent: skips tags already cached unless --refresh is passed.
Rate-limited: 0.5s between fetches. Runs cold in ~45s for 60 tags.
Graceful: private/gated/404/removed tags record a meta with status but
never crash the run.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / "config" / "PENDING_MODEL_VERDICTS.md"
CACHE_DIR = REPO_ROOT / "reports" / "model_cards"

ENTRY_RE = re.compile(r"^- \[[x ]\] `([^`]+)` — [\d.]+ GB")
FETCH_TIMEOUT = 15
POLITE_SLEEP = 0.5


def parse_ledger_tags() -> list[str]:
    if not LEDGER_PATH.exists():
        return []
    tags = []
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        m = ENTRY_RE.match(line)
        if m:
            tags.append(m.group(1))
    return tags


def tag_hash(tag: str) -> str:
    return hashlib.sha256(tag.encode("utf-8")).hexdigest()[:16]


def derive_card_url(tag: str) -> tuple[str | None, list[str]]:
    """Given a tag, return (primary_url, fallback_urls). None for
    unfetchable tags (local builds)."""
    lower = tag.lower()

    if lower.startswith("portal5/"):
        return None, []

    if lower.startswith("hf.co/"):
        # hf.co/<org>/<repo>[:<file-or-quant>]
        rest = tag[6:]
        # Strip the ':<file>' segment — that's a quant selector, not part of URL
        repo_part = rest.split(":", 1)[0]
        # <org>/<repo>
        if repo_part.count("/") >= 1:
            org_repo = "/".join(repo_part.split("/")[:2])
            primary = f"https://huggingface.co/{org_repo}/raw/main/README.md"
            fallback = [
                f"https://huggingface.co/{org_repo}/resolve/main/README.md",
                f"https://huggingface.co/{org_repo}/raw/master/README.md",
            ]
            return primary, fallback
        return None, []

    # Namespaced ollama library: <vendor>/<name>[:tag]
    if "/" in tag:
        base = tag.split(":", 1)[0]  # <vendor>/<name>
        return f"https://ollama.com/{base}", []

    # Bare ollama library: <name>[:tag]
    base = tag.split(":", 1)[0]
    return f"https://ollama.com/library/{base}", []


def curl_fetch(url: str) -> tuple[int, str]:
    """Fetch a URL via curl. Returns (http_status, body). Non-2xx → empty
    body but real status. curl failures → (0, error message)."""
    try:
        r = subprocess.run(
            [
                "curl",
                "-sSL",
                "--max-time",
                str(FETCH_TIMEOUT),
                "-w",
                "\n---HTTP_STATUS:%{http_code}---\n",
                "-A",
                "Portal5-Model-Card-Fetcher/1 (analysis only)",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=FETCH_TIMEOUT + 5,
        )
    except subprocess.TimeoutExpired:
        return 0, "TIMEOUT"
    except Exception as e:
        return 0, f"CURL_ERROR: {e}"

    body = r.stdout
    m = re.search(r"---HTTP_STATUS:(\d+)---", body)
    status = int(m.group(1)) if m else 0
    if m:
        body = body[: m.start()].rstrip()
    return status, body


def fetch_card(tag: str) -> dict:
    """Try primary URL then fallbacks. Return a meta record."""
    primary, fallbacks = derive_card_url(tag)
    if primary is None:
        return {
            "tag": tag,
            "status": "skipped-local-build",
            "url": None,
            "fetched_at": _dt.datetime.now(_dt.UTC).isoformat(),
            "body_size": 0,
        }

    code = 0
    for url in [primary, *fallbacks]:
        code, body = curl_fetch(url)
        if code == 200 and body.strip():
            return {
                "tag": tag,
                "status": "ok",
                "url": url,
                "http_code": code,
                "fetched_at": _dt.datetime.now(_dt.UTC).isoformat(),
                "body_size": len(body),
                "body": body,
            }
        if code in (401, 403):
            return {
                "tag": tag,
                "status": "gated-or-forbidden",
                "url": url,
                "http_code": code,
                "fetched_at": _dt.datetime.now(_dt.UTC).isoformat(),
                "body_size": 0,
            }
        # 404 or other — try next fallback
    return {
        "tag": tag,
        "status": "not-found",
        "url": primary,
        "http_code": code if primary else None,
        "fetched_at": _dt.datetime.now(_dt.UTC).isoformat(),
        "body_size": 0,
    }


def load_cached_meta(tag: str) -> dict | None:
    meta_p = CACHE_DIR / f"{tag_hash(tag)}.meta.json"
    if not meta_p.exists():
        return None
    try:
        return json.loads(meta_p.read_text())
    except Exception:
        return None


def write_cache(tag: str, meta: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    h = tag_hash(tag)
    body = meta.pop("body", "")
    (CACHE_DIR / f"{h}.card.md").write_text(body)
    (CACHE_DIR / f"{h}.meta.json").write_text(json.dumps(meta, indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch model cards for pending verdicts.")
    ap.add_argument("--refresh", action="store_true", help="Re-fetch cached tags (default: skip)")
    ap.add_argument("--limit", type=int, default=None, help="Cap total fetches this run")
    args = ap.parse_args(argv)

    tags = parse_ledger_tags()
    print(f"Parsed {len(tags)} tags from ledger")

    status_counts: dict[str, int] = {}
    n_fetched = 0
    n_cached = 0
    n_skipped = 0

    for i, tag in enumerate(tags, 1):
        if args.limit and n_fetched >= args.limit:
            print(f"  hit --limit {args.limit}; stopping")
            break

        cached = load_cached_meta(tag)
        if cached and not args.refresh:
            status_counts[cached["status"]] = status_counts.get(cached["status"], 0) + 1
            n_cached += 1
            continue

        print(f"  [{i}/{len(tags)}] {tag[:80]}...", end=" ", flush=True)
        meta = fetch_card(tag)
        write_cache(tag, meta)
        status_counts[meta["status"]] = status_counts.get(meta["status"], 0) + 1
        print(meta["status"])
        n_fetched += 1
        if meta["status"] not in ("skipped-local-build",):
            time.sleep(POLITE_SLEEP)

    print(f"\nFetched: {n_fetched}, cached-hit: {n_cached}, skipped-local: {n_skipped}")
    print("Status histogram:")
    for s, n in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"  {s}: {n}")
    print(f"\nCache dir: {CACHE_DIR.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
