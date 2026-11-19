#!/usr/bin/env python3
"""Inventory host dependencies and report OSV findings without changing installed packages."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OSV_API = "https://api.osv.dev/v1"


def default_output_dir() -> Path:
    """Sweep reports stay out of the git checkout. The weekly launchd job uses this."""
    return Path.home() / ".portal5" / "security"


sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class PackageRef:
    name: str
    version: str
    ecosystem: str
    locations: tuple[str, ...] = ()


@dataclass
class Inventory:
    packages: list[PackageRef]
    sources: dict[str, int]
    errors: list[str]


@dataclass
class SweepResult:
    findings: list[dict[str, str]]
    images: dict[str, int]
    brew_outdated: list[dict[str, str]]
    errors: list[str]


def _package_key(pkg: PackageRef) -> tuple[str, str, str]:
    return pkg.ecosystem.casefold(), pkg.name.casefold(), pkg.version


def merge_packages(packages: Iterable[PackageRef]) -> list[PackageRef]:
    merged: dict[tuple[str, str, str], PackageRef] = {}
    for pkg in packages:
        key = _package_key(pkg)
        previous = merged.get(key)
        if previous is None:
            merged[key] = pkg
        else:
            merged[key] = PackageRef(
                previous.name,
                previous.version,
                previous.ecosystem,
                tuple(sorted(set(previous.locations) | set(pkg.locations))),
            )
    return list(merged.values())


def query_batches(
    packages: Iterable[PackageRef], batch_size: int = 500
) -> list[list[dict[str, object]]]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    unique = merge_packages(packages)
    queries = [
        {"package": {"name": pkg.name, "ecosystem": pkg.ecosystem}, "version": pkg.version}
        for pkg in unique
    ]
    return [queries[index : index + batch_size] for index in range(0, len(queries), batch_size)]


def severity_from_score(score: object) -> str:
    try:
        value = float(str(score))
    except (TypeError, ValueError):
        return "UNKNOWN"
    if value >= 9.0:
        return "CRITICAL"
    if value >= 7.0:
        return "HIGH"
    if value >= 4.0:
        return "MODERATE"
    if value > 0:
        return "LOW"
    return "UNKNOWN"


def alert_required(findings: Iterable[Mapping[str, object]]) -> bool:
    for finding in findings:
        ids = finding.get("ids", (finding.get("id", ""),))
        if isinstance(ids, str):
            ids = ids.split("|")
        if any(str(value).upper().startswith("MAL-") for value in ids):
            return True
        if str(finding.get("severity", "")).upper() == "CRITICAL":
            return True
    return False


def _has_malware_id(finding: Mapping[str, object]) -> bool:
    ids = finding.get("ids", finding.get("id", ""))
    if isinstance(ids, str):
        ids = ids.split("|")
    return any(str(value).upper().startswith("MAL-") for value in ids)


def display_path(path: Path, home: Path) -> str:
    try:
        return "~/" + path.resolve().relative_to(home.resolve()).as_posix()
    except ValueError:
        return str(path)


def _config_services(config_path: Path) -> tuple[list[str], list[str]]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    labels: list[str] = []
    names: list[str] = []
    for service in config.get("mcp_fleet", []):
        if service.get("host_native"):
            names.extend(str(service.get(key, "")) for key in ("id", "native_service"))
            if service.get("launchd_label"):
                labels.append(str(service["launchd_label"]))
        command = service.get("command", {}).get("command", [])
        if any("${HOME}/mcp/" in str(part) for part in command):
            names.append("external-mcp")
            if service.get("launchd_label"):
                labels.append(str(service["launchd_label"]))
    for service in config.get("host_jobs", []):
        names.append(str(service.get("service", "")))
        if service.get("label"):
            labels.append(str(service["label"]))
    return sorted(set(filter(None, names))), sorted(set(labels))


def _find_venvs(root: Path, max_depth: int = 5) -> list[Path]:
    if not root.is_dir():
        return []
    found: list[Path] = []
    root_depth = len(root.parts)
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.parts) - root_depth
        dirs[:] = [name for name in dirs if name not in {".git", "node_modules", "models"}]
        if depth >= max_depth:
            dirs[:] = []
        if "pyvenv.cfg" in files:
            found.append(current_path)
            dirs[:] = []
    return found


def _plist_venv_paths(label: str, home: Path, repo_root: Path) -> list[Path]:
    plist_path = home / "Library" / "LaunchAgents" / f"{label}.plist"
    if not plist_path.is_file():
        return []
    try:
        plist = plistlib.loads(plist_path.read_bytes())
    except (OSError, plistlib.InvalidFileException):
        return []
    values = [str(value) for value in plist.get("ProgramArguments", [])]
    candidates: list[Path] = []
    for value in values:
        expanded = value.replace("__PORTAL_ROOT__", str(repo_root))
        for match in re.findall(r"[^\s\"']*\.venv(?:/bin/python(?:\d+(?:\.\d+)?)?)?", expanded):
            path = Path(os.path.expandvars(match.replace("$HOME", str(home)))).expanduser()
            if path.name.startswith("python"):
                candidates.append(path.parent.parent)
            else:
                candidates.append(path)
        if value.endswith((".sh", ".command")):
            script = Path(os.path.expandvars(value.replace("$HOME", str(home)))).expanduser()
            if script.is_file():
                candidates.extend(_venv_paths_in_text(script.read_text(errors="replace"), home))
    return candidates


def _venv_paths_in_text(content: str, home: Path) -> list[Path]:
    found: list[Path] = []
    pattern = r"[^\s\"'`]+\.venv(?:/bin/python(?:\d+(?:\.\d+)?)?)?"
    for match in re.findall(pattern, content):
        value = match.rstrip(",);]").replace("$HOME", str(home))
        path = Path(os.path.expandvars(value)).expanduser()
        found.append(path.parent.parent if path.name.startswith("python") else path)
    return found


def _service_venv_candidates(names: list[str], home: Path) -> list[Path]:
    candidates: list[Path] = []
    tokens = {name.casefold().replace("_", "-") for name in names}
    if "eg2-embedding" in names:
        tokens.add("eg2-venv")
    portal_root = home / ".portal5"
    if names:
        for path in _find_venvs(portal_root):
            relative = path.relative_to(portal_root)
            if any(part.casefold().replace("_", "-") in tokens for part in relative.parts):
                candidates.append(path)
    for name in names:
        if name == "music":
            candidates.append(home / "projects" / "ACE-Step-1.5")
        if name in {"video_mlx", "video-mlx", "vl-retrieval"}:
            candidates.append(Path("/Volumes/data01") / "ltx-2-mlx")
        if name == "mflux":
            candidates.append(Path("/Volumes/data01") / "mflux-venv")
        if name == "external-mcp":
            candidates.append(home / "mcp")
    return candidates


def _existing_venvs(candidates: Iterable[Path], repo_root: Path, main_root: Path) -> list[Path]:
    found: set[Path] = set()
    for candidate in candidates:
        if candidate.name == ".venv" or (candidate / "pyvenv.cfg").is_file():
            paths = [candidate]
        else:
            paths = _find_venvs(candidate)
        for path in paths:
            if (path / "pyvenv.cfg").is_file():
                resolved = path.resolve()
                if (
                    repo_root.resolve() != main_root.resolve()
                    and resolved == (repo_root / ".venv").resolve()
                ):
                    continue
                found.add(resolved)
    return sorted(found)


def configured_host_venvs(config_path: Path, repo_root: Path, home: Path) -> list[Path]:
    names, labels = _config_services(config_path)
    main_root = home / "projects" / "portal-5"
    main_venv = main_root / ".venv"
    candidates = [main_venv if main_venv.is_dir() else repo_root / ".venv"]
    candidates.extend(_service_venv_candidates(names, home))
    for label in labels:
        candidates.extend(_plist_venv_paths(label, home, repo_root))
    return _existing_venvs(candidates, repo_root, main_root)


def _python_packages(venv: Path, home: Path) -> tuple[list[PackageRef], str | None]:
    interpreter = next(
        (path for path in (venv / "bin" / "python", venv / "bin" / "python3") if path.is_file()),
        None,
    )
    if interpreter is None:
        return [], f"{display_path(venv, home)}: no Python interpreter"
    code = (
        "import importlib.metadata as m,json;"
        "print(json.dumps(sorted((d.metadata.get('Name'),d.version) for d in m.distributions() "
        "if d.metadata.get('Name') and d.version)))"
    )
    try:
        result = subprocess.run(
            [str(interpreter), "-c", code], capture_output=True, text=True, timeout=60, check=True
        )
        packages = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return [], f"{display_path(venv, home)}: {type(exc).__name__}"
    location = display_path(venv, home)
    return [PackageRef(name, version, "PyPI", (location,)) for name, version in packages], None


def _lock_packages(lock_path: Path) -> list[PackageRef]:
    packages: list[PackageRef] = []
    for block in lock_path.read_text(encoding="utf-8").split("[[package]]")[1:]:
        match = re.match(r'\s*name = "([^\"]+)"\nversion = "([^\"]+)"', block)
        header = block.split("\n\n", 1)[0]
        if match and 'source = { registry = "https://pypi.org/simple" }' in header:
            marker_block = re.search(r"resolution-markers = \[(.*?)\]", header, re.S)
            marker_text = marker_block.group(1) if marker_block else ""
            markers = sorted(
                {
                    value
                    for expression in re.findall(r'"([^"]+)"', marker_text)
                    for value in re.findall(r"python_full_version\s*[<>=!]+\s*'[^']+'", expression)
                }
            )
            location = "uv.lock" + (f" ({'; '.join(markers)})" if markers else "")
            packages.append(PackageRef(match.group(1), match.group(2), "PyPI", (location,)))
    return packages


def _uv_tool_venvs(home: Path) -> list[Path]:
    tool = shutil.which("uv") or str(home / ".local" / "bin" / "uv")
    try:
        result = subprocess.run(
            [tool, "tool", "dir"], capture_output=True, text=True, timeout=15, check=True
        )
        root = Path(result.stdout.strip()).expanduser()
    except (OSError, subprocess.SubprocessError):
        root = home / ".local" / "share" / "uv" / "tools"
    return [path for path in _find_venvs(root, max_depth=3) if path != root]


def _npm_cache_roots(home: Path) -> list[Path]:
    default = home / ".npm" / "_npx"
    return [default] if default.is_dir() else []


def _npm_packages(root: Path, home: Path) -> list[PackageRef]:
    packages: list[PackageRef] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in {".cache", ".git"}]
        if "package.json" not in files:
            continue
        path = Path(current) / "package.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name, version = data.get("name"), data.get("version")
        if name and version:
            packages.append(
                PackageRef(str(name), str(version), "npm", (display_path(path.parent, home),))
            )
    return packages


def collect_inventory(repo_root: Path, home: Path) -> Inventory:
    errors: list[str] = []
    packages = _lock_packages(repo_root / "uv.lock")
    sources: dict[str, int] = {"repo lock packages": len(merge_packages(packages))}
    host_venvs = configured_host_venvs(repo_root / "config" / "portal.yaml", repo_root, home)
    sources["configured host venvs"] = len(host_venvs)
    for venv in host_venvs:
        found, error = _python_packages(venv, home)
        packages.extend(found)
        if error:
            errors.append(error)
    tools = _uv_tool_venvs(home)
    sources["uv tool venvs"] = len(tools)
    for venv in tools:
        found, error = _python_packages(venv, home)
        packages.extend(found)
        if error:
            errors.append(error)
    caches = _npm_cache_roots(home)
    sources["npx caches"] = sum(
        sum(child.is_dir() for child in cache.iterdir()) for cache in caches
    )
    for cache in caches:
        packages.extend(_npm_packages(cache, home))
    return Inventory(merge_packages(packages), sources, errors)


def _post_json(url: str, body: dict[str, object]) -> dict[str, object]:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=45) as response:  # fixed OSV endpoint
        return json.loads(response.read().decode())


def _version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value))


def _fixed_versions(vuln: Mapping[str, object], package: PackageRef) -> str:
    fixed: list[str] = []
    for affected in vuln.get("affected", []) if isinstance(vuln.get("affected", []), list) else []:
        if not isinstance(affected, dict):
            continue
        identity = affected.get("package", {})
        if not isinstance(identity, dict):
            continue
        if str(identity.get("name", "")).casefold() != package.name.casefold():
            continue
        if str(identity.get("ecosystem", "")).casefold() != package.ecosystem.casefold():
            continue
        ranges = affected.get("ranges", [])
        if not isinstance(ranges, list):
            continue
        for version_range in ranges:
            if not isinstance(version_range, dict):
                continue
            events = version_range.get("events", [])
            if isinstance(events, list):
                fixed.extend(
                    str(event["fixed"])
                    for event in events
                    if isinstance(event, dict) and event.get("fixed")
                )
    return min(fixed, key=_version_key) if fixed else ""


def _fetch_vuln(vuln_id: str) -> dict[str, object]:
    url = f"{OSV_API}/vulns/{urllib.parse.quote(vuln_id, safe='')}"
    with urllib.request.urlopen(url, timeout=20) as response:  # fixed OSV endpoint
        return json.loads(response.read().decode())


def _finding(
    pkg: PackageRef, vuln: Mapping[str, object], severity_override: str = ""
) -> dict[str, str]:
    database = vuln.get("database_specific", {})
    severity = database.get("severity", "UNKNOWN") if isinstance(database, dict) else "UNKNOWN"
    severity = str(severity_override or severity).upper()
    if severity not in {"CRITICAL", "HIGH", "MODERATE", "LOW", "UNKNOWN"}:
        severity = severity_from_score(severity)
    aliases = vuln.get("aliases", [])
    ids = [str(vuln.get("id", "UNKNOWN"))]
    if isinstance(aliases, list):
        ids.extend(str(value) for value in aliases)
    return {
        "ecosystem": pkg.ecosystem,
        "package": pkg.name,
        "version": pkg.version,
        "id": str(vuln.get("id", "UNKNOWN")),
        "ids": "|".join(dict.fromkeys(ids)),
        "severity": severity,
        "fixed": _fixed_versions(vuln, pkg),
        "summary": str(vuln.get("summary", "")).replace("\n", " ")[:100],
        "source": ", ".join(pkg.locations),
    }


def query_osv(packages: Iterable[PackageRef]) -> tuple[list[dict[str, str]], list[str]]:
    unique = merge_packages(packages)
    by_key = {_package_key(pkg): pkg for pkg in unique}
    pending: list[tuple[PackageRef, dict[str, object]]] = []
    errors: list[str] = []
    for batch in query_batches(unique):
        try:
            response = _post_json(f"{OSV_API}/querybatch", {"queries": batch})
        except (OSError, ValueError, urllib.error.URLError) as exc:
            errors.append(f"OSV querybatch: {type(exc).__name__}")
            continue
        results = response.get("results", [])
        if not isinstance(results, list) or len(results) != len(batch):
            errors.append("OSV querybatch returned an unexpected result count")
            continue
        for query, result in zip(batch, results, strict=True):
            if not isinstance(result, dict) or not isinstance(query, dict):
                continue
            identity = query.get("package", {})
            if not isinstance(identity, dict):
                continue
            key = (
                str(identity.get("ecosystem", "")).casefold(),
                str(identity.get("name", "")).casefold(),
                str(query.get("version", "")),
            )
            package = by_key.get(key)
            vulns = result.get("vulns", [])
            if package is not None and isinstance(vulns, list):
                pending.extend((package, vuln) for vuln in vulns if isinstance(vuln, dict))
    missing_ids = {
        str(vuln.get("id"))
        for _, vuln in pending
        if vuln.get("id") and not isinstance(vuln.get("affected"), list)
    }
    details: dict[str, dict[str, object]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        requests = {pool.submit(_fetch_vuln, vuln_id): vuln_id for vuln_id in missing_ids}
        for future in concurrent.futures.as_completed(requests):
            vuln_id = requests[future]
            try:
                details[vuln_id] = future.result()
            except (OSError, ValueError, urllib.error.URLError) as exc:
                errors.append(f"OSV detail {vuln_id}: {type(exc).__name__}")
    findings: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for package, vuln in pending:
        vuln_id = str(vuln.get("id", "UNKNOWN"))
        detail = vuln if isinstance(vuln.get("affected"), list) else details.get(vuln_id, vuln)
        row = _finding(package, detail)
        key = (*_package_key(package), row["id"])
        if key not in seen:
            seen.add(key)
            findings.append(row)
    return findings, errors


def _docker_images(docker: str) -> tuple[dict[str, list[str]], list[str]]:
    try:
        result = subprocess.run(
            [docker, "image", "ls", "--format", "{{.Repository}}:{{.Tag}}\t{{.ID}}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {}, [f"Docker image inventory: {type(exc).__name__}"]
    images: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        ref, _, image_id = line.partition("\t")
        if ref and image_id and "<none>" not in ref:
            images.setdefault(image_id, []).append(ref)
    return images, []


def _docker_group_scores(item: Mapping[str, object]) -> dict[str, str]:
    scores: dict[str, str] = {}
    groups = item.get("groups", [])
    if not isinstance(groups, list):
        return scores
    for group in groups:
        if not isinstance(group, dict):
            continue
        score = severity_from_score(group.get("max_severity"))
        ids, aliases = group.get("ids", []), group.get("aliases", [])
        if isinstance(ids, list) and isinstance(aliases, list):
            scores.update({str(value): score for value in [*ids, *aliases]})
    return scores


def _docker_item_findings(item: Mapping[str, object], source: str) -> list[dict[str, str]]:
    package_data = item.get("package", {})
    if not isinstance(package_data, dict):
        return []
    package = PackageRef(
        str(package_data.get("name", "unknown")),
        str(package_data.get("version", "unknown")),
        str(package_data.get("ecosystem", "unknown")),
        (source,),
    )
    scores = _docker_group_scores(item)
    vulns = item.get("vulnerabilities", [])
    if not isinstance(vulns, list):
        return []
    return [
        _finding(package, vuln, scores.get(str(vuln.get("id", "")), ""))
        for vuln in vulns
        if isinstance(vuln, dict)
    ]


def _docker_findings(
    data: Mapping[str, object], refs: list[str]
) -> tuple[list[dict[str, str]], int]:
    findings: list[dict[str, str]] = []
    package_count = 0
    results = data.get("results", [])
    if not isinstance(results, list):
        return findings, package_count
    source = "docker image " + ", ".join(refs)
    for result in results:
        if not isinstance(result, dict):
            continue
        packages = result.get("packages", [])
        if isinstance(packages, list):
            package_count += len(packages)
            findings.extend(
                row
                for item in packages
                if isinstance(item, dict)
                for row in _docker_item_findings(item, source)
            )
    return findings, package_count


def scan_docker_images() -> tuple[list[dict[str, str]], dict[str, int], list[str]]:
    scanner = shutil.which("osv-scanner")
    docker = shutil.which("docker") or "/usr/local/bin/docker"
    if not scanner:
        return [], {"images": 0, "scanned": 0, "packages": 0}, ["osv-scanner is not installed"]
    images, errors = _docker_images(docker)
    findings: list[dict[str, str]] = []
    packages = 0
    scanned = 0
    for refs in images.values():
        print(f"Scanning Docker image {refs[0]}", flush=True)
        with tempfile.TemporaryDirectory(prefix="portal-osv-image-") as temp_dir:
            output = Path(temp_dir) / "result.json"
            try:
                result = subprocess.run(
                    [
                        scanner,
                        "scan",
                        "image",
                        refs[0],
                        "--format",
                        "json",
                        "--all-packages",
                        "--output-file",
                        str(output),
                        "--verbosity",
                        "error",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=900,
                )
                if not output.is_file():
                    errors.append(f"{refs[0]}: scanner exit {result.returncode}")
                    continue
                data = json.loads(output.read_text(encoding="utf-8"))
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
                errors.append(f"{refs[0]}: {type(exc).__name__}")
                continue
            image_findings, count = _docker_findings(data, refs)
            findings.extend(image_findings)
            packages += count
            scanned += 1
    return findings, {"images": len(images), "scanned": scanned, "packages": packages}, errors


def brew_outdated() -> tuple[list[dict[str, str]], list[str]]:
    brew = shutil.which("brew")
    if not brew:
        return [], ["Homebrew is not installed"]
    env = {**os.environ, "HOMEBREW_NO_AUTO_UPDATE": "1"}
    try:
        result = subprocess.run(
            [brew, "outdated", "--json=v2"],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
            env=env,
        )
        data = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return [], [f"Homebrew outdated: {type(exc).__name__}"]
    rows = []
    for formula in data.get("formulae", []):
        installed = ",".join(formula.get("installed_versions", [])) or "unknown"
        rows.append(
            {
                "name": str(formula.get("name", "")),
                "installed": installed,
                "current": str(formula.get("current_version", "unknown")),
            }
        )
    for cask in data.get("casks", []):
        installed = ",".join(cask.get("installed_versions", [])) or "unknown"
        rows.append(
            {
                "name": str(cask.get("token", "")),
                "installed": installed,
                "current": str(cask.get("current_version", "unknown")),
            }
        )
    return rows, []


def _bench_venvs(home: Path) -> list[str]:
    root = home / ".claude" / "orchestrate" / "bench"
    return [display_path(path, home) for path in _find_venvs(root, max_depth=6)]


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def write_report(
    path: Path,
    created: str,
    inventory: Inventory,
    result: SweepResult,
    bench_venvs: list[str],
) -> None:
    critical = sum(row["severity"] == "CRITICAL" for row in result.findings)
    malware = sum(_has_malware_id(row) for row in result.findings)
    package_findings = [
        row for row in result.findings if not row["source"].startswith("docker image ")
    ]
    image_findings = [row for row in result.findings if row["source"].startswith("docker image ")]
    lines = [
        f"# Security sweep — {created}",
        "",
        "Read-only dependency inventory using OSV.dev querybatch and osv-scanner.",
        "",
        f"- Package versions queried: {len(inventory.packages)}",
        f"- Package findings: {len(package_findings)}",
        f"- Container findings: {len(image_findings)}",
        f"- MAL advisories: {malware}",
        f"- CRITICAL findings: {critical}",
        f"- Docker images scanned: {result.images.get('scanned', 0)} / {result.images.get('images', 0)}",
        f"- Container package entries: {result.images.get('packages', 0)}",
        "",
        "## Inventory",
        "",
    ]
    lines.extend(f"- {name}: {count}" for name, count in inventory.sources.items())
    lines.extend(
        [
            "",
            "## OSV findings",
            "",
            "| Ecosystem | Package | Version | Advisory | Severity | Fixed in | Source |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for row in sorted(
        result.findings, key=lambda value: (value["severity"], value["id"], value["package"])
    ):
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(row[key])
                for key in ("ecosystem", "package", "version", "id", "severity", "fixed", "source")
            )
            + " |"
        )
    if not result.findings:
        lines.append("| — | — | — | — | — | — | No advisories found |")
    lines.extend(
        [
            "",
            "## Homebrew outdated",
            "",
            "Homebrew outdated versions are update signals, not OSV vulnerability claims.",
            "",
        ]
    )
    if result.brew_outdated:
        lines.extend(
            f"- `{row['name']}` {row['installed']} → {row['current']}"
            for row in result.brew_outdated
        )
    else:
        lines.append("- No outdated formulae or casks reported.")
    lines.extend(
        [
            "",
            "## Excluded throwaway bench venvs",
            "",
            "Listed for cleanup only; not scanned or patched.",
            "",
        ]
    )
    lines.extend(f"- `{value}`" for value in bench_venvs)
    if not bench_venvs:
        lines.append("- None found.")
    lines.extend(["", "## Scan errors", ""])
    lines.extend(f"- {error}" for error in result.errors)
    if not result.errors:
        lines.append("- None.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _telegram_alert(title: str, message: str) -> bool:
    token = os.environ.get("TELEGRAM_ALERT_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_ALERT_CHANNEL_ID") or os.environ.get("TELEGRAM_USER_IDS", "")
    if not token or not chat:
        return False
    chat_id = chat.split(",", 1)[0].strip()
    payload = json.dumps(
        {"chat_id": chat_id, "text": f"*{title}*\n{message[:3500]}", "parse_mode": "Markdown"}
    ).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15):  # fixed Telegram API host
            return True
    except urllib.error.URLError as exc:
        print(f"Telegram alert failed: {type(exc).__name__}", file=sys.stderr)
        return False


def send_alert(findings: list[dict[str, str]]) -> None:
    urgent = [row for row in findings if _has_malware_id(row) or row["severity"] == "CRITICAL"]
    message = "\n".join(
        f"{row['ids']} {row['severity']} — {row['package']} {row['version']} ({row['source']})"
        for row in urgent[:20]
    )
    if len(urgent) > 20:
        message += f"\n…and {len(urgent) - 20} more urgent findings"
    _telegram_alert("Portal security sweep alert", message)
    from scripts.check_updates import _pushover  # noqa: PLC0415

    _pushover("Portal security sweep alert", message, high=True)


def _run(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    home = Path(args.home).expanduser().resolve()
    date = args.date or dt.datetime.now().astimezone().date().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise SystemExit("--date must use YYYY-MM-DD")
    inventory = collect_inventory(repo, home)
    findings, query_errors = query_osv(inventory.packages)
    if args.skip_images:
        image_findings = []
        image_stats = {"images": 0, "scanned": 0, "packages": 0}
        image_errors = ["Docker image scan intentionally skipped"]
    else:
        image_findings, image_stats, image_errors = scan_docker_images()
    brew_rows, brew_errors = brew_outdated()
    result = SweepResult(
        findings + image_findings,
        image_stats,
        brew_rows,
        inventory.errors + query_errors + image_errors + brew_errors,
    )
    report = Path(args.output_dir) / f"security_sweep_{date.replace('-', '')}.md"
    write_report(report, date, inventory, result, _bench_venvs(home))
    print(f"Report: {report}")
    print(
        f"Packages: {len(inventory.packages)}; findings: {len(result.findings)}; "
        f"Docker images: {image_stats['scanned']}/{image_stats['images']}; "
        f"Homebrew outdated: {len(brew_rows)}; scan errors: {len(result.errors)}"
    )
    if alert_required(result.findings):
        print("SECURITY ALERT: MAL advisory or CRITICAL severity found")
        if not args.no_alert:
            send_alert(result.findings)
    return 1 if result.errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(ROOT), help="Portal repository root")
    parser.add_argument("--home", default=str(Path.home()), help="Host home directory")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD form")
    parser.add_argument("--output-dir", default=str(default_output_dir()))
    parser.add_argument(
        "--no-alert", action="store_true", help="Suppress outbound Telegram/Pushover alerts"
    )
    parser.add_argument(
        "--skip-images", action="store_true", help="Skip expensive Docker image scans"
    )
    return _run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
