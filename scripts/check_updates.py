#!/usr/bin/env python3
"""Check Portal 5's hand-pinned external components against upstream.

Covers the Obscura browser ref (``ARG OBSCURA_REF`` in
``deploy/browser-mcp/Dockerfile``), Ollama (``~/ollama-current`` symlink), oMLX
GitHub releases (with the Homebrew formula as a service fallback), catalog
models whose pinned file or registry manifest moved (``models``), and the worker
harnesses (``opencode``, ``codex``, ``grok`` — see ``harnesses``). Reports how far behind each pin is
and — the point of it — flags gaps that include a security fix or a published
GitHub advisory, so a "review later" bump can be promoted to "do this now".

Report, not a gate; exit 0 always. Sends a Pushover push (high-priority when
security-flagged) when a component is behind and ``PUSHOVER_API_TOKEN`` +
``PUSHOVER_USER_KEY`` are set. Weekly launchd job
``com.portal5.update-check.plist``; accepts a component subset, e.g.
``check_updates.py ollama omlx``. Stdlib only; ``brew`` is only the fallback service. Honors ``GITHUB_TOKEN``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "deploy" / "browser-mcp" / "Dockerfile"
OLLAMA_CURRENT = Path.home() / "ollama-current"
_API = "https://api.github.com"
_OSV = "https://api.osv.dev/v1"
COMPOSE_FILES = (
    REPO_ROOT / "deploy" / "portal-5" / "docker-compose.yml",
    REPO_ROOT / "deploy" / "portal-5" / "docker-compose.lab.yml",
)
# image repo (no registry/tag) -> GitHub repo carrying its releases + advisories.
_IMAGE_REPOS = {
    "open-webui/open-webui": "open-webui/open-webui",
    "searxng/searxng": "searxng/searxng",
    "grafana/grafana": "grafana/grafana",
    "prom/prometheus": "prometheus/prometheus",
    "wazuh/wazuh-manager": "wazuh/wazuh",
}
_FLOATING_TAGS = {"latest", "main", "master", "stable"}

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
    #: A release BETWEEN the installed and latest version carries a security
    #: fix. `security` is broader — any published repo advisory, including ones
    #: for long-superseded versions — so it must not trigger an out-of-cycle
    #: engine update on its own (engine_autoupdate.py uses this field).
    security_in_gap: bool = False
    lines: list[str] = field(default_factory=list)
    #: Floating-tag compose images with an advisory published since they were
    #: built (image repo names) — image_security_update.py re-pulls these.
    stale_images: list[str] = field(default_factory=list)
    high_priority: bool = False

    @property
    def actionable(self) -> bool:
        return self.status in ("behind", "error")


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


#: Python-version clause inside a PEP 508 marker, e.g. ``python_full_version < '3.11'``.
_PY_CLAUSE = re.compile(
    r"python_(?:full_)?version\s*(<=|>=|==|!=|<|>)\s*['\"](\d+(?:\.\d+)*)(\.\*)?['\"]"
)
_CMP = {
    "<": lambda c: c < 0,
    "<=": lambda c: c <= 0,
    "==": lambda c: c == 0,
    "!=": lambda c: c != 0,
    ">": lambda c: c > 0,
    ">=": lambda c: c >= 0,
}


def _cmp(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    n = max(len(a), len(b))
    a, b = a + (0,) * (n - len(a)), b + (0,) * (n - len(b))
    return (a > b) - (a < b)


def _py_clauses(marker: str) -> list[tuple[str, tuple[int, ...], bool]]:
    """(operator, version, wildcard) for each python clause of one PEP 508 marker."""
    return [
        (op, tuple(int(p) for p in ver.split(".")), bool(star))
        for op, ver, star in _PY_CLAUSE.findall(marker)
    ]


def _marker_holds(marker: str, py: tuple[int, ...]) -> bool:
    """Whether `py` satisfies `marker`'s python clauses (platform clauses are ignored)."""
    for op, want, star in _py_clauses(marker):
        ok = py[: len(want)] == want if star and op == "==" else _CMP[op](_cmp(py, want))
        if not ok:
            return False
    return True


def _fork_matches(markers: tuple[str, ...], py: tuple[int, ...]) -> bool:
    """Whether any of a fork's `resolution-markers` alternatives admits this python."""
    return not markers or any(_marker_holds(m, py) for m in markers)


def _py_range_label(markers: tuple[str, ...]) -> str:
    """The supported python versions a forked lock entry admits, e.g. 'py3.10' or 'py3.11+'."""
    floor = _supported_python()
    admits = [m for m in range(floor[1], 16) if _fork_matches(markers, (floor[0], m))]
    if not admits:
        return "forked"
    head = f"py{floor[0]}.{admits[0]}"
    if admits[0] == admits[-1]:
        return head
    return f"{head}+" if admits[-1] == 15 else f"{head}-{floor[0]}.{admits[-1]}"


def _supported_python() -> tuple[int, int]:
    """Lowest python the project supports (pyproject `requires-python`)."""
    try:
        text = (REPO_ROOT / "pyproject.toml").read_text()
    except OSError:
        return (3, 10)
    m = re.search(r'requires-python\s*=\s*"[^\d]*(\d+)\.(\d+)', text)
    return (int(m.group(1)), int(m.group(2))) if m else (3, 10)


def _fork_note(markers: tuple[str, ...], py: tuple[int, ...]) -> str:
    """Report the python fork a locked version is scoped to, flagging one this runtime skips."""
    if not markers:
        return ""
    label = _py_range_label(markers)
    if _fork_matches(markers, py):
        return f"  [{label} fork]"
    return f"  [{label} fork only — not this runtime (py{'.'.join(map(str, py))})]"


def _runtime_python() -> tuple[int, ...]:
    """The interpreter uv.lock is resolved for — the project venv, not whoever runs this."""
    try:
        cfg = (REPO_ROOT / ".venv" / "pyvenv.cfg").read_text()
    except OSError:
        return tuple(sys.version_info[:3])
    m = re.search(r"^version(?:_info)?\s*=\s*(\d+(?:\.\d+)*)", cfg, re.MULTILINE)
    return tuple(int(p) for p in m.group(1).split(".")) if m else tuple(sys.version_info[:3])


def _pypi_requires_python(name: str, version: str) -> str:
    """The `requires-python` a PyPI release declares ("" when it cannot be read)."""
    try:
        with urllib.request.urlopen(  # noqa: S310 - fixed pypi.org host
            f"https://pypi.org/pypi/{name}/{version}/json", timeout=15
        ) as resp:
            info = json.loads(resp.read().decode()).get("info") or {}
        return str(info.get("requires_python") or "")
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return ""


def _spec_allows(spec: str, py: tuple[int, ...]) -> bool:
    """Whether a bare `requires-python` specifier admits `py` (~= read as >=)."""
    for op, ver in re.findall(r"(<=|>=|==|!=|~=|<|>)\s*(\d+(?:\.\d+)*)", spec):
        if not _CMP[">=" if op == "~=" else op](_cmp(py, tuple(int(p) for p in ver.split(".")))):
            return False
    return True


def _fork_can_install(markers: tuple[str, ...], requires_python: str) -> bool:
    """Whether any python a fork admits is also allowed by the fix's `requires-python`."""
    if not markers or not requires_python:
        return True
    major, low = _supported_python()
    return any(
        _fork_matches(markers, (major, m)) and _spec_allows(requires_python, (major, m))
        for m in range(low, 16)
    )


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
    # Pre-releases (rc/beta) are not upgrade targets — counting them made the
    # report say BEHIND against v0.40.0-rc0 while 0.34.4 was the newest release.
    releases = [
        r
        for r in releases
        if not r.get("draft")
        and not r.get("prerelease")
        and not re.search(r"(rc|alpha|beta|dev|pre)\d*$", str(r.get("tag_name", "")), re.IGNORECASE)
    ]
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
            report.security_in_gap = True
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
    marker = OLLAMA_CURRENT.resolve() / "VERSION"  # ~/ollama-live (engine_autoupdate.py)
    if marker.exists():
        rep.current = marker.read_text().strip()
    elif OLLAMA_CURRENT.is_symlink():
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
            "  bump: automatic — scripts/engine_autoupdate.py (daily launchd job, "
            "contract-gated); force now with --now"
        )
    return rep


def check_omlx() -> Report:
    rep = Report("omlx")
    venv = Path(os.environ.get("OMLX_VENV_PATH", str(Path.home() / "omlx-live" / "venv")))
    python = venv / "bin" / "python"
    if python.is_file():
        try:
            active = subprocess.run(
                ["launchctl", "print", f"gui/{os.getuid()}/com.portal5.omlx"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if active.returncode == 0:
                version = subprocess.run(
                    [str(python), "-c", "import importlib.metadata as m; print(m.version('omlx'))"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                if version.returncode == 0 and version.stdout.strip():
                    rep.current = version.stdout.strip()
        except (OSError, subprocess.SubprocessError) as e:
            rep.lines.append(f"could not determine active venv version: {e}")
    if not rep.current:
        try:
            rep.current = os.readlink("/opt/homebrew/opt/omlx").rstrip("/").rsplit("/", 1)[-1]
        except OSError as e:
            rep.lines.append(f"could not determine installed oMLX version: {e}")
            return rep
    _release_gap("jundot/omlx", _semver(rep.current), rep)
    _advisories("jundot/omlx", rep)
    if rep.status == "behind":
        rep.lines.append(
            "  bump: scripts/engine_autoupdate.py (GitHub release wheel, contract-gated); "
            "Homebrew remains the fallback until com.portal5.omlx is loaded"
        )
    return rep


_WATCHED_DEPS = (
    "mlx",
    "mlx-embeddings",
    "mlx-vlm",
    "mlx-lm",
    "mlx-audio",
    "transformers",
    "torch",
    "torchvision",
    "torchaudio",
    "lancedb",
    "pymupdf",
    "phonemizer",
)


def check_python_deps() -> Report:
    """Two things (TASK_VL_RUNTIME_LANDING_V4 P9.5 / gate BR-sibling):
    1. the project venv must match uv.lock  -> `status = "behind"` on drift
       (this is the check that would have caught the VL-runtime destruction);
    2. watched packages in uv.lock vs PyPI  -> note when a minor+ is available.
    """
    rep = Report("python-deps")
    root = Path(__file__).resolve().parent.parent

    # 1 — venv vs lock (authoritative; a mismatch is actionable)
    try:
        r = subprocess.run(
            [_uv(), "sync", "--all-extras", "--frozen", "--check"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=root,
        )
        if r.returncode != 0:
            rep.status = "behind"
            rep.security = True  # a silently-diverged runtime is a standing risk
            diff_lines = [
                ln.strip()
                for ln in (r.stdout + r.stderr).splitlines()
                if ln.strip().startswith(("+", "-", "~"))
            ]
            # Direction matters. `uv sync` reconciles the venv TO the lock:
            #   `-`/`~` (uninstall/downgrade) => the venv is AHEAD of the lock —
            #   running `uv sync` would DESTROY newer packages (this is exactly
            #   how the VL runtime was lost). `+` only => venv is behind, safe.
            venv_ahead = any(ln.startswith(("-", "~")) for ln in diff_lines)
            if venv_ahead:
                rep.lines.append(
                    "VENV/LOCK DRIFT — the venv is AHEAD of uv.lock. Do NOT run "
                    "`uv sync --all-extras` (it would uninstall/downgrade the "
                    "packages below). Reconcile the LOCK to the venv (`uv lock`) "
                    "after reviewing the diff, or restore a known-good venv."
                )
            else:
                rep.lines.append(
                    "VENV/LOCK DRIFT — the venv is behind uv.lock; "
                    "`uv sync --all-extras` (after reviewing the diff) will catch it up:"
                )
            rep.lines.extend(f"  {ln}" for ln in diff_lines)
        else:
            rep.lines.append("venv matches uv.lock")
    except (OSError, subprocess.SubprocessError) as e:
        rep.status = "error"  # a check that cannot run must not read as healthy
        rep.security = True
        rep.lines.append(f"venv/lock check FAILED to run: {e}")

    # 2 — lock vs PyPI for the watched set (informational)
    try:
        lock = (root / "uv.lock").read_text()
    except OSError:
        return rep
    for pkg in _WATCHED_DEPS:
        m = re.search(rf'name = "{re.escape(pkg)}"\nversion = "([^"]+)"', lock)
        if not m:
            continue
        cur = m.group(1)
        try:
            with urllib.request.urlopen(  # noqa: S310 - fixed pypi.org host
                f"https://pypi.org/pypi/{pkg}/json", timeout=15
            ) as resp:
                latest = json.loads(resp.read().decode())["info"]["version"]
        except (urllib.error.URLError, KeyError, json.JSONDecodeError):
            continue
        if _semver(latest) > _semver(cur):
            cs, ls = _semver(cur), _semver(latest)
            minor_plus = ls[:2] > cs[:2]
            rep.lines.append(
                f"  {pkg}: lock {cur} -> PyPI {latest}" + ("  [minor+]" if minor_plus else "")
            )
            if minor_plus and rep.status not in ("behind", "error"):
                rep.status = "behind"
    return rep


def _uv() -> str:
    # launchd's PATH omits ~/.local/bin, where uv lives.
    return shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")


def _post_json(url: str, body: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - fixed api.osv.dev host
        return json.loads(r.read().decode())


def _resolution_markers(head: str) -> tuple[str, ...]:
    """The marker alternatives a forked lock entry is scoped to (() when it is not forked)."""
    m = re.search(r"resolution-markers = \[(.*?)\]", head, re.S)
    return tuple(re.findall(r'"([^"]+)"', m.group(1))) if m else ()


def _locked_packages() -> list[tuple[str, str, tuple[str, ...]]]:
    """(name, version, resolution markers) of every PyPI-sourced package in uv.lock."""
    text = (REPO_ROOT / "uv.lock").read_text()
    out = []
    for block in text.split("[[package]]")[1:]:
        head = block.split("\n\n")[0]
        m = re.match(r'\s*name = "([^"]+)"\nversion = "([^"]+)"', block)
        if m and 'source = { registry = "https://pypi.org/simple" }' in head:
            out.append((m.group(1), m.group(2), _resolution_markers(head)))
    return out


def _osv_detail(vuln_id: str, pkg: str, installed: str = "0") -> tuple[str, str, str]:
    """(severity, lowest fixed version above `installed`, summary) for one OSV record."""
    with urllib.request.urlopen(  # noqa: S310 - fixed api.osv.dev host
        f"{_OSV}/vulns/{urllib.parse.quote(vuln_id)}", timeout=20
    ) as r:
        v = json.loads(r.read().decode())
    sev = (v.get("database_specific") or {}).get("severity", "?")
    fixes = []
    for aff in v.get("affected", []):
        if aff.get("package", {}).get("name", "").lower() != pkg.lower():
            continue
        for rng in aff.get("ranges", []):
            fixes += [e["fixed"] for e in rng.get("events", []) if e.get("fixed")]
    above = [f for f in fixes if _semver(f) > _semver(installed)]
    return sev, min(above, key=_semver) if above else "", (v.get("summary") or "")[:80]


def osv_query(pkgs: list[tuple[str, str, tuple[str, ...]]]) -> dict[tuple[str, str], list[str]]:
    """{(name, version): [vuln ids]} for the packages OSV.dev knows a vuln for."""
    hits: dict[tuple[str, str], list[str]] = {}
    for i in range(0, len(pkgs), 500):
        chunk = pkgs[i : i + 500]
        res = _post_json(
            f"{_OSV}/querybatch",
            {
                "queries": [
                    {"package": {"name": n, "ecosystem": "PyPI"}, "version": v} for n, v, _ in chunk
                ]
            },
        )["results"]
        for key, r in zip(((n, v) for n, v, _ in chunk), res, strict=True):
            if r.get("vulns"):
                hits[key] = [x["id"] for x in r["vulns"]]
    return hits


def vuln_fixes(
    hits: dict[tuple[str, str], list[str]],
) -> dict[tuple[str, str], tuple[str, str, str]]:
    """{(name, version): (worst severity, version that fixes every fixable vuln, top summary)}.

    The fix is the highest per-vuln lowest-fixed version; "" when none is published.
    """
    order = {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "LOW": 1}
    out = {}
    for (name, ver), ids in hits.items():
        sev, fixed, summ = "?", "", ""
        for vid in ids:
            try:
                s, f, t = _osv_detail(vid, name, ver)
            except (OSError, ValueError):
                continue
            if order.get(s, 0) > order.get(sev, 0):
                sev, summ = s, t
            if f and (not fixed or _semver(f) > _semver(fixed)):
                fixed = f
        out[(name, ver)] = (sev, fixed, summ)
    return out


def check_python_vulns() -> Report:
    """Known vulnerabilities (OSV.dev) in every PyPI package pinned by uv.lock.

    Only a vuln with a published fix makes this actionable; an unfixed one is
    listed but cannot be bumped away. ``security_autoupdate.py deps`` applies them.
    A forked lock (e.g. a ``python_full_version < '3.11'`` entry) contributes one
    line per locked version, annotated with the python range it is locked for, so
    a vuln the running interpreter never resolves is not read as a live one.
    """
    rep = Report("python-vulns")
    try:
        pkgs = _locked_packages()
        hits = osv_query(pkgs)
    except (OSError, KeyError, ValueError) as e:
        rep.status = "error"  # a check that cannot run must not read as healthy
        rep.lines.append(f"OSV query FAILED to run: {e}")
        return rep
    rep.current = f"{len(pkgs)} locked pkgs"
    rep.latest = f"{len(hits)} vulnerable"
    if not hits:
        rep.status = "current"
        rep.lines.append("no known vulnerabilities in uv.lock")
        return rep
    fixes = vuln_fixes(hits)
    fixable = sum(bool(f) for _, f, _ in fixes.values())
    forks = {(n, v): markers for n, v, markers in pkgs}
    py = _runtime_python()
    detail = [
        f"  - {name} {ver}: {len(hits[(name, ver)])} vuln(s) [{sev}]"
        + (f" fixed in {fixed}" if fixed else " (no fix yet)")
        + (f" — {summ}" if summ else "")
        + _fork_note(forks.get((name, ver), ()), py)
        for (name, ver), (sev, fixed, summ) in sorted(fixes.items())
    ]
    rep.security = True
    rep.status = "behind" if fixable else "current"
    rep.security_in_gap = False  # engine_autoupdate keys off this; deps are not engines
    rep.lines.append(f"{len(hits)} package(s) with known vulns, {fixable} with a fix available")
    rep.lines.extend(detail[:12])
    if len(detail) > 12:
        rep.lines.append(f"  ... {len(detail) - 12} more")
    return rep


def _image_refs() -> dict[str, str]:
    """{image repo: tag} for compose images we have a GitHub repo mapping for."""
    refs = {}
    for f in COMPOSE_FILES:
        try:
            text = f.read_text()
        except OSError:
            continue
        for m in re.finditer(r"^\s*image:\s*(\S+)", text, re.MULTILINE):
            ref = re.sub(r"^(ghcr\.io|docker\.io)/", "", m.group(1))
            repo, _, tag = ref.partition(":")
            if repo in _IMAGE_REPOS:
                refs[repo] = tag or "latest"
    return refs


def _local_image_created(ref: str) -> str:
    docker = shutil.which("docker") or "/usr/local/bin/docker"
    try:
        out = subprocess.run(
            [docker, "image", "inspect", ref, "--format", "{{.Created}}"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return out.stdout.strip()[:10] if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


#: Worker harnesses driven by ~/.claude/orchestrate/bin/dispatch.py. Each is pinned by
#: whatever installed it, and each publishes its version somewhere different:
#:   opencode — a standalone binary; the Homebrew formula API is the source its own
#:              `upgrade` consults, and the only one whose 2.x line matches what ships
#:              (npm `opencode-ai` and GitHub releases both still track a 1.x line).
#:   codex    — GitHub releases, tagged `rust-vX.Y.Z`; advisories available.
#:   grok     — no public release feed; the CLI records what it last saw upstream in
#:              ~/.grok/version.json, so that is self-reported, not independent.
_HARNESS_BINS = {
    "opencode": Path.home() / ".opencode" / "bin" / "opencode",
    "codex": Path.home() / ".local" / "bin" / "codex",
    "grok": Path.home() / ".grok" / "bin" / "grok",
}
_BREW_FORMULA = "https://formulae.brew.sh/api/formula/opencode.json"
GROK_VERSION_FILE = Path.home() / ".grok" / "version.json"


def _binary_version(name: str) -> str | None:
    """`<bin> --version` reduced to its first dotted number, or None if it will not run."""
    binary = _HARNESS_BINS[name]
    if not binary.exists():
        return None
    try:
        out = subprocess.run(  # noqa: S603
            [str(binary), "--version"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"\d+\.\d+\.\d+", (out.stdout or "") + (out.returncode and out.stderr or ""))
    return m.group(0) if m else None


def _check_opencode(rep: Report) -> None:
    current = _binary_version("opencode")
    if not current:
        rep.lines.append("opencode: not installed or would not report a version")
        return
    try:
        with urllib.request.urlopen(_BREW_FORMULA, timeout=20) as r:  # noqa: S310 - fixed host
            latest = str((json.loads(r.read().decode()).get("versions") or {}).get("stable") or "")
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        rep.lines.append(f"opencode {current}: upstream check failed: {e}")
        return
    if not latest:
        rep.lines.append(f"opencode {current}: brew formula carried no stable version")
        return
    if _semver(latest) > _semver(current):
        rep.status = "behind"
        rep.lines.append(f"opencode {current} -> {latest}  bump: `opencode upgrade`")
        rep.lines.append(
            "  re-verify the measured quirks after upgrading (Code Mode `execute` ignoring "
            "deny rules, --standalone vs the shared service, $PWD project resolution)"
        )
    else:
        rep.lines.append(f"opencode {current} up to date (brew stable {latest})")


def _check_codex(rep: Report) -> None:
    current = _binary_version("codex")
    if not current:
        rep.lines.append("codex: not installed or would not report a version")
        return
    sub = Report("codex", current=current)
    _release_gap("openai/codex", _semver(current), sub)
    _advisories("openai/codex", sub)
    if sub.status == "behind":
        rep.status = "behind"
        rep.security |= sub.security_in_gap
        rep.lines.append(
            f"codex {current} -> {sub.latest}  bump: `codex update`"
            + ("  [SECURITY]" if sub.security_in_gap else "")
        )
        rep.lines.extend(f"  {ln}" for ln in sub.lines[1:4])
    else:
        rep.lines.append(f"codex {current} up to date (latest {sub.latest})")


def _check_grok(rep: Report) -> None:
    current = _binary_version("grok")
    if not current:
        rep.lines.append("grok: not installed or would not report a version")
        return
    try:
        seen = json.loads(GROK_VERSION_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        rep.lines.append(f"grok {current}: no upstream feed and no local version.json")
        return
    latest = str(seen.get("stable_version") or "")
    checked = str(seen.get("checked_at") or "?")[:10]
    if latest and _semver(latest) > _semver(current):
        rep.status = "behind"
        rep.lines.append(
            f"grok {current} -> {latest} (self-reported {checked})  bump: `grok update`"
        )
    else:
        rep.lines.append(
            f"grok {current} up to date (self-reported {latest or '?'}, checked {checked})"
        )


def check_harnesses() -> Report:
    """Worker harness binaries behind the orchestrator: opencode, codex, grok.

    These are not Portal 5 services — they are the harnesses `dispatch.py` drives — but
    they rot the same way and nothing else was watching them. Grok's figure is the CLI's
    own last-seen value, so it only moves when grok has run; the other two are checked
    against upstream directly.
    """
    rep = Report("harnesses", status="current")
    rep.current = f"{sum(1 for p in _HARNESS_BINS.values() if p.exists())}/3 installed"
    for check in (_check_opencode, _check_codex, _check_grok):
        check(rep)
    behind = sum(1 for ln in rep.lines if " -> " in ln)
    rep.latest = f"{behind} behind" if behind else "all current"
    return rep


def check_images() -> Report:
    """Compose images: pinned tags vs upstream releases; floating tags vs advisories
    published after the local image was built."""
    rep = Report("images")
    refs = _image_refs()
    if not refs:
        rep.status = "error"
        rep.lines.append("no mapped images found in compose files")
        return rep
    rep.current = f"{len(refs)} images"
    rep.status = "current"
    for repo, tag in sorted(refs.items()):
        gh = _IMAGE_REPOS[repo]
        sub = Report(repo)
        if tag in _FLOATING_TAGS:
            built = _local_image_created(
                f"{repo if '/' in repo else repo}:{tag}"
            ) or _local_image_created(f"ghcr.io/{repo}:{tag}")
            _advisories(gh, sub)
            newer = []
            if built:
                try:
                    adv = _get(f"{_API}/repos/{gh}/security-advisories")
                    newer = [
                        a
                        for a in adv
                        if a.get("state") == "published"
                        and str(a.get("published_at", ""))[:10] > built
                    ]
                except (urllib.error.URLError, json.JSONDecodeError):
                    pass
            if newer:
                rep.status = "behind"
                rep.security = True
                rep.stale_images.append(repo)
                rep.lines.append(
                    f"{repo}:{tag} built {built}: {len(newer)} advisory(ies) published since — "
                    "pull + `./launch.sh rebuild`"
                )
                rep.lines.extend(
                    f"  - {a.get('ghsa_id')}: {a.get('summary', '')[:100]}" for a in newer[:3]
                )
            else:
                rep.lines.append(
                    f"{repo}:{tag} (floating) built {built or 'unknown'}: no advisories since"
                )
        else:
            _release_gap(gh, _semver(tag), sub)
            if sub.status == "behind":
                rep.status = "behind"
                rep.security |= sub.security_in_gap
                rep.lines.append(
                    f"{repo}:{tag} -> {sub.latest}"
                    + ("  [SECURITY]" if sub.security_in_gap else "")
                )
                rep.lines.extend(ln for ln in sub.lines[1:4])
            else:
                rep.lines.append(f"{repo}:{tag} up to date ({sub.latest})")
    return rep


def check_models() -> Report:
    """Catalog models whose HF pin or Ollama registry manifest moved."""
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from scripts.model_upstream import collect_changes, models_dir

    rep = Report(name="models", current="pinned", latest="pinned")
    try:
        scan = collect_changes(
            (REPO_ROOT / "config" / "backends.yaml").read_text(encoding="utf-8"),
            models_dir(),
            _model_fetch(),
        )
    except OSError as exc:
        rep.status = "error"
        rep.lines.append(str(exc))
        return rep
    rep.lines.extend(
        f"{change.tag} {change.old[:12]} -> {change.new[:12]} ({change.size} bytes)"
        for change in scan.changes
    )
    rep.lines.extend(scan.notes)
    if scan.changes:
        rep.status = "behind"
        rep.current = str(len(scan.changes))
        rep.latest = "upstream"
        return rep
    if any(note.startswith("error ") for note in scan.notes):
        rep.status = "unknown"
    else:
        rep.status = "current"
    return rep


def _model_fetch():
    from scripts.model_upstream import default_fetch

    return default_fetch


@dataclass
class _Usage:
    path: Path
    size: int = 0
    mtime: float = 0.0
    is_dir: bool = False
    children: list[_Usage] = field(default_factory=list)
    files: list[_Usage] = field(default_factory=list)
    repositories: list[tuple[Path, int, float]] = field(default_factory=list)
    errors: int = 0


@dataclass
class _StorageRecord:
    path: str
    size: int
    mtime: float
    root: str


def _allocated_bytes(info: os.stat_result) -> int:
    return getattr(info, "st_blocks", 0) * 512 or info.st_size


def _walk_usage(path: Path, keep_children: set[Path], limit: int = 5) -> _Usage:
    try:
        info = path.stat(follow_symlinks=False)
    except OSError:
        return _Usage(path=path, errors=1)
    if not stat.S_ISDIR(info.st_mode):
        item = _Usage(path, _allocated_bytes(info), info.st_mtime)
        if stat.S_ISREG(info.st_mode):
            item.files = [item]
        return item
    usage = _Usage(path=path, is_dir=True)
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                child = _walk_usage(Path(entry.path), keep_children, limit)
                usage.size += child.size
                usage.mtime = max(usage.mtime, child.mtime)
                usage.errors += child.errors
                usage.repositories.extend(child.repositories)
                if path in keep_children:
                    usage.children.append(child)
                usage.files.extend(child.files)
                usage.files.sort(key=lambda item: item.size, reverse=True)
                del usage.files[limit:]
    except OSError:
        usage.errors += 1
    if not usage.mtime:
        usage.mtime = info.st_mtime
    if "hf-cache" in path.parts and path.name.startswith("models--"):
        usage.repositories.append((path, usage.size, usage.mtime))
    return usage


def _yaml_value(value: str) -> str:
    return value.split(" #", 1)[0].strip().strip("'\"")


def _backend_storage_refs(text: str) -> tuple[set[str], set[str]]:
    ollama_tags: set[str] = set()
    omlx_models: set[str] = set()
    groups = re.split(r"(?m)(?=^- group:\s*)", text)
    for block in groups:
        if not block.startswith("- group:"):
            continue
        backend_type = re.search(r"(?m)^  type:\s*([^\s#]+)", block)
        target = omlx_models if backend_type and backend_type.group(1) == "omlx" else ollama_tags
        target.update(_yaml_value(value) for value in re.findall(r"(?m)^  - id:\s*(.+)$", block))
        if target is not omlx_models:
            continue
        aliases = False
        for line in block.splitlines():
            if re.match(r"^  aliases:\s*$", line):
                aliases = True
                continue
            if aliases and line and not line[0].isspace():
                break
            if aliases and len(line) - len(line.lstrip()) < 4:
                aliases = False
            if aliases and line.strip() and not line.lstrip().startswith("#"):
                match = re.match(r"^(.+):\s+([^\s#]+)", line.strip())
                if match:
                    ollama_tags.add(_yaml_value(match.group(1)))
                    omlx_models.add(_yaml_value(match.group(2)))
    return ollama_tags, omlx_models


def _portal_storage_refs(text: str) -> tuple[set[str], dict[str, set[str]]]:
    enabled: dict[str, bool] = {}
    in_modules = False
    current = ""
    for line in text.splitlines():
        if re.match(r"^modules:\s*$", line):
            in_modules = True
            continue
        if in_modules and line and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        if in_modules:
            module = re.match(r"^  ([\w-]+):\s*$", line)
            if module:
                current = module.group(1)
            switch = re.match(r"^\s+enabled:\s*(true|false)\s*$", line, re.IGNORECASE)
            if current and switch:
                enabled[current] = switch.group(1).lower() == "true"

    lines = text.splitlines()
    module_refs: dict[str, set[str]] = {}
    for index, line in enumerate(lines):
        module = re.match(r"^(\s+)module:\s*([\w-]+)\s*$", line)
        if not module:
            continue
        body = _module_reference_block(lines, index, len(module.group(1)))
        module_refs.setdefault(module.group(2), set()).update(_workspace_model_refs(body))
    return {module for module, state in enabled.items() if not state}, module_refs


def _module_reference_block(lines: list[str], start: int, indent: int) -> str:
    body: list[str] = []
    literal_indent = 0
    for index, line in enumerate(lines[start:], start):
        stripped = line.strip()
        if not stripped:
            continue
        line_indent = len(line) - len(line.lstrip())
        if index > start and line_indent < indent and not stripped.startswith("#"):
            break
        if index == start or line_indent == indent:
            body.append(line)
            literal_indent = -1 if re.search(r":\s*[|>][+-]?\s*$", line) else 0
        elif literal_indent == -1 and line_indent > indent:
            body.append(line)
            literal_indent = line_indent
        elif literal_indent == -1:
            literal_indent = 0
        elif literal_indent and line_indent >= literal_indent:
            body.append(line)
        elif literal_indent:
            literal_indent = 0
    return "\n".join(body)


def _workspace_model_refs(text: str) -> set[str]:
    refs = set(re.findall(r"(?i)\bmodel\s*=\s*['\"]([^'\"]+)['\"]", text))
    refs.update(
        re.findall(r"(?m)^\s+(?:hf_id|actual_repo|repo_id|model_id):\s*['\"]?([^\s'\"]+)", text)
    )
    refs.update(
        value
        for value in re.findall(r"(?i)\b[a-z0-9]+(?:[-._][a-z0-9]+)+\b", text)
        if any(char.isdigit() for char in value)
    )
    return {re.sub(r"[^a-z0-9]", "", value.casefold()) for value in refs if len(value) >= 4}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# hf.co/org/repo[:tag], org/name, name:tag, or a bare id. A digit is required.
_MODEL_REF = re.compile(
    r"(?i)(?<![A-Za-z0-9_.+-])("
    r"hf\.co/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?::[A-Za-z0-9_.+-]+)?"
    r"|[A-Za-z][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_.-]+)+(?::[A-Za-z0-9_.+-]+)?"
    r"|[A-Za-z][A-Za-z0-9_.-]*:[A-Za-z0-9_.+-]+"
    r"|[A-Za-z][A-Za-z0-9_.-]*\d[A-Za-z0-9_.-]*"
    r")(?![A-Za-z0-9_.+-])"
)
_CODE_DEFAULT = re.compile(
    r"""os\.(?:environ\.get|getenv)\(\s*["'][^"']*["']\s*,\s*["']([^"']*)["']"""
)
_CONST_STRING = re.compile(r"""(?m)^[A-Z][A-Z0-9_]*\s*(?::[^=\n]+)?=\s*["']([^"']*)["']""")
_CODE_MODEL_CACHE: set[str] | None = None
_MEDIA_ALIAS_CACHE: frozenset[str] | None = None
_MEDIA_TABLES = (
    (
        REPO_ROOT / "portal/modules/media/tools/mflux_mcp.py",
        ("MFLUX_MODELS", "MFLUX_MODEL_BIN", "MFLUX_DEFAULT_STEPS"),
        False,
    ),
    (REPO_ROOT / "portal/modules/media/tools/_admission.py", ("MEDIA_MODEL_MEMORY_GB",), True),
    (REPO_ROOT / "portal/modules/media/tools/video_mlx_mcp.py", ("VIDEO_MLX_MODELS",), False),
)


def _keep_model_ref(value: str) -> bool:
    if not any(char.isdigit() for char in value):
        return False
    if ":" in value and not any(char.isalpha() for char in value.rsplit(":", 1)[1]):
        return False
    if "/" in value or ":" in value:
        return True
    digit = next(index for index, char in enumerate(value) if char.isdigit())
    return len(value) - digit - 1 >= 5


def _model_refs_in_text(text: str) -> set[str]:
    return {
        match.group(1).rstrip(".")
        for match in _MODEL_REF.finditer(text)
        if _keep_model_ref(match.group(1).rstrip("."))
    }


def _expand_model_name(name: str) -> set[str]:
    short = name.removeprefix("hf.co/")
    return {name, short, f"hf.co/{short}", short.rsplit("/", 1)[-1]}


def _merge_in_use_names(ollama_tags: set[str], omlx_models: set[str], names: set[str]) -> None:
    expanded: set[str] = set()
    for name in names:
        expanded.update(_expand_model_name(name))
    ollama_tags.update(expanded)
    omlx_models.update(expanded)


def _defaults_from_code(text: str) -> set[str]:
    candidates = _CODE_DEFAULT.findall(text)
    candidates.extend(_CONST_STRING.findall(text))
    refs: set[str] = set()
    for value in candidates:
        refs.update(_model_refs_in_text(value))
    return refs


def _code_model_refs(root: Path | None = None) -> set[str]:
    global _CODE_MODEL_CACHE
    if root is None and _CODE_MODEL_CACHE is not None:
        return set(_CODE_MODEL_CACHE)
    code_root = REPO_ROOT / "portal" if root is None else root
    found: set[str] = set()
    if code_root.is_dir():
        for path in code_root.rglob("*.py"):
            found.update(_defaults_from_code(_read_text(path)))
    if root is None:
        _CODE_MODEL_CACHE = set(found)
    return set(found)


def _config_model_refs(portal_text: str, config_dir: Path) -> set[str]:
    texts = [portal_text, _read_text(config_dir / "bench_workspaces.yaml")]
    personas = config_dir / "personas"
    if personas.is_dir():
        texts.extend(_read_text(path) for path in personas.rglob("*.yaml"))
    texts.extend(_read_text(path) for path in config_dir.glob("*council*") if path.is_file())
    refs: set[str] = set()
    for text in texts:
        refs.update(_model_refs_in_text(text))
    return refs


def _storage_config_refs(
    backend_text: str, portal_text: str, config_dir: Path
) -> tuple[set[str], set[str], set[str], dict[str, set[str]]]:
    ollama_tags, omlx_models = _backend_storage_refs(backend_text)
    disabled_modules, module_refs = _portal_storage_refs(portal_text)
    names = _model_refs_in_text(backend_text)
    names.update(_config_model_refs(portal_text, config_dir))
    names.update(_code_model_refs())
    _merge_in_use_names(ollama_tags, omlx_models, names)
    return ollama_tags, omlx_models, disabled_modules, module_refs


def _ollama_manifest_path(root: Path, tag: str) -> Path:
    name, _, version = tag.rpartition(":")
    if not version:
        name, version = tag, "latest"
    parts = name.split("/")
    if len(parts) == 1:
        parts.insert(0, "library")
    return root / "ollama" / "models" / "manifests" / "registry.ollama.ai" / Path(*parts) / version


_FROM_BLOB = re.compile(r"(?m)^FROM\s+\S+/blobs/(sha256-[0-9a-fA-F]+)")
_IMPLICIT_OLLAMA_HOSTS = frozenset({"registry.ollama.ai", "ollama.com"})


def _ollama_base_url() -> str:
    host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").strip() or "127.0.0.1:11434"
    if "://" not in host:
        host = f"http://{host}"
    return host.rstrip("/")


def _ollama_json(url: str, body: dict[str, str] | None = None) -> dict[str, object]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - local Ollama API
        payload = json.loads(response.read().decode())
    if not isinstance(payload, dict):
        raise ValueError(url)
    return payload


def _tag_name(model: object) -> str | None:
    if not isinstance(model, dict):
        return None
    name = model.get("name")
    return name if isinstance(name, str) and name else None


def _show_blobs(base: str, name: str) -> set[str] | None:
    try:
        shown = _ollama_json(f"{base}/api/show", {"name": name})
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None
    modelfile = shown.get("modelfile")
    text = modelfile if isinstance(modelfile, str) else ""
    return {item.lower() for item in _FROM_BLOB.findall(text)}


def _installed_ollama_blobs() -> dict[str, set[str]] | None:
    """Installed tag -> blob filenames. None when Ollama cannot be queried."""
    base = _ollama_base_url()
    try:
        document = _ollama_json(f"{base}/api/tags")
        models = document["models"]
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
        KeyError,
        ValueError,
    ):
        return None
    if not isinstance(models, list):
        return None
    blobs: dict[str, set[str]] = {}
    for model in models:
        name = _tag_name(model)
        if name is None:
            return None
        found = _show_blobs(base, name)
        if found is None:
            return None
        blobs[name] = found
    return blobs


def _digest_blob_name(digest: object) -> str:
    text = str(digest or "")
    if text.startswith("sha256:"):
        return "sha256-" + text[7:].lower()
    if text.startswith("sha256-"):
        return text.lower()
    return ""


def _document_blob_names(document: dict[str, object]) -> set[str]:
    names: set[str] = set()
    config = document.get("config")
    if isinstance(config, dict):
        name = _digest_blob_name(config.get("digest"))
        if name:
            names.add(name)
    layers = document.get("layers")
    if not isinstance(layers, list):
        return names
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        name = _digest_blob_name(layer.get("digest"))
        if name:
            names.add(name)
    return names


def _tag_from_manifest(path: Path, store: Path) -> str:
    parts = path.relative_to(store).parts
    if len(parts) < 3:
        return ""
    host, *rest = parts
    if host in _IMPLICIT_OLLAMA_HOSTS and rest[0] == "library":
        rest = rest[1:]
    if len(rest) < 2:
        return ""
    tag = f"{'/'.join(rest[:-1])}:{rest[-1]}"
    if host not in _IMPLICIT_OLLAMA_HOSTS:
        tag = f"{host}/{tag}"
    return tag


def _manifest_blob_owners(store: Path) -> dict[str, set[str]]:
    owners: dict[str, set[str]] = {}
    if not store.is_dir():
        return owners
    for path in store.rglob("*"):
        if not path.is_file():
            continue
        try:
            document = json.loads(path.read_text())
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        tag = _tag_from_manifest(path, store)
        for name in _document_blob_names(document):
            owners.setdefault(name, set()).add(tag)
    return owners


def _ollama_manifest_owners(root: Path) -> dict[str, set[str]]:
    models = root / "ollama" / "models"
    owners: dict[str, set[str]] = {}
    for store in (models / "manifests", models / "manifests-v2"):
        for name, tags in _manifest_blob_owners(store).items():
            owners.setdefault(name, set()).update(tags)
    return owners


def _invert_tag_blobs(tag_blobs: dict[str, set[str]]) -> dict[str, set[str]]:
    owners: dict[str, set[str]] = {}
    for tag, names in tag_blobs.items():
        for name in names:
            owners.setdefault(name.lower(), set()).add(tag)
    return owners


def _tag_is_configured(tag: str, configured: set[str]) -> bool:
    if not tag or tag.startswith("llamacpp:"):
        return False
    if tag in configured:
        return True
    short = tag.removeprefix("hf.co/")
    return short in configured or f"hf.co/{short}" in configured


def _ollama_blob_class(
    name: str,
    configured: set[str],
    api: dict[str, set[str]],
    manifests: dict[str, set[str]],
) -> str:
    if name not in api and name not in manifests:
        return "orphan model data"
    owners = api.get(name, set()) | manifests.get(name, set())
    if any(_tag_is_configured(tag, configured) for tag in owners):
        return "fleet"
    if any(tag and not tag.startswith("llamacpp:") for tag in owners):
        return "installed-but-unconfigured"
    return "fleet"


def _ollama_blob_display(
    name: str, api: dict[str, set[str]], manifests: dict[str, set[str]]
) -> str:
    owners = api.get(name, set()) | manifests.get(name, set())
    user = sorted(tag for tag in owners if tag and not tag.startswith("llamacpp:"))
    shown = user or sorted(tag for tag in owners if tag)
    return f"ollama/{', '.join(shown[:2])}" if shown else f"ollama/{name}"


def _cache_checkpoint(slug: str, checkpoints: set[str]) -> bool:
    parts = slug.casefold().split("--", 1)
    repo = parts[-1]
    return any(
        name.casefold() in {slug.casefold(), repo}
        or slug.casefold().endswith("--" + name.casefold())
        for name in checkpoints
    )


def _cache_modules(slug: str, module_refs: dict[str, set[str]]) -> set[str]:
    normalized = re.sub(r"[^a-z0-9]", "", slug.casefold())
    return {
        module
        for module, refs in module_refs.items()
        if any(ref and ref in normalized for ref in refs)
    }


def _dict_body(text: str, name: str) -> str:
    match = re.search(rf"(?m)^{re.escape(name)}\s*(?::[^\n=]*)?=\s*\{{", text)
    if not match:
        return ""
    start = match.end() - 1
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""


def _quoted_alias_tokens(body: str, media_keys_only: bool) -> set[str]:
    lines = body.splitlines()
    if media_keys_only:
        lines = [line for line in lines if "mflux:" in line or "video_mlx:" in line]
    tokens: set[str] = set()
    for line in lines:
        for quoted in re.findall(r"""["']([^"']+)["']""", line):
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", quoted):
                continue
            token = re.sub(r"[^a-z0-9]", "", quoted.casefold())
            # Length 6: bare "qwen", "flux2", and "dev" match unrelated repos.
            if len(token) >= 6:
                tokens.add(token)
    return tokens


def _load_media_alias_tokens() -> set[str]:
    tokens: set[str] = set()
    for path, names, media_keys_only in _MEDIA_TABLES:
        text = _read_text(path)
        for name in names:
            tokens.update(_quoted_alias_tokens(_dict_body(text, name), media_keys_only))
    return tokens


def _media_alias_tokens() -> frozenset[str]:
    global _MEDIA_ALIAS_CACHE
    if _MEDIA_ALIAS_CACHE is None:
        _MEDIA_ALIAS_CACHE = frozenset(_load_media_alias_tokens())
    return _MEDIA_ALIAS_CACHE


def _matches_media_alias(slug: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", slug.casefold())
    return any(token in normalized for token in _media_alias_tokens())


def _cache_owner(
    slug: str,
    checkpoints: set[str],
    disabled_modules: set[str],
    module_refs: dict[str, set[str]],
) -> str:
    if _matches_media_alias(slug):
        return "disabled-module weights" if "media" in disabled_modules else "fleet"
    modules = _cache_modules(slug, module_refs)
    if modules and modules <= disabled_modules:
        return "disabled-module weights"
    if _cache_checkpoint(slug, checkpoints):
        return "duplicate"
    return "other/unclassified"


def _hf_blob_owners(root: Path) -> dict[Path, set[str]]:
    blob_root = root / "hf-cache" / "blobs"
    owners: dict[Path, set[str]] = {}
    try:
        blobs = blob_root.rglob("*")
        for blob in blobs:
            if not blob.is_file() or blob.name.endswith((".lock", ".refs")):
                continue
            references = Path(f"{blob}.refs")
            try:
                refs_text = references.read_text()
            except OSError:
                refs_text = ""
            repos = {
                value.removeprefix("models--") for value in re.findall(r"models--[^/]+", refs_text)
            }
            owners[blob] = repos
    except OSError:
        pass
    return owners


def _add_storage_record(
    records: dict[str, list[_StorageRecord]],
    label: str,
    root: Path,
    path: Path,
    size: int,
    mtime: float,
    source: str,
    display: str | None = None,
) -> None:
    if size > 0:
        records[label].append(
            _StorageRecord(display or str(path.relative_to(root)), size, mtime, source)
        )


def _record_ollama(
    records: dict[str, list[_StorageRecord]],
    root: Path,
    roots: dict[str, _Usage],
    tags: set[str],
    installed_blobs: dict[str, set[str]] | None,
) -> bool:
    if installed_blobs is None:
        return False
    manifests = _ollama_manifest_owners(root)
    api = _invert_tag_blobs(installed_blobs)
    blob_path = root / "ollama" / "models" / "blobs"
    blobs = _walk_usage(blob_path, {blob_path}) if blob_path.exists() else _Usage(blob_path)
    blob_total = 0
    for blob in blobs.children:
        name = blob.path.name.lower()
        _add_storage_record(
            records,
            _ollama_blob_class(name, tags, api, manifests),
            root,
            blob.path,
            blob.size,
            blob.mtime,
            "ollama",
            _ollama_blob_display(name, api, manifests),
        )
        blob_total += blob.size
    if "ollama" in roots:
        _add_storage_record(
            records,
            "other/unclassified",
            root,
            root / "ollama" / "metadata",
            max(0, roots["ollama"].size - blob_total),
            roots["ollama"].mtime,
            "ollama",
        )
    return True


def _record_omlx(
    records: dict[str, list[_StorageRecord]],
    root: Path,
    roots: dict[str, _Usage],
    configured: set[str],
) -> set[str]:
    items = roots.get("omlx-models", _Usage(root)).children
    checkpoints = {item.path.name for item in items if item.is_dir}
    configured_names = {name.casefold() for name in configured}
    for item in items:
        category = "fleet" if item.path.name.casefold() in configured_names else "orphan model data"
        if not item.is_dir:
            category = "other/unclassified"
        _add_storage_record(
            records, category, root, item.path, item.size, item.mtime, "omlx-models"
        )
    return checkpoints


def _record_hf_cache(
    records: dict[str, list[_StorageRecord]],
    root: Path,
    usage: _Usage,
    roots: dict[str, _Usage],
    checkpoints: set[str],
    disabled_modules: set[str],
    module_refs: dict[str, set[str]],
) -> None:
    hf_root = root / "hf-cache"
    repositories = [item for item in usage.repositories if item[0].is_relative_to(hf_root)]
    owners: dict[str, str] = {}
    grouped: dict[tuple[str, str], tuple[int, float]] = {}
    repository_size = 0
    for path, size, mtime in repositories:
        slug = path.name[len("models--") :]
        label = _cache_owner(slug, checkpoints, disabled_modules, module_refs)
        owners[slug] = label
        repository_size += size
        _group_hf_record(grouped, label, f"hf-cache/{slug}", size, mtime)
    blob_size = _record_hf_blobs(grouped, root, owners, checkpoints, disabled_modules, module_refs)
    for (label, display), (size, mtime) in grouped.items():
        records[label].append(_StorageRecord(display, size, mtime, "hf-cache"))
    if "hf-cache" in roots:
        _add_storage_record(
            records,
            "other/unclassified",
            root,
            hf_root / "metadata",
            max(0, roots["hf-cache"].size - repository_size - blob_size),
            roots["hf-cache"].mtime,
            "hf-cache",
        )


def _group_hf_record(
    grouped: dict[tuple[str, str], tuple[int, float]],
    label: str,
    display: str,
    size: int,
    mtime: float,
) -> None:
    key = (label, display)
    old_size, old_mtime = grouped.get(key, (0, 0.0))
    grouped[key] = (old_size + size, max(old_mtime, mtime))


def _record_hf_blobs(
    grouped: dict[tuple[str, str], tuple[int, float]],
    root: Path,
    owners: dict[str, str],
    checkpoints: set[str],
    disabled_modules: set[str],
    module_refs: dict[str, set[str]],
) -> int:
    total = 0
    for path, repos in _hf_blob_owners(root).items():
        try:
            info = path.stat(follow_symlinks=False)
        except OSError:
            continue
        size = _allocated_bytes(info)
        total += size
        labels = {
            owners.get(repo, _cache_owner(repo, checkpoints, disabled_modules, module_refs))
            for repo in repos
        }
        label = next(iter(labels)) if len(labels) == 1 else "other/unclassified"
        display = (
            f"hf-cache/{next(iter(repos))}"
            if len(repos) == 1
            else f"hf-cache/shared-blobs/{path.name}"
        )
        _group_hf_record(grouped, label, display, size, info.st_mtime)
    return total


def _storage_records(
    root: Path,
    usage: _Usage,
    ollama_tags: set[str],
    omlx_models: set[str],
    disabled_modules: set[str],
    module_refs: dict[str, set[str]],
    installed_blobs: dict[str, set[str]] | None,
) -> tuple[dict[str, list[_StorageRecord]], list[str]]:
    labels = (
        "fleet",
        "installed-but-unconfigured",
        "orphan model data",
        "duplicate",
        "disabled-module weights",
        "staging/backups",
        "other/unclassified",
    )
    records = {label: [] for label in labels}
    roots = {item.path.name: item for item in usage.children}
    ollama_verified = _record_ollama(records, root, roots, ollama_tags, installed_blobs)
    checkpoints = _record_omlx(records, root, roots, omlx_models)
    _record_hf_cache(records, root, usage, roots, checkpoints, disabled_modules, module_refs)
    for name in ("gguf-staging", "portal5_backups"):
        for item in roots.get(name, _Usage(root)).children:
            _add_storage_record(
                records, "staging/backups", root, item.path, item.size, item.mtime, name
            )
    handled = {"ollama", "hf-cache", "omlx-models", "gguf-staging", "portal5_backups"}
    for item in usage.children:
        if item.path.name not in handled:
            _add_storage_record(
                records,
                "other/unclassified",
                root,
                item.path,
                item.size,
                item.mtime,
                item.path.name,
            )
    root_lines = []
    for root_name, item in roots.items():
        if root_name == "ollama" and not ollama_verified:
            root_lines.append(f"root {root_name}: {_format_bytes(item.size)}; unverified")
            continue
        classes = sorted(
            label
            for label, values in records.items()
            if any(record.root == root_name for record in values)
        )
        owner_text = ", ".join(classes) if classes else "other/unclassified"
        root_lines.append(f"root {root_name}: {_format_bytes(item.size)}; owner {owner_text}")
    return records, root_lines


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TiB"


def _age_days(mtime: float, now: float) -> str:
    return "age unknown" if not mtime else f"age {max(0, int((now - mtime) // 86400))}d"


def _append_reclaim_lines(report: Report, records: dict[str, list[_StorageRecord]]) -> None:
    # Duplicates stay their own class and are in neither total.
    safe = sum(item.size for item in records["orphan model data"])
    decision = sum(
        item.size
        for label in ("disabled-module weights", "staging/backups")
        for item in records[label]
    )
    report.lines.append(f"safe to reclaim: {_format_bytes(safe)}")
    report.lines.append(f"operator decision: {_format_bytes(decision)}")


def _storage_report(
    root: Path,
    backends_file: Path,
    portal_file: Path,
    total: int | None = None,
    free: int | None = None,
    floor_gib: float = 250,
    floor_percent: float = 15,
    *,
    query_ollama: bool = True,
    installed_blobs: dict[str, set[str]] | None = None,
) -> Report:
    report = Report("storage", current="disk inventory", latest="read-only")
    if not root.is_dir():
        report.status = "unknown"
        report.lines.append(f"storage root missing: {root}")
        return report
    try:
        backend_text = backends_file.read_text()
        portal_text = portal_file.read_text()
    except OSError as error:
        report.status = "error"
        report.lines.append(f"storage config unavailable: {error}")
        return report
    ollama_tags, omlx_models, disabled_modules, module_refs = _storage_config_refs(
        backend_text, portal_text, portal_file.parent
    )
    if query_ollama:
        installed_blobs = _installed_ollama_blobs()
    keep = {
        root,
        *(root / name for name in ("hf-cache", "omlx-models", "gguf-staging", "portal5_backups")),
    }
    keep.add(root / "ollama" / "models" / "blobs")
    usage = _walk_usage(root, keep)
    records, root_lines = _storage_records(
        root,
        usage,
        ollama_tags,
        omlx_models,
        disabled_modules,
        module_refs,
        installed_blobs,
    )
    if total is None or free is None:
        disk = shutil.disk_usage(root)
        total, free = disk.total, disk.free
    floor = max(int(total * floor_percent / 100), int(floor_gib * 1024**3))
    now = time.time()
    ratio = free / total if total else 0
    report.status = "behind" if free < floor else "current"
    report.current = f"{_format_bytes(free)} free ({ratio:.1%})"
    report.latest = f"floor {_format_bytes(floor)}"
    report.high_priority = report.status == "behind"
    report.lines.append(
        f"free: {_format_bytes(free)} / {_format_bytes(total)} ({ratio:.1%}); alert floor "
        f"max({floor_percent:g}%, {floor_gib:g} GiB) = {_format_bytes(floor)}"
    )
    report.lines.extend(root_lines)
    for label, items in records.items():
        total_size = sum(item.size for item in items)
        top = sorted(items, key=lambda item: item.size, reverse=True)[:5]
        report.lines.append(
            f"{label}: {_format_bytes(total_size)}; "
            + (
                "top: "
                + ", ".join(
                    f"{item.path} {_format_bytes(item.size)} ({_age_days(item.mtime, now)})"
                    for item in top
                )
                if top
                else "no items"
            )
        )
    _append_reclaim_lines(report, records)
    if usage.errors:
        report.lines.append(f"partial inventory: {usage.errors} path(s) could not be read")
    return report


def check_storage() -> Report:
    try:
        floor_gib = float(os.environ.get("PORTAL5_STORAGE_FLOOR_GIB", "250"))
        floor_percent = float(os.environ.get("PORTAL5_STORAGE_FLOOR_PERCENT", "15"))
    except ValueError:
        floor_gib, floor_percent = 250, 15
    root = Path(os.environ.get("PORTAL5_STORAGE_ROOT", "/Volumes/data01"))
    return _storage_report(
        root,
        REPO_ROOT / "config" / "backends.yaml",
        REPO_ROOT / "config" / "portal.yaml",
        floor_gib=floor_gib,
        floor_percent=floor_percent,
    )


CHECKERS = {
    "obscura": check_obscura,
    "ollama": check_ollama,
    "omlx": check_omlx,
    "storage": check_storage,
    "python-deps": check_python_deps,
    "python-vulns": check_python_vulns,
    "images": check_images,
    "harnesses": check_harnesses,
    "models": check_models,
}


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
        critical = any(r.high_priority for r in behind)
        title = (
            "Updates need review — SECURITY"
            if sec
            else ("Storage space low" if critical else "Updates need review")
        )
        _pushover(title, out, high=sec or critical)
        names = ", ".join(r.name for r in behind)
        print(f"\n-> actionable: {names} behind upstream" + (" (security-flagged)" if sec else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
