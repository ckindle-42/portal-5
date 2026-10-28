"""Refresh Ollama models from config: library tags pull, pinned GGUFs are created."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import quote

import httpx
import typer

from portal.platform.inference.cluster_backends import BackendRegistry
from portal.platform.inference.config import Model

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]
_Action = Literal["pull", "create", "skip"]
_Status = Literal["created", "pulled", "skipped", "failed"]
_SHA = re.compile(r"[0-9a-fA-F]{64}")
_STOP_RE = re.compile(
    r"""^\s*PARAMETER\s+stop\s+(?:"([^"]*)"|'([^']*)'|(\S+))\s*$""",
    re.MULTILINE,
)
_PIN_KEYS = ("filename", "sha256", "repo", "actual_repo", "num_ctx", "stops")


@dataclass(frozen=True)
class GGUFPin:
    """Pinned Hugging Face GGUF: repo, filename and sha256 are all required."""

    tag: str
    repo: str
    filename: str
    sha256: str
    num_ctx: int | None = None
    stops: tuple[str, ...] = ()


@dataclass(frozen=True)
class RefreshPlan:
    tag: str
    action: _Action
    pin: GGUFPin | None = None
    reason: str = ""


@dataclass(frozen=True)
class InstallResult:
    ok: bool
    status: _Status
    message: str


@dataclass(frozen=True)
class RefreshSummary:
    pulled: int
    created: int
    skipped: int
    failed: int
    skipped_tags: tuple[tuple[str, str], ...]
    failures: tuple[tuple[str, str], ...]


def capturing_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, capture_output=True, text=True)


def streaming_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, text=True)


def hf_client() -> httpx.Client:
    return httpx.Client(follow_redirects=True, timeout=httpx.Timeout(30.0, read=None))


def hf_resolve_url(repo: str, filename: str) -> str:
    repo_part = quote(repo.strip("/"), safe="/")
    file_part = quote(filename, safe="/")
    return f"https://huggingface.co/{repo_part}/resolve/main/{file_part}"


def plans_from_registry(registry: BackendRegistry) -> list[RefreshPlan]:
    """Unique ollama-backend model ids in file order. oMLX ids are left out."""
    order: list[str] = []
    meta: dict[str, dict[str, object]] = {}
    for backend in registry.list_backends():
        if backend.type != "ollama":
            continue
        for model_id in backend.models:
            if model_id not in meta:
                order.append(model_id)
                meta[model_id] = {}
        for entry in backend.ollama_metadata:
            raw_id = entry.get("id")
            if not isinstance(raw_id, str) or not raw_id:
                continue
            slot = meta.setdefault(raw_id, {})
            if raw_id not in order:
                order.append(raw_id)
            _merge_pin_fields(slot, entry)
    return [_plan_for_tag(model_id, meta[model_id]) for model_id in order]


def plan_for_catalog_model(model: Model) -> RefreshPlan:
    """Portal.yaml ``models:`` entry. HF entries need a pin; other tags pull."""
    tag = model.ollama_name
    if _catalog_entry_is_hf(model):
        pin, reason = pin_from_catalog(model)
        if pin is None:
            return RefreshPlan(tag, "skip", reason=reason)
        return RefreshPlan(tag, "create", pin=pin)
    return RefreshPlan(tag, "pull")


def pin_from_catalog(model: Model) -> tuple[GGUFPin | None, str]:
    return parse_pin(
        model.ollama_name,
        {
            "filename": model.filename,
            "sha256": model.sha256,
            "repo": model.actual_repo or model.hf_id,
            "num_ctx": model.num_ctx,
            "stops": model.stops,
        },
    )


def parse_pin(tag: str, meta: Mapping[str, object]) -> tuple[GGUFPin | None, str]:
    """Build a pin from catalog fields. Missing filename or sha256 is unpinned."""
    filename = _clean_str(meta.get("filename"))
    sha, sha_err = _sha_text(meta.get("sha256"))
    if sha_err:
        return None, sha_err
    if not filename or not sha:
        return None, "missing pinned filename+sha256"
    name_err = _filename_error(filename)
    if name_err:
        return None, name_err
    repo, repo_err = _repo_text(tag, meta)
    if repo_err:
        return None, repo_err
    num_ctx, ctx_err = _parse_num_ctx(meta.get("num_ctx"))
    if ctx_err:
        return None, ctx_err
    stops, stops_err = _parse_stops(meta.get("stops"))
    if stops_err:
        return None, stops_err
    return (
        GGUFPin(
            tag=tag,
            repo=repo,
            filename=filename,
            sha256=sha,
            num_ctx=num_ctx,
            stops=stops,
        ),
        "",
    )


def rendered_stops(modelfile: str) -> list[str]:
    found: list[str] = []
    for match in _STOP_RE.finditer(modelfile):
        stop = next(group for group in match.groups() if group is not None)
        found.append(stop)
    return found


def forbidden_stops(modelfile: str, allowed: tuple[str, ...]) -> list[str]:
    """``<think>`` is never legal. Any other stop must be one the catalog declares."""
    bad: list[str] = []
    for stop in rendered_stops(modelfile):
        if ("<think>" in stop or stop not in allowed) and stop not in bad:
            bad.append(stop)
    return bad


def pull_library(tag: str, ollama_cmd: str, runner: Runner) -> InstallResult:
    argv = [*ollama_cmd.split(), "pull", tag]
    completed = runner(argv)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        message = f"FAIL {tag}: ollama pull failed"
        if detail:
            message = f"{message}: {detail}"
        return InstallResult(False, "failed", message)
    return InstallResult(True, "pulled", tag)


def download_file(client: httpx.Client, repo: str, filename: str, dest: Path) -> None:
    headers: dict[str, str] = {}
    token = os.environ.get("HF_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with client.stream("GET", hf_resolve_url(repo, filename), headers=headers) as response:
        response.raise_for_status()
        with dest.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)


def install_pinned(
    pin: GGUFPin,
    ollama_cmd: str,
    *,
    runner: Runner,
    client: httpx.Client,
    dest_dir: Path,
) -> InstallResult:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / PurePosixPath(pin.filename).name
    try:
        download_file(client, pin.repo, pin.filename, dest)
    except httpx.HTTPError as exc:
        dest.unlink(missing_ok=True)
        return InstallResult(False, "failed", f"FAIL {pin.tag}: download failed: {exc}")
    digest = _file_sha256(dest)
    if digest != pin.sha256:
        dest.unlink(missing_ok=True)
        return InstallResult(
            False,
            "failed",
            f"FAIL {pin.tag}: sha256 mismatch for {pin.filename}: expected {pin.sha256} got {digest}",
        )
    modelfile = _write_modelfile(dest_dir, dest, pin.num_ctx)
    try:
        return _create_and_check(pin, ollama_cmd, runner, modelfile, dest)
    finally:
        modelfile.unlink(missing_ok=True)


def execute_plan(
    plan: RefreshPlan,
    ollama_cmd: str,
    *,
    runner: Runner,
    client: httpx.Client,
    dest_dir: Path,
) -> InstallResult:
    if plan.action == "skip":
        return InstallResult(True, "skipped", f"{plan.tag}: {plan.reason}")
    if plan.action == "pull":
        return pull_library(plan.tag, ollama_cmd, runner)
    if plan.pin is None:
        return InstallResult(False, "failed", f"FAIL {plan.tag}: create plan has no pin")
    return install_pinned(plan.pin, ollama_cmd, runner=runner, client=client, dest_dir=dest_dir)


def summarize(rows: list[tuple[RefreshPlan, InstallResult]]) -> RefreshSummary:
    skipped = tuple(
        (plan.tag, result.message) for plan, result in rows if result.status == "skipped"
    )
    failures = tuple(
        (plan.tag, result.message) for plan, result in rows if result.status == "failed"
    )
    return RefreshSummary(
        pulled=sum(result.status == "pulled" for _, result in rows),
        created=sum(result.status == "created" for _, result in rows),
        skipped=len(skipped),
        failed=len(failures),
        skipped_tags=skipped,
        failures=failures,
    )


def refresh_from_backends(ollama_cmd: str) -> RefreshSummary:
    """Refresh every ollama-backend model id from config/backends.yaml."""
    plans = plans_from_registry(BackendRegistry())
    if not plans:
        typer.echo("  No Ollama models declared in config/backends.yaml")
        return RefreshSummary(0, 0, 0, 0, (), ())
    rows: list[tuple[RefreshPlan, InstallResult]] = []
    with hf_client() as client:
        for index, plan in enumerate(plans, start=1):
            typer.echo(f"  [{index}/{len(plans)}] {plan.tag}")
            dest = _dest_for(plan)
            result = execute_plan(
                plan, ollama_cmd, runner=capturing_run, client=client, dest_dir=dest
            )
            _echo(result)
            if plan.action == "create" and result.status != "failed":
                shutil.rmtree(dest, ignore_errors=True)
            rows.append((plan, result))
    summary = summarize(rows)
    typer.echo(
        f"  Ollama: {summary.created + summary.pulled} refreshed, "
        f"{summary.skipped} skipped, {summary.failed} failed"
    )
    return summary


def _dest_for(plan: RefreshPlan) -> Path:
    if plan.action == "create":
        return Path(tempfile.mkdtemp(prefix="portal5-gguf-"))
    return Path(tempfile.gettempdir())


def _echo(result: InstallResult) -> None:
    if result.status == "skipped":
        typer.echo(f"  ⚠️  {result.message}")
    elif result.status == "failed":
        typer.echo(f"  ❌ {result.message}", err=True)
    else:
        typer.echo("  ✅ Done")


def _create_and_check(
    pin: GGUFPin,
    ollama_cmd: str,
    runner: Runner,
    modelfile: Path,
    dest: Path,
) -> InstallResult:
    base = ollama_cmd.split()
    created = runner([*base, "create", pin.tag, "-f", str(modelfile)])
    if created.returncode != 0:
        detail = (created.stderr or created.stdout or "").strip()
        message = f"FAIL {pin.tag}: ollama create failed"
        if detail:
            message = f"{message}: {detail}"
        message = f"{message}; GGUF kept at {dest}"
        return InstallResult(False, "failed", message)
    shown = runner([*base, "show", pin.tag, "--modelfile"])
    if shown.returncode != 0 or shown.stdout is None:
        detail = (shown.stderr or shown.stdout or "").strip()
        message = f"FAIL {pin.tag}: ollama show --modelfile failed"
        if detail:
            message = f"{message}: {detail}"
        return InstallResult(False, "failed", message)
    bad = forbidden_stops(shown.stdout or "", pin.stops)
    if bad:
        return InstallResult(
            False,
            "failed",
            f"FAIL {pin.tag}: ollama show --modelfile has forbidden stop(s) {bad}",
        )
    return InstallResult(True, "created", pin.tag)


def _write_modelfile(dest_dir: Path, gguf: Path, num_ctx: int | None) -> Path:
    lines = [f"FROM {gguf.resolve()}"]
    if num_ctx is not None:
        lines.append(f"PARAMETER num_ctx {num_ctx}")
    path = dest_dir / "Modelfile"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _plan_for_tag(tag: str, entry: Mapping[str, object]) -> RefreshPlan:
    if not tag.startswith("hf.co/"):
        return RefreshPlan(tag, "pull")
    pin, reason = parse_pin(tag, entry)
    if pin is None:
        return RefreshPlan(tag, "skip", reason=reason)
    return RefreshPlan(tag, "create", pin=pin)


def _catalog_entry_is_hf(model: Model) -> bool:
    if model.filename or model.sha256:
        return True
    if model.ollama_name.startswith("hf.co/") or model.hf_id.startswith("hf.co/"):
        return True
    # org/repo is a Hugging Face id. huihui_ai/name:tag is an Ollama library tag.
    return "/" in model.hf_id and ":" not in model.hf_id


def _merge_pin_fields(into: dict[str, object], entry: Mapping[str, object]) -> None:
    for key in _PIN_KEYS:
        if key not in entry or _blank(entry.get(key)):
            continue
        if _blank(into.get(key)):
            into[key] = entry[key]


def _blank(value: object) -> bool:
    return value is None or value == "" or value == []


def _clean_str(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _sha_text(value: object) -> tuple[str, str]:
    if value is None or value == "":
        return "", ""
    if not isinstance(value, str):
        return "", "sha256 must be a 64-character hex string"
    text = value.strip()
    if not _SHA.fullmatch(text):
        return "", "sha256 is not 64 hex characters"
    return text.lower(), ""


def _filename_error(filename: str) -> str:
    if "\\" in filename or filename.startswith("/"):
        return "filename is not a repo-relative path"
    parts = PurePosixPath(filename).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return "filename is not a repo-relative path"
    return ""


def _repo_text(tag: str, meta: Mapping[str, object]) -> tuple[str, str]:
    repo = _clean_str(meta.get("repo")) or _clean_str(meta.get("actual_repo"))
    if repo.startswith("hf.co/"):
        repo = _repo_from_hf_tag(repo)
    if not repo and tag.startswith("hf.co/"):
        repo = _repo_from_hf_tag(tag)
    if not repo or "/" not in repo or ":" in repo:
        return "", "missing repo for pinned GGUF"
    return repo, ""


def _repo_from_hf_tag(tag: str) -> str:
    rest = tag[len("hf.co/") :] if tag.startswith("hf.co/") else tag
    repo, _, _quant = rest.partition(":")
    return repo.strip()


def _parse_num_ctx(value: object) -> tuple[int | None, str]:
    if value is None or value == "":
        return None, ""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None, "num_ctx must be a positive int"
    return value, ""


def _parse_stops(value: object) -> tuple[tuple[str, ...], str]:
    if value is None or value == "":
        return (), ""
    if not isinstance(value, list):
        return (), "stops must be a list of strings"
    stops: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            return (), "stops must be a list of strings"
        stops.append(item)
    return tuple(stops), ""
