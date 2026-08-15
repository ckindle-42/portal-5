"""P6.4 -- TRAIN: LoRA flywheel + frozen five-arm acceptance + toolchain
install (M8).

Hermetic (`tmp_path`, no network, no real subprocess -- every subprocess
call is intercepted by a fake `runner`). Feeds C11 TRAIN + F1-F2 shadow:
import-scan (no training extras at startup); toolchain-missing -> explicit
error; no-gain -> non-serve, alias unchanged; five-arm gate arithmetic on
fixtures; canary rollback = alias re-point.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from portal.modules.security.core.bully import training
from portal.modules.security.core.bully.store import Store

REPO_ROOT = Path(__file__).resolve().parents[3]
TRAINING_PY = REPO_ROOT / "portal" / "modules" / "security" / "core" / "bully" / "training.py"


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hunt_state.db")
    yield s
    s.close()


def _released_dataset(store, dataset_version="dv-1"):
    store.dataset_version_put(
        dataset_version=dataset_version,
        role="hunter",
        window={},
        counts={"total": 30},
        split_manifest={},
        dedup_leakage_report={},
        replay_mix_sources=[],
        manifest_path=None,
    )
    store.dataset_version_release(
        dataset_version, operator_actor="operator:alice", approval_ref="ref-1"
    )
    return dataset_version


FAKE_TOOLCHAIN = {
    "mlx_lm_lora": "FAKE_LORA",
    "mlx_lm_fuse": "FAKE_FUSE",
    "llama_quantize": "FAKE_QUANTIZE",
    "convert_hf_to_gguf": "FAKE_CONVERT_SCRIPT",
    "convert_python": "FAKE_CONVERT_PY",
    "ollama": "FAKE_OLLAMA",
}


def _fake_runner(calls, *, fail_step: str | None = None):
    def runner(cmd, **kwargs):
        calls.append(cmd)
        exe = cmd[0]
        if fail_step is not None and exe == fail_step:
            return SimpleNamespace(returncode=1, stderr=f"{exe} exploded")
        if exe == "FAKE_QUANTIZE":
            Path(cmd[2]).write_bytes(b"fake-gguf-bytes")
        return SimpleNamespace(returncode=0, stderr="")

    return runner


def _passing_five_arm():
    return {
        "macro_f1_delta_vs_full_stack": 7.2,
        "ci95_lower": 1.1,
        "per_arm_regressions_pt": {"retrieval": -0.5},
    }


def _passing_intake():
    return {"tps": 40.0, "tps_ok": True, "tool_ok": True}


# ── import-scan: no training extras at startup ─────────────────────────────


def test_training_module_never_imports_training_extras():
    """Rule 8: training.py orchestrates subprocesses only -- it must never
    `import` mlx_lm/torch/transformers/mlx_vlm at all, not even lazily
    inside a function (stricter than the generic module-scope-only guard
    test_boundaries.py already applies to the whole package)."""
    tree = ast.parse(TRAINING_PY.read_text(encoding="utf-8"))
    forbidden = {"mlx_lm", "torch", "transformers", "mlx_vlm"}
    hit = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hit |= {alias.name.split(".")[0] for alias in node.names} & forbidden
        elif isinstance(node, ast.ImportFrom) and node.module:
            hit |= {node.module.split(".")[0]} & forbidden
    assert not hit, f"training.py imports a training extra: {hit}"


# ── toolchain-missing -> explicit error ─────────────────────────────────────


def test_check_toolchain_raises_with_install_instructions_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(training.shutil, "which", lambda name: None)
    with pytest.raises(training.ToolchainMissingError) as exc_info:
        training.check_toolchain(toolchain_root=tmp_path / "toolchain")
    message = str(exc_info.value)
    assert "install" in message.lower()
    assert "mlx-lm" in message
    assert "llama.cpp" in message


def test_run_raises_toolchain_missing_before_any_subprocess(store, tmp_path):
    dv = _released_dataset(store)
    calls = []
    with pytest.raises(training.ToolchainMissingError):
        training.run(
            store,
            "hunter",
            dataset_version=dv,
            base_model="fake/base-model",
            train_data_dir=tmp_path / "data",
            toolchain=None,  # forces a real check_toolchain() call
            toolchain_root=tmp_path / "toolchain",  # empty -- nothing installed there
            runner=_fake_runner(calls),
            process_lister=lambda: [],
            artifacts_root=tmp_path / "artifacts",
        )
    assert calls == []  # never reached a subprocess step


# ── preflight: refuses when a hunt or heavy process is active ─────────────


def test_run_refuses_when_hunt_lease_active(store, tmp_path):
    store.hunt_create(
        hunt_id="h1",
        objective="o",
        neighborhood_scope="lab",
        authorization_ref="a",
        config_version="c",
        role_snapshot={},
        budgets={},
    )
    store.lease_acquire("h1", "operator:alice", ttl_s=300.0)
    dv = _released_dataset(store)
    with pytest.raises(training.TrainingBlockedError, match="hunt lease"):
        training.run(
            store,
            "hunter",
            dataset_version=dv,
            base_model="fake/base-model",
            train_data_dir=tmp_path / "data",
            toolchain=FAKE_TOOLCHAIN,
            runner=_fake_runner([]),
            process_lister=lambda: [],
            artifacts_root=tmp_path / "artifacts",
        )


def test_run_refuses_when_heavy_process_active(store, tmp_path):
    dv = _released_dataset(store)
    with pytest.raises(training.TrainingBlockedError, match="heavy"):
        training.run(
            store,
            "hunter",
            dataset_version=dv,
            base_model="fake/base-model",
            train_data_dir=tmp_path / "data",
            toolchain=FAKE_TOOLCHAIN,
            runner=_fake_runner([]),
            process_lister=lambda: ["user  123  python -m mlx_lm.lora --train"],
            artifacts_root=tmp_path / "artifacts",
        )


def test_run_requires_released_dataset(store, tmp_path):
    store.dataset_version_put(
        dataset_version="dv-unreleased",
        role="hunter",
        window={},
        counts={},
        split_manifest={},
        dedup_leakage_report={},
        replay_mix_sources=[],
        manifest_path=None,
    )
    with pytest.raises(training.TrainingError, match="not released"):
        training.run(
            store,
            "hunter",
            dataset_version="dv-unreleased",
            base_model="fake/base-model",
            train_data_dir=tmp_path / "data",
            toolchain=FAKE_TOOLCHAIN,
            runner=_fake_runner([]),
            process_lister=lambda: [],
            artifacts_root=tmp_path / "artifacts",
        )


def test_concurrent_lock_refuses_second_run(store, tmp_path):
    lock_path = tmp_path / "train.lock"
    lock_path.write_text("999999")
    with (
        pytest.raises(training.TrainingBlockedError, match="lock already held"),
        training.exclusive_resource_lock(store, lock_path=lock_path, process_lister=lambda: []),
    ):
        pass


# ── run(): subprocess failure -> training_failed, alias untouched ─────────


def test_lora_subprocess_failure_is_training_failed_no_row(store, tmp_path):
    dv = _released_dataset(store)
    calls = []
    outcome = training.run(
        store,
        "hunter",
        dataset_version=dv,
        base_model="fake/base-model",
        train_data_dir=tmp_path / "data",
        toolchain=FAKE_TOOLCHAIN,
        runner=_fake_runner(calls, fail_step="FAKE_LORA"),
        process_lister=lambda: [],
        artifacts_root=tmp_path / "artifacts",
    )
    assert outcome["verdict"] == "training_failed"
    assert outcome["model_tag"] is None
    assert store.model_alias_get("hunter") is None  # alias untouched


# ── run(): full pipeline, no-gain -> declined_no_gain, non-serve ──────────


def test_full_pipeline_no_gain_default_is_declined_non_serve(store, tmp_path):
    """The default five-arm evaluator is an honest no-gain report (no real
    cousin-suite harness exists yet) -- proves the no-gain path end to end
    through the real subprocess sequence (faked) without loosening any
    threshold to force a fabricated pass."""
    dv = _released_dataset(store)
    calls = []
    outcome = training.run(
        store,
        "hunter",
        dataset_version=dv,
        base_model="fake/base-model",
        train_data_dir=tmp_path / "data",
        toolchain=FAKE_TOOLCHAIN,
        runner=_fake_runner(calls),
        process_lister=lambda: [],
        artifacts_root=tmp_path / "artifacts",
        pending_verdicts_path=tmp_path / "PENDING_MODEL_VERDICTS.md",
        intake_eval_fn=lambda tag: _passing_intake(),
    )
    assert outcome["passed"] is False
    assert outcome["verdict"] == "declined_no_gain"
    assert outcome["model_tag"] is not None
    row = store.trained_model_get(outcome["model_tag"])
    assert row["verdict"] == "declined_no_gain"
    assert store.model_alias_get("hunter") is None  # never promoted
    assert store.promotion_list(state="pending") == []  # no-gain never queued
    assert Path(outcome["verdict_file"]).exists()
    # 5 real subprocess steps: lora, fuse, convert, quantize, ollama create.
    assert len(calls) == 5


def test_full_pipeline_passing_five_arm_queues_for_operator(store, tmp_path):
    dv = _released_dataset(store)
    outcome = training.run(
        store,
        "hunter",
        dataset_version=dv,
        base_model="fake/base-model",
        train_data_dir=tmp_path / "data",
        toolchain=FAKE_TOOLCHAIN,
        runner=_fake_runner([]),
        process_lister=lambda: [],
        artifacts_root=tmp_path / "artifacts",
        pending_verdicts_path=tmp_path / "PENDING_MODEL_VERDICTS.md",
        intake_eval_fn=lambda tag: _passing_intake(),
        five_arm_eval_fn=lambda tag: _passing_five_arm(),
    )
    assert outcome["passed"] is True
    assert outcome["verdict"] == "pending"
    row = store.trained_model_get(outcome["model_tag"])
    assert row["verdict"] == "pending"
    pending = store.promotion_list(state="pending")
    assert len(pending) == 1
    assert pending[0]["item_kind"] == "model"
    assert pending[0]["item_id"] == outcome["model_tag"]


def test_full_pipeline_never_touches_the_real_tracked_pending_verdicts_file(store, tmp_path):
    """Regression guard: `pending_verdicts_path` must be threaded through
    (and every test in this file must inject a tmp_path override) so a
    hermetic test run never appends bullets to the real, git-tracked
    `config/PENDING_MODEL_VERDICTS.md`."""
    real_path = training._PENDING_VERDICTS_MD
    before = real_path.read_text(encoding="utf-8") if real_path.exists() else None

    dv = _released_dataset(store)
    training.run(
        store,
        "hunter",
        dataset_version=dv,
        base_model="fake/base-model",
        train_data_dir=tmp_path / "data",
        toolchain=FAKE_TOOLCHAIN,
        runner=_fake_runner([]),
        process_lister=lambda: [],
        artifacts_root=tmp_path / "artifacts",
        pending_verdicts_path=tmp_path / "PENDING_MODEL_VERDICTS.md",
        intake_eval_fn=lambda tag: _passing_intake(),
    )

    after = real_path.read_text(encoding="utf-8") if real_path.exists() else None
    assert before == after


# ── evaluate_acceptance: five-arm gate arithmetic on fixtures ─────────────


def test_evaluate_acceptance_passes_with_a_clean_five_arm_win():
    result = training.evaluate_acceptance(
        intake_report=_passing_intake(),
        incumbent_delta_pt=0.5,
        five_arm_report=_passing_five_arm(),
    )
    assert result["passed"] is True
    assert result["reasons"] == []


def test_evaluate_acceptance_fails_below_intake_floor():
    result = training.evaluate_acceptance(
        intake_report={"tps_ok": False, "tps": 5.0},
        incumbent_delta_pt=0.5,
        five_arm_report=_passing_five_arm(),
    )
    assert result["passed"] is False
    assert any("intake" in r for r in result["reasons"])


def test_evaluate_acceptance_fails_on_incumbent_regression():
    result = training.evaluate_acceptance(
        intake_report=_passing_intake(),
        incumbent_delta_pt=-3.0,
        five_arm_report=_passing_five_arm(),
    )
    assert result["passed"] is False
    assert any("incumbent" in r for r in result["reasons"])


def test_evaluate_acceptance_fails_below_five_arm_macro_f1_floor():
    result = training.evaluate_acceptance(
        intake_report=_passing_intake(),
        incumbent_delta_pt=0.0,
        five_arm_report={
            "macro_f1_delta_vs_full_stack": 2.0,
            "ci95_lower": 1.0,
            "per_arm_regressions_pt": {},
        },
    )
    assert result["passed"] is False
    assert any("macro-F1" in r for r in result["reasons"])


def test_evaluate_acceptance_fails_when_ci_lower_bound_not_positive():
    result = training.evaluate_acceptance(
        intake_report=_passing_intake(),
        incumbent_delta_pt=0.0,
        five_arm_report={
            "macro_f1_delta_vs_full_stack": 6.0,
            "ci95_lower": -0.1,
            "per_arm_regressions_pt": {},
        },
    )
    assert result["passed"] is False
    assert any("CI" in r for r in result["reasons"])


def test_evaluate_acceptance_fails_on_per_arm_regression_over_2pt():
    result = training.evaluate_acceptance(
        intake_report=_passing_intake(),
        incumbent_delta_pt=0.0,
        five_arm_report={
            "macro_f1_delta_vs_full_stack": 6.0,
            "ci95_lower": 1.0,
            "per_arm_regressions_pt": {"playbook": -2.5},
        },
    )
    assert result["passed"] is False
    assert any("regression" in r for r in result["reasons"])


def test_evaluate_acceptance_fails_on_flipped_canary():
    result = training.evaluate_acceptance(
        intake_report=_passing_intake(),
        incumbent_delta_pt=0.0,
        five_arm_report=_passing_five_arm(),
        canary_report={"status": "FLIPPED"},
    )
    assert result["passed"] is False
    assert any("canary" in r for r in result["reasons"])


# ── serve() + rollback(): canary-gated atomic alias re-point ──────────────


def _pending_trained_model(store, tmp_path, *, model_tag="mt-1", dataset_version="dv-1"):
    _released_dataset(store, dataset_version)
    store.trained_model_put(
        model_tag=model_tag,
        role="hunter",
        base_model="fake/base",
        base_digest=None,
        dataset_version=dataset_version,
        seed=1,
        hyperparams={},
        toolchain_versions={},
        acceptance_policy_version="v1",
        provenance={},
    )
    store.trained_model_set_reports(model_tag, gguf_path=str(tmp_path / "m.gguf"), gguf_hash="h1")
    return model_tag


def test_serve_promotes_alias_when_canary_clean(store, tmp_path):
    model_tag = _pending_trained_model(store, tmp_path)
    outcome = training.serve(
        store,
        model_tag,
        operator_actor="operator:alice",
        canary_eval_fn=lambda tag: {"status": "OK"},
    )
    assert outcome["verdict"] == "served"
    assert store.model_alias_get("hunter")["model_tag"] == model_tag
    assert store.trained_model_get(model_tag)["verdict"] == "served"


def test_serve_refuses_promotion_when_canary_flipped(store, tmp_path):
    model_tag = _pending_trained_model(store, tmp_path)
    outcome = training.serve(
        store,
        model_tag,
        operator_actor="operator:alice",
        canary_eval_fn=lambda tag: {"status": "FLIPPED", "flipped": ["probe-1"]},
    )
    assert outcome["verdict"] == "rejected"
    assert store.model_alias_get("hunter") is None  # never promoted
    assert store.trained_model_get(model_tag)["verdict"] == "rejected"


def test_rollback_is_atomic_alias_repoint(store, tmp_path):
    mt1 = _pending_trained_model(store, tmp_path, model_tag="mt-1", dataset_version="dv-1")
    training.serve(
        store, mt1, operator_actor="operator:alice", canary_eval_fn=lambda tag: {"status": "OK"}
    )

    mt2 = _pending_trained_model(store, tmp_path, model_tag="mt-2", dataset_version="dv-2")
    training.serve(
        store, mt2, operator_actor="operator:alice", canary_eval_fn=lambda tag: {"status": "OK"}
    )
    assert store.model_alias_get("hunter")["model_tag"] == mt2

    outcome = training.rollback(
        store, "hunter", operator_actor="operator:alice", reason="post-serve regression"
    )
    assert outcome["rolled_back_to"] == mt1
    assert store.model_alias_get("hunter")["model_tag"] == mt1
