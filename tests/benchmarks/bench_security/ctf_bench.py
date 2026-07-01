"""CTF lane + flag-oracle bench (Gap 9).

A captured flag is unambiguous ground truth — the cleanest possible bench.
"""


def bench_ctf(challenge_dir: str, *, dry_run: bool = False) -> dict:
    """Run a CTF challenge and score on flag capture."""
    if dry_run:
        return {"status": "dry_run", "challenge": challenge_dir, "expects": "flag{...} capture"}
    return {"status": "placeholder", "reason": "CTF challenge target required"}


def flag_oracle(flag_candidate: str, expected_flag: str) -> bool:
    """Oracle: exact flag match = VERIFIED."""
    return flag_candidate.strip() == expected_flag.strip()
