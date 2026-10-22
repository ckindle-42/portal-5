# Security re-review: orchestration arm task-scoped client tools

Reviewed base: `5b1c6d1a3a1cb963197ea2da0ed5ac9db9adda1a` plus the SR-06 fix in this commit.

## Verdict

**MERGE.** SR-01 through SR-06 pass their offline probes. The review did not call the live Pipeline or sandbox service.

## Finding ledger

| ID | Result | Re-probe result |
|---|---|---|
| SR-01 | PASS | The five original host-execution cases now cross a container boundary. The request contains only explicitly readable/writable task-data files; the generated container has no network, no host-root/workspace mount, a fixed minimal environment, dropped capabilities, a read-only root, and UID/GID 65534 for pytest. Model-written tests, `conftest.py`, `sitecustomize.py`, and subprocesses remain arbitrary code, but only inside that boundary. |
| SR-02 | PASS | The sandbox command applies 0.5 CPU, 256 MiB memory, 64 PIDs, bounded tmpfs mounts, bounded output/copy-back, and task file/byte quotas. The timeout probe removes the named container with `docker rm -f`, covering detached descendants. |
| SR-03 | PASS | Discipline validation rejects a bite that combines read and action tools. An action pytest receives only its explicit staged inputs and write allowlist in the disposable sandbox; copy-back is constrained by the same exact write allowlist. It has no host read/process capability. |
| SR-04 | PASS | Raw submit rejects tools outside the discipline allowlist and absolute/out-of-root inputs. Queue insertion requires a policy-validated `TaskPlan`; queue execution and resume re-enter `ArmService.submit` / `resume`, which call `validate_execution_plan`. |
| SR-05 | PASS | Model-writable files live below `task/data`; plan, ledger, receipts, transcripts, and attempt records remain in the parent control-plane tree. The original `plan.json` overwrite probe cannot alter the control copy. |
| SR-06 | PASS | Every confined-tool file open, directory traversal, snapshot read, quota walk, and pytest selector check is descriptor-relative. Each component is opened with `O_NOFOLLOW`; writes bind the parent directory FD before the final `open`. The adversarial test renames the checked parent and replaces it with an outside symlink immediately before the final read/write open; both operations stay on the already-open contained directory and the outside file is unchanged. |

## Probe evidence

The original temporary review probe was rerun for the three cases that do not call the live sandbox endpoint. Two passed unchanged. The absolute-input case rejected the input as required but the old probe expected the superseded message `outside the allowed roots`; HEAD now reports `input path escapes source directory`. The repository regression with the current contract passes.

```text
$ uv run pytest /tmp/test_arm_tools_security_review.py -q --tb=short -k 'action_tools_cannot_overwrite_arm_control_files or raw_submit_rejects_tools_outside_discipline_allowlist or raw_submit_rejects_absolute_host_inputs'
..F
FAILED test_raw_submit_rejects_absolute_host_inputs - expected old message; actual: ValueError: bite work: input path escapes source directory
1 failed, 2 passed, 8 deselected in 0.19s
```

The original pytest exploitation, timeout, hardlink, and symlink cases would call the running sandbox HTTP endpoint, which this brief forbids. Their offline replacements exercise the generated isolation command, timeout cleanup, exact staged-file/copy-back surfaces, and descriptor race directly:

```text
$ uv run pytest -q --tb=short <14 SR-01..06 regression nodes>
collected 14 items
tests/unit/test_orchestration_arm.py .....
tests/unit/test_orchestration_phase2.py .
tests/unit/test_orchestration_bite_suite.py .
tests/unit/test_orchestration_arm.py .......
14 passed in 1.52s
```

Focused orchestration-arm regression after SR-06:

```text
$ uv run pytest tests/unit/test_orchestration_arm.py -q
collected 43 items
43 passed in 14.88s
```

## Required gate

```text
$ uv sync --all-extras
Resolved 317 packages in 185ms
Audited 279 packages in 28ms

$ uv run pytest tests/unit/ -q && uv run ruff check . && uv run ruff format --check . && uv run mypy portal/
3807 passed, 116 skipped, 42 warnings in 198.72s
All checks passed!
1746 files already formatted
Success: no issues found in 657 source files

$ python3 scripts/complexity_report.py --gate
[complexity] GATE OK — totals within the declared ceilings
```

## Residual boundary

This is an offline source-and-unit review. It does not claim a live Docker/DinD integration run; the brief explicitly prohibited touching the live stack. The existing live smoke remains an orchestrator responsibility after merge.

## Post-merge 66ded0a7

SR-01 through SR-06 remain **PASS** after merging main at `66ded0a7`. The production-authenticated fake Pipeline, production bite gate, and production SSE converter are now exercised alongside the task-tool isolation regressions. No live Pipeline or sandbox endpoint was called.

The three non-live cases from the original temporary probe retain the prior result: both policy probes pass, and the absolute-input probe rejects the input but its obsolete message matcher still expects `outside the allowed roots` instead of the current `input path escapes source directory`.

```text
$ uv run pytest /tmp/test_arm_tools_security_review.py -q --tb=short -k 'action_tools_cannot_overwrite_arm_control_files or raw_submit_rejects_tools_outside_discipline_allowlist or raw_submit_rejects_absolute_host_inputs'
..F
FAILED ../../../../tmp/test_arm_tools_security_review.py::test_raw_submit_rejects_absolute_host_inputs
1 failed, 2 passed, 8 deselected in 0.19s
```

The repository replacements for the exploitation, resource-limit, read/action, raw-submit, control-plane, and descriptor-race probes all pass on the merged tree:

```text
$ uv run pytest -q --tb=short <14 SR-01..06 regression nodes>
collected 14 items
tests/unit/test_orchestration_arm.py .....
tests/unit/test_orchestration_phase2.py .
tests/unit/test_orchestration_bite_suite.py .
tests/unit/test_orchestration_arm.py .......
14 passed in 1.77s
```
