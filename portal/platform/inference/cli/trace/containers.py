"""Section 2 — each portal container against the image it should be running."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .context import run_cmd
from .model import Hop, Status, short

#: Config files whose bake-vs-mount state caused the 2026-11-15 Pipeline incident.
CONFIG_PROBES = (
    "config/portal.yaml",
    "config/backends.yaml",
    "config/bench_workspaces.yaml",
)
_ISO = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?(.*)$")
_COPY = re.compile(r"^COPY\s+(.+)$")
_REVISION_LABEL = "org.opencontainers.image.revision"


@dataclass
class ContainerRow:
    """One running compose container, as ``docker inspect`` reports it."""

    name: str
    image_ref: str
    image_id: str
    created: float
    started: float
    service: str
    mounts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def repo(self) -> str:
        return self.image_ref.rsplit(":", 1)[0] if ":" in self.image_ref else self.image_ref


def parse_iso(ts: str) -> float:
    """Docker's RFC3339 timestamps (nanosecond fractions) to epoch seconds."""
    match = _ISO.match(ts.strip())
    if not match:
        return 0.0
    head, fraction, tail = match.groups()
    micro = (fraction or "")[:7]
    try:
        return datetime.fromisoformat(f"{head}{micro}{tail}").timestamp()
    except ValueError:
        return 0.0


def normalize_image_id(image_id: str) -> str:
    return image_id.strip().removeprefix("sha256:")


def same_image(left: str, right: str) -> bool:
    """Docker reports 12-char short ids in some places and full ids in others."""
    a, b = normalize_image_id(left), normalize_image_id(right)
    return bool(a) and bool(b) and (a.startswith(b) or b.startswith(a))


def resolve_image(ref: str) -> tuple[str, float]:
    """The image ID and build time a container's reference resolves to right now.

    A reference is the container's own ``Config.Image`` — ``repo:tag`` when compose
    names one, ``repo`` (``:latest``) when it builds. The repository's *newest* image
    is not the answer: a rollback tag is written in the same second as the image it
    copies, and ``docker images`` then orders them arbitrarily.
    """
    result = run_cmd(["docker", "image", "inspect", ref, "--format", "{{.Id}} {{.Created}}"])
    parts = result.stdout.split()
    return (parts[0], parse_iso(parts[1])) if len(parts) == 2 else ("", 0.0)


def _stamp(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def parse_container(payload: dict[str, Any]) -> ContainerRow:
    labels = (payload.get("Config") or {}).get("Labels") or {}
    state = payload.get("State") or {}
    return ContainerRow(
        name=str(payload.get("Name") or "").lstrip("/"),
        image_ref=str((payload.get("Config") or {}).get("Image") or ""),
        image_id=str(payload.get("Image") or ""),
        created=parse_iso(str(payload.get("Created") or "")),
        started=parse_iso(str(state.get("StartedAt") or "")),
        service=str(labels.get("com.docker.compose.service") or ""),
        mounts=list(payload.get("Mounts") or []),
    )


def copied_paths(dockerfile: str) -> list[str]:
    """Repo-relative paths a Dockerfile copies into the image (``--from`` stages excluded)."""
    paths: list[str] = []
    for line in dockerfile.splitlines():
        match = _COPY.match(line.strip())
        if not match or "--from=" in match.group(1):
            continue
        sources = match.group(1).split()[:-1]
        for source in sources:
            clean = source.removeprefix("./").rstrip("/")
            if clean and clean not in paths:
                paths.append(clean)
    return paths


def mounts_of(mounts: list[dict[str, Any]]) -> dict[str, str]:
    """Destination → source for the container's bind mounts under /app/config."""
    out: dict[str, str] = {}
    for mount in mounts:
        destination = str(mount.get("Destination") or "")
        if destination.startswith("/app/config"):
            out[destination] = str(mount.get("Source") or "")
    return out


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_hash_lines(text: str) -> dict[str, str]:
    """``sha256sum`` output (hash then path); a missing file yields no entry."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        digest, path = (parts[0], parts[1]) if len(parts[0]) == 64 else (parts[1], parts[0])
        if len(digest) == 64:
            out[path] = digest
    return out


def image_freshness_hop(container: ContainerRow, current_id: str) -> Hop:
    """The container runs the image its own reference resolves to now."""
    match = same_image(container.image_id, current_id)
    return Hop(
        f"image {container.name}",
        Status.PASS if match else Status.FAIL,
        f"running={normalize_image_id(container.image_id)[:12]}"
        f" {container.image_ref}={normalize_image_id(current_id)[:12]}",
        "container runs its reference's current image",
        "" if match else "the reference was rebuilt; the container was not recreated",
    )


def start_after_build_hop(container: ContainerRow, built: float) -> Hop:
    if not container.started or not built:
        return Hop(f"start {container.name}", Status.WARN, "timestamps unreadable", "start>build")
    status = Status.PASS if container.started >= built else Status.FAIL
    return Hop(
        f"start {container.name}",
        status,
        f"started={_stamp(container.started)} built={_stamp(built)}",
        "start after build",
    )


def revision_hop(
    repo: str,
    label: str,
    head: str,
    dirty: list[str],
    built: float = 0.0,
    introduced: tuple[str, float] = ("", 0.0),
    *,
    current: bool,
    changed: list[str] | None = None,
) -> Hop:
    """A label must contain the newest copied-path commit; an absent one WARNs only if it postdates the build."""
    if label:
        status = Status.PASS if current else Status.FAIL
        if status is Status.FAIL:
            detail = f"changed since label: {', '.join(changed[:4])}" if changed else ""
        else:
            detail = f"uncommitted in copied paths: {', '.join(dirty[:4])}" if dirty else ""
        return Hop(
            f"revision {repo}",
            Status.WARN if status is Status.PASS and dirty else status,
            f"label={label[:12]}",
            f"label contains head={head[:12] or 'unknown'}",
            detail,
        )
    sha, since = introduced
    if since and built and built < since:
        return Hop(
            f"revision {repo}",
            Status.WARN,
            "label=absent",
            "revision label (added later)",
            f"built={_stamp(built)} predates {sha[:7]}; a rebuild stamps it",
        )
    return Hop(
        f"revision {repo}",
        Status.FAIL,
        "label=absent",
        "org.opencontainers.image.revision",
        f"built={_stamp(built) or 'unknown'} without a label; rebuild it",
    )


def config_hop(container: ContainerRow, repo_root: Path, hashes: dict[str, str]) -> Hop:
    """Mounted vs baked config, with the baked files that differ from the repo copy."""
    mounts = mounts_of(container.mounts)
    baked, differ = [], []
    for probe in CONFIG_PROBES:
        destination = f"/app/{probe}"
        if destination in mounts:
            continue
        if destination not in hashes:
            continue
        baked.append(probe)
        local = repo_root / probe
        if local.is_file() and sha256_file(local) != hashes[destination]:
            differ.append(probe)
    detail = f"baked differs: {', '.join(differ)}" if differ else ""
    return Hop(
        f"config {container.name}",
        Status.WARN if differ else Status.PASS,
        f"mounted={len(mounts)} baked={len(baked)}",
        "baked == repo",
        detail,
    )


def baked_hashes(container: str, probes: tuple[str, ...]) -> dict[str, str]:
    """One in-container ``sha256sum`` pass over the config probes."""
    args = " ".join(f"/app/{probe}" for probe in probes)
    result = run_cmd(["docker", "exec", container, "sh", "-c", f"sha256sum {args} 2>/dev/null"])
    return parse_hash_lines(result.stdout) if result.ok else {}


def _inspect(name: str) -> ContainerRow | None:
    result = run_cmd(["docker", "inspect", name, "--format", "{{json .}}"])
    if not result.ok:
        return None
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        return None
    return parse_container(payload) if isinstance(payload, dict) else None


def _image_label(image_id: str, label: str) -> str:
    result = run_cmd(
        ["docker", "image", "inspect", image_id, "--format", "{{json .Config.Labels}}"]
    )
    if not result.ok:
        return ""
    try:
        labels = json.loads(result.stdout) or {}
    except ValueError:
        return ""
    return str(labels.get(label) or "") if isinstance(labels, dict) else ""


def _git(repo_root: Path, args: list[str]) -> str:
    return run_cmd(["git", "-C", str(repo_root), *args]).stdout.strip()


def _dockerfiles(repo_root: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for path in sorted(repo_root.glob("Dockerfile*")):
        if path.is_file():
            out[path.name] = copied_paths(path.read_text(encoding="utf-8"))
    return out


def _compose_dockerfile(repo_root: Path, service: str) -> str:
    """The Dockerfile a compose service builds from, else the pipeline default."""
    compose = repo_root / "deploy" / "portal-5" / "docker-compose.yml"
    if not compose.is_file():
        return ""
    text = compose.read_text(encoding="utf-8")
    block = re.search(rf"^  {re.escape(service)}:\n(.*?)(?=^  \S)", text, re.S | re.M)
    if not block:
        return ""
    found = re.search(r"dockerfile:\s*(\S+)", block.group(1))
    return found.group(1) if found else ""


def _mounted_elsewhere(repo_root: Path) -> list[str]:
    """Repo paths a long-running stock-image service consumes via bind mount, not a baked copy."""
    import yaml

    compose = repo_root / "deploy" / "portal-5" / "docker-compose.yml"
    if not compose.is_file():
        return []
    try:
        data = yaml.safe_load(compose.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(data, dict) or not isinstance(data.get("services"), dict):
        return []
    out: list[str] = []
    for svc in data["services"].values():
        if not isinstance(svc, dict) or "build" in svc or "image" not in svc:
            continue
        # One-shot init containers (restart: "no") run the mounted repo tree itself.
        if str(svc.get("restart") or "") == "no":
            continue
        for vol in svc.get("volumes") or []:
            if isinstance(vol, str) and vol.startswith("../../"):
                source = vol.split(":")[0].removeprefix("../../")
                if source and source not in out:
                    out.append(source)
    return out


def _staleness_paths(copied: list[str], mounted: list[str]) -> list[str]:
    """Git pathspec of the copied paths minus what a stock service mounts at runtime."""
    kept = [path for path in copied if path not in mounted]
    excluded = [m for m in mounted if any(m.startswith(p + "/") for p in kept)]
    return [*kept, *(f":(exclude){m}" for m in excluded)]


def label_commit(repo_root: Path, dockerfile: str) -> tuple[str, float]:
    """The commit that introduced the revision label into ``dockerfile``, and its timestamp."""
    parts = _git(
        repo_root, ["log", "-1", "--format=%H %ct", "-S", _REVISION_LABEL, "--", dockerfile]
    ).split()
    return (parts[0], float(parts[1])) if len(parts) == 2 else ("", 0.0)


def label_contains(repo_root: Path, commit: str, label: str) -> bool:
    """The label commit contains ``commit``: a merge contains the branch commits it brought in."""
    if not commit or not label:
        return False
    if label.startswith(commit):
        return True
    return run_cmd(["git", "-C", str(repo_root), "merge-base", "--is-ancestor", commit, label]).ok


def _container_hops(
    container: ContainerRow,
    repo_root: Path,
    dockerfiles: dict[str, list[str]],
    mounted: list[str],
) -> list[Hop]:
    """Image identity, start time, revision label and config state for one container."""
    current, built = resolve_image(container.image_ref)
    if not current:
        return [
            Hop(
                f"image {container.name}",
                Status.FAIL,
                f"{container.image_ref} resolves to nothing",
                "image present",
            )
        ]
    hops = [image_freshness_hop(container, current), start_after_build_hop(container, built)]
    dockerfile = _compose_dockerfile(repo_root, container.service)
    specs = _staleness_paths(dockerfiles.get(dockerfile, []), mounted)
    if specs:
        head = _git(repo_root, ["rev-list", "-1", "HEAD", "--", *specs])
        dirty = [
            line
            for line in _git(repo_root, ["status", "--porcelain", "--", *specs]).splitlines()
            if line.strip()
        ]
        label = _image_label(current, _REVISION_LABEL)
        current_label = label_contains(repo_root, head, label)
        changed = (
            _git(repo_root, ["diff", "--name-only", label, head, "--", *specs]).splitlines()
            if label and head and not current_label
            else []
        )
        hops.append(
            revision_hop(
                container.repo,
                label,
                head,
                dirty,
                built,
                label_commit(repo_root, dockerfile),
                current=current_label,
                changed=changed,
            )
        )
    return hops


def run(ctx: Any) -> list[Hop]:
    """Per portal container: image identity, start time, revision label, config state."""
    repo_root: Path = ctx.repo_root
    listing = run_cmd(["docker", "ps", "--format", "{{.Names}}"], timeout=20)
    if not listing.ok:
        return [Hop("docker", Status.FAIL, short(listing.error), "docker reachable")]
    dockerfiles = _dockerfiles(repo_root)
    mounted = _mounted_elsewhere(repo_root)
    hops: list[Hop] = []
    for name in [line.strip() for line in listing.stdout.splitlines() if line.strip()]:
        container = _inspect(name)
        if container is None or not container.image_ref:
            hops.append(Hop(f"image {name}", Status.FAIL, "inspect failed", "readable container"))
            continue
        hops.extend(_container_hops(container, repo_root, dockerfiles, mounted))
        hops.append(config_hop(container, repo_root, baked_hashes(name, CONFIG_PROBES)))
    if not hops:
        hops.append(Hop("containers", Status.FAIL, "no portal containers", "stack running"))
    return hops
