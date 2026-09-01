#!/usr/bin/env python3
"""Check Portal 5's hand-pinned external components against upstream.

Covers the Obscura browser ref (``ARG OBSCURA_REF`` in
``deploy/browser-mcp/Dockerfile``), Ollama (``~/ollama-current`` symlink), and
the oMLX brew formula (``jundot/omlx/omlx``). Reports how far behind each pin is
and — the point of it — flags gaps that include a security fix or a published
GitHub advisory, so a "review later" bump can be promoted to "do this now".

Report, not a gate; exit 0 always. Sends a Pushover push (high-priority when
security-flagged) when a component is behind and ``PUSHOVER_API_TOKEN`` +
``PUSHOVER_USER_KEY`` are set. Weekly launchd job
``com.portal5.update-check.plist``; accepts a component subset, e.g.
``check_updates.py ollama omlx``. Stdlib only + ``brew``; honors ``GITHUB_TOKEN``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "deploy" / "browser-mcp" / "Dockerfile"
OLLAMA_CURRENT = Path.home() / "ollama-current"
_API = "https://api.github.com"

# Substrings that mark a changelog / release-notes line as security-relevant.
_SECURITY_RE = re.compile(
    r"\b(cve-\d{4}-\d+|ghsa-[a-z0-9-]+|security|vulnerab|exploit|rce\b|"
    r"denial of service|dos\b|sandbox escape|path traversal|ssrf|xxe)\b",
    re.IGNORECASE,
)


@dataclass
class Report:
    name: str
    current: str = "?"
    latest: str = "?"
    status: str = "unknown"  # "current" | "behind" | "unknown"
    security: bool = False
    lines: list[str] = field(default_factory=list)

    @property
    def actionable(self) -> bool:
        return self.status == "behind"


def _get(url: str) -> dict | list:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - fixed api.github.com host
        return json.loads(r.read().decode())


def _semver(tag: str) -> tuple[int, ...]:
    """'v0.33.2' / 'ollama-0.33.2' -> (0, 33, 2); non-numeric parts drop out."""
    nums = re.findall(r"\d+", tag)
    return tuple(int(n) for n in nums[:3]) or (0,)


def _advisories(repo: str, report: Report) -> None:
    try:
        adv = _get(f"{_API}/repos/{repo}/security-advisories")
        published = [a for a in adv if a.get("state") == "published"]
        if published:
            report.security = True
            report.lines.append(f"SECURITY ADVISORIES: {len(published)} published")
            for a in published[:5]:
                report.lines.append(f"  - {a.get('ghsa_id')}: {a.get('summary', '')[:120]}")
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
        # 404 = advisories not enabled for the repo; treat as "none".
        report.lines.append(f"advisory check: {e}")


def _release_gap(repo: str, current: tuple[int, ...], report: Report) -> None:
    """Fill latest tag + a security scan of release notes newer than `current`."""
    try:
        releases = _get(f"{_API}/repos/{repo}/releases?per_page=20")
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        report.lines.append(f"release check failed: {e}")
        return
    releases = [r for r in releases if not r.get("draft")]
    if not releases:
        report.lines.append("no releases found")
        return
    latest = releases[0]
    report.latest = latest["tag_name"]
    if _semver(report.latest) <= current:
        report.status = "current"
        report.lines.append(f"up to date (latest {report.latest})")
        return
    report.status = "behind"
    newer = [r for r in releases if _semver(r["tag_name"]) > current]
    report.lines.append(
        f"BEHIND: {report.current} -> {report.latest} ({len(newer)} release(s) back)"
    )
    for r in newer[:8]:
        hits = sorted({m.group(0).lower() for m in _SECURITY_RE.finditer(r.get("body") or "")})
        mark = f"  [SECURITY: {', '.join(hits)}]" if hits else ""
        if hits:
            report.security = True
        report.lines.append(f"  - {r['tag_name']} ({r.get('published_at', '?')[:10]}){mark}")


def check_obscura() -> Report:
    rep = Report("obscura")
    text = DOCKERFILE.read_text()
    m = re.search(r"ARG OBSCURA_REF=([0-9a-fA-F]{7,40})", text)
    if not m:
        rep.lines.append(f"could not find 'ARG OBSCURA_REF=<sha>' in {DOCKERFILE}")
        return rep
    pin = m.group(1)
    rep.current = pin[:12]
    try:
        compare = _get(f"{_API}/repos/h4ckf0r0day/obscura/compare/{pin}...main")
        behind = compare.get("behind_by", 0)
        if behind:
            rep.status = "behind"
            head = compare["commits"][-1]
            rep.latest = head["sha"][:12]
            rep.lines.append(
                f"BEHIND main by {behind} commit(s); HEAD {rep.latest} "
                f"@ {head['commit']['committer']['date'][:10]}"
            )
            for c in compare["commits"][-10:]:
                subj = c["commit"]["message"].splitlines()[0]
                mark = "  [SECURITY]" if _SECURITY_RE.search(subj) else ""
                if mark:
                    rep.security = True
                rep.lines.append(f"  - {subj[:100]}{mark}")
        else:
            rep.status = "current"
            rep.latest = rep.current
            rep.lines.append("up to date with main")
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
        rep.lines.append(f"compare check failed: {e}")
    _advisories("h4ckf0r0day/obscura", rep)
    return rep


def check_ollama() -> Report:
    rep = Report("ollama")
    if OLLAMA_CURRENT.is_symlink():
        rep.current = re.sub(r"^ollama-", "", os.readlink(OLLAMA_CURRENT).rsplit("/", 1)[-1])
    else:
        try:
            out = subprocess.run(
                ["ollama", "--version"], capture_output=True, text=True, timeout=10
            ).stdout
            rep.current = (re.search(r"[\d.]+", out) or ["?"])[0]
        except (OSError, subprocess.SubprocessError) as e:
            rep.lines.append(f"could not determine installed version: {e}")
            return rep
    _release_gap("ollama/ollama", _semver(rep.current), rep)
    _advisories("ollama/ollama", rep)
    if rep.status == "behind":
        rep.lines.append(
            "  bump: unpack release to ~/ollama-<ver>/, flip ~/ollama-current, "
            "reload com.portal5.ollama (see docs/ADMIN_GUIDE.md)"
        )
    return rep


def check_omlx() -> Report:
    rep = Report("omlx")
    try:
        out = subprocess.run(
            ["brew", "list", "--versions", "jundot/omlx/omlx"],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.split()
        rep.current = out[-1] if len(out) > 1 else "?"
    except (OSError, subprocess.SubprocessError) as e:
        rep.lines.append(f"brew not available: {e}")
        return rep
    _release_gap("jundot/omlx", _semver(rep.current), rep)
    _advisories("jundot/omlx", rep)
    if rep.status == "behind":
        rep.lines.append(
            "  bump: brew update && brew upgrade jundot/omlx/omlx && brew services restart omlx"
        )
    return rep


CHECKERS = {"obscura": check_obscura, "ollama": check_ollama, "omlx": check_omlx}


def _pushover(title: str, message: str, high: bool) -> None:
    tok = os.environ.get("PUSHOVER_API_TOKEN", "")
    usr = os.environ.get("PUSHOVER_USER_KEY", "")
    if not (tok and usr):
        return
    payload = {"token": tok, "user": usr, "title": title, "message": message[:1024]}
    if high:
        payload["priority"] = "1"
    try:
        urllib.request.urlopen(  # noqa: S310 - fixed api.pushover.net host
            "https://api.pushover.net/1/messages.json",
            data=urllib.parse.urlencode(payload).encode(),
            timeout=15,
        )
    except urllib.error.URLError as e:
        print(f"pushover send failed: {e}", file=sys.stderr)


def main(argv: list[str]) -> int:
    wanted = [a for a in argv if not a.startswith("-")] or list(CHECKERS)
    unknown = [w for w in wanted if w not in CHECKERS]
    if unknown:
        sys.exit(f"unknown component(s): {', '.join(unknown)}; pick from {', '.join(CHECKERS)}")

    reports = [CHECKERS[w]() for w in wanted]
    blocks = []
    for r in reports:
        flag = "  <-- SECURITY" if r.security else ""
        header = f"[{r.status.upper()}] {r.name}: {r.current} -> {r.latest}{flag}"
        blocks.append("\n".join([header, *(f"    {ln}" for ln in r.lines)]))
    out = "\n\n".join(blocks)
    print(out)

    behind = [r for r in reports if r.actionable]
    if behind:
        sec = any(r.security for r in behind)
        title = "Updates need review" + (" — SECURITY" if sec else "")
        _pushover(title, out, high=sec)
        names = ", ".join(r.name for r in behind)
        print(f"\n-> actionable: {names} behind upstream" + (" (security-flagged)" if sec else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
