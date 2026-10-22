# Security dependency report — 2026-10-21

## Result

Done. Repo-owned Homebrew-Python launch paths are remediated, the requested safe Starlette
floor is committed, and host plus Docker dependency declarations were audited read-only. No
running container, live service, launchd job, system package, or external venv was changed.

## Commits

- `5bf659f3 fix(security): isolate launchd jobs from Homebrew Python`
- `b76e6ffd fix(deps): require Starlette 1.3 on standalone services`

Neither commit was pushed.

## Homebrew Python inventory

The current `/opt/homebrew/lib/python3.14/site-packages` audit found **310 advisory records in
29 packages**. This supersedes the 2026-10-20 resume count of 289 records; nothing in the
Homebrew site-packages tree was upgraded or otherwise modified.

| Surface | Current interpreter path | Disposition |
|---|---|---|
| `/Library/LaunchDaemons/com.portal5.powermetrics.plist` | `/usr/local/bin/portal5-powermetrics` -> Homebrew Python 3.14 shebang | Repo plist now invokes `__PORTAL_ROOT__/.venv/bin/python3` plus the repo script. Installer renders the root into the plist and no longer installs an executable with a Homebrew shebang. Host still needs reinstallation. |
| `com.portal5.omlx-watchdog` -> `scripts/omlx-watchdog.sh` | Bare `python3` inherited its Homebrew-first launchd `PATH` | Watchdog and its parser installer now use the repo `.venv` explicitly. |
| Native MCP launch agents -> `scripts/native-mcp-service.sh` | Repo `.venv`, but previously fell back to `command -v python3` | Fails closed when the repo venv is absent; no global fallback remains. |
| `launch.sh start-speech` / `start-transcribe` helpers | Bare or fallback `python3` | Both now require the repo `.venv`; these are repo scripts even though the current launch agents already use `native-mcp-service.sh`. |
| `~/Library/LaunchAgents/com.portal5.orchestrate-usage.plist` | Explicit `/opt/homebrew/bin/python3` | Outside the repo. Move to a dedicated orchestrator venv; reviewer action below. |
| `~/Library/LaunchAgents/com.portal5.orchestrate-digest.plist` | Explicit `/opt/homebrew/bin/python3` | Outside the repo. Move to the same dedicated orchestrator venv; reviewer action below. |

No `/Library/LaunchAgents` or other `/Library/LaunchDaemons` plist referenced Python. The
Ollama daemons are native binaries. Current process inspection also saw the live powermetrics
daemon and usage exporter on Homebrew Python, plus temporary Claude dispatcher/proxy and
pre-commit processes outside the repo-owned launch surfaces. Those active orchestration
processes were not disrupted.

## Requested major versions

| Dependency | Current locked/installed version | Action |
|---|---:|---|
| `cryptography` | 50.0.2 | Already satisfied at HEAD (introduced by `6cee0a22`); no duplicate direct dependency or synthetic commit added. |
| `starlette` | 1.6.0 | Lock already exceeded 1.3. All eight standalone Docker/native installer declarations now require `starlette>=1.3.0` in `b76e6ffd`. |
| `torch` | 2.14.0 | Existing `apple-silicon` floor is already `>=2.14.0` (introduced by `d1dedcf3`); no change needed. |
| `transformers` | 5.17.0 | Existing `rag` floor is already `>=5.16.1` (introduced by `019cd9dc`); no change needed. |
| `Pillow` | 13.0.0 | Already completed before this slice. |
| `docling` | 2.137.0 | Already completed before this slice. |

## Read-only environment audits

Each audit used `uvx pip-audit 2.10.1 --path <site-packages> --format json`; a nonzero exit
means vulnerabilities were found, not that packages were changed.

| Environment / consumers | Python | Result | Scanner gaps |
|---|---|---|---|
| `/Users/chris/projects/portal-5/.venv` — speech, transcribe, VL reranker | 3.13.12 arm64 | 3 records in 2 packages: `accelerate 1.14.0` / `PYSEC-2026-3804` (no fix), and `diskcache 5.6.3` / `PYSEC-2026-2447` reported twice (no fix) | `en-core-web-sm`, editable `portal-5` |
| `/Volumes/data01/ltx-2-mlx/.venv` — video-MLX | 3.11.16 arm64 | `transformers 5.3.0`: `PYSEC-2026-2290` (fix 5.5.0), `PYSEC-2026-3929` (fix 5.10.0), `PYSEC-2026-4174` (no fix) | Three local `ltx-*-mlx 0.15.1` distributions |
| `/opt/homebrew/opt/omlx/libexec` | 3.11.16 arm64 | No known vulnerability in auditable PyPI packages | `dflash-mlx`, `en-core-web-sm`, dev `mlx-lm`, `omlx` |
| `~/.portal5/eg2-venv` | 3.12.12 arm64 | No known vulnerability; no skipped distributions | None |
| Homebrew Python site-packages | 3.14.7 arm64 | 310 records in 29 packages | Two non-PyPI distributions |

Video-MLX should not receive an in-place `pip install`. Update and test the ltx-2-mlx lock so
its own compatibility constraints decide whether `transformers>=5.10.0` is viable; one of its
three advisories has no published fix in any case. The shared Portal venv findings have no
published fixes and remain monitor/accept items.

## Docker declaration audit

The repo declares Python packages inline rather than with an image-specific lock:

- Python sets: `Dockerfile.pipeline`, `Dockerfile.mcp`, `Dockerfile.cad`,
  `Dockerfile.attack`, `Dockerfile.binresearch`, and `deploy/browser-mcp/Dockerfile`.
- No Python requirement set: `Dockerfile.dind`, `Dockerfile.pwsh`, and the documentation-only
  `Dockerfile.mcp.x86`.

Direct `pip-audit -r` scans first failed at the resolver bootstrap point:

```text
subprocess.CalledProcessError: Command '[.../bin/python3.13', '-m', 'ensurepip',
'--upgrade', '--default-pip']' died with <Signals.SIGABRT: 6>.
```

The completed fallback used pinned `pip-audit 2.10.1` in a seeded uv Python 3.12 venv. Each
declaration set was resolved with `uv pip compile --python-version 3.11` for Linux arm64, then
audited with `--no-deps --disable-pip`, so the broken temporary-venv path was not used. CAD was
resolved for `aarch64-manylinux_2_31`, the minimum tag published by its pinned OCP dependency.
The MCP resolution applied the Dockerfile's post-Docling `Pillow>=13.0.0` override.

| Declaration | Exact packages audited | Result |
|---|---:|---|
| `Dockerfile.pipeline` | 32 | No known vulnerabilities |
| `Dockerfile.mcp` | 220 | No known vulnerabilities |
| `Dockerfile.cad` | 117 | No known vulnerabilities |
| `Dockerfile.binresearch` | 49 | No known vulnerabilities |
| `Dockerfile.attack` core (`pwntools`, `ROPGadget`, pandas/openpyxl) | 39 | No known vulnerabilities |
| `deploy/browser-mcp/Dockerfile` | 31 | No known vulnerabilities |

`Dockerfile.attack` has two defective best-effort pip declarations: the cloud-tool group is
unsatisfiable because `kube-bench` is not on PyPI, and the separate `zsteg` install is
unsatisfiable because `zsteg` is a Ruby gem, not a PyPI distribution. Pip resolves the group
before installation, so its `|| echo` path leaves that group absent. GraphQL-Cop requirements
are fetched from an external repository during build and are not declared in this repo, so they
cannot be audited from this source tree. The ranged declarations above are point-in-time current
resolutions, not reproducible image locks.

## Reviewer host actions

1. Merge/cherry-pick `5bf659f3` and `b76e6ffd`, then run `uv sync --all-extras --frozen` in
   `/Users/chris/projects/portal-5`.
2. Reload powermetrics so launchd reads the new `ProgramArguments` rather than kickstarting the
   already-loaded old plist:

   ```bash
   sudo launchctl bootout system/com.portal5.powermetrics
   cd /Users/chris/projects/portal-5
   ./launch.sh install-powermetrics
   ps ax -o pid=,command= | grep '[p]ortal5-powermetrics'
   ```

   The final process command must start with `/Users/chris/projects/portal-5/.venv/bin/python3`,
   not `/opt/homebrew/Cellar/python@3.14/...`.
3. Create a dedicated interpreter for the stdlib-only usage exporter, change both external
   orchestrator plists to it, then bootout/bootstrap those two labels:

   ```bash
   uv venv --python 3.13 /Users/chris/.claude/orchestrate/.venv
   ```

   Set `ProgramArguments[0]` (or the digest shell command's interpreter) to
   `/Users/chris/.claude/orchestrate/.venv/bin/python3`. Do not edit Homebrew site-packages.
4. Let in-flight dispatcher/proxy processes finish. Future orchestration launches should use the
   same dedicated venv if their external launcher can be updated safely.
5. Replace the attack image's invalid `kube-bench` and `zsteg` pip installs with their intended
   upstream binary/gem installation methods, and vendor or pin GraphQL-Cop's requirements.
6. Add exact per-image locks/constraints; current ranged declarations can resolve differently on
   the next build even though today's Linux-arm64 resolutions audited cleanly.

## Verification receipts

Focused interpreter tests: `12 passed`. Focused Starlette/dependency tests: `61 passed`.

Per-commit gate after interpreter migration:

```text
3515 passed, 116 skipped
All checks passed!
1716 files already formatted
Success: no issues found in 653 source files
[complexity] GATE OK
```

Per-commit gate after Starlette floor:

```text
3516 passed, 116 skipped
All checks passed!
1716 files already formatted
Success: no issues found in 653 source files
[complexity] GATE OK
```

Both commits also passed the repository pre-commit hook (gitleaks, Ruff lint/format, and the unit
suite). No live services, containers, launchd jobs, or external venvs were changed.

Docker audit receipts:

```text
docker-pipeline:    dependencies 32  vulnerabilities 0  skipped 0
docker-browser:     dependencies 31  vulnerabilities 0  skipped 0
docker-cad:         dependencies 117 vulnerabilities 0  skipped 0
docker-binresearch: dependencies 49  vulnerabilities 0  skipped 0
docker-attack:      dependencies 39  vulnerabilities 0  skipped 0
docker-mcp:         dependencies 220 vulnerabilities 0  skipped 0
```
