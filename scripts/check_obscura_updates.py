#!/usr/bin/env python3
"""Check the pinned Obscura browser backend against upstream.

Portal 5's browser MCP (``deploy/browser-mcp/Dockerfile``) builds Obscura from a
pinned commit (``OBSCURA_REF``). Obscura is a fast-moving Rust headless browser;
we want to stay current with its fixes and security advisories without tracking a
moving ref. This script compares the pin against upstream and reports:

- how many commits / how many days behind ``main`` the pin is
- the newest release tag
- any published GitHub security advisories for the repo

Exit code 0 always (it is a report, not a gate). Sends a Pushover push when
``PUSHOVER_API_TOKEN`` + ``PUSHOVER_USER_KEY`` are set AND there is something to
act on (pin is behind, or an advisory exists). Intended to run weekly from cron:

    0 13 * * 1  cd /Users/chris/projects/portal-5 && .venv/bin/python scripts/check_obscura_updates.py

No third-party deps — stdlib urllib only. Honors ``GITHUB_TOKEN`` for a higher
API rate limit but does not require it.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "h4ckf0r0day/obscura"
DOCKERFILE = Path(__file__).resolve().parent.parent / "deploy" / "browser-mcp" / "Dockerfile"
_API = "https://api.github.com"


def _get(url: str) -> dict | list:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - fixed api.github.com host
        return json.loads(r.read().decode())


def _pinned_ref() -> str:
    text = DOCKERFILE.read_text()
    m = re.search(r"ARG OBSCURA_REF=([0-9a-fA-F]{7,40})", text)
    if not m:
        sys.exit(f"could not find 'ARG OBSCURA_REF=<sha>' in {DOCKERFILE}")
    return m.group(1)


def _pushover(title: str, message: str) -> None:
    tok = os.environ.get("PUSHOVER_API_TOKEN", "")
    usr = os.environ.get("PUSHOVER_USER_KEY", "")
    if not (tok and usr):
        return
    data = urllib.parse.urlencode(
        {"token": tok, "user": usr, "title": title, "message": message[:1024]}
    ).encode()
    try:
        urllib.request.urlopen(  # noqa: S310 - fixed api.pushover.net host
            "https://api.pushover.net/1/messages.json", data=data, timeout=15
        )
    except urllib.error.URLError as e:
        print(f"pushover send failed: {e}", file=sys.stderr)


def main() -> int:
    pin = _pinned_ref()
    lines: list[str] = [f"Obscura pin: {pin[:12]}"]
    actionable = False

    try:
        compare = _get(f"{_API}/repos/{REPO}/compare/{pin}...main")
        behind = compare.get("behind_by", 0)
        ahead = compare.get("ahead_by", 0)
        head_sha = compare.get("commits", [{}])[-1].get("sha", "?")[:12] if behind else pin[:12]
        if behind:
            actionable = True
            newest_date = compare["commits"][-1]["commit"]["committer"]["date"][:10]
            lines.append(
                f"BEHIND main by {behind} commit(s) (ahead {ahead}); "
                f"main HEAD {head_sha} @ {newest_date}"
            )
            subjects = [c["commit"]["message"].splitlines()[0] for c in compare["commits"][-10:]]
            lines.append("recent upstream commits:")
            lines += [f"  - {s[:100]}" for s in subjects]
        else:
            lines.append("up to date with main")
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
        lines.append(f"compare check failed: {e}")

    try:
        tags = _get(f"{_API}/repos/{REPO}/tags")
        if tags:
            newest_tag = tags[0]["name"]
            tag_sha = tags[0]["commit"]["sha"][:12]
            marker = " (== our pin)" if tags[0]["commit"]["sha"].startswith(pin[:12]) else ""
            lines.append(f"newest release tag: {newest_tag} @ {tag_sha}{marker}")
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError) as e:
        lines.append(f"tag check failed: {e}")

    try:
        advisories = _get(f"{_API}/repos/{REPO}/security-advisories")
        published = [a for a in advisories if a.get("state") == "published"]
        if published:
            actionable = True
            lines.append(f"SECURITY ADVISORIES: {len(published)} published")
            for a in published[:5]:
                lines.append(f"  - {a.get('ghsa_id')}: {a.get('summary', '')[:120]}")
        else:
            lines.append("no published security advisories")
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
        # 404 = advisories not enabled for the repo; treat as "none"
        lines.append(f"advisory check: {e}")

    report = "\n".join(lines)
    print(report)

    if actionable:
        _pushover("Obscura pin needs review", report)
        print("\n-> actionable: bump ARG OBSCURA_REF in deploy/browser-mcp/Dockerfile,")
        print(
            "   rebuild browser-mcp, re-run the Phase 0 smoke (see TASK_A_OBSCURA_BROWSER_V1.md)."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
