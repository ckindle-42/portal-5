#!/usr/bin/env python3
"""Stdlib pin backfill and upstream-change detection for Ollama catalog tags.

The models directory comes from ``OLLAMA_MODELS`` or the ``com.portal5.ollama``
LaunchDaemon. Paths inside that directory are never hardcoded.
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

OLLAMA_DAEMON_PLIST = Path("/Library/LaunchDaemons/com.portal5.ollama.plist")
UNPINNED_NOT_ON_HF = "local blob not on HF main (upstream moved or local import)"
_MODEL_MEDIA = "application/vnd.ollama.image.model"
_MANIFEST_ACCEPT = "application/vnd.docker.distribution.manifest.v2+json"
_REGISTRY = "https://registry.ollama.ai"
_DERIVED_RE = re.compile(r"-ctx(\d+)k(?:-[A-Za-z0-9]+)?$")
_BARE_CTX_RE = re.compile(r"^ctx(\d+)k$")
_ID_RE = re.compile(r"^(\s*)- id:\s*(.*?)\s*$")
_KEY_RE = re.compile(r"^(\s+)([A-Za-z_][\w-]*):\s*(.*)$")
_MODELS_RE = re.compile(r"^(\s*)models:\s*(?:#.*)?$")
_SAFE_SCALAR = re.compile(r"[A-Za-z0-9_./+-]+")
Fetch = Callable[[str, str], tuple[int, dict[str, str], bytes]]


@dataclass
class Entry:
    tag: str
    fields: dict[str, str]
    start: int
    end: int
    key_indent: int


@dataclass(frozen=True)
class Change:
    tag: str
    kind: str
    old: str
    new: str
    size: int
    repo: str = ""
    filename: str = ""
    num_ctx: int | None = None
    supports_tools: bool = False
    stops: tuple[str, ...] = ()
    derived: tuple[tuple[str, int], ...] = ()


@dataclass
class Scan:
    changes: list[Change] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def models_dir(
    env: Mapping[str, str] | None = None,
    plist_path: Path | None = None,
) -> Path:
    """Resolve the Ollama models directory. Never hardcodes the live volume."""
    source = os.environ if env is None else env
    raw = source.get("OLLAMA_MODELS", "").strip()
    if raw:
        return Path(raw).expanduser()
    path = OLLAMA_DAEMON_PLIST if plist_path is None else plist_path
    if path.is_file():
        try:
            data = plistlib.loads(path.read_bytes())
        except (plistlib.InvalidFileException, OSError):
            data = {}
        variables = data.get("EnvironmentVariables") or {}
        value = variables.get("OLLAMA_MODELS")
        if isinstance(value, str) and value.strip():
            return Path(value.strip()).expanduser()
    return Path.home() / ".ollama" / "models"


def manifest_path(models: Path, tag: str) -> Path:
    """Local manifest file for an Ollama tag."""
    name, sep, qual = tag.rpartition(":")
    if not sep or not qual:
        name, qual = tag, "latest"
    if name.startswith("hf.co/"):
        rel = Path("manifests") / name / qual
    elif "/" not in name:
        rel = Path("manifests/registry.ollama.ai/library") / name / qual
    else:
        rel = Path("manifests/registry.ollama.ai") / name / qual
    return models / rel


def split_derived(tag: str) -> tuple[str, int] | None:
    """Base tag and context-thousands for a baked ``-ctxNk`` / ``ctxNk`` tag."""
    name, sep, qual = tag.rpartition(":")
    if not sep:
        return None
    bare = _BARE_CTX_RE.fullmatch(qual)
    if bare is not None:
        kilos = int(bare.group(1))
        if kilos < 1 or not name:
            return None
        return f"{name}:latest", kilos
    match = _DERIVED_RE.search(qual)
    if match is None:
        return None
    kilos = int(match.group(1))
    if kilos < 1:
        return None
    root = qual[: match.start()]
    while True:
        inner = _DERIVED_RE.search(root)
        if inner is None:
            break
        root = root[: inner.start()]
    if not root:
        return None
    return f"{name}:{root}", kilos


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_model_entries(text: str) -> list[Entry]:
    """Model dicts under each ``models:`` block. Comments outside them are kept."""
    lines = text.splitlines(keepends=True)
    entries: list[Entry] = []
    index = 0
    while index < len(lines):
        header = _MODELS_RE.match(lines[index])
        if header is None:
            index += 1
            continue
        index = _consume_models_block(lines, index + 1, len(header.group(1)), entries)
    return entries


def apply_field_updates(text: str, updates: dict[str, dict[str, str]]) -> str:
    """Set or clear keys on existing model ids. Never inserts a new id."""
    lines = text.splitlines(keepends=True)
    entries = parse_model_entries(text)
    for entry in sorted(entries, key=lambda item: item.start, reverse=True):
        fields = updates.get(entry.tag)
        if not fields:
            continue
        block = _rewrite_block(lines[entry.start : entry.end], fields, entry.key_indent)
        lines[entry.start : entry.end] = block
    return "".join(lines)


def backfill_lines(
    text: str,
    models: Path,
    fetch: Fetch,
    *,
    write: bool,
) -> tuple[list[str], str]:
    """Match each ``hf.co/`` id's model-layer sha256 to an HF ``lfs.oid``."""
    entries = parse_model_entries(text)
    seen: set[str] = set()
    lines: list[str] = []
    updates: dict[str, dict[str, str]] = {}
    trees: dict[str, list[dict] | None] = {}
    for entry in entries:
        if not entry.tag.startswith("hf.co/") or entry.tag in seen:
            continue
        seen.add(entry.tag)
        _backfill_one(entry.tag, models, fetch, trees, lines, updates)
    new_text = apply_field_updates(text, updates) if write else text
    return lines, new_text


def collect_changes(text: str, models: Path, fetch: Fetch) -> Scan:
    """Upstream drift: pinned HF file sha, or library manifest digest."""
    scan = Scan()
    merged = _merged(parse_model_entries(text))
    derived = _derived_index(merged)
    trees: dict[str, list[dict] | None] = {}
    reported: set[str] = set()
    scanned: set[str] = set()
    for entry in merged:
        if entry.tag.startswith("portal5/"):
            continue
        if entry.tag.startswith("hf.co/"):
            _hf_change(entry, models, fetch, trees, scan, reported)
            continue
        if split_derived(entry.tag) is not None:
            continue
        scanned.add(entry.tag)
        _library_change(entry, models, fetch, derived.get(entry.tag, ()), scan)
    _orphan_library_bases(derived, scanned, models, fetch, scan)
    return scan


def blob_referenced(models: Path, digest: str) -> bool:
    """True when any manifest layer or config still names this sha256."""
    root = models / "manifests"
    if not root.is_dir():
        return False
    want = _hex(digest)
    return any(path.is_file() and want in _manifest_digests(path) for path in root.rglob("*"))


def drop_unreferenced_blob(models: Path, digest: str) -> bool:
    """Delete one blob only when no manifest still names it."""
    if not digest or blob_referenced(models, digest):
        return False
    blob = models / "blobs" / f"sha256-{_hex(digest)}"
    if not blob.is_file():
        return False
    blob.unlink()
    return True


def model_layer(path: Path) -> tuple[str, int] | None:
    """``(sha256 hex, size)`` of the image.model layer, if the manifest has one."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for layer in payload.get("layers") or []:
        if not isinstance(layer, dict) or layer.get("mediaType") != _MODEL_MEDIA:
            continue
        digest = _hex(str(layer.get("digest") or ""))
        if len(digest) != 64:
            return None
        try:
            size = int(layer.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        return digest, size
    return None


def registry_manifest_url(tag: str) -> str:
    name, sep, qual = tag.rpartition(":")
    if not sep or not qual:
        name, qual = tag, "latest"
    if "/" not in name:
        name = f"library/{name}"
    return f"{_REGISTRY}/v2/{quote(name, safe='/')}/manifests/{quote(qual, safe='')}"


def repo_from_tag(tag: str) -> str:
    rest = tag[len("hf.co/") :] if tag.startswith("hf.co/") else tag
    repo, _, _quant = rest.partition(":")
    return repo.strip()


def default_fetch(method: str, url: str) -> tuple[int, dict[str, str], bytes]:
    headers = {"Accept": "application/json", "User-Agent": "portal5-model-refresh"}
    if "registry.ollama.ai" in url:
        headers["Accept"] = _MANIFEST_ACCEPT
    token = os.environ.get("HF_TOKEN", "")
    if token and "huggingface.co" in url:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            body = b"" if method.upper() == "HEAD" else response.read()
            return response.status, _header_map(response.headers), body
    except urllib.error.HTTPError as exc:
        body = b"" if method.upper() == "HEAD" else exc.read()
        return exc.code, _header_map(exc.headers), body


def download_verified(url: str, dest: Path, sha: str, fetch: Fetch) -> None:
    """Write ``url`` to ``dest`` and require its sha256 to match ``sha``."""
    status, _headers, body = fetch("GET", url)
    if status != 200:
        raise OSError(f"download HTTP {status}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    got = hashlib.sha256(body).hexdigest()
    if got != _hex(sha):
        dest.unlink(missing_ok=True)
        raise OSError(f"sha256 mismatch expected {_hex(sha)} got {got}")


def stream_download(url: str, dest: Path, sha: str) -> None:
    """Stream a resolve URL onto the models volume and require the sha256."""
    headers = {"User-Agent": "portal5-model-refresh"}
    token = os.environ.get("HF_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    digest = hashlib.sha256()
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            if response.status != 200:
                raise OSError(f"download HTTP {response.status}")
            with dest.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    handle.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    got = digest.hexdigest()
    if got != _hex(sha):
        dest.unlink(missing_ok=True)
        raise OSError(f"sha256 mismatch expected {_hex(sha)} got {got}")


def resolve_url(repo: str, filename: str) -> str:
    return (
        f"https://huggingface.co/{quote(repo, safe='/')}/resolve/main/{quote(filename, safe='/')}"
    )


def _backfill_one(
    tag: str,
    models: Path,
    fetch: Fetch,
    trees: dict[str, list[dict] | None],
    lines: list[str],
    updates: dict[str, dict[str, str]],
) -> None:
    layer = model_layer(manifest_path(models, tag))
    repo = repo_from_tag(tag)
    if layer is None:
        updates[tag] = _clear_pin("no local manifest")
        lines.append(f"UNPINNED {tag} no local manifest")
        return
    files = _tree(repo, fetch, trees)
    if files is None:
        lines.append(f"ERROR {tag} HF tree for {repo} failed")
        return
    match = _match_oid(files, layer[0])
    if match is None:
        updates[tag] = _clear_pin(UNPINNED_NOT_ON_HF)
        lines.append(f"UNPINNED {tag} {UNPINNED_NOT_ON_HF}")
        return
    filename = str(match.get("path") or "")
    updates[tag] = {
        "repo": repo,
        "filename": filename,
        "sha256": layer[0],
        "unpinned": "",
    }
    size = _file_size(match)
    lines.append(f"PIN {tag} repo={repo} file={filename} sha256={layer[0]} bytes={size}")


def _hf_change(
    entry: Entry,
    models: Path,
    fetch: Fetch,
    trees: dict[str, list[dict] | None],
    scan: Scan,
    reported: set[str],
) -> None:
    filename = entry.fields.get("filename", "")
    pinned = _hex(entry.fields.get("sha256", ""))
    repo = entry.fields.get("repo", "") or repo_from_tag(entry.tag)
    if entry.tag in reported:
        return
    if not filename or len(pinned) != 64:
        if entry.fields.get("unpinned"):
            reported.add(entry.tag)
            scan.notes.append(f"unpinned {entry.tag}: {entry.fields['unpinned']}")
        return
    files = _tree(repo, fetch, trees)
    if files is None:
        reported.add(entry.tag)
        scan.notes.append(f"error {entry.tag}: HF tree for {repo} failed")
        return
    match = _file_by_path(files, filename)
    if match is None:
        reported.add(entry.tag)
        scan.notes.append(f"error {entry.tag}: pinned file {filename} is not on HF main")
        return
    current = _hex(str((match.get("lfs") or {}).get("oid") or ""))
    if len(current) != 64 or current == pinned:
        return
    reported.add(entry.tag)
    scan.changes.append(
        Change(
            tag=entry.tag,
            kind="hf",
            old=pinned,
            new=current,
            size=_file_size(match),
            repo=repo,
            filename=filename,
            num_ctx=_num_ctx(entry),
            supports_tools=entry.fields.get("supports_tools") == "true",
            stops=_stops(entry.fields.get("stops", "")),
        )
    )


def _orphan_library_bases(
    derived: dict[str, tuple[tuple[str, int], ...]],
    scanned: set[str],
    models: Path,
    fetch: Fetch,
    scan: Scan,
) -> None:
    """A baked library tag whose base is not itself a catalog id still tracks that base."""
    for base, pairs in derived.items():
        if base in scanned or base.startswith("hf.co/") or base.startswith("portal5/"):
            continue
        _library_change(Entry(base, {}, 0, 0, 4), models, fetch, pairs, scan)


def _library_change(
    entry: Entry,
    models: Path,
    fetch: Fetch,
    derived: tuple[tuple[str, int], ...],
    scan: Scan,
) -> None:
    path = manifest_path(models, entry.tag)
    if not path.is_file():
        return
    local = file_sha256(path)
    status, headers, _body = fetch("HEAD", registry_manifest_url(entry.tag))
    if status == 404:
        scan.notes.append(f"skip {entry.tag}: not on the Ollama registry")
        return
    if status != 200:
        scan.notes.append(f"error {entry.tag}: registry HTTP {status}")
        return
    remote = _hex(headers.get("ollama-content-digest", ""))
    if len(remote) != 64 or remote == local:
        return
    status, _headers, body = fetch("GET", registry_manifest_url(entry.tag))
    if status != 200:
        scan.notes.append(f"error {entry.tag}: registry manifest HTTP {status}")
        return
    try:
        payload = json.loads(body.decode())
    except json.JSONDecodeError:
        scan.notes.append(f"error {entry.tag}: registry manifest is not JSON")
        return
    scan.changes.append(
        Change(
            tag=entry.tag,
            kind="library",
            old=local,
            new=remote,
            size=_missing_blob_bytes(models, payload),
            supports_tools=entry.fields.get("supports_tools") == "true",
            stops=_stops(entry.fields.get("stops", "")),
            derived=derived,
        )
    )


def _missing_blob_bytes(models: Path, payload: dict) -> int:
    total = 0
    for layer in payload.get("layers") or []:
        if not isinstance(layer, dict):
            continue
        digest = _hex(str(layer.get("digest") or ""))
        if len(digest) != 64:
            continue
        if (models / "blobs" / f"sha256-{digest}").is_file():
            continue
        try:
            total += int(layer.get("size") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _tree(repo: str, fetch: Fetch, cache: dict[str, list[dict] | None]) -> list[dict] | None:
    if repo in cache:
        return cache[repo]
    try:
        cache[repo] = _hf_files(repo, fetch)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        cache[repo] = None
    return cache[repo]


def _hf_files(repo: str, fetch: Fetch) -> list[dict]:
    url = f"https://huggingface.co/api/models/{quote(repo, safe='/')}/tree/main"
    files: list[dict] = []
    seen: set[str] = set()
    while url and url not in seen:
        seen.add(url)
        status, headers, body = fetch("GET", url)
        if status != 200:
            raise OSError(f"HF tree HTTP {status}")
        payload = json.loads(body.decode())
        if not isinstance(payload, list):
            raise OSError("HF tree payload is not a list")
        files.extend(item for item in payload if isinstance(item, dict))
        url = _next_link(headers.get("link", ""))
    return files


def _next_link(header: str) -> str:
    for part in header.split(","):
        if 'rel="next"' not in part:
            continue
        match = re.search(r"<([^>]+)>", part)
        if match is not None:
            return match.group(1)
    return ""


def _match_oid(files: list[dict], sha: str) -> dict | None:
    want = _hex(sha)
    hits = [item for item in files if _hex(str((item.get("lfs") or {}).get("oid") or "")) == want]
    if not hits:
        return None
    hits.sort(
        key=lambda item: (
            not str(item.get("path", "")).endswith(".gguf"),
            len(str(item.get("path", ""))),
        )
    )
    return hits[0]


def _file_by_path(files: list[dict], filename: str) -> dict | None:
    for item in files:
        if item.get("path") == filename:
            return item
    return None


def _file_size(item: dict) -> int:
    lfs = item.get("lfs") or {}
    raw = lfs.get("size", item.get("size", 0))
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _clear_pin(reason: str) -> dict[str, str]:
    return {"repo": "", "filename": "", "sha256": "", "unpinned": reason}


def _merged(entries: list[Entry]) -> list[Entry]:
    order: list[str] = []
    fields: dict[str, dict[str, str]] = {}
    for entry in entries:
        slot = fields.setdefault(entry.tag, {})
        if entry.tag not in order:
            order.append(entry.tag)
        for key, value in entry.fields.items():
            if value and not slot.get(key):
                slot[key] = value
        if entry.fields.get("supports_tools") == "true":
            slot["supports_tools"] = "true"
    return [Entry(tag, fields[tag], 0, 0, 4) for tag in order]


def _derived_index(entries: list[Entry]) -> dict[str, tuple[tuple[str, int], ...]]:
    found: dict[str, list[tuple[str, int]]] = {}
    for entry in entries:
        if entry.tag.startswith("portal5/"):
            continue
        split = split_derived(entry.tag)
        if split is None:
            continue
        base, _kilos = split
        found.setdefault(base, []).append((entry.tag, _num_ctx(entry) or 0))
    return {base: tuple(pairs) for base, pairs in found.items()}


def _num_ctx(entry: Entry) -> int | None:
    raw = entry.fields.get("num_ctx", "")
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    split = split_derived(entry.tag)
    if split is None:
        return None
    return split[1] * 1024


def _stops(raw: str) -> tuple[str, ...]:
    if not raw.startswith("["):
        return ()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if isinstance(payload, list) and all(isinstance(item, str) and item for item in payload):
        return tuple(payload)
    return ()


def _consume_models_block(lines: list[str], index: int, base: int, into: list[Entry]) -> int:
    """Items sit at the same indent as the ``models:`` key in backends.yaml."""
    while index < len(lines):
        if _blank_or_comment(lines[index]):
            index += 1
            continue
        indent = _indent(lines[index])
        stripped = lines[index].lstrip()
        if indent < base or (indent == base and not stripped.startswith("- ")):
            break
        matched = _ID_RE.match(lines[index].rstrip("\n"))
        if matched is None:
            index += 1
            continue
        start = index
        index += 1
        fields: dict[str, str] = {}
        index = _consume_keys(lines, index, len(matched.group(1)), fields)
        into.append(
            Entry(
                tag=_scalar(matched.group(2)),
                fields=fields,
                start=start,
                end=index,
                key_indent=len(matched.group(1)) + 2,
            )
        )
    return index


def _consume_keys(lines: list[str], index: int, item_indent: int, fields: dict[str, str]) -> int:
    while index < len(lines):
        if _blank_or_comment(lines[index]):
            nxt = _next_content(lines, index)
            if (
                nxt is None
                or _indent(lines[nxt]) <= item_indent
                or lines[nxt].lstrip().startswith("- ")
            ):
                break
            index = nxt
            continue
        matched = _KEY_RE.match(lines[index].rstrip("\n"))
        if matched is None or len(matched.group(1)) <= item_indent:
            break
        fields[matched.group(2)] = _scalar(matched.group(3))
        index += 1
    return index


def _rewrite_block(block: list[str], updates: dict[str, str], key_indent: int) -> list[str]:
    lines = list(block)
    if lines and not lines[0].endswith("\n"):
        lines[0] += "\n"
    _delete_keys(lines, [key for key, value in updates.items() if value == ""])
    present = _key_index(lines)
    indent = " " * key_indent
    for key, value in updates.items():
        if value == "":
            continue
        rendered = f"{indent}{key}: {_yaml_scalar(value)}\n"
        if key in present:
            lines[present[key]] = rendered
        else:
            lines.append(rendered)
    return lines


def _delete_keys(lines: list[str], keys: list[str]) -> None:
    for key in keys:
        present = _key_index(lines)
        if key in present:
            del lines[present[key]]


def _key_index(lines: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for index, line in enumerate(lines):
        matched = _KEY_RE.match(line.rstrip("\n"))
        if matched is not None:
            found[matched.group(2)] = index
    return found


def _yaml_scalar(value: str) -> str:
    if _SAFE_SCALAR.fullmatch(value):
        return value
    return json.dumps(value)


def _scalar(raw: str) -> str:
    text = raw.strip()
    if " #" in text:
        text = text.split(" #", 1)[0].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        if text[0] == '"':
            try:
                loaded = json.loads(text)
            except json.JSONDecodeError:
                return text[1:-1]
            return loaded if isinstance(loaded, str) else text[1:-1]
        return text[1:-1]
    return text


def _manifest_digests(path: Path) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    found: set[str] = set()
    config = payload.get("config") or {}
    if isinstance(config, dict):
        found.add(_hex(str(config.get("digest") or "")))
    for layer in payload.get("layers") or []:
        if isinstance(layer, dict):
            found.add(_hex(str(layer.get("digest") or "")))
    found.discard("")
    return found


def _hex(value: str) -> str:
    text = value.strip().lower()
    if text.startswith("sha256:"):
        text = text.split(":", 1)[1]
    return text


def _header_map(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _blank_or_comment(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _next_content(lines: list[str], index: int) -> int | None:
    cursor = index
    while cursor < len(lines):
        if not _blank_or_comment(lines[cursor]):
            return cursor
        cursor += 1
    return None
