"""Pin backfill, upstream change detection, and in-place replace. No network."""

from __future__ import annotations

import hashlib
import json
import plistlib
import subprocess
from pathlib import Path

from scripts import model_upstream as mu
from scripts.model_autoupdate import replace_one
from scripts.model_upstream import Change

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _manifest(model_sha: str, size: int = 100) -> bytes:
    body = {
        "schemaVersion": 2,
        "layers": [
            {
                "mediaType": "application/vnd.ollama.image.model",
                "digest": f"sha256:{model_sha}",
                "size": size,
            }
        ],
    }
    return json.dumps(body, separators=(",", ":")).encode()


def _write_manifest(models: Path, tag: str, model_sha: str, size: int = 100) -> Path:
    path = mu.manifest_path(models, tag)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_manifest(model_sha, size))
    blob = models / "blobs" / f"sha256-{model_sha}"
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(b"old")
    return path


def _hf_tree(filename: str, oid: str, size: int = 50) -> bytes:
    return json.dumps(
        [{"path": filename, "size": size, "lfs": {"oid": oid, "size": size}}]
    ).encode()


def _fetch(routes: dict[tuple[str, str], tuple[int, dict, bytes]]):
    def fetch(method: str, url: str) -> tuple[int, dict[str, str], bytes]:
        status, headers, body = routes[(method, url)]
        return status, {key.lower(): value for key, value in headers.items()}, body

    return fetch


def test_real_backends_parse_keeps_model_ids_only() -> None:
    text = Path("config/backends.yaml").read_text(encoding="utf-8")
    tags = [entry.tag for entry in mu.parse_model_entries(text)]
    assert "ollama-general" not in tags
    assert any(tag.startswith("hf.co/") for tag in tags)
    assert "granite4.1:8b" in tags


def test_models_dir_env_beats_plist(tmp_path: Path) -> None:
    plist = tmp_path / "daemon.plist"
    plist.write_bytes(plistlib.dumps({"EnvironmentVariables": {"OLLAMA_MODELS": "/from/plist"}}))
    assert mu.models_dir({"OLLAMA_MODELS": str(tmp_path / "env")}, plist) == tmp_path / "env"


def test_models_dir_reads_daemon_plist(tmp_path: Path) -> None:
    plist = tmp_path / "daemon.plist"
    plist.write_bytes(
        plistlib.dumps({"EnvironmentVariables": {"OLLAMA_MODELS": str(tmp_path / "models")}})
    )
    assert mu.models_dir({}, plist) == tmp_path / "models"


def test_manifest_paths_for_hf_library_and_namespace(tmp_path: Path) -> None:
    assert mu.manifest_path(tmp_path, "hf.co/org/Repo:Q4").name == "Q4"
    library = mu.manifest_path(tmp_path, "granite4.1:8b")
    assert library.parts[-3:] == ("library", "granite4.1", "8b")
    named = mu.manifest_path(tmp_path, "huihui_ai/qwen:9b")
    assert named.parts[-3:] == ("huihui_ai", "qwen", "9b")


def test_backfill_dry_run_matches_oid_and_does_not_write(tmp_path: Path) -> None:
    models = tmp_path / "models"
    _write_manifest(models, "hf.co/org/Repo:Q4", SHA_A, 80)
    text = "backends:\n- id: ol\n  models:\n  - id: hf.co/org/Repo:Q4\n    supports_tools: true\n"
    url = "https://huggingface.co/api/models/org/Repo/tree/main"
    lines, updated = mu.backfill_lines(
        text,
        models,
        _fetch({("GET", url): (200, {}, _hf_tree("model.gguf", SHA_A, 80))}),
        write=False,
    )
    assert updated == text
    assert lines == [f"PIN hf.co/org/Repo:Q4 repo=org/Repo file=model.gguf sha256={SHA_A} bytes=80"]


def test_backfill_write_sets_pin_on_every_copy_and_keeps_comments(tmp_path: Path) -> None:
    models = tmp_path / "models"
    _write_manifest(models, "hf.co/org/Repo:Q4", SHA_A)
    text = (
        "backends:\n- id: ol\n  models:\n"
        "  # keep\n  - id: hf.co/org/Repo:Q4\n    supports_tools: true\n"
        "- id: ol2\n  models:\n  - id: hf.co/org/Repo:Q4\n    supports_tools: false\n"
    )
    url = "https://huggingface.co/api/models/org/Repo/tree/main"
    _lines, updated = mu.backfill_lines(
        text,
        models,
        _fetch({("GET", url): (200, {}, _hf_tree("model.gguf", SHA_A))}),
        write=True,
    )
    assert "# keep" in updated
    assert updated.count("filename: model.gguf") == 2
    assert updated.count(f"sha256: {SHA_A}") == 2
    assert "supports_tools: false" in updated


def test_backfill_no_hf_match_uses_the_required_sentence(tmp_path: Path) -> None:
    models = tmp_path / "models"
    _write_manifest(models, "hf.co/org/Repo:Q4", SHA_A)
    text = "backends:\n- id: ol\n  models:\n  - id: hf.co/org/Repo:Q4\n"
    url = "https://huggingface.co/api/models/org/Repo/tree/main"
    lines, updated = mu.backfill_lines(
        text,
        models,
        _fetch({("GET", url): (200, {}, _hf_tree("other.gguf", SHA_B))}),
        write=True,
    )
    assert lines == [f"UNPINNED hf.co/org/Repo:Q4 {mu.UNPINNED_NOT_ON_HF}"]
    assert f"unpinned: {json.dumps(mu.UNPINNED_NOT_ON_HF)}" in updated


def test_backfill_missing_manifest_is_not_the_hf_sentence(tmp_path: Path) -> None:
    text = "backends:\n- id: ol\n  models:\n  - id: hf.co/org/Missing:Q4\n"
    lines, updated = mu.backfill_lines(text, tmp_path / "models", _fetch({}), write=True)
    assert lines == [f"UNPINNED hf.co/org/Missing:Q4 {mu.NOT_INSTALLED}"]
    assert mu.UNPINNED_NOT_ON_HF not in updated


def test_hf_pin_change_reports_the_new_file_size(tmp_path: Path) -> None:
    text = (
        "backends:\n- id: ol\n  models:\n"
        "  - id: hf.co/org/Repo:Q4\n"
        "    repo: org/Repo\n    filename: model.gguf\n"
        f"    sha256: {SHA_A}\n    supports_tools: true\n"
    )
    url = "https://huggingface.co/api/models/org/Repo/tree/main"
    scan = mu.collect_changes(
        text,
        tmp_path,
        _fetch({("GET", url): (200, {}, _hf_tree("model.gguf", SHA_B, 4321))}),
    )
    assert len(scan.changes) == 1
    change = scan.changes[0]
    assert change.kind == "hf"
    assert change.new == SHA_B
    assert change.size == 4321
    assert change.supports_tools is True


def test_matching_hf_pin_is_not_a_change(tmp_path: Path) -> None:
    text = (
        "backends:\n- id: ol\n  models:\n  - id: hf.co/org/Repo:Q4\n"
        f"    repo: org/Repo\n    filename: model.gguf\n    sha256: {SHA_A}\n"
    )
    url = "https://huggingface.co/api/models/org/Repo/tree/main"
    scan = mu.collect_changes(
        text, tmp_path, _fetch({("GET", url): (200, {}, _hf_tree("model.gguf", SHA_A, 10))})
    )
    assert scan.changes == []


def test_library_digest_change_reports_missing_blob_size(tmp_path: Path) -> None:
    models = tmp_path / "models"
    path = _write_manifest(models, "granite4.1:8b", SHA_A, 10)
    local = hashlib.sha256(path.read_bytes()).hexdigest()
    remote = _manifest(SHA_B, 999)
    url = mu.registry_manifest_url("granite4.1:8b")
    text = "backends:\n- id: ol\n  models:\n  - id: granite4.1:8b\n    supports_tools: true\n"
    scan = mu.collect_changes(
        text,
        models,
        _fetch(
            {
                ("HEAD", url): (200, {"ollama-content-digest": "b" * 64}, b""),
                ("GET", url): (200, {}, remote),
            }
        ),
    )
    assert local != "b" * 64
    assert len(scan.changes) == 1
    assert scan.changes[0].kind == "library"
    assert scan.changes[0].size == 999


def test_library_same_digest_is_not_a_change(tmp_path: Path) -> None:
    models = tmp_path / "models"
    path = _write_manifest(models, "granite4.1:8b", SHA_A)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    url = mu.registry_manifest_url("granite4.1:8b")
    text = "backends:\n- id: ol\n  models:\n  - id: granite4.1:8b\n"
    scan = mu.collect_changes(
        text, models, _fetch({("HEAD", url): (200, {"ollama-content-digest": digest}, b"")})
    )
    assert scan.changes == []


def test_registry_404_is_not_a_change(tmp_path: Path) -> None:
    models = tmp_path / "models"
    _write_manifest(models, "ling30-tiny-test:latest", SHA_A)
    url = mu.registry_manifest_url("ling30-tiny-test:latest")
    text = "backends:\n- id: ol\n  models:\n  - id: ling30-tiny-test:latest\n"
    scan = mu.collect_changes(text, models, _fetch({("HEAD", url): (404, {}, b"")}))
    assert scan.changes == []
    assert any("not on the Ollama registry" in note for note in scan.notes)


def _change(**kwargs) -> Change:
    base = {
        "tag": "hf.co/org/Repo:Q4",
        "kind": "hf",
        "old": SHA_A,
        "new": SHA_B,
        "size": 40,
        "repo": "org/Repo",
        "filename": "model.gguf",
    }
    base.update(kwargs)
    return Change(**base)


def _ok_run(blobs: dict[str, list[str]] | None = None):
    calls: list[list[str]] = []
    state = {tag: list(digests) for tag, digests in (blobs or {}).items()}

    def run(argv: list[str]):
        calls.append(argv)
        if len(argv) > 3 and argv[1] == "show" and argv[3] == "--modelfile":
            digests = state.get(argv[2])
            if digests is None:
                return subprocess.CompletedProcess(argv, 1, "", "no such model")
            return subprocess.CompletedProcess(argv, 0, _show_body(digests), "")
        return subprocess.CompletedProcess(argv, 0, "FROM blob\n", "")

    return calls, run, state


def _show_body(digests: list[str]) -> str:
    return "".join(f"FROM /models/blobs/sha256-{digest}\n" for digest in digests)


def _show_run(blobs: dict[str, list[str]], on_create=None):
    def run(argv: list[str]):
        if len(argv) > 3 and argv[1] == "show" and argv[3] == "--modelfile":
            digests = blobs.get(argv[2])
            if digests is None:
                return subprocess.CompletedProcess(argv, 1, "", "no such model")
            return subprocess.CompletedProcess(argv, 0, _show_body(digests), "")
        if on_create is not None and "create" in argv:
            on_create(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    return run


def test_missing_manifest_does_not_download(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    calls, run, _state = _ok_run()
    status, text = replace_one(
        _change(),
        models=models,
        backends="backends:\n- id: ol\n  models:\n  - id: hf.co/org/Repo:Q4\n",
        run=run,
        free=lambda: 10**9,
        download=lambda *_a: (_ for _ in ()).throw(AssertionError("downloaded")),
        chat=lambda *_a: None,
        render=lambda *_a: None,
        state={},
        cache={},
    )
    assert status == "absent"
    assert calls == []
    assert "sha256:" not in text


def test_short_disk_skips_without_touching_the_manifest(tmp_path: Path) -> None:
    models = tmp_path / "models"
    manifest = _write_manifest(models, "hf.co/org/Repo:Q4", SHA_A)
    before = manifest.read_bytes()
    calls, run, _state = _ok_run()
    status, _text = replace_one(
        _change(),
        models=models,
        backends="backends:\n- id: ol\n  models:\n  - id: hf.co/org/Repo:Q4\n",
        run=run,
        free=lambda: 10,
        download=lambda *_a: (_ for _ in ()).throw(AssertionError("downloaded")),
        chat=lambda *_a: None,
        render=lambda *_a: None,
        state={},
        cache={},
    )
    assert status == "short"
    assert calls == []
    assert manifest.read_bytes() == before


def test_render_failure_restores_the_manifest_and_rejects(tmp_path: Path) -> None:
    models = tmp_path / "models"
    manifest = _write_manifest(models, "hf.co/org/Repo:Q4", SHA_A)
    before = manifest.read_bytes()
    state: dict = {}
    blobs = {"hf.co/org/Repo:Q4": [SHA_A]}

    def on_create(_argv: list[str]) -> None:
        manifest.write_bytes(_manifest(SHA_B))
        blobs["hf.co/org/Repo:Q4"] = [SHA_B]

    run = _show_run(blobs, on_create)
    status, text = replace_one(
        _change(),
        models=models,
        backends="backends:\n- id: ol\n  models:\n  - id: hf.co/org/Repo:Q4\n",
        run=run,
        free=lambda: 10**9,
        download=lambda _u, dest, _s: dest.write_bytes(b"new"),
        chat=lambda *_a: None,
        render=lambda *_a: "forbidden stop(s) ['<think>']",
        state=state,
        cache={},
    )
    assert status == "rolled_back"
    assert manifest.read_bytes() == before
    assert state["rejected"]["hf.co/org/Repo:Q4"] == [SHA_B]
    assert "sha256:" not in text
    again, _text = replace_one(
        _change(),
        models=models,
        backends=text,
        run=run,
        free=lambda: 10**9,
        download=lambda *_a: (_ for _ in ()).throw(AssertionError("retried")),
        chat=lambda *_a: None,
        render=lambda *_a: None,
        state=state,
        cache={},
    )
    assert again == "rejected"


def test_smoke_failure_restores_the_manifest(tmp_path: Path) -> None:
    models = tmp_path / "models"
    manifest = _write_manifest(models, "hf.co/org/Repo:Q4", SHA_A)
    before = manifest.read_bytes()
    blobs = {"hf.co/org/Repo:Q4": [SHA_A]}

    def on_create(_argv: list[str]) -> None:
        blobs["hf.co/org/Repo:Q4"] = [SHA_B]

    status, _text = replace_one(
        _change(),
        models=models,
        backends="backends:\n- id: ol\n  models:\n  - id: hf.co/org/Repo:Q4\n",
        run=_show_run(blobs, on_create),
        free=lambda: 10**9,
        download=lambda _u, dest, _s: dest.write_bytes(b"new"),
        chat=lambda *_a: "tool-call probe returned no tool_calls",
        render=lambda *_a: None,
        state={},
        cache={},
    )
    assert status == "rolled_back"
    assert manifest.read_bytes() == before


def test_success_updates_the_pin_and_keeps_a_shared_blob(tmp_path: Path) -> None:
    models = tmp_path / "models"
    tag = "hf.co/org/Repo:Q4"
    _write_manifest(models, tag, SHA_A)
    other = _write_manifest(models, "hf.co/org/Other:Q4", SHA_A)
    other.write_bytes(_manifest(SHA_A))
    backends = (
        "backends:\n- id: ol\n  models:\n"
        "  - id: hf.co/org/Repo:Q4\n    supports_tools: true\n"
        "  - id: gemma4:8b\n"
    )
    blobs = {"hf.co/org/Repo:Q4": [SHA_A], "hf.co/org/Other:Q4": [SHA_A]}

    def on_create(_argv: list[str]) -> None:
        mu.manifest_path(models, tag).write_bytes(_manifest(SHA_B))
        blobs[tag] = [SHA_B]

    status, text = replace_one(
        _change(supports_tools=True),
        models=models,
        backends=backends,
        run=_show_run(blobs, on_create),
        free=lambda: 10**9,
        download=lambda _u, dest, _s: dest.write_bytes(b"new"),
        chat=lambda tag, tools: None if tools else "unexpected",
        render=lambda *_a: None,
        state={},
        cache={},
    )
    assert status == "updated"
    assert f"sha256: {SHA_B}" in text
    assert "gemma4:8b" in text
    assert "- id: hf.co/org/brand-new" not in text
    assert (models / "blobs" / f"sha256-{SHA_A}").is_file()
    assert not list(models.glob(".portal5-mf-*"))


def test_success_deletes_an_unreferenced_old_blob(tmp_path: Path) -> None:
    models = tmp_path / "models"
    tag = "hf.co/org/Repo:Q4"
    _write_manifest(models, tag, SHA_A)
    blobs = {tag: [SHA_A]}

    def on_create(_argv: list[str]) -> None:
        mu.manifest_path(models, tag).write_bytes(_manifest(SHA_B))
        blobs[tag] = [SHA_B]

    status, _text = replace_one(
        _change(),
        models=models,
        backends="backends:\n- id: ol\n  models:\n  - id: hf.co/org/Repo:Q4\n",
        run=_show_run(blobs, on_create),
        free=lambda: 10**9,
        download=lambda _u, dest, _s: dest.write_bytes(b"x"),
        chat=lambda *_a: None,
        render=lambda *_a: None,
        state={},
        cache={},
    )
    assert status == "updated"
    assert not (models / "blobs" / f"sha256-{SHA_A}").exists()


def test_library_rebuilds_derived_ctx_without_pulling_it(tmp_path: Path) -> None:
    models = tmp_path / "models"
    _write_manifest(models, "granite4.1:8b", SHA_A)
    calls, run, _state = _ok_run()
    change = Change(
        tag="granite4.1:8b",
        kind="library",
        old=SHA_A,
        new=SHA_C,
        size=10,
        derived=(("granite4.1:8b-ctx8k", 8192),),
    )
    status, text = replace_one(
        change,
        models=models,
        backends="backends:\n- id: ol\n  models:\n  - id: granite4.1:8b\n",
        run=run,
        free=lambda: 10**9,
        download=lambda *_a: (_ for _ in ()).throw(AssertionError("downloaded")),
        chat=lambda *_a: None,
        render=lambda *_a: None,
        state={},
        cache={},
    )
    assert status == "updated"
    installs = [cmd for cmd in calls if cmd[1] != "show"]
    assert installs[0][1:] == ["pull", "granite4.1:8b"]
    assert installs[1][1:3] == ["create", "granite4.1:8b-ctx8k"]
    assert not any(cmd[1] == "pull" and cmd[2].endswith("-ctx8k") for cmd in calls)
    assert "granite4.1:8b-ctx8k" not in text


def test_check_models_lists_upstream_changes(monkeypatch, tmp_path: Path) -> None:
    import scripts.check_updates as cu

    change = _change()
    scan = mu.Scan(changes=[change], notes=["unpinned hf.co/org/Old:Q4: gone"])

    def collect(text: str, models: Path, fetch) -> mu.Scan:
        assert "backends" in text or text == ""
        return scan

    monkeypatch.setattr(mu, "collect_changes", collect)
    monkeypatch.setattr(mu, "models_dir", lambda: tmp_path)
    monkeypatch.setattr(cu, "REPO_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "backends.yaml").write_text("backends: []\n", encoding="utf-8")
    report = cu.check_models()
    assert report.status == "behind"
    assert report.name == "models"
    assert SHA_B[:12] in report.lines[0]
    assert "4321" not in report.lines[0]
    assert "40 bytes" in report.lines[0]


def test_backfill_does_not_add_an_id(tmp_path: Path) -> None:
    text = "backends:\n- id: ol\n  models:\n  - id: gemma4:8b\n"
    lines, updated = mu.backfill_lines(text, tmp_path, _fetch({}), write=True)
    assert lines == []
    assert updated == text
    assert "hf.co/" not in updated


def test_apply_field_updates_refuses_unknown_ids() -> None:
    text = "backends:\n- id: ol\n  models:\n  - id: gemma4:8b\n"
    updated = mu.apply_field_updates(text, {"hf.co/org/New:Q4": {"sha256": SHA_A}})
    assert updated == text


def test_show_blobs_parses_weights_and_projector_from_lines() -> None:
    body = (
        '# Modelfile generated by "ollama show"\n'
        "# FROM hf.co/org/Repo:Q4\n"
        f"FROM /models/blobs/sha256-{SHA_A}\n"
        f"FROM /models/blobs/sha256-{SHA_B}\n"
    )

    def run(argv: list[str]):
        return subprocess.CompletedProcess(argv, 0, body, "")

    assert mu.show_blobs("hf.co/org/Repo:Q4", run) == [SHA_A, SHA_B]


def test_show_blobs_none_when_ollama_cannot_resolve() -> None:
    def run(argv: list[str]):
        return subprocess.CompletedProcess(argv, 1, "", "no such model")

    assert mu.show_blobs("ghost:latest", run) is None
    assert mu.show_blobs("ghost:latest", None) is None


def test_manifest_paths_cover_both_stores(tmp_path: Path) -> None:
    paths = mu.manifest_paths(tmp_path, "hf.co/org/Repo:Q4")
    assert paths[0] == tmp_path / "manifests-v2" / "hf.co" / "org" / "Repo" / "Q4"
    assert paths[1] == tmp_path / "manifests" / "hf.co" / "org" / "Repo" / "Q4"
    library = mu.manifest_paths(tmp_path, "granite4.1:8b")
    assert library[0] == tmp_path / "manifests-v2" / "ollama.com" / "library" / "granite4.1" / "8b"
    assert library[1].parts[-3:] == ("library", "granite4.1", "8b")


def test_backfill_uses_ollama_show_before_files(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    text = "backends:\n- id: ol\n  models:\n  - id: hf.co/org/Repo:Q4\n"
    url = "https://huggingface.co/api/models/org/Repo/tree/main"
    body = f"FROM {models}/blobs/sha256-{SHA_A}\nFROM {models}/blobs/sha256-{SHA_B}\n"

    def run(argv: list[str]):
        return subprocess.CompletedProcess(argv, 0, body, "")

    lines, updated = mu.backfill_lines(
        text,
        models,
        _fetch({("GET", url): (200, {}, _hf_tree("model.gguf", SHA_A, 80))}),
        write=True,
        run=run,
    )
    assert lines == [f"PIN hf.co/org/Repo:Q4 repo=org/Repo file=model.gguf sha256={SHA_A} bytes=80"]


def test_backfill_falls_back_to_a_manifests_v2_symlink(tmp_path: Path) -> None:
    models = tmp_path / "models"
    blob = models / "blobs" / f"sha256-{SHA_A}"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(_manifest(SHA_A, 80))
    link = models / "manifests-v2" / "hf.co" / "org" / "Repo" / "Q4"
    link.parent.mkdir(parents=True)
    link.symlink_to(f"../../../../blobs/sha256-{SHA_A}")
    text = "backends:\n- id: ol\n  models:\n  - id: hf.co/org/Repo:Q4\n"
    url = "https://huggingface.co/api/models/org/Repo/tree/main"
    lines, _updated = mu.backfill_lines(
        text,
        models,
        _fetch({("GET", url): (200, {}, _hf_tree("model.gguf", SHA_A, 80))}),
        write=True,
    )
    assert lines == [f"PIN hf.co/org/Repo:Q4 repo=org/Repo file=model.gguf sha256={SHA_A} bytes=80"]


def test_backfill_separates_not_installed_from_real_misses(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    text = "backends:\n- id: ol\n  models:\n  - id: hf.co/org/Ghost:Q4\n"

    def run(argv: list[str]):
        return subprocess.CompletedProcess(argv, 1, "", "no such model")

    lines, updated = mu.backfill_lines(text, models, _fetch({}), write=True, run=run)
    assert lines == [f"UNPINNED hf.co/org/Ghost:Q4 {mu.NOT_INSTALLED}"]
    assert mu.UNPINNED_NOT_ON_HF not in updated


def test_installed_tags_reads_both_stores(tmp_path: Path) -> None:
    models = tmp_path / "models"
    _write_manifest(models, "granite4.1:8b", SHA_A)
    v2 = models / "manifests-v2" / "hf.co" / "org" / "Repo" / "Q4"
    v2.parent.mkdir(parents=True)
    v2.symlink_to(f"../../../../blobs/sha256-{SHA_A}")
    com = models / "manifests-v2" / "ollama.com" / "library" / "gemma4" / "8b"
    com.parent.mkdir(parents=True)
    com.write_bytes(_manifest(SHA_B))
    engine = models / "manifests" / "registry.ollama.ai" / "library" / "llamacpp" / ("0" * 64)
    engine.parent.mkdir(parents=True)
    engine.write_bytes(_manifest(SHA_C))
    assert mu.installed_tags(models) == [
        "gemma4:8b",
        "granite4.1:8b",
        "hf.co/org/Repo:Q4",
        f"llamacpp:{'0' * 64}",
    ]


def test_drop_refuses_when_any_tag_cannot_be_resolved(tmp_path: Path) -> None:
    models = tmp_path / "models"
    _write_manifest(models, "hf.co/org/Repo:Q4", SHA_A)
    _write_manifest(models, "granite4.1:8b", SHA_A)
    blob = models / "blobs" / f"sha256-{SHA_C}"
    blob.write_bytes(b"x")
    run = _show_run({"hf.co/org/Repo:Q4": [SHA_A]})
    assert mu.blob_referenced(models, SHA_C, run, "ollama") is None
    assert mu.drop_unreferenced_blob(models, SHA_C, run, "ollama") is False
    assert blob.is_file()


def test_drop_requires_show_and_both_manifest_stores_clear(tmp_path: Path) -> None:
    models = tmp_path / "models"
    _write_manifest(models, "hf.co/org/Repo:Q4", SHA_A)
    keep = models / "blobs" / f"sha256-{SHA_A}"
    gone = models / "blobs" / f"sha256-{SHA_C}"
    gone.write_bytes(b"gone")
    run = _show_run({"hf.co/org/Repo:Q4": [SHA_A]})
    assert mu.drop_unreferenced_blob(models, SHA_C, run, "ollama") is True
    assert not gone.exists()
    assert mu.drop_unreferenced_blob(models, SHA_A, run, "ollama") is False
    assert keep.is_file()


def test_llamacpp_engine_manifest_keeps_the_blob(tmp_path: Path) -> None:
    models = tmp_path / "models"
    _write_manifest(models, "granite4.1:8b", SHA_A)
    engine_id = "0" * 64
    engine = models / "manifests" / "registry.ollama.ai" / "library" / "llamacpp" / engine_id
    engine.parent.mkdir(parents=True)
    engine.write_bytes(_manifest(SHA_C))
    blob = models / "blobs" / f"sha256-{SHA_C}"
    blob.write_bytes(b"engine")
    run = _show_run({"granite4.1:8b": [SHA_A], f"llamacpp:{engine_id}": []})
    assert mu.drop_unreferenced_blob(models, SHA_C, run, "ollama") is False
    assert blob.is_file()


def test_v2_manifest_keeps_the_blob(tmp_path: Path) -> None:
    models = tmp_path / "models"
    _write_manifest(models, "granite4.1:8b", SHA_A)
    v2 = models / "manifests-v2" / "hf.co" / "org" / "Repo" / "Q4"
    v2.parent.mkdir(parents=True)
    v2.write_bytes(_manifest(SHA_C))
    blob = models / "blobs" / f"sha256-{SHA_C}"
    blob.write_bytes(b"v2")
    run = _show_run({"granite4.1:8b": [SHA_A], "hf.co/org/Repo:Q4": []})
    assert mu.drop_unreferenced_blob(models, SHA_C, run, "ollama") is False
    assert blob.is_file()


def test_manifest_read_error_refuses_the_delete(tmp_path: Path) -> None:
    models = tmp_path / "models"
    manifest = _write_manifest(models, "granite4.1:8b", SHA_A)
    blob = models / "blobs" / f"sha256-{SHA_C}"
    blob.write_bytes(b"x")
    manifest.chmod(0)
    run = _show_run({"granite4.1:8b": [SHA_A]})
    try:
        assert mu.drop_unreferenced_blob(models, SHA_C, run, "ollama") is False
        assert blob.is_file()
    finally:
        manifest.chmod(0o644)


def test_weekly_job_exits_when_no_pin_is_recorded(tmp_path: Path, monkeypatch, capsys) -> None:
    from scripts import model_autoupdate as job

    backends = tmp_path / "backends.yaml"
    backends.write_text(
        "backends:\n- id: ol\n  models:\n  - id: hf.co/org/Repo:Q4\n    unpinned: gone\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(job, "BACKENDS", backends)
    monkeypatch.setattr(job, "busy", lambda: False)
    monkeypatch.setattr(
        job, "collect_changes", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("scanned"))
    )
    assert job.main([]) == 0
    assert "no recorded pins" in capsys.readouterr().out
    assert not mu.has_recorded_pins(backends.read_text(encoding="utf-8"))


def test_weekly_job_scans_once_a_pin_is_recorded(tmp_path: Path, monkeypatch) -> None:
    from scripts import model_autoupdate as job

    backends = tmp_path / "backends.yaml"
    backends.write_text(
        "backends:\n- id: ol\n  models:\n"
        f"  - id: hf.co/org/Repo:Q4\n    filename: model.gguf\n    sha256: {SHA_A}\n",
        encoding="utf-8",
    )
    seen: dict[str, bool] = {}

    def collect(text: str, models: Path, fetch) -> mu.Scan:
        seen["yes"] = True
        assert SHA_A in text
        return mu.Scan()

    monkeypatch.setattr(job, "BACKENDS", backends)
    monkeypatch.setattr(job, "busy", lambda: False)
    monkeypatch.setattr(job, "models_dir", lambda: tmp_path)
    monkeypatch.setattr(job, "collect_changes", collect)
    assert job.main([]) == 0
    assert seen["yes"] is True


def test_backup_and_restore_cover_the_manifests_v2_symlink(tmp_path: Path) -> None:
    from scripts.model_autoupdate import _backup, _restore

    models = tmp_path / "models"
    manifest_blob = models / "blobs" / f"sha256-{SHA_A}"
    manifest_blob.parent.mkdir(parents=True)
    manifest_blob.write_bytes(_manifest(SHA_A))
    link = models / "manifests-v2" / "hf.co" / "org" / "Repo" / "Q4"
    link.parent.mkdir(parents=True)
    target = f"../../../../blobs/sha256-{SHA_A}"
    link.symlink_to(target)
    saved = _backup(models, ["hf.co/org/Repo:Q4"])
    link.unlink()
    link.write_bytes(_manifest(SHA_B))
    _restore(models, saved)
    assert link.is_symlink()
    assert str(link.readlink()) == target
    payload = json.loads(link.read_text())
    assert payload["layers"][0]["digest"] == f"sha256:{SHA_A}"


def test_restore_removes_manifests_created_in_either_store(tmp_path: Path) -> None:
    from scripts.model_autoupdate import _backup, _restore

    models = tmp_path / "models"
    models.mkdir()
    saved = _backup(models, ["hf.co/org/New:Q4"])
    v2 = mu.manifest_paths(models, "hf.co/org/New:Q4")[0]
    v1 = mu.manifest_path(models, "hf.co/org/New:Q4")
    v2.parent.mkdir(parents=True)
    v2.write_bytes(_manifest(SHA_B))
    v1.parent.mkdir(parents=True)
    v1.write_bytes(_manifest(SHA_B))
    _restore(models, saved)
    assert not v2.exists()
    assert not v1.exists()
