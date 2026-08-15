"""bully.training -- periodic operator-launched LoRA refinement (P6.7, I-17).

``run(store, role, dataset_version=...)`` drives: dataset (already built +
released by HARV/an operator, checked here) -> exclusive resource lock +
preflight (refuses if a hunt or a bench/training process is active) ->
``mlx_lm.lora`` (subprocess) -> ``mlx_lm.fuse`` (subprocess) -> llama.cpp
GGUF convert + quantize (subprocess) -> ``ollama create`` (subprocess,
mirrors ``cli/models.py:cmd_models_import_gguf``'s Modelfile mechanism) ->
right-sized acceptance (intake + incumbent comparison + canary) -> verdict
file + `PENDING_MODEL_VERDICTS.md` entry.
``serve()`` is the separate operator-confirmed step that runs the model
canary and only then does the atomic alias promotion; ``rollback()`` is the
atomic alias re-point on a canary regression.

Runtime isolation (Rule 8): every training tool is invoked as an **external
subprocess** -- this module never `import`s ``mlx_lm``/``torch``/
``transformers``/``mlx_vlm`` at all (not even lazily inside a function), so
the "training libraries are never imported by any runtime startup path"
guarantee holds trivially, verified by the existing package-wide import-scan
test (test_boundaries.py) plus a dedicated subprocess-only check here.

Toolchain (installed + verified as this phase's owned build step, MASTER
SS9's Dockerfile-split precedent for "installs are an explicit, auditable
action" applied to a host-native tool instead): `mlx-lm>=0.31` is a
pyproject.toml dependency (installable via `uv pip install -e '.[dev]'` or
the `apple-silicon` extra); llama.cpp's compiled binaries come from
`brew install llama.cpp` (provides `llama-quantize`/`llama-cli`, but not the
Python GGUF converter script, which the brew binary bottle does not ship);
the converter (`convert_hf_to_gguf.py` + its `gguf-py`/`conversion` package)
is fetched by a shallow clone of the llama.cpp repo into
`PORTAL5_HUNT_DIR/toolchain/llama.cpp-src`, with its own dedicated venv at
`PORTAL5_HUNT_DIR/toolchain/venv` (torch/transformers/gguf -- never added to
this repo's pyproject.toml, MASTER SS8/Rule 8) built from that repo's own
`requirements/requirements-convert_hf_to_gguf.txt`. `check_toolchain`
verifies presence only (never auto-installs on a normal `run()` call) --
`ToolchainMissingError` carries the exact install commands.

Boundary rules (MASTER SS3): this module never touches SQL directly
(``store.py`` is the sole SQL owner); it orchestrates subprocesses only, no
model calls of its own (`training.py` is not in the four allowed
model-calling modules).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from . import config as bully_config
from .contracts import DecisionEvent, new_id
from .store import Store

SubprocessRunner = Callable[..., subprocess.CompletedProcess]


class TrainingError(RuntimeError):
    """Base class for TRAIN errors."""


class TrainingBlockedError(TrainingError):
    """Preflight refusal (a hunt or a bench/training process is active, the
    resource lock is already held, or resources are insufficient) -- MASTER
    SS5/SS8: honest-BLOCKED, never a silently-degraded run."""


class ToolchainMissingError(TrainingError):
    """A required host-native tool is missing; carries install instructions
    (I-17 FAILURE SEMANTICS 'toolchain missing -> explicit setup error with
    install instructions')."""


class TrainingSubprocessError(TrainingError):
    """A training subprocess exited non-zero."""


# MASTER SS5 / P6.4: "refuse if a hunt or the bench supervisor is active."
# Scoped exactly to that: the bench harness, and a *concurrent* TRAIN
# subprocess (another mlx_lm.lora/mlx_lm.fuse already running -- the lock
# file also catches this, but a stray un-locked invocation from outside
# this module should too). Deliberately does NOT include a resident
# mlx_lm.server/other long-lived inference process: those are ordinary
# chat-serving load this box runs continuously, not the hunt/bench-sweep
# concurrency this gate exists to prevent.
_HEAVY_PROCESS_MARKERS = (
    "bench_tps",
    "bench_security",
    "bench_supervisor",
    "mlx_lm.lora",
    "mlx_lm lora",
    "mlx_lm.fuse",
)


# ── preflight: exclusive resource lock + hunt/bench-active refusal ────────


def _default_process_lister() -> list[str]:
    result = subprocess.run(["ps", "aux"], capture_output=True, text=True, check=False)
    return result.stdout.splitlines()


def _active_conflict_reason(
    store: Store, process_lister: Callable[[], list[str]] | None
) -> str | None:
    """Real preflight check (P6.4, MASTER SS5 'refuse if a hunt or the bench
    supervisor is active'): a live hunt lease, or a heavy bench/training
    process already on the box. Returns a human reason, or None if clear."""
    if store.any_active_lease():
        return "a hunt lease is currently active"
    lister = process_lister or _default_process_lister
    for line in lister():
        if any(marker in line for marker in _HEAVY_PROCESS_MARKERS):
            return f"a heavy bench/training process is already running: {line.strip()[:160]}"
    return None


def _preflight_disk(
    *, min_free_gb: float = 5.0, path: Path | None = None, disk_usage_fn=None
) -> None:
    disk_usage_fn = disk_usage_fn or shutil.disk_usage
    path = path or bully_config.hunt_dir()
    path.mkdir(parents=True, exist_ok=True)
    usage = disk_usage_fn(str(path))
    free_gb = usage.free / (1024**3)
    if free_gb < min_free_gb:
        raise TrainingBlockedError(
            f"insufficient disk under {path}: {free_gb:.1f}GB free < {min_free_gb}GB floor"
        )


@contextmanager
def exclusive_resource_lock(
    store: Store,
    *,
    lock_path: Path | None = None,
    process_lister: Callable[[], list[str]] | None = None,
    min_free_gb: float = 5.0,
    disk_usage_fn=None,
):
    """The `[GATE]`-adjacent preflight (not an operator gate itself, but the
    hard refusal MASTER SS5/P6.4 requires): raises `TrainingBlockedError`
    -- never silently proceeds -- if a hunt or a bench/training process is
    active, disk is short, or a concurrent TRAIN run already holds the
    lock. The lock file itself is the exclusivity mechanism (O_EXCL is
    atomic at the filesystem level)."""
    reason = _active_conflict_reason(store, process_lister)
    if reason is not None:
        raise TrainingBlockedError(f"refusing to start TRAIN: {reason}")
    _preflight_disk(min_free_gb=min_free_gb, disk_usage_fn=disk_usage_fn)
    lock_path = lock_path or (bully_config.hunt_dir() / "artifacts" / "train.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise TrainingBlockedError(
            f"training resource lock already held: {lock_path} "
            "(a concurrent TRAIN run is in progress)"
        ) from None
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock_path.unlink(missing_ok=True)


# ── toolchain: verify-only (install is this phase's own owned action) ─────


def check_toolchain(*, toolchain_root: Path | None = None) -> dict[str, str]:
    """Verifies every TRAIN toolchain piece is present (never installs).
    Raises `ToolchainMissingError` with the exact install command(s) for
    whatever is missing (I-17 FAILURE SEMANTICS)."""
    root = toolchain_root or (bully_config.hunt_dir() / "toolchain")
    missing: list[str] = []

    lora_bin = shutil.which("mlx_lm.lora")
    fuse_bin = shutil.which("mlx_lm.fuse")
    if lora_bin is None or fuse_bin is None:
        missing.append(
            "mlx-lm -- install: uv pip install -e '.[apple-silicon]' (or: uv pip install 'mlx-lm>=0.31')"
        )

    quantize_bin = shutil.which("llama-quantize")
    if quantize_bin is None:
        missing.append("llama.cpp -- install: brew install llama.cpp")

    convert_script = root / "llama.cpp-src" / "convert_hf_to_gguf.py"
    convert_python = root / "venv" / "bin" / "python3"
    if not convert_script.exists() or not convert_python.exists():
        req = root / "llama.cpp-src" / "requirements" / "requirements-convert_hf_to_gguf.txt"
        missing.append(
            "llama.cpp GGUF converter -- install: "
            f"git clone --depth 1 https://github.com/ggml-org/llama.cpp {root / 'llama.cpp-src'} "
            f"&& uv venv {root / 'venv'} "
            f"&& VIRTUAL_ENV={root / 'venv'} uv pip install -r {req} "
            "--extra-index-url https://download.pytorch.org/whl/cpu -U transformers"
        )

    ollama_bin = shutil.which("ollama")
    if ollama_bin is None:
        missing.append("ollama -- install: ./launch.sh install-ollama")

    if missing:
        raise ToolchainMissingError(
            "TRAIN toolchain incomplete, cannot proceed:\n- " + "\n- ".join(missing)
        )

    return {
        "mlx_lm_lora": lora_bin,
        "mlx_lm_fuse": fuse_bin,
        "llama_quantize": quantize_bin,
        "convert_hf_to_gguf": str(convert_script),
        "convert_python": str(convert_python),
        "ollama": ollama_bin,
    }


# ── subprocess steps (each: build cmd, run, raise on non-zero) ────────────


def _default_runner(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kwargs)


def _run_step(
    runner: SubprocessRunner, cmd: list[str], *, step: str, **kwargs
) -> subprocess.CompletedProcess:
    result = runner(cmd, **kwargs)
    if result.returncode != 0:
        stderr = (result.stderr or "")[-2000:]
        raise TrainingSubprocessError(
            f"TRAIN step {step!r} failed (exit {result.returncode}): {stderr}"
        )
    return result


def _lora_train(
    toolchain: dict,
    *,
    base_model: str,
    data_dir: Path,
    adapter_path: Path,
    iters: int,
    batch_size: int,
    num_layers: int,
    seed: int,
    runner: SubprocessRunner,
) -> None:
    cmd = [
        toolchain["mlx_lm_lora"],
        "--model",
        base_model,
        "--train",
        "--data",
        str(data_dir),
        "--adapter-path",
        str(adapter_path),
        "--iters",
        str(iters),
        "--batch-size",
        str(batch_size),
        "--num-layers",
        str(num_layers),
        "--seed",
        str(seed),
    ]
    _run_step(runner, cmd, step="mlx_lm.lora")


def _fuse(
    toolchain: dict,
    *,
    base_model: str,
    adapter_path: Path,
    save_path: Path,
    runner: SubprocessRunner,
) -> None:
    cmd = [
        toolchain["mlx_lm_fuse"],
        "--model",
        base_model,
        "--adapter-path",
        str(adapter_path),
        "--save-path",
        str(save_path),
    ]
    _run_step(runner, cmd, step="mlx_lm.fuse")


def _convert_gguf(
    toolchain: dict, *, fused_dir: Path, out_path: Path, runner: SubprocessRunner
) -> None:
    cmd = [
        toolchain["convert_python"],
        toolchain["convert_hf_to_gguf"],
        str(fused_dir),
        "--outfile",
        str(out_path),
        "--outtype",
        "f16",
    ]
    _run_step(runner, cmd, step="convert_hf_to_gguf")


def _quantize(
    toolchain: dict, *, f16_path: Path, out_path: Path, quant: str, runner: SubprocessRunner
) -> None:
    cmd = [toolchain["llama_quantize"], str(f16_path), str(out_path), quant]
    _run_step(runner, cmd, step="llama-quantize")


def _ollama_create(
    toolchain: dict, *, model_tag: str, gguf_path: Path, runner: SubprocessRunner
) -> None:
    """Mirrors `cli/models.py:cmd_models_import_gguf`'s mechanism (a
    temporary Modelfile + `ollama create`) rather than importing that typer
    command directly (its parameters are typer.Argument/Option wrappers,
    not a plain callable)."""
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".Modelfile", delete=False, prefix="portal5_train_"
    ) as mf:
        mf.write(f"FROM {gguf_path}\nPARAMETER temperature 0.7\nPARAMETER num_ctx 8192\n")
        mf_path = mf.name
    try:
        cmd = [toolchain["ollama"], "create", model_tag, "-f", mf_path]
        _run_step(runner, cmd, step="ollama create")
    finally:
        Path(mf_path).unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── acceptance gate arithmetic (I-18, P6.7 right-sized policy) ────────

_MAX_ARM_REGRESSION_PT = 2.0


def evaluate_acceptance(
    *,
    intake_report: dict[str, Any],
    incumbent_delta_pt: float | None,
    canary_report: dict[str, Any] | None,
) -> dict[str, Any]:
    """Evaluate the three P6.7 evidence legs, all fail-closed.

    Operator confirmation remains a separate authenticated action in
    :func:`serve`; this pure function only decides whether a candidate may
    enter that queue.
    """
    reasons: list[str] = []

    if not intake_report.get("tps_ok", False):
        reasons.append(f"intake TPS floor not met: {intake_report.get('tps')}")
    if not intake_report.get("tool_ok", False):
        reasons.append("intake tool-call gate failed")

    if incumbent_delta_pt is None:
        reasons.append("incumbent regression evidence missing")
    elif incumbent_delta_pt < -_MAX_ARM_REGRESSION_PT:
        reasons.append(
            f"regression vs incumbent on general security bench: {incumbent_delta_pt:+.1f}pt"
        )

    if canary_report is None:
        reasons.append("model canary evidence missing")
    elif canary_report.get("status") == "FLIPPED":
        reasons.append("model canary flipped vs baseline")
    elif canary_report.get("status") not in {"OK", "PASS", "STABLE"}:
        reasons.append(f"model canary did not pass: {canary_report.get('status')!r}")

    return {"passed": not reasons, "reasons": reasons}


def _default_intake_eval(model_tag: str) -> dict[str, Any]:
    from ..intake import TPS_FLOOR, run_candidate_intake

    results = run_candidate_intake([model_tag], skip_pull=True, tps_floor=TPS_FLOOR)
    row = results[0] if results else {}
    return {
        "model": model_tag,
        "tps": row.get("tps", 0.0),
        "tps_ok": not row.get("below_floor", True),
        "tool_ok": row.get("tool_outcome") == "tool_call",
    }


def _default_canary_eval(model_tag: str) -> dict[str, Any]:
    from ..drift_gate import check_model_canary

    return check_model_canary(model_tag)


# ── verdict file + PENDING_MODEL_VERDICTS.md (existing operator flow) ─────

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PENDING_VERDICTS_MD = _REPO_ROOT / "config" / "PENDING_MODEL_VERDICTS.md"


def _write_verdict_file(model_tag: str, outcome: dict[str, Any], *, verdicts_dir: Path) -> Path:
    import json

    verdicts_dir.mkdir(parents=True, exist_ok=True)
    path = verdicts_dir / f"{model_tag}.verdict.json"
    path.write_text(json.dumps(outcome, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def _append_pending_verdict_entry(
    model_tag: str, outcome: dict[str, Any], *, pending_verdicts_path: Path | None = None
) -> None:
    """I-17 `[GATE]` 'serve only via operator verdict (existing
    PENDING_MODEL_VERDICTS flow)': append a `- [ ]` bullet in the same
    format `scripts/model_cleanup_audit.py` generates, so this TRAIN
    candidate shows up in the operator's existing promote/decline queue
    instead of a bespoke new mechanism. `pending_verdicts_path` defaults to
    the real tracked `config/PENDING_MODEL_VERDICTS.md` -- injectable so
    tests never append real bullets to that file (mirrors every other
    real-default/injectable-for-tests split in this module)."""
    path = pending_verdicts_path if pending_verdicts_path is not None else _PENDING_VERDICTS_MD
    if not path.exists():
        return
    reasons = "; ".join(outcome.get("reasons", [])) or "acceptance evaluation pending review"
    entry = (
        f"- [ ] `{model_tag}` -- TRAIN candidate (role={outcome.get('role')}, "
        f"dataset_version={outcome.get('dataset_version')})\n"
        f"  - evidence: {outcome.get('verdict_file')}\n"
        f"  - verdict: {'accept-candidate' if outcome.get('passed') else 'declined-no-gain'} ({reasons})\n"
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry)


# ── run() -- I-17 ────────────────────────────────────────────────────────


def _record(store: Store, *, subject_id: str, rationale: str, data: dict) -> None:
    store.record_decision(
        DecisionEvent(
            event_id=new_id("de"),
            hunt_id=None,
            iteration_id=None,
            actor="system:training",
            kind="train",
            subject_id=subject_id,
            rationale=rationale,
            data=data,
        )
    )


def run(
    store: Store,
    role: str,
    *,
    dataset_version: str,
    base_model: str,
    train_data_dir: Path,
    seed: int = 1234,
    lora_iters: int = 200,
    lora_batch_size: int = 4,
    lora_num_layers: int = 8,
    quant: str = "Q4_K_M",
    acceptance_policy_version: str = "v1",
    toolchain: dict[str, str] | None = None,
    runner: SubprocessRunner | None = None,
    process_lister: Callable[[], list[str]] | None = None,
    intake_eval_fn: Callable[[str], dict] | None = None,
    incumbent_delta_pt: float | None = None,
    canary_eval_fn: Callable[[str], dict] | None = None,
    artifacts_root: Path | None = None,
    toolchain_root: Path | None = None,
    pending_verdicts_path: Path | None = None,
) -> dict[str, Any]:
    """I-17 `run(role) -> TrainOutcome`. `dataset_version` must already be
    HARV-built *and* operator-released (checked here, never re-released by
    this function -- I-17 OPERATOR BOUNDARY: dataset release and model
    promotion are separate approvals)."""
    if role not in bully_config.REFINEMENT_ROLE_MAP:
        raise TrainingError(
            f"role {role!r} is not an investigation refinement target; "
            "deterministic cousin grading is calibrated, not trained"
        )
    dataset = store.dataset_version_get(dataset_version)
    if dataset is None:
        raise TrainingError(f"no such dataset_version: {dataset_version}")
    if dataset["status"] != "released":
        raise TrainingError(
            f"dataset_version {dataset_version} is not released (status={dataset['status']!r}); "
            "dataset release is a separate operator approval (I-15/I-17)"
        )

    runner = runner or _default_runner

    with exclusive_resource_lock(store, process_lister=process_lister):
        toolchain = toolchain or check_toolchain(toolchain_root=toolchain_root)

        model_tag = (
            "bully-"
            + bully_config.content_hash(
                {
                    "role": role,
                    "base_model": base_model,
                    "dataset_version": dataset_version,
                    "seed": seed,
                    "lora_iters": lora_iters,
                    "lora_num_layers": lora_num_layers,
                }
            )[:16]
        )

        root = artifacts_root or (
            bully_config.hunt_dir() / "artifacts" / "trained_models" / model_tag
        )
        root.mkdir(parents=True, exist_ok=True)
        adapter_path = root / "adapter"
        fused_path = root / "fused"
        f16_path = root / "model-f16.gguf"
        quantized_path = root / f"model-{quant.lower()}.gguf"

        provenance = {
            "dataset_version": dataset_version,
            "base_model": base_model,
            "seed": seed,
            "toolchain_versions": toolchain,
        }

        try:
            _lora_train(
                toolchain,
                base_model=base_model,
                data_dir=train_data_dir,
                adapter_path=adapter_path,
                iters=lora_iters,
                batch_size=lora_batch_size,
                num_layers=lora_num_layers,
                seed=seed,
                runner=runner,
            )
            _fuse(
                toolchain,
                base_model=base_model,
                adapter_path=adapter_path,
                save_path=fused_path,
                runner=runner,
            )
            _convert_gguf(toolchain, fused_dir=fused_path, out_path=f16_path, runner=runner)
            _quantize(
                toolchain, f16_path=f16_path, out_path=quantized_path, quant=quant, runner=runner
            )
        except TrainingSubprocessError as exc:
            # I-17 FAILURE SEMANTICS "training failure -> active alias
            # unchanged" -- no trained_models row is even created for a
            # subprocess that never produced an artifact.
            _record(
                store, subject_id=model_tag, rationale=f"TRAIN failed: {exc}", data={"role": role}
            )
            return {
                "model_tag": None,
                "verdict": "training_failed",
                "reasons": [str(exc)],
                "role": role,
                "dataset_version": dataset_version,
            }

        store.trained_model_put(
            model_tag=model_tag,
            role=role,
            base_model=base_model,
            base_digest=None,
            dataset_version=dataset_version,
            seed=seed,
            hyperparams={
                "iters": lora_iters,
                "batch_size": lora_batch_size,
                "num_layers": lora_num_layers,
            },
            toolchain_versions=toolchain,
            acceptance_policy_version=acceptance_policy_version,
            provenance=provenance,
        )

        gguf_hash = _sha256_file(quantized_path) if quantized_path.exists() else "unavailable"
        try:
            _ollama_create(toolchain, model_tag=model_tag, gguf_path=quantized_path, runner=runner)
        except TrainingSubprocessError as exc:
            store.trained_model_set_reports(
                model_tag, gguf_path=str(quantized_path), gguf_hash=gguf_hash
            )
            store.trained_model_set_verdict(model_tag, "training_failed")
            _record(
                store,
                subject_id=model_tag,
                rationale=f"ollama create failed: {exc}",
                data={"role": role},
            )
            return {
                "model_tag": model_tag,
                "verdict": "training_failed",
                "reasons": [str(exc)],
                "role": role,
                "dataset_version": dataset_version,
            }

        store.trained_model_set_reports(
            model_tag, gguf_path=str(quantized_path), gguf_hash=gguf_hash
        )

        intake_eval_fn = intake_eval_fn or _default_intake_eval
        canary_eval_fn = canary_eval_fn or _default_canary_eval
        intake_report = intake_eval_fn(model_tag)
        canary_report = canary_eval_fn(model_tag)
        acceptance = evaluate_acceptance(
            intake_report=intake_report,
            incumbent_delta_pt=incumbent_delta_pt,
            canary_report=canary_report,
        )
        store.trained_model_set_reports(
            model_tag,
            acceptance_report=acceptance,
            canary_report=canary_report,
            intake_report=intake_report,
        )

        outcome = {
            "model_tag": model_tag,
            "role": role,
            "dataset_version": dataset_version,
            "passed": acceptance["passed"],
            "reasons": acceptance["reasons"],
            "verdict": "pending" if acceptance["passed"] else "declined_no_gain",
        }
        if not acceptance["passed"]:
            store.trained_model_set_verdict(model_tag, "declined_no_gain")
        verdict_path = _write_verdict_file(model_tag, outcome, verdicts_dir=root)
        outcome["verdict_file"] = str(verdict_path)

        if acceptance["passed"]:
            _append_pending_verdict_entry(
                model_tag, outcome, pending_verdicts_path=pending_verdicts_path
            )
            store.promotion_enqueue(
                queue_id=new_id("q"), item_kind="model", item_id=model_tag, hunt_id=None
            )

        _record(
            store,
            subject_id=model_tag,
            rationale=(
                "TRAIN candidate queued for operator verdict"
                if acceptance["passed"]
                else f"TRAIN acceptance failed: {'; '.join(acceptance['reasons'])}"
            ),
            data=outcome,
        )
        return outcome


# ── serve() / rollback() -- canary + atomic alias promotion (I-17) ────────


def serve(
    store: Store,
    model_tag: str,
    *,
    operator_actor: str,
    canary_eval_fn: Callable[[str], dict] | None = None,
) -> dict[str, Any]:
    """`[GATE]` role-alias canary -> atomic promotion, confirm-only. Order
    matters (I-17 STEPS): the canary runs *before* the alias is ever
    re-pointed, so a flipped canary never reaches serving traffic."""
    row = store.trained_model_get(model_tag)
    if row is None:
        raise TrainingError(f"no such trained_model: {model_tag}")
    if row["verdict"] != "pending":
        raise TrainingError(f"serve requires verdict='pending', got {row['verdict']!r}")

    canary_eval_fn = canary_eval_fn or _default_canary_eval
    canary_report = canary_eval_fn(model_tag)
    store.trained_model_set_reports(model_tag, canary_report=canary_report)

    if canary_report.get("status") == "FLIPPED":
        store.trained_model_set_verdict(model_tag, "rejected")
        _record(
            store,
            subject_id=model_tag,
            rationale="model canary flipped -- serve refused",
            data=canary_report,
        )
        return {"model_tag": model_tag, "verdict": "rejected", "reason": "model canary flipped"}

    active_before = store.model_alias_get(row["role"])
    store.trained_model_set_verdict(model_tag, "served", operator_actor=operator_actor)
    store.model_alias_promote(row["role"], model_tag, operator_actor=operator_actor)
    _record(
        store,
        subject_id=model_tag,
        rationale=f"{operator_actor} served {model_tag} for role={row['role']}",
        data={"active_before": active_before, "active_after": model_tag},
    )
    return {"model_tag": model_tag, "verdict": "served", "role": row["role"]}


def rollback(store: Store, role: str, *, operator_actor: str, reason: str) -> dict[str, Any]:
    """Atomic alias re-point (I-17 'canary rollback = alias re-point',
    MASTER SS8 'training failure -> active alias unchanged' generalized to
    a post-serve regression). Returns the tag rolled back to, or None if
    there was nothing to roll back to."""
    target = store.model_alias_rollback(role, operator_actor=operator_actor, reason=reason)
    _record(
        store,
        subject_id=role,
        rationale=f"{operator_actor} rolled back role={role} to {target!r}: {reason}",
        data={"role": role, "rolled_back_to": target, "reason": reason},
    )
    return {"role": role, "rolled_back_to": target}
