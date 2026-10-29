#!/usr/bin/env python3
"""Dry-run keep/remove table for the fleet fallback rule (one oMLX checkpoint plus
one GGUF fallback per model family).

Reads `config/backends.yaml`, the config surfaces that name models, the live
Ollama tag list and the oMLX model dirs. Writes nothing: no model is deleted and
no config is edited — the operator approves a row, the orchestrator executes it.

Families and their WARN worklist come from `scripts.validation.inference`
(`check_fleet_fallback_rule`); this script only adds the per-variant economics:
install state, bytes no other kept tag shares, every config line that names the
variant, and the repoint that removing it would need.

Usage:
    python3 scripts/fleet_consolidate.py            # markdown table
    python3 scripts/fleet_consolidate.py --json      # same facts as JSON
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import model_upstream  # noqa: E402
from scripts.validation.inference import (  # noqa: E402
    _DRAFT_RE,
    _families,
    _model_entries,
    _weights_tag,
)

CONFIG_GLOBS: tuple[str, ...] = (
    "config/backends.yaml",
    "config/portal.yaml",
    "config/bench_workspaces.yaml",
    "config/council.yaml",
    "config/compliance/council.yaml",
    "config/personas/**/*.yaml",
)
BACKENDS_FILE = "config/backends.yaml"
PORTAL_FILE = "config/portal.yaml"
OMLX_SETTINGS = Path.home() / ".omlx" / "settings.json"
NO_FALLBACK = "oMLX seat has no Ollama GGUF fallback"
_GIB = 2**30
_CTX = re.compile(r"-ctx(\d+)k$")
# A plain YAML key ends at the first colon followed by a space (or the line end), so
# `fam:q4_K_M-ctx32k: Fam-4bit` is the alias `fam:q4_K_M-ctx32k` → `Fam-4bit`.
_KV = re.compile(r"^\s*(?:-\s*)?([A-Za-z_][\w./:-]*):(?:[ \t]+(.*?))?\s*$")
_ITEM = re.compile(r"^\s*-\s+(.+?)\s*$")
_FLOW = re.compile(r"([A-Za-z_][\w-]*):\s*('[^']*'|\"[^\"]*\"|[^,}]+)")
_DEFINITION = re.compile(r"^\s*- id:\s*(.+?)\s*$")
_BLOCK = re.compile(r"^\s*(?:-\s*)?[A-Za-z_][\w./-]*:\s*[|>][-+]?\s*$")
_BLOCK_MARKERS = frozenset({"|", "|-", "|+", ">", ">-", ">+"})


@dataclass(frozen=True)
class Ref:
    """One config line that names a variant."""

    file: str
    line: int
    field: str
    value: str
    kind: str
    via: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "field": self.field,
            "value": self.value,
            "kind": self.kind,
            "via": self.via,
        }


@dataclass
class Variant:
    """One artifact in a family: an oMLX checkpoint or a GGUF weights tag."""

    engine: str
    id: str
    tags: list[str] = field(default_factory=list)
    installed: bool = False
    unique_bytes: int = 0
    refs: list[Ref] = field(default_factory=list)
    action: str = "KEEP"
    reason: str = ""
    repoints: list[dict[str, Any]] = field(default_factory=list)

    @property
    def consumer_refs(self) -> list[Ref]:
        """Refs from a workspace, persona, council or seat — not a backend registration."""
        return [ref for ref in self.refs if ref.kind == "reference"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "id": self.id,
            "installed": self.installed,
            "unique_bytes": self.unique_bytes,
            "unique_gib": round(self.unique_bytes / _GIB, 2),
            "action": self.action,
            "reason": self.reason,
            "tags": list(self.tags),
            "refs": [ref.as_dict() for ref in self.refs],
            "repoints": list(self.repoints),
        }


@dataclass
class Family:
    """One WARN family: the oMLX checkpoints and GGUF weights tags of one model."""

    key: str
    checkpoints: list[str]
    weights: list[str]
    variants: list[Variant] = field(default_factory=list)


@dataclass
class Facts:
    """Live engine state: Ollama tags with blob sizes, oMLX dirs with file identities."""

    ollama_tags: dict[str, str] = field(default_factory=dict)
    blob_sizes: dict[str, dict[str, int]] = field(default_factory=dict)
    omlx_dirs: dict[str, Path] = field(default_factory=dict)
    dir_files: dict[str, dict[tuple[int, int], int]] = field(default_factory=dict)


# ── config surface ────────────────────────────────────────────────────────────
def _scalar(raw: str) -> str:
    """A YAML line's scalar with any trailing comment and quotes stripped."""
    text = raw.strip()
    if " #" in text:
        text = text.split(" #", 1)[0].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _line_values(line: str) -> list[tuple[str, str]]:
    """(field, value) pairs a line carries, inline flow maps included."""
    pairs: list[tuple[str, str]] = []
    item = _ITEM.match(line)
    if item is not None and ": " not in item.group(1):
        # `- fam:q8_0` is a plain scalar list item, not a mapping of field `fam`.
        pairs.append(("", item.group(1)))
    else:
        matched = _KV.match(line)
        if matched is not None:
            pairs.append((matched.group(1), matched.group(2) or ""))
        elif item is not None:
            pairs.append(("", item.group(1)))
    for _field, value in list(pairs):
        if value.startswith("{"):
            pairs.extend((hit.group(1), hit.group(2)) for hit in _FLOW.finditer(value))
    out: list[tuple[str, str]] = []
    for name, value in pairs:
        scalar = _scalar(value)
        if scalar and scalar not in _BLOCK_MARKERS:
            out.append((name, scalar))
    return out


def _scalars_in(text: str) -> Iterator[tuple[int, str, str]]:
    """(line, field, value) for every scalar outside a block-scalar body."""
    block: int | None = None
    for line_no, raw in enumerate(text.splitlines(), 1):
        indent = len(raw) - len(raw.lstrip())
        if block is not None:
            if raw.strip() and indent <= block:
                block = None
            else:
                continue
        if _BLOCK.match(raw):
            block = indent
            continue
        if raw.lstrip().startswith("#"):
            continue
        for name, value in _line_values(raw):
            yield line_no, name, value


def _config_files(root: Path) -> list[str]:
    found: list[str] = []
    for pattern in CONFIG_GLOBS:
        for path in sorted(root.glob(pattern)):
            rel = path.relative_to(root).as_posix()
            if rel not in found:
                found.append(rel)
    return found


def scan_config(root: Path = REPO_ROOT) -> list[tuple[str, int, str, str]]:
    """(file, line, field, value) for every scalar in the model-reference config surface."""
    rows: list[tuple[str, int, str, str]] = []
    for rel in _config_files(root):
        text = (root / rel).read_text(encoding="utf-8")
        rows.extend((rel, line, name, value) for line, name, value in _scalars_in(text))
    return rows


def _alias_targets(cfg: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Lowercased alias hint → (hint as written, oMLX checkpoint it names)."""
    out: dict[str, tuple[str, str]] = {}
    for backend in cfg.get("backends") or []:
        if backend.get("type") != "omlx":
            continue
        for hint, target in (backend.get("aliases") or {}).items():
            out[str(hint).lower()] = (str(hint), str(target))
    return out


def _alias_line(raw: str, aliases: dict[str, tuple[str, str]]) -> str | None:
    """The alias hint a `hint: checkpoint` line declares, if it declares one."""
    text = raw.strip()
    if not text or text.startswith("#") or ": " not in text:
        return None
    key, _, value = text.rpartition(": ")
    hint = key.strip().strip("'\"")
    known = aliases.get(hint.lower())
    if known is None or known[1] != value.strip().strip("'\""):
        return None
    return hint


def _backend_roles(root: Path) -> dict[int, str]:
    """backends.yaml line → 'definition' (a models: entry) or 'alias' (a hint → checkpoint)."""
    text = (root / BACKENDS_FILE).read_text(encoding="utf-8")
    aliases = _alias_targets(yaml.safe_load(text) or {})
    roles: dict[int, str] = {}
    for line_no, raw in enumerate(text.splitlines(), 1):
        if _DEFINITION.match(raw):
            roles[line_no] = "definition"
        elif _alias_line(raw, aliases):
            roles[line_no] = "alias"
    return roles


def _workspace_hints(root: Path) -> dict[str, str]:
    """Lowercased `workspace` and `workspace::variant` seats → the model_hint each names."""
    try:
        cfg = yaml.safe_load((root / PORTAL_FILE).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    out: dict[str, str] = {}
    for name, ws in (cfg.get("workspaces") or {}).items():
        if not isinstance(ws, dict):
            continue
        if ws.get("model_hint"):
            out[str(name).lower()] = str(ws["model_hint"])
        for vname, var in (ws.get("variants") or {}).items():
            if isinstance(var, dict) and var.get("model_hint"):
                out[f"{str(name).lower()}::{str(vname).lower()}"] = str(var["model_hint"])
    return out


# ── families and variants ─────────────────────────────────────────────────────
def _keep_texts(backends: list[dict[str, Any]]) -> dict[str, str]:
    """Weights-tag identity → the entry's keep_reason: text."""
    out: dict[str, str] = {}
    for backend in backends:
        for model_id, entry in _model_entries(backend):
            reason = entry.get("keep_reason")
            if reason:
                out.setdefault(_weights_tag(model_id), str(reason))
    return out


def _warns(checkpoints: list[str], weights: list[str], keep_text: dict[str, str]) -> bool:
    """True when the family holds more than one non-exempt checkpoint or weights tag."""
    live_ckpts = [c for c in checkpoints if _weights_tag(c) not in keep_text]
    live_weights = [w for w in weights if _weights_tag(w) not in keep_text]
    return len(live_ckpts) > 1 or len(live_weights) > 1


def _registered_tags(backends: list[dict[str, Any]], weights_tag: str) -> list[str]:
    """Every backends.yaml model id that shares this GGUF weights identity."""
    return sorted(
        model_id
        for backend in backends
        for model_id, _entry in _model_entries(backend)
        if _weights_tag(model_id) == weights_tag
    )


def build_families(backends: list[dict[str, Any]]) -> list[Family]:
    """The WARN families of the fleet fallback rule, every member variant included."""
    keep_text = _keep_texts(backends)
    families: list[Family] = []
    for comp in _families(backends):
        checkpoints = sorted(comp["checkpoints"])
        weights = sorted(comp["weights"])
        if not _warns(checkpoints, weights, keep_text):
            continue
        variants = [Variant("omlx", ckpt) for ckpt in checkpoints]
        variants += [
            Variant("ollama", weight, tags=_registered_tags(backends, _weights_tag(weight)))
            for weight in weights
        ]
        families.append(
            Family(
                key=min(checkpoints + weights, key=lambda s: (len(s), s)),
                checkpoints=checkpoints,
                weights=weights,
                variants=variants,
            )
        )
    return sorted(families, key=lambda f: f.key)


def _resolve(
    value: str,
    by_ckpt: dict[str, Variant],
    by_tag: dict[str, Variant],
    aliases: dict[str, tuple[str, str]],
    *,
    alias_hop: bool = True,
) -> list[tuple[Variant, str]]:
    """Variants a config value names — directly, as an alias hint, or as a ctx/quant twin."""
    hits: list[tuple[Variant, str]] = []
    if value in by_ckpt:
        hits.append((by_ckpt[value], "id"))
    if alias_hop:
        alias = aliases.get(value.lower())
        if alias is not None and alias[1] in by_ckpt:
            hits.append((by_ckpt[alias[1]], "alias"))
    tagged = by_tag.get(_weights_tag(value))
    if tagged is not None:
        hits.append((tagged, "tag"))
    return hits


def attribute(
    families: list[Family],
    aliases: dict[str, tuple[str, str]],
    rows: list[tuple[str, int, str, str]],
    roles: dict[int, str],
    hints: dict[str, str] | None = None,
) -> None:
    """Attach every config line that names a family variant to that variant."""
    by_ckpt = {v.id: v for fam in families for v in fam.variants if v.engine == "omlx"}
    by_tag = {
        _weights_tag(v.id): v for fam in families for v in fam.variants if v.engine == "ollama"
    }
    for file, line_no, name, value in rows:
        kind = roles.get(line_no, "reference") if file == BACKENDS_FILE else "reference"
        # A registration line names the artifact it registers; it does not consume the
        # checkpoint its id happens to alias to.
        hop = kind == "reference"
        hits = _resolve(value, by_ckpt, by_tag, aliases, alias_hop=hop)
        if not hits and kind == "reference" and hints is not None:
            hinted = hints.get(value.lower())
            if hinted is not None:
                hits = [
                    (variant, "workspace")
                    for variant, _via in _resolve(hinted, by_ckpt, by_tag, aliases)
                ]
        for variant, via in hits:
            variant.refs.append(Ref(file, line_no, name, value, kind, via))


# ── keep / remove decision ────────────────────────────────────────────────────
def _sites(variant: Variant) -> set[tuple[str, str]]:
    """Distinct consumer config values per file, so one workspace repeating a model counts once."""
    return {(ref.file, ref.value) for ref in variant.consumer_refs}


def _rank(variant: Variant) -> tuple[bool, int, int, int, str]:
    """Seated variants first, then most consumer sites, most refs, the shorter id."""
    sites = _sites(variant)
    return (not sites, -len(sites), -len(variant.refs), len(variant.id), variant.id)


def _window(value: str) -> int:
    """The -ctxNk window a config value or tag bakes, 0 when none."""
    matched = _CTX.search(value)
    return int(matched.group(1)) if matched else 0


def _variant_window(variant: Variant) -> int:
    """Largest window the variant's id, tags or named values can serve."""
    values = [variant.id, *variant.tags, *(ref.value for ref in variant.refs)]
    return max((_window(value) for value in values), default=0)


def _window_demand(family: Family) -> int:
    """Largest window any consumer config asks a variant of this family to serve."""
    return max((_window(ref.value) for v in family.variants for ref in v.consumer_refs), default=0)


def _widest(variants: list[Variant], demand: int) -> list[Variant]:
    """The variants serving the in-use window — all of them when none does."""
    fits = [v for v in variants if _variant_window(v) >= demand]
    return fits or variants


def _weights_owner(
    weight: Variant, checkpoints: set[str], aliases: dict[str, tuple[str, str]]
) -> str | None:
    """The family checkpoint whose alias hints name this GGUF weights tag."""
    for tag in weight.tags:
        target = aliases.get(tag.lower(), ("", ""))[1]
        if target in checkpoints:
            return target
    return None


def _groups(family: Family, aliases: dict[str, tuple[str, str]]) -> list[list[Variant]]:
    """A checkpoint plus the GGUF tags that shadow onto it; unpaired members stand alone."""
    checkpoints = {v.id: v for v in family.variants if v.engine == "omlx"}
    groups: dict[str, list[Variant]] = {key: [value] for key, value in checkpoints.items()}
    for weight in (v for v in family.variants if v.engine == "ollama"):
        owner = _weights_owner(weight, set(checkpoints), aliases)
        groups.setdefault(owner or weight.id, []).append(weight)
    return list(groups.values())


def _group_key(group: list[Variant]) -> tuple[int, tuple[str, ...]]:
    """Higher consumer demand first, then a stable id ordering."""
    sites = set().union(*(_sites(v) for v in group))
    return (-len(sites), tuple(sorted(v.id for v in group)))


def _pick_fallback(
    group: list[Variant], weights: list[Variant], primary: Variant, demand: int
) -> Variant | None:
    """The GGUF tag kept alongside the primary seat — the family's own fallback first."""
    if primary.engine == "ollama":
        return None
    inside = _widest([v for v in group if v.engine == "ollama"], demand)
    if inside:
        return min(inside, key=_rank)
    outside = _widest([v for v in weights if v is not primary], demand)
    return min(outside, key=_rank) if outside else None


def _decision(
    variant: Variant,
    primary: Variant,
    fallback: Variant | None,
    others_referenced: bool,
    keep_text: dict[str, str],
) -> tuple[str, str]:
    """(action, why) for one variant of a WARN family."""
    reason = keep_text.get(_weights_tag(variant.id))
    if reason:
        return "KEEP", f"keep_reason: {reason}"
    if _DRAFT_RE.search(variant.id):
        return "KEEP", "draft / DFlash helper"
    if variant is primary:
        return "KEEP", "primary seat" if variant.engine == "omlx" else "primary GGUF tag"
    if variant is fallback:
        return "KEEP", f"GGUF fallback for {primary.id}"
    if variant.consumer_refs and not others_referenced:
        return "KEEP", "only config-referenced variant in the family"
    second = "second oMLX checkpoint" if variant.engine == "omlx" else "second GGUF weights tag"
    return "REMOVE-CANDIDATE", f"{second} in the family"


def _hints_for(primary: Variant, aliases: dict[str, tuple[str, str]]) -> list[str]:
    """Alias hints that resolve to the primary seat, narrowest window first."""
    hints = [hint for hint, target in aliases.values() if target == primary.id]
    return sorted(hints, key=_target_order)


def _target_order(value: str) -> tuple[int, int, str]:
    """Baked-window tags first (narrowest), a bare tag last."""
    matched = _CTX.search(value)
    if matched is None:
        return (1, 0, value)
    return (0, int(matched.group(1)), value)


def _ctx_suffix(value: str) -> str:
    matched = _CTX.search(value)
    return matched.group(1) + "k" if matched else ""


def _window_match(value: str, candidates: list[str]) -> tuple[str, bool]:
    """(target, window kept?) — the candidate holding value's -ctxNk window, else the narrowest."""
    matched = _CTX.search(value)
    if matched is not None:
        for cand in candidates:
            found = _CTX.search(cand)
            if found is not None and found.group(0) == matched.group(0):
                return cand, True
    target = candidates[0]
    return target, matched is None or _ctx_suffix(target) == _ctx_suffix(value)


def _repoint_targets(
    primary: Variant, fallback: Variant | None, aliases: dict[str, tuple[str, str]]
) -> list[str]:
    """Where a consumer line naming a removed variant should point instead."""
    if primary.engine == "ollama":
        return sorted(primary.tags or [primary.id], key=_target_order)
    if fallback is not None:
        targets = fallback.tags or _hints_for(primary, aliases) or [primary.id]
        return sorted(targets, key=_target_order)
    return _hints_for(primary, aliases) or [primary.id]


def _repoints(
    variant: Variant, primary: Variant, targets: list[str], gone_tags: set[str]
) -> list[dict[str, Any]]:
    """Every config line that must change for this variant to go away."""
    out: list[dict[str, Any]] = []
    for ref in variant.refs:
        if ref.kind == "definition":
            out.append({"file": ref.file, "line": ref.line, "how": "delete-entry", "to": ""})
        elif ref.kind == "alias":
            # An `aliases:` key is the GGUF hint itself: when that tag goes too the entry
            # has nothing left to point at, so it is deleted rather than repointed.
            stale = _weights_tag(ref.field) in gone_tags
            out.append(
                {
                    "file": ref.file,
                    "line": ref.line,
                    "how": "delete-alias" if stale else "repoint-alias",
                    "to": "" if stale else primary.id,
                }
            )
        else:
            target, kept = _window_match(ref.value, targets)
            out.append(
                {
                    "file": ref.file,
                    "line": ref.line,
                    "how": "repoint",
                    "to": target,
                    "from_ctx": _ctx_suffix(ref.value),
                    "to_ctx": _ctx_suffix(target),
                    "window_lost": not kept,
                }
            )
    return out


def assign_actions(
    family: Family, aliases: dict[str, tuple[str, str]], keep_text: dict[str, str]
) -> None:
    """Fill action/reason/repoints for every variant of one family."""
    weights = [v for v in family.variants if v.engine == "ollama"]
    demand = _window_demand(family)
    groups = _groups(family, aliases)
    wide = [g for g in groups if max((_variant_window(v) for v in g), default=0) >= demand]
    group = min(wide or groups, key=_group_key)
    seats = [v for v in group if v.engine == "omlx"]
    primary = min(_widest(seats, demand) or group, key=_rank)
    fallback = _pick_fallback(group, weights, primary, demand)
    targets = _repoint_targets(primary, fallback, aliases)
    for variant in family.variants:
        others = any(v.consumer_refs for v in family.variants if v is not variant)
        variant.action, variant.reason = _decision(variant, primary, fallback, others, keep_text)
    gone_tags = {_weights_tag(v.id) for v in weights if v.action == "REMOVE-CANDIDATE"}
    for variant in family.variants:
        if variant.action == "REMOVE-CANDIDATE":
            variant.repoints = _repoints(variant, primary, targets, gone_tags)


# ── live facts ────────────────────────────────────────────────────────────────
def live_ollama_tags(url: str = "http://127.0.0.1:11434") -> dict[str, str]:
    """Lowercased tag → served tag, from Ollama's /api/tags."""
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=10) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read {url}/api/tags: {exc}") from exc
    return {
        str(m.get("name", "")).lower(): str(m.get("name", "")) for m in payload.get("models", [])
    }


def tag_blobs(
    tag: str,
    models: Path | None = None,
    run: model_upstream.Runner | None = None,
    binary: str | None = None,
) -> dict[str, int]:
    """Blob digest → bytes for one Ollama tag, from `ollama show` then the manifest."""
    root = models if models is not None else model_upstream.models_dir()
    digests = model_upstream.show_blobs(tag, run, binary or model_upstream.ollama_bin())
    if digests is None:
        path = model_upstream.find_manifest(root, tag)
        layer = model_upstream.model_layer(path) if path is not None else None
        return {layer[0]: layer[1]} if layer is not None else {}
    out: dict[str, int] = {}
    for digest in digests:
        blob = root / "blobs" / f"sha256-{digest}"
        out[digest] = blob.stat().st_size if blob.is_file() else 0
    return out


def omlx_model_dirs(settings_path: Path | None = None) -> dict[str, Path]:
    """oMLX model name → directory, from the host's oMLX settings."""
    path = settings_path or OMLX_SETTINGS
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    model = cfg.get("model") or {}
    roots = [model.get("model_dir"), *(model.get("model_dirs") or [])]
    out: dict[str, Path] = {}
    for raw in roots:
        if not raw:
            continue
        root = Path(os.path.expanduser(str(raw)))
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.is_dir():
                out.setdefault(child.name, child)
    return out


def dir_files(path: Path) -> dict[tuple[int, int], int]:
    """(device, inode) → bytes for every file under a model dir, hardlinks included."""
    out: dict[tuple[int, int], int] = {}
    for root, _dirs, names in os.walk(path, followlinks=True):
        for name in names:
            try:
                stat = os.stat(os.path.join(root, name))
            except OSError:
                continue
            out[(stat.st_dev, stat.st_ino)] = stat.st_size
    return out


def live_facts(
    ollama_url: str = "http://127.0.0.1:11434",
    settings_path: Path | None = None,
    run: model_upstream.Runner | None = None,
) -> Facts:
    """Read both engines' live state once."""
    served = live_ollama_tags(ollama_url)
    models = model_upstream.models_dir()
    dirs = omlx_model_dirs(settings_path)
    return Facts(
        ollama_tags=served,
        blob_sizes={name: tag_blobs(name, models, run) for name in served.values()},
        omlx_dirs=dirs,
        dir_files={name: dir_files(path) for name, path in dirs.items()},
    )


# ── economics ─────────────────────────────────────────────────────────────────
def assign_installed(variants: list[Variant], facts: Facts) -> None:
    """Mark each variant installed, and record the live tags a GGUF variant covers."""
    for variant in variants:
        if variant.engine == "omlx":
            variant.installed = variant.id in facts.omlx_dirs
            continue
        live = sorted(
            name
            for name in facts.ollama_tags.values()
            if _weights_tag(name) == _weights_tag(variant.id)
        )
        variant.tags = sorted({*variant.tags, *live})
        variant.installed = bool(live)


def _variant_blobs(variant: Variant, facts: Facts) -> dict[str, int]:
    """Blob digest → bytes for every live tag of one GGUF variant."""
    out: dict[str, int] = {}
    for name in facts.ollama_tags.values():
        if _weights_tag(name) == _weights_tag(variant.id):
            out.update(facts.blob_sizes.get(name, {}))
    return out


def _shared_blobs(variant: Variant, facts: Facts, removed_tags: set[str]) -> set[str]:
    """Blob digests another kept tag holds — the variant's own tags excluded."""
    shared: set[str] = set()
    for name in facts.ollama_tags.values():
        if name.lower() in removed_tags or _weights_tag(name) == _weights_tag(variant.id):
            continue
        shared.update(facts.blob_sizes.get(name, {}))
    return shared


def _shared_files(variant: Variant, facts: Facts, removed_dirs: set[str]) -> set[tuple[int, int]]:
    """File identities another kept oMLX dir holds — the variant's own dir excluded."""
    return {
        key
        for name, files in facts.dir_files.items()
        if name not in removed_dirs and name != variant.id
        for key in files
    }


def assign_sizes(families: list[Family], facts: Facts) -> dict[str, int]:
    """Per-variant unique bytes plus the family-wide reclaimable total."""
    variants = [v for fam in families for v in fam.variants]
    removed = [v for v in variants if v.action == "REMOVE-CANDIDATE"]
    removed_tags = {t.lower() for v in removed if v.engine == "ollama" for t in v.tags}
    removed_dirs = {v.id for v in removed if v.engine == "omlx"}
    freed_blobs: dict[str, int] = {}
    freed_files: dict[tuple[int, int], int] = {}
    for variant in variants:
        if variant.engine == "ollama":
            own = _variant_blobs(variant, facts)
            shared = _shared_blobs(variant, facts, removed_tags)
            variant.unique_bytes = sum(size for d, size in own.items() if d not in shared)
            if variant.action == "REMOVE-CANDIDATE":
                freed_blobs.update({d: s for d, s in own.items() if d not in shared})
            continue
        own_files = facts.dir_files.get(variant.id, {})
        shared_files = _shared_files(variant, facts, removed_dirs)
        variant.unique_bytes = sum(
            size for key, size in own_files.items() if key not in shared_files
        )
        if variant.action == "REMOVE-CANDIDATE":
            freed_files.update({k: s for k, s in own_files.items() if k not in shared_files})
    ollama_bytes = sum(freed_blobs.values())
    omlx_bytes = sum(freed_files.values())
    return {
        "ollama_bytes": ollama_bytes,
        "omlx_bytes": omlx_bytes,
        "total_bytes": ollama_bytes + omlx_bytes,
    }


# ── report ────────────────────────────────────────────────────────────────────
def build_report(
    root: Path = REPO_ROOT,
    facts: Facts | None = None,
    check_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The whole dry-run report as plain data."""
    cfg = yaml.safe_load((root / BACKENDS_FILE).read_text(encoding="utf-8")) or {}
    backends = cfg.get("backends") or []
    aliases = _alias_targets(cfg)
    keep_text = _keep_texts(backends)
    families = build_families(backends)
    attribute(families, aliases, scan_config(root), _backend_roles(root), _workspace_hints(root))
    for family in families:
        assign_actions(family, aliases, keep_text)
    facts = facts if facts is not None else live_facts()
    variants = [v for fam in families for v in fam.variants]
    assign_installed(variants, facts)
    freed = assign_sizes(families, facts)
    removed = [v for v in variants if v.action == "REMOVE-CANDIDATE"]
    return {
        "check": check_summary or {},
        "totals": {
            "families": len(families),
            "variants": len(variants),
            "installed": len([v for v in variants if v.installed]),
            "config_only": len([v for v in variants if not v.installed]),
            "remove_candidates": len(removed),
            "remove_candidates_installed": len([v for v in removed if v.installed]),
            "reclaimable_bytes": freed["total_bytes"],
            "reclaimable_gib": round(freed["total_bytes"] / _GIB, 2),
            "ollama_bytes": freed["ollama_bytes"],
            "omlx_bytes": freed["omlx_bytes"],
        },
        "families": [
            {
                "key": fam.key,
                "checkpoints": fam.checkpoints,
                "weights": fam.weights,
                "variants": [v.as_dict() for v in fam.variants],
            }
            for fam in families
        ],
        "config_debt": [v.as_dict() for v in variants if not v.installed],
        "no_fallback_seats": [
            sub["name"]
            for sub in (check_summary or {}).get("findings", [])
            if sub.get("detail") == NO_FALLBACK
        ],
    }


def _check_summary(root: Path) -> dict[str, Any]:
    """The fleet fallback rule's own worklist, so the table and the check agree."""
    from scripts.validation.inference import check_fleet_fallback_rule

    status, detail, findings = check_fleet_fallback_rule(root / BACKENDS_FILE)
    return {"status": status, "detail": detail, "findings": findings}


def _row(variant: dict[str, Any]) -> str:
    engine = "oMLX" if variant["engine"] == "omlx" else "Ollama"
    installed = "yes" if variant["installed"] else "no (config debt)"
    return (
        f"| **{variant['action']}** | {engine} | `{variant['id']}` | {installed} "
        f"| {variant['unique_gib']:.1f} | {len(variant['refs'])} |"
    )


def _ref_line(ref: dict[str, Any]) -> str:
    return f"`{ref['file']}:{ref['line']}`"


_DELETE_TEXT = {
    "delete-entry": "delete the `models:` entry",
    "delete-alias": "delete the `aliases:` entry",
}


def _family_markdown(family: dict[str, Any]) -> list[str]:
    """One family's table plus the repoint lines its removals would need."""
    parts = []
    if len(family["checkpoints"]) > 1:
        parts.append(f"{len(family['checkpoints'])} oMLX checkpoints")
    if len(family["weights"]) > 1:
        parts.append(f"{len(family['weights'])} GGUF weights tags")
    lines = [f"## {family['key']} — {', '.join(parts) or 'one variant'}", ""]
    lines.append("| action | engine | id | installed | unique GiB | refs |")
    lines.append("|---|---|---|---|---|---|")
    lines.extend(_row(item) for item in family["variants"])
    lines.append("")
    for item in family["variants"]:
        if item["action"] != "REMOVE-CANDIDATE" or not item["repoints"]:
            continue
        lines.append(f"repoint for `{item['id']}` ({item['reason']}):")
        for repoint in item["repoints"]:
            delete = _DELETE_TEXT.get(repoint["how"])
            if delete is not None:
                lines.append(f"- {_ref_line(repoint)} {delete}")
                continue
            note = ""
            if repoint["how"] == "repoint" and repoint["window_lost"]:
                note = f" (window {repoint['from_ctx'] or 'none'} → {repoint['to_ctx'] or 'none'})"
            lines.append(f"- {_ref_line(repoint)} {repoint['how']} → `{repoint['to']}`{note}")
        lines.append("")
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    """The dry-run table as markdown."""
    totals = report["totals"]
    check = report.get("check") or {}
    lines = [
        "# Fleet consolidation — dry run (read-only)",
        "",
        "Nothing is deleted or edited here. The operator approves a row; the orchestrator "
        "executes it.",
    ]
    if check:
        lines.append(f"Source: validate_system HY — {check.get('status')} {check.get('detail')}")
    lines += [
        "",
        f"**{totals['families']} WARN families · {totals['variants']} variants · "
        f"{totals['installed']} installed · {totals['config_only']} config-only · "
        f"{totals['remove_candidates']} REMOVE-CANDIDATE · "
        f"{totals['reclaimable_gib']} GiB reclaimable**",
        "",
        "`unique GiB` = bytes no other kept tag shares. `refs` = config lines naming the "
        "variant. Removal is never proposed for the primary seat, its GGUF fallback, a "
        "draft, a `keep_reason:` entry, or a variant no other variant can replace. Seated "
        "variants rank first, and the keep never picks a variant that shrinks a context "
        "window another variant serves in use.",
        "",
    ]
    for family in report["families"]:
        lines.extend(_family_markdown(family))
    debt = report["config_debt"]
    lines += ["## Config debt — configured, not installed", ""]
    if not debt:
        lines.append("None.")
    else:
        lines += ["| engine | id | refs |", "|---|---|---|"]
        lines.extend(
            f"| {'oMLX' if v['engine'] == 'omlx' else 'Ollama'} | `{v['id']}` | {len(v['refs'])} |"
            for v in debt
        )
    lines.append("")
    seats = report["no_fallback_seats"]
    if seats:
        lines += ["## oMLX seats with no GGUF fallback (not a removal decision)", ""]
        lines.extend(f"- `{seat}`" for seat in seats)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--omlx-settings", default=str(OMLX_SETTINGS))
    parser.add_argument("--root", default=str(REPO_ROOT), help="repo root to read config from")
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        facts = live_facts(args.ollama_url, Path(args.omlx_settings))
    except RuntimeError as exc:
        print(f"fleet_consolidate: {exc}", file=sys.stderr)
        return 2
    report = build_report(root, facts, _check_summary(root))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
