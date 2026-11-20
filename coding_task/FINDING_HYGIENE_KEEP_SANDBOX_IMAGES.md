# FINDING — disk hygiene must keep the images the sandbox runs

Lane: `lane/hygiene-keep-sandbox-images` (2026-11-19). Brief:
`coding_task/BRIEF_HYGIENE_KEEP_SANDBOX_IMAGES.md`.

## Diagnosis (code read, live effect reported by the operator 2026-11-19 ~22:10 CST)

`_disk_hygiene` (scripts/lib/util.sh, merged e022c4025) deleted `portal5-attack:latest`,
`portal5-sandbox-data:latest` and `portal5-pwsh:latest`:

- **Host prune**: every `portal5-*`/`portal-5-*` tag not returned by `docker compose config
  --images` and not referenced by a container was removed. The three sandbox images are built
  and loaded by launch.sh, never declared as compose services, so they matched.
- **DinD prune**: keep set was `portal5-*:tag` greps in docker-compose.yml + `portal5-pwsh` +
  the image env vars *present in the launching shell*. `portal5-attack` survived only when
  `SANDBOX_LAB_IMAGE` happened to be exported; `portal5-binresearch` only when
  `BINRESEARCH_IMAGE` was; the defaults the code/compose actually resolve were never in the
  set.

Effect observed live: `execute_python` → `Unable to find image 'portal5-attack:latest'
locally … pull access denied`; `portal trace -s owui` FAIL "owui tool receipt". The image is
not on any registry (`pull access denied`), so once pruned only a rebuild restores it.

Nothing in `up` restored a missing image: only `rebuild`/`rebuild-mcp` built pwsh +
sandbox-data, and only `up` (which follows a manual prune in the operator's report) runs the
prune.

## Change

- `scripts/lib/util.sh`
  - `_sandbox_images required`: the refs the sandbox/tool MCPs resolve — `SANDBOX_DOCKER_IMAGE`
    (default `portal5-sandbox-data:latest`, the compose default), `SANDBOX_PS_IMAGE` (default
    `portal5-pwsh:latest`), `BINRESEARCH_IMAGE` (default `portal5-binresearch:latest`), plus
    `SANDBOX_LAB_IMAGE` only while `SANDBOX_LAB_EXEC=true` (the sandbox's own `_resolve_image`).
  - `_sandbox_images all`: adds `SANDBOX_BASH_IMAGE`/`SANDBOX_NODE_IMAGE` (upstream bases the
    sandbox may pull) for the DinD keep set.
  - `_sandbox_images built`: `portal5-pwsh`, `portal5-sandbox-data`, `portal5-attack`,
    `portal5-binresearch` — launch.sh can rebuild every one.
  - `_build_portal_image` / `_dind_has_image` / `_load_into_dind`: one definition of each
    recipe and of the save|load step, reused by `launch.sh` and `scripts/lib/lab.sh`.
  - `_ensure_sandbox_images [--rebuild]`: refuses to run with DinD down; rebuilds a missing
    required image from its own recipe and loads it into DinD — a failed build of the two
    default images (pwsh, sandbox-data) stops `up`, a failed opt-in build (attack while
    lab-exec is on, binresearch) warns and continues; `--rebuild` always rebuilds
    pwsh + sandbox-data and reloads them (a rebuilt image must not be shadowed by an older
    DinD copy).
  - `_disk_hygiene`: the keep set is `built ∪ all`, applied to the **host** prune as well as
    DinD.
- `launch.sh`: `up` calls `_ensure_sandbox_images` after the health gate and before
  `_disk_hygiene`; `rebuild`/`rebuild-mcp` replace their inline build/load blocks with
  `_ensure_sandbox_images --rebuild` (same commands, now shared).
- `scripts/lib/lab.sh`: `build-lab-attack` / `build-binresearch` use the shared build/load
  helpers, so the tags hygiene keeps are exactly the tags those commands produce.
- `portal/platform/inference/cli/trace/containers.py`: a `dind sandbox images` hop in the
  `containers` section. It resolves each ref from the live MCP container's own `Config.Env`
  (falling back to the repo `.env`), then checks it in `portal5-dind`; FAIL names every
  missing ref, FAIL when DinD is not running.
- `CHANGELOG.md`: the disk-hygiene entry carries the sandbox keep set and the ensure/hop.

## Unproven here (orchestrator runs it live)

`./launch.sh rebuild && ./launch.sh up`; `docker exec portal5-dind docker images`;
`portal trace -s owui`; `portal trace -s containers`.
