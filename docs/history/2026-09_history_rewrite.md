# History rewrite, September 2026

On 2026-09-30 the repository history was rewritten so that the public tree
carries outcome summaries only. Compliance run data, operator document text,
identity terms and operator section ids are not part of the public record.

## What changed

- **First changed commit:** `4f8c8017` (2026-05-03, in the rewritten history).
  Every commit from there on has a new hash: 2,769 of the 3,167 commits on
  `main`. Commits before it keep their hashes.
- **Paths removed:**      894 historical paths (old compliance reports, run outputs,
  logs and test results, wherever they were kept).
- **Text replaced** in kept files and commit messages only where operator
  content genuinely occurred. NERC and NIST product data, the planted
  synthetic corpus, design docs and wiki units keep their text and their
  history.
- **Signatures:** the rewrite tool cannot carry commit signatures through a
  rewrite, so signed commits lost their signature when their content or their
  parents changed.
- **Commit references** in tracked files were translated to the new hashes;
  references that are part of a path name were left as they are.

## Generations

Two earlier generations exist and are superseded: the original history, and an
intermediate rewrite made on 2026-09-29. The commit maps from both to this
generation are held locally.

## Clones

Any clone made before this rewrite should be discarded and re-cloned.
