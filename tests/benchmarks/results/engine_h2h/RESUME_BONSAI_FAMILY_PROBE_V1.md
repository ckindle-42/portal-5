# Bonsai Family Probe V1 — safe resume checkpoint

**State:** Paused at the user's request on 2026-09-24 12:54 UTC. The working branch was
`main` at `07706a6d`, equal to `origin/main` before this local checkpoint.

## Stopped lane

The Qwen3.6 27B Q4 control (`qwen36_27b_q4`, Ollama/plain) quality run was interrupted with
SIGINT after 2h08m47s, while its client was waiting for a streamed HTTP response. The harness
keeps item results in memory and appends the quality receipt only after the entire lane returns;
there is no partial quality receipt, so this lane must be rerun from the beginning. Its valid speed
and preflight receipts remain in `qwen36_27b_q4.jsonl` (`20260923T150212Z` and
`20260924T104323Z`). Do not repeat speed or preflight.

The frozen fixture contains 43 items: 129 requests per thinking mode and 258 requests total.
The harness has no per-item progress receipt, so the interrupted lane's completed request count is
unknown.

## Preserved completed work

All 19 append-only JSONL receipt files are present and parse cleanly: 83 rows total, including valid,
invalid, and review results from completed attempts. They are committed with this checkpoint. The
generated shared prefill fixture is also preserved at
`tests/benchmarks/fixtures/engine_h2h/prefill_2048.txt`.

Quality is complete for Anchor V2 PQ2_0/PTQ1_0 and MTP n1/n2; Qwen3.8 27B; Bonsai v1 GGUF
1.7B/4B/8B/27B; Ternary v1 GGUF 1.7B/4B/8B/27B and Ternary v1 8B MLX; and Qwen3 Q4 controls
1.7B/4B/8B. Preserve the recorded qualification outcomes: Anchor V2 MLX quality is invalid after
the long-context Metal allocation failure; Bonsai v1 27B MLX quality was not completed after the
swap gate failed; Bonsai v1 4B preflight is REVIEW; Ternary v1 8B MLX preflight is REVIEW while its
quality receipt is valid. Do not erase or replace these receipts.

## Machine state at pause

- `./launch.sh down` completed. Docker has zero running containers and Ollama is empty.
- The launchd-managed embedding service remains running. Other services reported stopped by
  `launch.sh down` were not uninstalled.
- Swap: 2,641.75 MB used and 1,454.25 MB free of 4,096 MB.
- No benchmark client or Qwen3.6 27B model process remains.

## Resume steps

1. Start the stack with `./launch.sh up`. Verify the swap start gate and an empty Ollama model list.
2. Run only the missing quality lane:

   ```sh
   HF_HUB_CACHE="$HOME/.cache/hf-bonsai/hub" uv run --no-sync python tests/benchmarks/bench_engine_h2h.py quality --engine ollama --model qwen36_27b_q4 --mode plain --repeats 3
   ```

3. Confirm its appended quality row has a valid resource guard, then stop
   `bonsai-control:qwen36-27b-ctx32k`.
4. Finish the control-relative and per-category comparison, rank the top three by thinking-off score
   × decode TG, and perform the required five-prompt side-by-side quick-chat read. The known top
   three before adding the final 27B control lane are Bonsai v1 1.7B, Bonsai v1 4B, and Ternary v1
   1.7B; recompute after the control result.
5. Record the overall Phase 4 verdict, stop the stack with `./launch.sh down`, and create the final
   summary commit and push to `main` as the user requested. Do not start Phase 5.

The gitignored source task file `coding_task/TASK_BONSAI_FAMILY_PROBE_V1.md` was updated with this
same resume point. This checkpoint commit is local while the phase is incomplete; the requested
push is for the final Phase 4 completion.
