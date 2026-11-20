#!/usr/bin/env python3
"""Media variant screen: measured peak memory per row and prompt, dated table + judge sheet.

Rows, pins, commands and prompts come from docs/media/MEDIA_VARIANT_SCREEN_202611.md via
scripts/proofs/media_screen_catalog.yaml. For every selected row and every fixed prompt this
runs the row's generate command as a subprocess and samples once per second: the process
tree's RSS sum (children included), the largest single RSS, the `memory_pressure` system-free
percentage and `vm.swapusage`. It records wall time, exit code and the output path, and
writes a dated markdown table, a judge sheet pairing incumbent vs candidate per prompt, and
rows.jsonl receipts under ${AI_OUTPUT_DIR:-$HOME/AI_Output}/generated/screens/.

Judging stays human or independent-model; this script only measures, pairs and prints.

    uv run python scripts/proofs/media_variant_screen.py --medium image [--only iris-q8] [--dry-run]

Exit codes: 0 run completed (row failures are recorded in the table), 130 interrupted,
2 setup error.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = Path(__file__).resolve().parent / "media_screen_catalog.yaml"
SCREEN_SUBPATH = ("generated", "screens")
MEDIA_ORDER = ("image", "video", "music")
SAMPLE_SECONDS = 1.0
FREE_COLLAPSE_PCT = 1.0
GIB = 1024**3
FREE_RE = re.compile(r"System-wide memory free percentage:\s*(\d+)%")
SWAP_RE = re.compile(r"used = ([0-9.]+)M")
OUTPUT_RE = re.compile(r"^OUTPUT_PATHS: (\[.*\])\s*$", re.MULTILINE)
PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}")


@dataclass
class Sample:
    """One sampler tick: tree RSS bytes, largest RSS bytes, system free %, swap used GB."""

    rss_tree: int = 0
    rss_max: int = 0
    free_pct: float | None = None
    swap_gb: float | None = None


@dataclass
class Peak:
    """Running peak/floor over the samples of one run."""

    rss_tree: int = 0
    rss_max: int = 0
    free_floor: float | None = None
    free_after: float | None = None
    swap_start: float | None = None
    swap_peak: float | None = None
    stop: str | None = None  # "timeout" | "interrupt" when the run was cut short

    def add(self, s: Sample) -> None:
        self.rss_tree = max(self.rss_tree, s.rss_tree)
        self.rss_max = max(self.rss_max, s.rss_max)
        if s.free_pct is not None:
            self.free_floor = (
                s.free_pct if self.free_floor is None else min(self.free_floor, s.free_pct)
            )
            self.free_after = s.free_pct
        if s.swap_gb is not None:
            self.swap_peak = s.swap_gb if self.swap_peak is None else max(self.swap_peak, s.swap_gb)


@dataclass
class Plan:
    """One row-prompt execution: argv, cwd, env additions, expected output, music spec."""

    row: dict
    medium: str
    prompt_index: int
    prompt_text: str
    argv: list[str]
    cwd: Path
    env_add: dict[str, str]
    output: Path | None
    spec: dict | None = None


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    """Load and validate the screen catalog; expand ~ in its path entries."""
    raw = yaml.safe_load(path.read_text())
    _validate_catalog(raw)
    raw["paths"] = {k: str(Path(v).expanduser()) for k, v in raw.get("paths", {}).items()}
    return raw


def _validate_catalog(raw: dict) -> None:
    if not isinstance(raw, dict) or not isinstance(raw.get("media"), dict):
        raise ValueError("catalog must be a mapping with a `media` mapping")
    if set(raw["media"]) != set(MEDIA_ORDER):
        raise ValueError(f"media must be exactly {MEDIA_ORDER}")
    for medium, spec in raw["media"].items():
        _validate_medium(medium, spec)


def _validate_medium(medium: str, spec: dict) -> None:
    if not spec.get("prompts"):
        raise ValueError(f"{medium}: prompts missing")
    rows = spec.get("rows") or []
    ids = [row.get("id") for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{medium}: duplicate row ids")
    if sum(1 for row in rows if row.get("role") == "incumbent") != 1:
        raise ValueError(f"{medium}: exactly one incumbent row required")
    for row in rows:
        _validate_row(medium, row)


def _validate_row(medium: str, row: dict) -> None:
    rid = row.get("id")
    if row.get("role") not in ("incumbent", "candidate"):
        raise ValueError(f"{medium}/{rid}: role must be incumbent or candidate")
    kind = row.get("kind", "cli")
    if kind == "cli":
        text = " ".join(row.get("argv") or [])
        if "{prompt}" not in text or "{output}" not in text:
            raise ValueError(
                f"{medium}/{rid}: argv needs a {{prompt}} and an {{output}} placeholder"
            )
    elif kind == "music":
        if not row.get("dit") or not isinstance(row.get("load_lm"), bool):
            raise ValueError(f"{medium}/{rid}: music rows need a `dit` and a boolean `load_lm`")
        if row.get("load_lm") and not row.get("lm"):
            raise ValueError(f"{medium}/{rid}: load_lm rows need an `lm` checkpoint name")
    elif kind == "heartlib":
        if medium != "music":
            raise ValueError(f"{medium}/{rid}: heartlib rows are music-only")
    else:
        raise ValueError(f"{medium}/{rid}: unknown kind {kind}")


def _order_rows(rows: list[dict]) -> list[dict]:
    def key(row: dict) -> tuple:
        rank = row.get("rank")
        return (
            row.get("role") != "incumbent",
            rank if rank is not None else 99,
            bool(row.get("optional")),
            row["id"],
        )

    return sorted(rows, key=key)


def select_rows(rows: list[dict], only: list[str] | None) -> list[dict]:
    """Default: incumbent + ranked candidates (optional rows excluded). --only picks by id."""
    if not only:
        return _order_rows([row for row in rows if not row.get("optional")])
    wanted = set(only)
    unknown = wanted - {row["id"] for row in rows}
    if unknown:
        raise ValueError(
            f"unknown row id(s) {sorted(unknown)}; valid ids: {sorted(r['id'] for r in rows)}"
        )
    return _order_rows([row for row in rows if row["id"] in wanted])


def tree_rss(ps_text: str, root_pid: int) -> tuple[int, int]:
    """(sum, max) RSS in bytes over root_pid's descendant closure; (0, 0) once root is gone."""
    children: dict[int, list[int]] = {}
    rss: dict[int, int] = {}
    for line in ps_text.splitlines():
        parts = line.split()
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        children.setdefault(int(parts[1]), []).append(int(parts[0]))
        rss[int(parts[0])] = int(parts[2]) * 1024
    if root_pid not in rss:
        return 0, 0
    total = peak = 0
    queue, seen = [root_pid], set()
    while queue:
        pid = queue.pop()
        if pid in seen:
            continue
        seen.add(pid)
        total += rss.get(pid, 0)
        peak = max(peak, rss.get(pid, 0))
        queue.extend(children.get(pid, []))
    return total, peak


def parse_free_pct(memory_pressure_text: str) -> float | None:
    match = FREE_RE.search(memory_pressure_text or "")
    return float(match.group(1)) if match else None


def parse_swap_gb(swapusage_text: str) -> float | None:
    match = SWAP_RE.search(swapusage_text or "")
    return round(float(match.group(1)) / 1024, 3) if match else None


def parse_output_paths(runner_text: str) -> list[str]:
    """Ace runner receipts print `OUTPUT_PATHS: [json]`; take the last one."""
    matches = OUTPUT_RE.findall(runner_text or "")
    if not matches:
        return []
    try:
        paths = json.loads(matches[-1])
    except json.JSONDecodeError:
        return []
    if not isinstance(paths, list):
        return []
    return [path for path in paths if isinstance(path, str) and Path(path).suffix.lower() == ".wav"]


def _free_pct() -> float | None:
    try:
        out = subprocess.run(
            ["memory_pressure"], capture_output=True, text=True, check=False, timeout=15
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_free_pct(out.stdout)


def _swap_used_gb() -> float | None:
    try:
        out = subprocess.run(
            ["sysctl", "-n", "vm.swapusage"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_swap_gb(out.stdout)


def _sample(root_pid: int) -> Sample:
    s = Sample()
    try:
        out = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,rss="],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        s.rss_tree, s.rss_max = tree_rss(out.stdout, root_pid)
    except (OSError, subprocess.TimeoutExpired):
        pass
    s.free_pct = _free_pct()
    s.swap_gb = _swap_used_gb()
    return s


def _snapshot_top(limit: int = 8) -> list[str]:
    """What `ps` shows resident before the run — the doc asks for this next to each row."""
    out = subprocess.run(
        ["ps", "-axo", "rss=,pid=,comm="], capture_output=True, text=True, check=False, timeout=10
    )
    rows = []
    for line in out.stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit():
            rows.append((int(parts[0]), parts[1], parts[2].rsplit("/", 1)[-1]))
    rows.sort(reverse=True)
    return [f"{name} pid={pid} {kb / GIB:.2f} GB" for kb, pid, name in rows[:limit]]


def _host_line() -> str:
    out = subprocess.run(
        ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=False, timeout=10
    )
    try:
        gib = int(out.stdout.strip()) / GIB
    except ValueError:
        gib = 0.0
    return f"{platform.machine()} / macOS {platform.mac_ver()[0]} / {gib:.0f} GB unified memory"


def _substitute(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def _plan_prompt(
    catalog: dict, medium: str, row: dict, index: int, run_dir: Path, out_dir: Path
) -> Plan:
    """Pure plan for one row-prompt; music specs are materialised later by _materialize_plan."""
    spec_media = catalog["media"][medium]
    entry = spec_media["prompts"][index - 1]
    if row.get("kind") == "heartlib":
        spec_dir = run_dir / "heartlib_run" / f"{row['id']}-p{index}"
        gen = spec_media["gen"]
        output = out_dir / f"{row['id']}-p{index}.wav"
        src = Path(catalog["paths"]["heartlib_src"])
        spec = {
            "src": str(src),
            "checkpoint": str(Path(catalog["paths"]["heartlib_root"]) / "ckpt-mlx"),
            "caption": entry["caption"],
            "lyrics": entry.get("lyrics", ""),
            "duration": gen["duration"],
            "seed": gen["seed"],
            "output": str(output),
            "save_dir": str(spec_dir),
        }
        argv = [
            str(src / ".venv" / "bin" / "python"),
            str(run_dir / "heartlib_run" / "runner.py"),
            "--spec",
            str(spec_dir / "spec.json"),
        ]
        return Plan(
            row, medium, index, entry["caption"], argv, src, _row_env(catalog, row), output, spec
        )
    if row.get("kind") == "music":
        spec_dir = run_dir / "ace_run" / f"{row['id']}-p{index}"
        gen = spec_media["gen"]
        spec = {
            "root": catalog["paths"]["ace_root"],
            "dit": row["dit"],
            "lm": row.get("lm"),
            "load_lm": row["load_lm"],
            "caption": entry["caption"],
            "lyrics": entry.get("lyrics", ""),
            "instrumental": entry["instrumental"],
            "duration": gen["duration"],
            "steps": gen["steps"],
            "seed": gen["seed"],
            "shift": gen["shift"],
            "save_dir": str(spec_dir),
        }
        argv = [
            "uv",
            "run",
            "--no-sync",
            "python",
            str(_music_runner(run_dir)),
            "--spec",
            str(spec_dir / "spec.json"),
        ]
        return Plan(
            row,
            medium,
            index,
            entry["caption"],
            argv,
            Path(catalog["paths"]["ace_root"]),
            _row_env(catalog, row),
            None,
            spec,
        )
    output = out_dir / f"{row['id']}-p{index}.{row.get('ext', 'out')}"
    values = {**catalog["paths"], "prompt": str(entry), "output": str(output)}
    argv = [_substitute(str(part), values) for part in row["argv"]]
    cwd = Path(_substitute(row["cwd"], values)) if row.get("cwd") else REPO
    leftover = [part for part in argv if PLACEHOLDER_RE.search(part)]
    if leftover:
        raise ValueError(f"{row['id']} p{index}: unsubstituted placeholder(s) in {leftover}")
    return Plan(row, medium, index, str(entry), argv, cwd, _row_env(catalog, row), output)


def _row_env(catalog: dict, row: dict) -> dict[str, str]:
    if row.get("role") != "candidate":
        return {}
    return {"HF_HUB_CACHE": catalog["paths"]["hf_cache"]}


def _materialize_plan(plan: Plan) -> None:
    """Create the row's output parent; music rows also get the runner and spec written."""
    if plan.output is not None:
        plan.output.parent.mkdir(parents=True, exist_ok=True)
    if plan.spec is None:
        return
    spec_dir = Path(plan.spec["save_dir"])
    spec_dir.mkdir(parents=True, exist_ok=True)
    heartlib = plan.row.get("kind") == "heartlib"
    sub = "heartlib_run" if heartlib else "ace_run"
    runner = spec_dir.parent.parent / sub / "runner.py"
    if not runner.exists():
        runner.write_text(_heartlib_runner_text() if heartlib else _music_runner_text())
    (spec_dir / "spec.json").write_text(json.dumps(plan.spec, indent=2))


def _music_runner(run_dir: Path) -> Path:
    return run_dir / "ace_run" / "runner.py"


def _heartlib_runner_text() -> str:
    # Seeds MLX, then delegates to the port's own generate.py so the arm stays upstream code.
    return """#!/usr/bin/env python3
# Generated by scripts/proofs/media_variant_screen.py — one HeartMuLa prompt from --spec.
import argparse, json, runpy, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--spec", required=True)
spec = json.loads(Path(ap.parse_args().spec).read_text())
import mlx.core as mx  # noqa: E402
mx.random.seed(spec["seed"])
generate = Path(spec["src"]) / "generate.py"
argv = [str(generate), "--tags", spec["caption"], "--duration", str(spec["duration"]),
        "--checkpoint", spec["checkpoint"], "--dtype", "bfloat16", "--output", spec["output"]]
if spec["lyrics"]:
    argv += ["--lyrics", spec["lyrics"]]
sys.argv = argv
runpy.run_path(str(generate), run_name="__main__")
print("OUTPUT_PATHS: " + json.dumps([spec["output"]]))
"""


def _music_runner_text() -> str:
    return """#!/usr/bin/env python3
# Generated by scripts/proofs/media_variant_screen.py — one ACE-Step prompt from --spec.
import argparse, json, os, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--spec", required=True)
spec = json.loads(Path(ap.parse_args().spec).read_text())
root = Path(spec["root"]).expanduser()
os.environ.setdefault("MUSIC_ACE_ROOT", str(root))
sys.path.insert(0, str(root))
from acestep.handler import AceStepHandler  # noqa: E402
from acestep.inference import GenerationConfig, GenerationParams, generate_music  # noqa: E402
from acestep.llm_inference import LLMHandler  # noqa: E402

save_dir = Path(spec["save_dir"])
save_dir.mkdir(parents=True, exist_ok=True)
dit = AceStepHandler()
status, ok = dit.initialize_service(
    project_root=str(root), config_path=spec["dit"], device="auto", use_mlx_dit=True, offload_to_cpu=True,
)
if not ok:
    raise SystemExit(f"init failed: {status}")
lm = LLMHandler()
if spec["load_lm"]:
    lm.initialize(checkpoint_dir=str(root / "checkpoints"), lm_model_path=spec["lm"], backend="mlx", device="auto")
params = GenerationParams(
    task_type="text2music", caption=spec["caption"], lyrics=spec["lyrics"], duration=spec["duration"],
    inference_steps=spec["steps"], seed=spec["seed"], shift=spec["shift"], instrumental=spec["instrumental"],
)
config = GenerationConfig(batch_size=1, use_random_seed=False, seeds=[spec["seed"]], audio_format="wav")
result = generate_music(dit, lm, params, config, save_dir=str(save_dir))

def audio_paths(value):
    if isinstance(value, (str, os.PathLike)):
        path = os.fspath(value)
        return [path] if Path(path).suffix.lower() == ".wav" else []
    if isinstance(value, dict):
        path = value.get("path")
        if isinstance(path, (str, os.PathLike)):
            return audio_paths(path)
        return [path for item in value.values() for path in audio_paths(item)]
    if isinstance(value, (list, tuple)):
        return [path for item in value for path in audio_paths(item)]
    path = getattr(value, "path", None)
    return audio_paths(path) if isinstance(path, (str, os.PathLike)) else []

audios = getattr(result, "audios", None)
print("OUTPUT_PATHS: " + json.dumps(audio_paths(audios if audios is not None else result)))
"""


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), 15)
        proc.wait(timeout=10)
    except (ProcessLookupError, PermissionError, subprocess.TimeoutExpired):
        try:
            os.killpg(os.getpgid(proc.pid), 9)
        except (ProcessLookupError, PermissionError):
            pass


def _run_plan(plan: Plan, log_path: Path, timeout_s: int) -> tuple[dict, bool]:
    """Run one row-prompt under the 1 s sampler; returns (receipt, interrupted)."""
    peak = Peak()
    peak.swap_start = _swap_used_gb()
    env = {**os.environ, **plan.env_add}
    started = time.monotonic()
    interrupted = False
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as log:
        log.write(f"# {plan.row['id']} p{plan.prompt_index} ({plan.medium})\n")
        log.write(f"command: {shlex.join(plan.argv)}\ncwd: {plan.cwd}\nenv+: {plan.env_add}\n\n")
        log.flush()
        try:
            proc = subprocess.Popen(
                plan.argv,
                cwd=str(plan.cwd),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            log.write(f"launch failed: {exc}\n")
            receipt = _finish_receipt(plan, peak, log_path, started, None)
            receipt["status"] = "launch-failed"
            receipt["error"] = str(exc)
            return receipt, False
        try:
            while proc.poll() is None:
                peak.add(_sample(proc.pid))
                if timeout_s and time.monotonic() - started > timeout_s:
                    peak.stop = "timeout"
                    _kill_tree(proc)
                    break
                time.sleep(SAMPLE_SECONDS)
            peak.add(_sample(proc.pid))
        except KeyboardInterrupt:
            peak.stop = "interrupt"
            interrupted = True
            _kill_tree(proc)
    return _finish_receipt(plan, peak, log_path, started, proc.returncode), interrupted


def _finish_receipt(
    plan: Plan, peak: Peak, log_path: Path, started: float, exit_code: int | None
) -> dict:
    log_text = log_path.read_text(errors="replace") if log_path.exists() else ""
    outputs = _collect_outputs(plan, log_text)
    receipt = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "medium": plan.medium,
        "row": plan.row["id"],
        "role": plan.row.get("role"),
        "rank": plan.row.get("rank"),
        "prompt_index": plan.prompt_index,
        "prompt": plan.prompt_text,
        "command": plan.argv,
        "cwd": str(plan.cwd),
        "env_added": plan.env_add,
        "wall_s": round(time.monotonic() - started, 1),
        "peak_rss_tree_gb": round(peak.rss_tree / GIB, 3),
        "peak_rss_max_gb": round(peak.rss_max / GIB, 3),
        "free_floor_pct": peak.free_floor,
        "free_after_pct": peak.free_after,
        "swap_start_gb": peak.swap_start,
        "swap_peak_gb": peak.swap_peak,
        "swap_delta_gb": None
        if (peak.swap_start is None or peak.swap_peak is None)
        else round(peak.swap_peak - peak.swap_start, 3),
        "exit_code": exit_code,
        "status": _status(exit_code, outputs, peak.stop),
        "outputs": [str(o) for o in outputs],
        "log": str(log_path),
        "note": plan.row.get("note"),
        "expected_peak_gb": plan.row.get("expected_peak_gb"),
        "expected_note": plan.row.get("expected_note"),
        "stop_reason": None,
    }
    if peak.free_floor is not None and peak.free_floor <= FREE_COLLAPSE_PCT:
        receipt["free_collapse"] = True
    if plan.medium == "video" and outputs:
        streams = _probe_streams(outputs[0])
        receipt["has_video"], receipt["has_audio"] = streams or (None, None)
    return receipt


def _collect_outputs(plan: Plan, log_text: str) -> list[Path]:
    if plan.output is not None:
        return [plan.output] if plan.output.exists() else []
    return [Path(p) for p in parse_output_paths(log_text) if Path(p).exists()]


def _status(exit_code: int | None, outputs: list[Path], stop: str | None) -> str:
    if stop:
        return stop
    if exit_code is None:
        return "no-exit"
    if exit_code < 0:
        return f"killed-sig{-exit_code}"
    if exit_code != 0:
        return f"exit{exit_code}"
    return "ok" if outputs else "no-output"


def _probe_streams(path: Path) -> tuple[int, int] | None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    kinds = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    return kinds.count("video"), kinds.count("audio")


def _append_jsonl(path: Path, record: dict) -> None:
    with path.open("a") as stream:
        stream.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def _screens_root(override: Path | None = None) -> Path:
    if override is not None:
        return override
    base = Path(os.environ.get("AI_OUTPUT_DIR") or Path.home() / "AI_Output")
    return base.joinpath(*SCREEN_SUBPATH)


def _run_row(
    catalog: dict, medium: str, row: dict, run_dir: Path, out_dir: Path, timeout_s: int
) -> list[dict]:
    prompts = len(catalog["media"][medium]["prompts"])
    receipts = []
    for index in range(1, prompts + 1):
        plan = _plan_prompt(catalog, medium, row, index, run_dir, out_dir)
        _materialize_plan(plan)
        receipt, interrupted = _run_plan(
            plan, run_dir / "logs" / f"{row['id']}-p{index}.log", timeout_s
        )
        if receipt["status"] == "launch-failed":
            receipt["stop_reason"] = (
                f"launch failed ({receipt.get('error')}); remaining prompts skipped"
            )
        limit = row.get("abort_rss_gb")
        if limit and receipt["peak_rss_tree_gb"] > limit:
            receipt["stop_reason"] = (
                f"peak {receipt['peak_rss_tree_gb']:.2f} GB exceeds the {limit} GB stop; remaining prompts skipped"
            )
        _append_jsonl(run_dir / "rows.jsonl", receipt)
        receipts.append(receipt)
        print(
            f"  [{row['id']} p{index}] {receipt['status']} wall={receipt['wall_s']}s "
            f"peak={_num(receipt['peak_rss_tree_gb'])} GB floor={_num(receipt['free_floor_pct'], 0)}%",
            flush=True,
        )
        if interrupted:
            raise KeyboardInterrupt
        if receipt["stop_reason"]:
            break
    return receipts


def _print_dry_run(
    catalog: dict, medium: str, rows: list[dict], run_dir: Path, out_dir: Path
) -> None:
    print(f"DRY RUN — medium {medium}: nothing runs, nothing writes")
    print(f"run dir would be: {run_dir}")
    prompts = catalog["media"][medium]["prompts"]
    for row in rows:
        for index in range(1, len(prompts) + 1):
            plan = _plan_prompt(catalog, medium, row, index, run_dir, out_dir)
            print(f"\n[{row['id']} p{index}] role={row.get('role')} rank={row.get('rank', '-')}")
            print(f"  cwd: {plan.cwd}")
            print(f"  env+: {plan.env_add or '(none)'}")
            print(f"  output: {plan.output or '(runner-declared, via OUTPUT_PATHS in the log)'}")
            print(f"  command: {shlex.join(plan.argv)}")
            if plan.spec is not None:
                print(f"  spec: {json.dumps(plan.spec, sort_keys=True)}")


def _rel(path: str, run_dir: Path) -> str:
    try:
        return str(Path(path).relative_to(run_dir))
    except ValueError:
        return path


def _num(value: Any, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _render_table(
    catalog: dict, medium: str, results: list[dict], run_dir: Path, snapshot: list[str]
) -> str:
    spec = catalog["media"][medium]
    lines = [
        f"# Media variant screen — {medium} — {datetime.now(UTC):%Y-%m-%d}",
        "",
        f"run: {run_dir}",
        f"host: {_host_line()}",
        f"resident before run (top RSS): {'; '.join(snapshot) if snapshot else '(ps unavailable)'}",
        f"canvas: {spec['canvas']}",
        "",
        "peak RSS GB = process-tree RSS sum incl. children, sampled 1 s; rss max = largest single process;",
        "free floor % = lowest `memory_pressure` system-wide free percentage during the run;",
        "swap Δ GB = peak swap used minus swap used at row start.",
        "",
        "| row | role | rank | p | wall s | peak RSS GB | rss max GB | free floor % | swap Δ GB | exit | status | output |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        outputs = "; ".join(_rel(o, run_dir) for o in r["outputs"]) or "(missing)"
        status = r["status"] + ("+free-collapse" if r.get("free_collapse") else "")
        lines.append(
            f"| {r['row']} | {r['role']} | {r['rank'] if r['rank'] is not None else '-'} | {r['prompt_index']} "
            f"| {_num(r['wall_s'], 1)} | {_num(r['peak_rss_tree_gb'])} | {_num(r['peak_rss_max_gb'])} "
            f"| {_num(r['free_floor_pct'], 0)} | {_num(r['swap_delta_gb'])} | {r['exit_code']} | {status} | {outputs} |"
        )
    lines += ["", "## Row notes", ""]
    seen: set[str] = set()
    for r in results:
        if r["row"] in seen:
            continue
        seen.add(r["row"])
        expected = (
            f"expected (doc): {r['expected_peak_gb']} GB — {r['expected_note']}"
            if r.get("expected_note")
            else ""
        )
        lines.append(f"- **{r['row']}**: {r.get('note') or ''} {expected}".rstrip())
        if r.get("stop_reason"):
            lines.append(f"  - stop: {r['stop_reason']}")
    return "\n".join(lines) + "\n"


def _render_judge(catalog: dict, medium: str, results: list[dict], run_dir: Path) -> str:
    spec = catalog["media"][medium]
    by_row: dict[str, dict[int, dict]] = {}
    for r in results:
        by_row.setdefault(r["row"], {})[r["prompt_index"]] = r
    incumbent_id = next(
        (rid for rid, runs in by_row.items() if runs and runs[min(runs)]["role"] == "incumbent"),
        None,
    )
    lines = [
        f"# Judge sheet — {medium} — {datetime.now(UTC):%Y-%m-%d}",
        "",
        f"run: {run_dir}",
        f"canvas: {spec['canvas']}",
        "",
        f"criteria: {spec['criteria']}",
        "",
    ]
    if incumbent_id is None:
        lines.append(
            "NOTE: no incumbent receipt in this run — pair against a run that included the incumbent row."
        )
    for rid, runs in by_row.items():
        first = runs[min(runs)]
        if first["role"] != "candidate":
            continue
        lines.append(
            f"## {rid} (rank {first['rank'] if first['rank'] is not None else '-'}) vs {incumbent_id or '(no incumbent run)'}"
        )
        if first.get("expected_note"):
            lines.append(
                f"expected from the doc: {first.get('expected_peak_gb', '-')} — {first['expected_note']}"
            )
        lines.append("")
        for index in sorted(runs):
            cand, inc = runs[index], (by_row.get(incumbent_id) or {}).get(index)
            lines.append(
                f"- p{index}: candidate → {'; '.join(_rel(o, run_dir) for o in cand['outputs']) or '(missing)'}"
                f" | incumbent → {'; '.join(_rel(o, run_dir) for o in inc['outputs']) if inc else '-'}"
            )
            lines.append(
                f"  measured: wall {_num(cand['wall_s'], 1)}s vs {_num(inc['wall_s'], 1) if inc else '-'}s"
                f"; peak RSS {_num(cand['peak_rss_tree_gb'])} vs {_num(inc['peak_rss_tree_gb']) if inc else '-'} GB"
                f"; free floor {_num(cand['free_floor_pct'], 0)} vs {_num(inc['free_floor_pct'], 0) if inc else '-'}%"
            )
            if cand.get("has_video") is not None or (inc or {}).get("has_video") is not None:
                lines.append(
                    f"  streams: candidate v={cand.get('has_video')} a={cand.get('has_audio')}"
                    f" | incumbent v={inc.get('has_video') if inc else '-'} a={inc.get('has_audio') if inc else '-'}"
                )
        lines.append("")
    lines.append(
        "Score the pair blind to which checkpoint made which file; a candidate passes only if it is not worse."
    )
    return "\n".join(lines) + "\n"


def _screen_medium(
    args: argparse.Namespace, catalog: dict, medium: str, rows: list[dict], out_root: Path
) -> None:
    run_dir = out_root / f"{medium}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    out_dir = run_dir / medium
    if args.dry_run:
        _print_dry_run(catalog, medium, rows, run_dir, out_dir)
        return
    run_dir.mkdir(parents=True, exist_ok=True)
    snapshot = _snapshot_top()
    _append_jsonl(
        run_dir / "rows.jsonl",
        {
            "kind": "run",
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "medium": medium,
            "host": _host_line(),
            "resident_before": snapshot,
        },
    )
    results: list[dict] = []
    for row in rows:
        results.extend(_run_row(catalog, medium, row, run_dir, out_dir, args.timeout_sec))
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    table_path = run_dir / f"screen_{medium}_{date}.md"
    table_path.write_text(_render_table(catalog, medium, results, run_dir, snapshot))
    (run_dir / f"judge_sheet_{medium}_{date}.md").write_text(
        _render_judge(catalog, medium, results, run_dir)
    )
    if args.listen and medium == "music":
        _listen_step(run_dir, args.listen)
    print(table_path.read_text(), flush=True)
    print(
        f"table: {table_path}\njudge sheet: {run_dir / f'judge_sheet_{medium}_{date}.md'}\nreceipts: {run_dir / 'rows.jsonl'}"
    )


def _listen_step(run_dir: Path, listener: str) -> None:
    """Run the blind A/B listener as the music judge step, in its own process."""
    script = Path(__file__).with_name("media_screen_listen.py")
    proc = subprocess.run(
        [sys.executable, str(script), "--run-dir", str(run_dir), "--listener", listener],
        check=False,
    )
    print(f"listener step: {script.name} --run-dir {run_dir} (exit {proc.returncode})", flush=True)


def _screen(args: argparse.Namespace) -> int:
    catalog = load_catalog()
    media = [args.medium] if args.medium else list(MEDIA_ORDER)
    if not args.dry_run and args.medium is None:
        raise ValueError("--medium is required for a real run (image|video|music)")
    out_root = _screens_root(args.out_root)
    for medium in media:
        rows = select_rows(catalog["media"][medium]["rows"], args.only)
        if not rows:
            raise ValueError(f"{medium}: selection is empty")
        _screen_medium(args, catalog, medium, rows, out_root)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--medium", choices=MEDIA_ORDER, help="run one medium (required unless --dry-run)"
    )
    parser.add_argument(
        "--only", nargs="+", default=[], help="row ids from media_screen_catalog.yaml"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print commands and paths; run nothing"
    )
    parser.add_argument("--out-root", type=Path, default=None, help="override the screens root")
    parser.add_argument(
        "--timeout-sec", type=int, default=0, help="kill a row after this many seconds; 0 = no cap"
    )
    parser.add_argument(
        "--listen",
        metavar="MODEL",
        default="",
        help="after a music run, judge every pair with this audio model (scripts/proofs/media_screen_listen.py)",
    )
    args = parser.parse_args()
    try:
        return _screen(args)
    except ValueError as exc:
        print(f"media_variant_screen: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted — receipts for finished prompts are in rows.jsonl", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
