#!/usr/bin/env python3
"""Replace catalog models whose upstream changed. Weekly, in place.

Same gates as the engine and security jobs: defer while a WFE, UAT or bench
run is in flight, Pushover, a state file of rejected upstream ids, and a
commit of ``config/backends.yaml`` only. A plain ``portal update`` does not
run this; ``--refresh-models`` / ``--now`` opts in.

This Ollama build has no ``prune`` command. After a successful replace the job
deletes the previous model-layer blob only when no manifest still names it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from portal.platform.inference.cli.model_refresh import (  # noqa: E402
    ctx_modelfile_text,
    forbidden_stops,
)
from scripts.check_updates import _pushover  # noqa: E402
from scripts.engine_autoupdate import busy, log  # noqa: E402
from scripts.model_upstream import (  # noqa: E402
    Change,
    apply_field_updates,
    collect_changes,
    default_fetch,
    drop_unreferenced_blob,
    manifest_path,
    model_layer,
    models_dir,
    resolve_url,
    stream_download,
)

STATE = Path.home() / ".portal5" / "model_update.json"
BACKENDS = REPO / "config" / "backends.yaml"
Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]
Chat = Callable[[str, bool], str | None]
Render = Callable[[str, tuple[str, ...]], str | None]
Download = Callable[[str, Path, str], None]


def ollama_bin() -> str:
    override = os.environ.get("OLLAMA_BIN", "").strip()
    if override:
        return override
    live = Path.home() / "ollama-current" / "ollama"
    if live.is_file():
        return str(live)
    return "ollama"


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, capture_output=True, text=True)


def _live_render(tag: str, stops: tuple[str, ...]) -> str | None:
    shown = _run([ollama_bin(), "show", tag, "--modelfile"])
    if shown.returncode != 0 or shown.stdout is None:
        return "ollama show --modelfile failed"
    bad = forbidden_stops(shown.stdout, stops)
    if bad:
        return f"forbidden stop(s) {bad}"
    return None


def _live_chat(tag: str, tools: bool) -> str | None:
    import urllib.request

    payload: dict = {
        "model": tag,
        "stream": False,
        "messages": [{"role": "user", "content": "Reply with the single word ok."}],
        "options": {"num_predict": 32},
    }
    if tools:
        payload["messages"] = [{"role": "user", "content": "Call the ping tool."}]
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": "ping",
                    "description": "Reply ping.",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310
            body = json.loads(response.read().decode())
    except Exception as exc:
        return f"chat failed: {exc}"
    message = body.get("message") or {}
    if tools and not message.get("tool_calls"):
        return "tool-call probe returned no tool_calls"
    if not message:
        return "empty chat response"
    return None


def _rejected(state: dict, change: Change) -> bool:
    known = (state.get("rejected") or {}).get(change.tag) or []
    return change.new in known


def _remember(state: dict, change: Change) -> None:
    bucket = state.setdefault("rejected", {}).setdefault(change.tag, [])
    if change.new not in bucket:
        bucket.append(change.new)


def _backup(models: Path, tags: list[str]) -> dict[str, bytes | None]:
    saved: dict[str, bytes | None] = {}
    for tag in tags:
        path = manifest_path(models, tag)
        saved[tag] = path.read_bytes() if path.is_file() else None
    return saved


def _restore(models: Path, saved: dict[str, bytes | None]) -> None:
    for tag, blob in saved.items():
        path = manifest_path(models, tag)
        if blob is None:
            path.unlink(missing_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)


def _create(run: Runner, binary: str, tag: str, modelfile: Path) -> None:
    done = run([binary, "create", tag, "-f", str(modelfile)])
    if done.returncode != 0:
        detail = (done.stderr or done.stdout or "ollama create failed").strip()
        raise OSError(detail)


def _write_from(path: Path, source: str, num_ctx: int | None) -> None:
    lines = [f"FROM {source}"]
    if num_ctx:
        lines.append(f"PARAMETER num_ctx {num_ctx}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _install(
    change: Change,
    *,
    models: Path,
    run: Runner,
    binary: str,
    gguf: Path | None,
    work: Path,
) -> None:
    if change.kind == "hf":
        if gguf is None:
            raise OSError("missing verified GGUF")
        modelfile = work / "Modelfile"
        _write_from(modelfile, str(gguf), change.num_ctx)
        _create(run, binary, change.tag, modelfile)
        return
    pulled = run([binary, "pull", change.tag])
    if pulled.returncode != 0:
        detail = (pulled.stderr or pulled.stdout or "ollama pull failed").strip()
        raise OSError(detail)
    for tag, num_ctx in change.derived:
        derived = work / "Modelfile.ctx"
        derived.write_text(ctx_modelfile_text(change.tag, num_ctx), encoding="utf-8")
        _create(run, binary, tag, derived)


def _stage(
    change: Change,
    models: Path,
    download: Download,
    cache: dict[tuple[str, str, str], Path],
) -> Path | None:
    if change.kind != "hf":
        return None
    key = (change.repo, change.filename, change.new)
    cached = cache.get(key)
    if cached is not None and cached.is_file():
        return cached
    folder = Path(tempfile.mkdtemp(prefix=".portal5-refresh-", dir=models))
    dest = folder / Path(change.filename).name
    try:
        download(resolve_url(change.repo, change.filename), dest, change.new)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    cache[key] = dest
    return dest


def _needs_space(change: Change, cache: dict[tuple[str, str, str], Path]) -> bool:
    if change.kind != "hf":
        return True
    cached = cache.get((change.repo, change.filename, change.new))
    return not (cached is not None and cached.is_file())


def _tags(change: Change) -> list[str]:
    return [change.tag, *[tag for tag, _ctx in change.derived]]


def _layer_sha(models: Path, tag: str) -> str:
    layer = model_layer(manifest_path(models, tag))
    if layer is None:
        return ""
    return layer[0]


def _fail(
    models: Path,
    change: Change,
    saved: dict[str, bytes | None],
    new_sha: str,
    old_sha: str,
    state: dict,
    reason: str,
) -> None:
    _restore(models, saved)
    if new_sha and new_sha != old_sha:
        drop_unreferenced_blob(models, new_sha)
    _remember(state, change)
    log(f"rolled back {change.tag}: {reason}")


def replace_one(
    change: Change,
    *,
    models: Path,
    backends: str,
    run: Runner,
    free: Callable[[], int],
    download: Download,
    chat: Chat,
    render: Render,
    state: dict,
    cache: dict[tuple[str, str, str], Path],
    binary: str = "ollama",
) -> tuple[str, str]:
    """Replace one changed tag. Returns ``(status, backends text)``."""
    if _rejected(state, change):
        log(f"skip {change.tag}: rejected upstream {change.new[:12]}")
        return "rejected", backends
    if not manifest_path(models, change.tag).is_file():
        log(f"skip {change.tag}: no local manifest")
        return "absent", backends
    if _needs_space(change, cache) and free() < change.size:
        log(f"skip {change.tag}: free space {free()} < {change.size}")
        return "short", backends
    work = Path(tempfile.mkdtemp(prefix=".portal5-mf-", dir=models))
    saved = _backup(models, _tags(change))
    old_sha = _layer_sha(models, change.tag)
    try:
        gguf = _stage(change, models, download, cache)
        _install(change, models=models, run=run, binary=binary, gguf=gguf, work=work)
        problem = render(change.tag, change.stops)
        if problem:
            raise OSError(problem)
        problem = chat(change.tag, change.supports_tools)
        if problem:
            raise OSError(problem)
    except OSError as exc:
        new_sha = _layer_sha(models, change.tag)
        _fail(models, change, saved, new_sha, old_sha, state, str(exc))
        shutil.rmtree(work, ignore_errors=True)
        return "rolled_back", backends
    drop_unreferenced_blob(models, old_sha)
    shutil.rmtree(work, ignore_errors=True)
    if change.kind != "hf":
        return "updated", backends
    updated = apply_field_updates(
        backends,
        {
            change.tag: {
                "repo": change.repo,
                "filename": change.filename,
                "sha256": change.new,
                "unpinned": "",
            }
        },
    )
    return "updated", updated


def _dirty(path: Path) -> bool:
    probe = subprocess.run(
        ["git", "status", "--porcelain", "--", str(path)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(probe.stdout.strip())


def _commit(path: Path, lines: list[str]) -> bool:
    message = "fix(models): refresh upstream pins\n\n" + "\n".join(lines)
    subprocess.run(["git", "add", "--", str(path)], cwd=REPO, check=False)
    done = subprocess.run(
        ["git", "commit", "-m", message, "--", str(path)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        log(f"commit failed: {(done.stdout + done.stderr)[-400:]}")
    return done.returncode == 0


def _load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _notify(results: list[tuple[str, str]]) -> None:
    rolled = [tag for status, tag in results if status == "rolled_back"]
    short = [tag for status, tag in results if status == "short"]
    updated = [tag for status, tag in results if status == "updated"]
    if rolled:
        _pushover("Model refresh rolled back", ", ".join(rolled), True)
    elif short:
        _pushover("Model refresh skipped (disk)", ", ".join(short), False)
    elif updated:
        _pushover("Model refresh", ", ".join(updated), False)


def _clean_cache(cache: dict[tuple[str, str, str], Path]) -> None:
    for path in cache.values():
        shutil.rmtree(path.parent, ignore_errors=True)


def apply_scanned(
    scan_changes: list[Change],
    *,
    models: Path,
    backends: str,
    dirty: bool,
    run: Runner,
    free: Callable[[], int],
    download: Download,
    chat: Chat,
    render: Render,
    state: dict,
    binary: str = "ollama",
) -> tuple[str, list[tuple[str, str]]]:
    """Apply a known change list. Returns ``(backends text, status rows)``."""
    cache: dict[tuple[str, str, str], Path] = {}
    results: list[tuple[str, str]] = []
    text = backends
    try:
        for change in scan_changes:
            if dirty and change.kind == "hf":
                log(f"defer {change.tag}: config/backends.yaml has uncommitted changes")
                results.append(("deferred", change.tag))
                continue
            status, text = replace_one(
                change,
                models=models,
                backends=text,
                run=run,
                free=free,
                download=download,
                chat=chat,
                render=render,
                state=state,
                cache=cache,
                binary=binary,
            )
            results.append((status, change.tag))
    finally:
        _clean_cache(cache)
    return text, results


def main(argv: list[str]) -> int:
    if busy():
        log("deferring: a sweep is running")
        return 0
    models = models_dir()
    text = BACKENDS.read_text(encoding="utf-8")
    scan = collect_changes(text, models, default_fetch)
    for note in scan.notes:
        log(note)
    if not scan.changes:
        log("models: no upstream change")
        return 0
    for change in scan.changes:
        log(
            f"upstream {change.kind} {change.tag} "
            f"{change.old[:12]} -> {change.new[:12]} bytes={change.size}"
        )
    if "--dry-run" in argv:
        return 0
    state = _load_state()
    updated, results = apply_scanned(
        scan.changes,
        models=models,
        backends=text,
        dirty=_dirty(BACKENDS),
        run=_run,
        free=lambda: shutil.disk_usage(models).free,
        download=stream_download,
        chat=_live_chat,
        render=_live_render,
        state=state,
    )
    if updated != text:
        BACKENDS.write_text(updated, encoding="utf-8")
        pins = [f"{tag} refreshed" for status, tag in results if status == "updated"]
        if not _commit(BACKENDS, pins):
            log("backends.yaml updated and left uncommitted")
    _save_state(state)
    _notify(results)
    log("models: " + ", ".join(f"{status} {tag}" for status, tag in results))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
