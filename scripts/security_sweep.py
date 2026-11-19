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
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OSV_API = "https://api.osv.dev/v1"
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
    triage: list[dict[str, str]] = field(default_factory=list)
    npx_pins: list[dict[str, str]] = field(default_factory=list)
    brew_security: list[dict[str, str]] = field(default_factory=list)
    brew_routine: list[dict[str, str]] = field(default_factory=list)
    delta: dict[str, object] = field(default_factory=dict)


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


def _npx_packages(config_path: Path) -> list[dict[str, str]]:
    """npx-launched MCP commands from config/portal.yaml: floating unless pinned pkg@exact."""
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    rows: list[dict[str, str]] = []
    for service in config.get("mcp_fleet", []):
        if not isinstance(service, dict):
            continue
        command = service.get("command", {}).get("command", [])
        if not command or str(command[0]) != "npx":
            continue
        spec = next((str(part) for part in command[1:] if not str(part).startswith("-")), "")
        rows.append(
            {
                "service": str(service.get("id", "")),
                "package": spec,
                "pinned": _pinned_version(spec),
            }
        )
    return rows


def _pinned_version(spec: str) -> str:
    if spec.startswith("@"):
        _, _, rest = spec.partition("@")
        return rest.rpartition("@")[2] if "@" in rest else ""
    return spec.rpartition("@")[2] if "@" in spec else ""


def _npm_latest(package: str) -> str:
    url = f"https://registry.npmjs.org/{urllib.parse.quote(package, safe='@')}/latest"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.loads(response.read().decode())
    except (OSError, ValueError, urllib.error.URLError):
        return ""
    return str(data.get("version", ""))


def npx_pin_rows(config_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    rows = _npx_packages(config_path)
    errors: list[str] = []
    for row in rows:
        row["latest"] = _npm_latest(row["package"])
        if not row["latest"]:
            errors.append(f"npm registry: no latest version for {row['package']}")
            row["status"] = "unknown"
        elif row["pinned"] == row["latest"]:
            row["status"] = "pinned (latest)"
        elif row["pinned"]:
            row["status"] = "stale pin"
        else:
            row["status"] = "floating"
    return rows, errors


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


IMAGE_CACHE_VERSION = 1
OURS_IMAGE_PREFIXES = ("portal5-", "portal-5-")
DOCKERFILE_HINTS = (
    ("pipeline", "Dockerfile.pipeline"),
    ("open-webui", "deploy/portal-5/Dockerfile.openwebui (OPENWEBUI_VERSION arg)"),
    ("browser", "deploy/browser-mcp/Dockerfile"),
    ("dind", "Dockerfile.dind"),
    ("cad", "Dockerfile.cad"),
    ("binresearch", "Dockerfile.binresearch"),
    ("attack", "Dockerfile.attack"),
    ("pwsh", "Dockerfile.pwsh"),
    ("mcp", "Dockerfile.mcp"),
)


def _parse_image_inspect(stdout: str) -> dict[str, list[str]]:
    """Map cache key (first repo digest, else image id) -> all tagged refs."""
    keys: dict[str, list[str]] = {}
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        image_id, digest_json, tag_blob = parts
        tags = [tag for tag in tag_blob.split() if "<none>" not in tag]
        if not tags:
            continue
        try:
            digests = json.loads(digest_json)
        except json.JSONDecodeError:
            digests = []
        key = str(digests[0]) if isinstance(digests, list) and digests else image_id
        refs = keys.setdefault(key, [])
        refs.extend(tag for tag in tags if tag not in refs)
    return keys


def image_inventory(
    docker: str, images: dict[str, list[str]]
) -> tuple[dict[str, list[str]], list[str]]:
    try:
        result = subprocess.run(
            [
                docker,
                "image",
                "inspect",
                "--format",
                '{{.ID}}{{"\\t"}}{{json .RepoDigests}}{{"\\t"}}{{range .RepoTags}}{{.}} {{end}}',
                *images,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {}, [f"Docker image inspect: {type(exc).__name__}"]
    return _parse_image_inspect(result.stdout), []


def _scanner_version(scanner: str) -> str:
    try:
        result = subprocess.run(
            [scanner, "--version"], capture_output=True, text=True, timeout=15, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else "unknown"


def load_image_cache(path: Path, scanner_id: str) -> dict[str, dict[str, object]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict) or data.get("version") != IMAGE_CACHE_VERSION:
        return {}
    if data.get("scanner") != scanner_id:
        return {}
    images = data.get("images")
    return images if isinstance(images, dict) else {}


def save_image_cache(path: Path, scanner_id: str, images: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": IMAGE_CACHE_VERSION, "scanner": scanner_id, "images": images}
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def classify_image(refs: list[str]) -> str:
    return (
        "ours"
        if any(ref.startswith(prefix) for ref in refs for prefix in OURS_IMAGE_PREFIXES)
        else "upstream"
    )


def dockerfile_hint(refs: list[str]) -> str:
    name = refs[0].casefold() if refs else ""
    for token, hint in DOCKERFILE_HINTS:
        if token in name:
            return hint
    return "deploy/portal-5/docker-compose.yml (build: section)"


def latest_upstream_tags(ref: str, count: int = 3) -> str:
    """Newest Docker Hub tags for an upstream image; '' when unavailable (local-only builds, ghcr, offline)."""
    name = ref.rsplit(":", 1)[0]
    if name.startswith("ghcr.io/") or name.count("/") > 1:
        return ""
    if "/" not in name:
        name = f"library/{name}"
    url = f"https://hub.docker.com/v2/repositories/{name}/tags/?page_size={count}&ordering=last_updated"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.loads(response.read().decode())
    except (OSError, ValueError, urllib.error.URLError):
        return ""
    tags = [
        str(result["name"])
        for result in data.get("results", [])
        if isinstance(result, dict) and result.get("name")
    ]
    return ", ".join(tags)


def build_image_triage(
    rows_by_key: dict[str, list[dict[str, str]]], keys: dict[str, list[str]]
) -> list[dict[str, str]]:
    """One triage row per image with HIGH/CRITICAL findings: ours (fix in our Dockerfile) vs upstream."""
    triage: list[dict[str, str]] = []
    for key, refs in sorted(keys.items(), key=lambda item: item[1][0]):
        rows = rows_by_key.get(key, [])
        high = [row for row in rows if row["severity"] == "HIGH"]
        critical = [row for row in rows if row["severity"] == "CRITICAL"]
        if not high and not critical:
            continue
        ids = dict.fromkeys(row["id"] for row in [*critical, *high])
        ownership = classify_image(refs)
        if ownership == "ours":
            action = f"base bump / rebuild from {dockerfile_hint(refs)}"
        else:
            tags = latest_upstream_tags(refs[0])
            suffix = f" (latest: {tags})" if tags else ""
            action = f"upstream: pull newer tag{suffix}, then rescan"
        triage.append(
            {
                "image": refs[0] + (f" (+{len(refs) - 1} tags)" if len(refs) > 1 else ""),
                "ownership": ownership,
                "critical": str(len(critical)),
                "high": str(len(high)),
                "advisories": "|".join(list(ids)[:6]),
                "action": action,
            }
        )
    return triage


def scan_docker_images(
    docker: str,
    cache_path: Path,
    image_timeout: int = 600,
    refresh: bool = False,
) -> tuple[list[dict[str, str]], dict[str, int], list[str], list[dict[str, str]]]:
    scanner = shutil.which("osv-scanner")
    if not scanner:
        return (
            [],
            {"images": 0, "scanned": 0, "cached": 0, "packages": 0},
            ["osv-scanner is not installed"],
            [],
        )
    images, errors = _docker_images(docker)
    keys, inspect_errors = image_inventory(docker, list(images))
    errors.extend(inspect_errors)
    scanner_id = _scanner_version(scanner)
    cache: dict[str, dict[str, object]] = (
        {} if refresh else load_image_cache(cache_path, scanner_id)
    )
    findings: list[dict[str, str]] = []
    rows_by_key: dict[str, list[dict[str, str]]] = {}
    packages = scanned = cached = 0
    for key, refs in sorted(keys.items(), key=lambda item: item[1][0]):
        entry = cache.get(key)
        if isinstance(entry, dict):
            rows = [
                dict(row, source="docker image " + ", ".join(refs))
                for row in entry.get("findings", [])
            ]
            findings.extend(rows)
            rows_by_key[key] = rows
            packages += int(entry.get("packages", 0))
            cached += 1
            continue
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
                    timeout=image_timeout,
                )
                if not output.is_file():
                    errors.append(f"{refs[0]}: scanner exit {result.returncode}")
                    continue
                data = json.loads(output.read_text(encoding="utf-8"))
            except subprocess.TimeoutExpired:
                errors.append(f"{refs[0]}: scan timed out after {image_timeout}s; re-run to resume")
                continue
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
                errors.append(f"{refs[0]}: {type(exc).__name__}")
                continue
            image_findings, count = _docker_findings(data, refs)
        findings.extend(image_findings)
        rows_by_key[key] = image_findings
        packages += count
        scanned += 1
        cache[key] = {
            "findings": [dict(row, source="") for row in image_findings],
            "packages": count,
            "scanned": dt.datetime.now().astimezone().date().isoformat(),
        }
    save_image_cache(cache_path, scanner_id, cache)
    stats = {"images": len(keys), "scanned": scanned, "cached": cached, "packages": packages}
    triage = build_image_triage(rows_by_key, keys) if keys else []
    return findings, stats, errors, triage


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


BREW_OSV_ECOSYSTEMS = (
    "PyPI",
    "npm",
    "Alpine:v3.20",
    "Alpine:v3.21",
    "Alpine:v3.22",
    "Debian:12",
    "Debian:13",
    "Ubuntu:24.04",
)


def _brew_name_candidates(name: str) -> list[str]:
    base = name.casefold()
    return [base, re.sub(r"@[0-9.]+$", "", base)]


def brew_security_split(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    """Split outdated formulae by whether OSV knows an advisory at the installed version.

    Heuristic triage: distro ecosystems version packages differently from Homebrew,
    so a hit means "investigate before upgrading", never "proven vulnerable".
    """
    queries: list[dict[str, object]] = []
    owner: dict[tuple[str, str], str] = {}
    for row in rows:
        versions = [part.strip() for part in row["installed"].split(",") if part.strip()]
        for name in _brew_name_candidates(row["name"]):
            for ecosystem in BREW_OSV_ECOSYSTEMS:
                for version in versions:
                    if (name, ecosystem) in owner:
                        continue
                    owner[(name, ecosystem)] = row["name"]
                    queries.append(
                        {"package": {"name": name, "ecosystem": ecosystem}, "version": version}
                    )
    hits: set[str] = set()
    ids_by_row: dict[str, list[str]] = {}
    for start in range(0, len(queries), 500):
        batch = queries[start : start + 500]
        try:
            response = _post_json(f"{OSV_API}/querybatch", {"queries": batch})
        except (OSError, ValueError, urllib.error.URLError) as exc:
            return [], [], [f"OSV querybatch (brew): {type(exc).__name__}"]
        results = response.get("results", [])
        if not isinstance(results, list) or len(results) != len(batch):
            return [], [], ["OSV querybatch (brew): unexpected result count"]
        for query, result in zip(batch, results, strict=True):
            vulns = result.get("vulns", []) if isinstance(result, dict) else []
            if not vulns:
                continue
            identity = query.get("package", {})
            row_name = owner.get(
                (str(identity.get("name", "")), str(identity.get("ecosystem", ""))), ""
            )
            if not row_name:
                continue
            hits.add(row_name)
            ids_by_row.setdefault(row_name, []).extend(
                str(vuln.get("id", "unknown")) for vuln in vulns if isinstance(vuln, dict)
            )
    security: list[dict[str, str]] = []
    routine: list[dict[str, str]] = []
    for row in rows:
        target, label = (
            (security, ", ".join(dict.fromkeys(ids_by_row.get(row["name"], []))))
            if row["name"] in hits
            else (routine, "")
        )
        target.append({**row, "advisories": label})
    return security, routine, []


def _bench_venvs(home: Path) -> list[str]:
    root = home / ".claude" / "orchestrate" / "bench"
    return [display_path(path, home) for path in _find_venvs(root, max_depth=6)]


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _delta_rows_table(title: str, rows: list[object]) -> list[str]:
    if not rows:
        return [f"### {title}", "", "None.", ""]
    lines = [
        f"### {title}",
        "",
        "| Ecosystem | Package | Version | Advisory | Severity | Source |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        if isinstance(row, Mapping):
            cells = (
                _markdown_cell(str(row.get(key, "")))
                for key in ("ecosystem", "package", "version", "id", "severity", "source")
            )
            lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def _render_delta(delta: Mapping[str, object]) -> list[str]:
    previous_date = str(delta.get("previous_date", ""))
    if delta.get("baseline"):
        return [
            "## Delta",
            "",
            "Baseline run: no previous sweep state, so every finding below counts as new.",
            "",
        ]
    new = delta.get("new", [])
    carried = delta.get("carried", [])
    resolved = delta.get("resolved", [])
    return [
        f"## Delta vs previous sweep ({previous_date})",
        "",
        f"- New: {len(new)} / Carried: {len(carried)} / Resolved: {len(resolved)}",
        "- Carried findings are the rows in the OSV findings table above.",
        "",
        *_delta_rows_table("New", new),
        *_delta_rows_table("Resolved", resolved),
    ]


def _render_triage(triage: list[dict[str, str]]) -> list[str]:
    lines = [
        "## Docker image HIGH/CRITICAL triage",
        "",
        "| Image | Ownership | CRITICAL | HIGH | Advisories | Action |",
        "|---|---|---|---|---|---|",
    ]
    if not triage:
        lines.append("| — | — | — | — | — | No HIGH/CRITICAL image findings |")
    for row in triage:
        keys = ("image", "ownership", "critical", "high", "advisories", "action")
        lines.append("| " + " | ".join(_markdown_cell(row.get(key, "")) for key in keys) + " |")
    lines.append("")
    return lines


def _render_npx_pins(rows: list[dict[str, str]]) -> list[str]:
    lines = [
        "## npx MCP pins",
        "",
        "config/portal.yaml npx sources vs npm latest; a floating pin lets a poisoned npx cache re-execute.",
        "",
        "| Service | Package | Pinned | Latest | Status |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        keys = ("service", "package", "pinned", "latest", "status")
        lines.append("| " + " | ".join(_markdown_cell(row.get(key, "")) for key in keys) + " |")
    lines.append("")
    return lines


def _render_brew_split(security: list[dict[str, str]], routine: list[dict[str, str]]) -> list[str]:
    lines = [
        "## Homebrew outdated — security split",
        "",
        "Update signals with an OSV advisory hit at the installed version (heuristic triage,",
        "not proof — distro ecosystems version packages differently from Homebrew).",
        "",
        f"### Security-relevant ({len(security)})",
        "",
    ]
    lines.extend(
        f"- `{row['name']}` {row['installed']} → {row['current']} — {row['advisories'] or 'advisory hits in tracked ecosystems'}"
        for row in security
    )
    if not security:
        lines.append("- None.")
    lines.extend(["", f"### Routine ({len(routine)})", ""])
    lines.extend(f"- `{row['name']}` {row['installed']} → {row['current']}" for row in routine)
    lines.extend(
        [
            "",
            "Exact upgrade commands for the operator:",
            "",
            "```bash",
            "brew upgrade " + " ".join(row["name"] for row in security),
            "brew upgrade " + " ".join(row["name"] for row in routine),
            "```",
            "",
        ]
    )
    return lines


def _finding_identity(row: Mapping[str, str]) -> tuple[str, str, str, str]:
    return (
        row.get("ecosystem", ""),
        row.get("package", ""),
        row.get("version", ""),
        row.get("id", ""),
    )


def load_previous_findings(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_findings_state(path: Path, date: str, rows: list[dict[str, str]]) -> None:
    slim = [
        {
            "ecosystem": row["ecosystem"],
            "package": row["package"],
            "version": row["version"],
            "id": row["id"],
            "severity": row.get("severity", ""),
            "source": row.get("source", ""),
        }
        for row in rows
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"date": date, "findings": slim}, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def compute_delta(
    rows: list[dict[str, str]], previous: Mapping[str, object] | None
) -> dict[str, object]:
    """Classify this run's findings against the stored last-run state: new / carried / resolved."""
    if previous is None:
        return {"baseline": True, "previous_date": "", "new": rows, "carried": [], "resolved": []}
    prior_rows = [row for row in previous.get("findings", []) if isinstance(row, Mapping)]
    prior = {_finding_identity(row) for row in prior_rows}
    current: dict[tuple[str, str, str, str], dict[str, str]] = {
        _finding_identity(row): row for row in rows
    }
    carried_keys = prior.intersection(current)
    resolved = [dict(row) for row in prior_rows if _finding_identity(row) in prior - current.keys()]
    return {
        "baseline": False,
        "previous_date": str(previous.get("date", "")),
        "new": [current[key] for key in sorted(current.keys() - prior)],
        "carried": [current[key] for key in sorted(carried_keys)],
        "resolved": resolved,
    }


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
        f"- Docker images: {result.images.get('cached', 0)} cached + {result.images.get('scanned', 0)} scanned / {result.images.get('images', 0)}",
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
    lines.extend(["", *_render_delta(result.delta)])
    lines.extend(_render_triage(result.triage))
    lines.extend(_render_npx_pins(result.npx_pins))
    lines.extend(_render_brew_split(result.brew_security, result.brew_routine))
    lines.extend(
        [
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
    image_findings: list[dict[str, str]] = []
    image_stats = {"images": 0, "scanned": 0, "cached": 0, "packages": 0}
    image_triage: list[dict[str, str]] = []
    if args.skip_images:
        image_errors = ["Docker image scan intentionally skipped"]
    else:
        docker = shutil.which("docker") or "/usr/local/bin/docker"
        image_findings, image_stats, image_errors, image_triage = scan_docker_images(
            docker,
            Path(args.image_cache),
            image_timeout=args.image_timeout,
            refresh=args.refresh_images,
        )
    brew_rows, brew_errors = brew_outdated()
    brew_security, brew_routine, brew_split_errors = brew_security_split(brew_rows)
    npx_pins, npx_errors = npx_pin_rows(repo / "config" / "portal.yaml")
    state_path = (
        Path(args.state_file)
        if args.state_file
        else Path(args.output_dir) / "last_sweep_findings.json"
    )
    previous = None if args.no_delta else load_previous_findings(state_path)
    result = SweepResult(
        findings + image_findings,
        image_stats,
        brew_rows,
        inventory.errors
        + query_errors
        + image_errors
        + brew_errors
        + brew_split_errors
        + npx_errors,
        triage=image_triage,
        npx_pins=npx_pins,
        brew_security=brew_security,
        brew_routine=brew_routine,
        delta=compute_delta(findings + image_findings, previous),
    )
    report = Path(args.output_dir) / f"security_sweep_{date.replace('-', '')}.md"
    write_report(report, date, inventory, result, _bench_venvs(home))
    if not args.no_delta:
        save_findings_state(state_path, date, result.findings)
    print(f"Report: {report}")
    stale_pins = sum(row["status"] in {"floating", "stale pin"} for row in npx_pins)
    print(
        f"Packages: {len(inventory.packages)}; findings: {len(result.findings)}; "
        f"Docker images: {image_stats['cached']} cached + {image_stats['scanned']} scanned "
        f"/ {image_stats['images']}; "
        f"Homebrew outdated: {len(brew_rows)} ({len(brew_security)} with advisory hits); "
        f"npx pins unpinned/stale: {stale_pins}; scan errors: {len(result.errors)}"
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
    parser.add_argument("--output-dir", default=str(ROOT / "docs" / "security"))
    parser.add_argument(
        "--no-alert", action="store_true", help="Suppress outbound Telegram/Pushover alerts"
    )
    parser.add_argument(
        "--skip-images", action="store_true", help="Skip expensive Docker image scans"
    )
    parser.add_argument(
        "--image-timeout",
        type=int,
        default=600,
        help="Per-image osv-scanner timeout in seconds (default 600)",
    )
    parser.add_argument(
        "--image-cache",
        default=str(ROOT / "docs" / "security" / "docker_scan_cache.json"),
        help="Digest-keyed scan cache: unchanged images reuse their previous findings",
    )
    parser.add_argument(
        "--refresh-images",
        action="store_true",
        help="Ignore the Docker scan cache and rescan every image",
    )
    parser.add_argument(
        "--state-file",
        default=str(ROOT / "docs" / "security" / "last_sweep_findings.json"),
        help="Findings state used to compute the new/carried/resolved delta",
    )
    parser.add_argument(
        "--no-delta",
        action="store_true",
        help="Do not read or write the sweep state file",
    )
    return _run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
