# RBP attack grounding regression — 2026-07-30

## Outcome

The post-tuning strong arm notified on 4/5 previously model-visible attack
cells. This is a fresh live replay using the same verdict-grounding contract
that produced 12/12 correct silences on the expanded benign corpus.

| Expected | Verdict | Reported technique | Notify |
|---|---|---|---:|
| `T1595` | `CONFIRMED` | `T1499.004` | yes |
| `T1083` | `CONFIRMED` | `T1599` | yes |
| `T1557` | `RULED_OUT` | — | no |
| `T1003.003` | `CONFIRMED` | `T1003` | yes |
| `T1552` | `CONFIRMED` | `T1078.001` | yes |

## T1557 audit

The T1557 miss is not evidence that explicit authorization context suppressed
an attack. The model-visible evidence contained only successful EventCode 4624
network-logon counts and representative 4624 rows. It contained no relay,
LLMNR/NBT-NS, Responder, source-process, or other adversary-in-the-middle
discriminator, and no affirmative authorization markers either.

The retained V4 trace had reported T1557 only by inventing an EventCode 4738
that was not present and by incorrectly describing T1557 as OS Credential
Dumping. The new grounded `RULED_OUT` is therefore a correction of an
unsupported old notification. The underlying T1557 SPL
(`stats count by IpAddress, Account | where count > 5`) remains too weak to
establish adversary-in-the-middle activity and is carried into the planned
Windows-aware SPL work.

## Interpretation

- Benign false flags improved from 4/12 before grounding to 0/12 after
  grounding.
- Fresh attack notifications were 4/5. The one non-notify lacked a technique
  discriminator and had previously notified only through hallucinated
  evidence.
- Exact MITRE attribution remains weak on 3/5 notifying cells. This is a
  separate known limitation; the benign-corpus fix does not claim to resolve
  it.
- The retained V4 attack axis in `RBP_BENIGN_CORPUS_20260730.json` is preserved
  for historical comparison. It must not be presented as a post-tuning replay.

## Artifacts

- Attack checkpoint:
  `portal/modules/security/core/results/checkpoints/corpus_replay_bench_v5_grounding_regression.json`
  (`sha256:c1fb932be123daad8381984f4c4dadb364f0686256d8a0a3d1c11358aad03d30`)
- Final benign checkpoint:
  `portal/modules/security/core/results/checkpoints/benign_corpus_closeout.json`
  (`sha256:0d24228dae285169ddb3d6d2fa3506e3593e15087bdd2241782180aa1270c5bc`)
- Pre-grounding benign backup:
  `portal/modules/security/core/results/checkpoints/benign_corpus_closeout_20260730_pre_grounding.json.bak`
  (`sha256:c5b694604b1c919c707733885cb5039e3690e31d30f1440c81b6234eaa785b0f`)
