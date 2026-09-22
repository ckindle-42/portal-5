# Qwen-Image-2.1 probe (correct model — supersedes the reverted 2509 probe)

- Portal HEAD: `4543441560ce80f927e230fd4a1027bdcbd8d6a0`
- Baseline tag: `qwen-image-edit` (seated qwen-image-edit)
- 2.1: Qwen/Qwen-Image-2.1 via mflux 0.20.0 mflux-generate-qwen-2.1
- img2img strength for identity/text items: 0.5
- Started: 2026-09-22T12:57:52.206303Z

Qwen-Image-2.1 has no instruction-following edit mode like qwen-image-edit — its arm uses --image as an img2img init at the strength above, with the target description as the prompt, not an editing instruction. gen01/gen02 are base generation only (no baseline arm — qwen-image-edit requires a source image).

## Mechanical rates

- baseline: 6/6 (100.0%)
- 2.1: 8/8 (100.0%)

## Items

| id | category | baseline | 2.1 | baseline_s | 2.1_s | operator score (1-5) |
|---|---|---|---|---|---|---|
| id01 | identity_preservation | `tests/benchmarks/results/qwen21_outputs/baseline/id01.png` | `tests/benchmarks/results/qwen21_outputs/2.1/id01.png` | 736.5 | 69.9 |  |
| id02 | identity_preservation | `tests/benchmarks/results/qwen21_outputs/baseline/id02.png` | `tests/benchmarks/results/qwen21_outputs/2.1/id02.png` | 729.83 | 68.18 |  |
| id03 | identity_preservation | `tests/benchmarks/results/qwen21_outputs/baseline/id03.png` | `tests/benchmarks/results/qwen21_outputs/2.1/id03.png` | 715.4 | 68.21 |  |
| id04 | identity_preservation | `tests/benchmarks/results/qwen21_outputs/baseline/id04.png` | `tests/benchmarks/results/qwen21_outputs/2.1/id04.png` | 728.23 | 68.15 |  |
| tx01 | text_editing | `tests/benchmarks/results/qwen21_outputs/baseline/tx01.png` | `tests/benchmarks/results/qwen21_outputs/2.1/tx01.png` | 728.27 | 68.3 |  |
| tx02 | text_editing | `tests/benchmarks/results/qwen21_outputs/baseline/tx02.png` | `tests/benchmarks/results/qwen21_outputs/2.1/tx02.png` | 728.34 | 68.82 |  |
| gen01 | base_generation | `` | `tests/benchmarks/results/qwen21_outputs/2.1/gen01.png` |  | 121.44 |  |
| gen02 | base_generation | `` | `tests/benchmarks/results/qwen21_outputs/2.1/gen02.png` |  | 121.75 |  |

## Operator gate

Score identity preservation, text editing, and base-generation quality 1-5.
Promotion is not applied by this task.

Operator scores: PENDING

## Caveat found on review — img2img strength 0.5 is not editing

Checked id01, tx01, and id04 directly. At `--image-strength 0.5`, the 2.1 arm
is not applying the requested change at all:

- id01 asked for a red sweater — output kept the original dark sweater.
- tx01 asked for "HELLO" printed on the sweater — no text appears anywhere.
- id04 asked for a side-profile pose — output is still front-facing.

So the "8/8 mechanical" rate and the visually strong identity preservation on
these items are not evidence of good editing — the model is essentially
re-rendering the source with the prompt largely ignored at this strength.
0.5 was carried over from the old edit-model corpus design; Qwen-Image-2.1's
img2img is a different mechanism (denoise-from-init, not instruction
edit) and likely needs a much higher strength (0.75-0.9) before the prompt
actually overrides the source image. gen01/gen02 (pure text-to-image, no
init image) are unaffected by this and look genuinely strong — that's where
this model's real strength is.

Reran all six at `--image-strength 0.8` (files with `_1` suffix in
`tests/benchmarks/results/qwen21_outputs/2.1/`, since mflux auto-suffixes
rather than overwriting). Result: no change. Sweater still not red, no
"HELLO" text appears, id04 is still front-facing rather than a side
profile — identical outcome to strength 0.5, just faster (~30s vs ~68s).

Conclusion: this is not a strength-tuning issue. As tested, Qwen-Image-2.1's
img2img path via `mflux-generate-qwen-2.1` (mflux 0.20.0) does not follow
edit instructions on the six identity/text items in this corpus — it
regenerates a close variant of the source image regardless of what the
prompt asks for. Score the 2.1 arm on `gen01`/`gen02` base generation only;
id01-04/tx01-02 should not be scored as an editing comparison against
`qwen-image-edit` on this evidence.
