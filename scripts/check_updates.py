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


CHECKERS = {
    "obscura": check_obscura,
    "ollama": check_ollama,
    "omlx": check_omlx,
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
        title = "Updates need review" + (" — SECURITY" if sec else "")
        _pushover(title, out, high=sec)
        names = ", ".join(r.name for r in behind)
        print(f"\n-> actionable: {names} behind upstream" + (" (security-flagged)" if sec else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
