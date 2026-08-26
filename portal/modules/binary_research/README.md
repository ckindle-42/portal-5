# Binary Research Harness

A model-swappable agent loop for static binary research. Infrastructure (this module,
the RE toolchain MCP, the container) installs once; each research item gets its own
project directory with a static structure.

## Two layers

- **Infrastructure (installed once):** the harness, the RE toolchain MCP (port 8930,
  `portal5-binresearch`), the tools. Available from anywhere.
- **Per-research-item project:** a directory under `BINRESEARCH_PROJECTS_ROOT`
  (default `~/binresearch`) with `artifacts/`, `verifiers/`, `00`–`05` markdown,
  `trace.jsonl`. The whole root is bind-mounted into DinD, so the RE container can
  run tools against any project — including a brand-new one — with no extra wiring.

## One-time setup

```bash
./launch.sh up
./launch.sh build-binresearch     # build the RE image, load into DinD
./launch.sh restart-mcp           # bring up the binresearch MCP on :8930
python -m portal.modules.binary_research.harness preflight   # confirm the toolchain
```

## Starting a research item (the trigger)

The operator entry point is the **skill + slash-command** (see `integrations/`), installed
into OpenCode/Pi. In the agent, invoke `/binresearch` (or just ask to "research this
firmware") and answer the questions it relays. Under the hood the skill drives a
harness-conducted session:

```bash
# The skill runs these; you normally never type them.
brh intake --project router_fw --json                 # → opening question
brh intake --project router_fw --answer "..." --json  # → next question, or READY
# ... repeat until {"state":"ready"} ...
```

At **READY** the harness pauses. Place the binaries and make the oracles real:

```bash
cp firmware.bin ~/binresearch/router_fw/artifacts/
# edit ~/binresearch/router_fw/verifiers/*.sh into real pass/fail checks
```

Then confirm — the skill runs the loop (or run it yourself):

```bash
brh run --project router_fw            # model: Qwen3.8-27B default, or a MoE lane
cat ~/binresearch/router_fw/05_report.md
```

`brh` = `python -m portal.modules.binary_research.harness`. `run` requires a ready project
(initialized + artifacts present); it does not scaffold — that's `intake`'s job.

## Model lanes

| Model | Role |
|-------|------|
| `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` | Analysis loop — thinking, slow, strong (**default**) |
| `portal5/gemma4-26b-heretic:q4_K_M-ctx256k` | Scaffold interview (fastest) + rapid-fire analysis |
| `portal5/hauhaucs-qwen36-35b:q4_K_M-ctx256k` | Rapid-fire analysis |
| `portal5/ornith15-35b:q4_K_M-ctx256k` | Rapid-fire analysis |

`--model` (or `llm.model`) pins the analysis model and skips the prompt. `num_ctx` is
raised to 262144 automatically.

## Tools

`bash target='container'` (default) runs in the RE toolchain (radare2, rizin, binwalk,
unblob, readelf, objdump, nm, strings, yara, ssdeep, LIEF, capstone, pefile). For Mach-O,
`bash target='host'` runs otool/codesign/lipo natively — gated by `allow_host_exec`.
