#!/usr/bin/env python3
"""Install Splunk BOTS v1/v2/v3 pre-indexed datasets into the lab Splunk instance.

BOTS ships as pre-indexed Splunk buckets, so it does NOT go through HEC like the
corpora in ``scripts/corpus_ingest.py``. Each tarball untars into
``$SPLUNK_HOME/etc/apps`` and serves its own ``botsvN`` index, queried directly::

    index=botsv3 earliest=0

Run this ON the Splunk host (for Portal 5 that is the ``splunk`` Docker container
inside LXC 301), where ``$SPLUNK_HOME`` and network egress both exist::

    docker exec splunk /opt/splunk/bin/python3 /tmp/lab_bots_install.py --only botsv3

Idempotent: a version whose app dir is already present is skipped. Additive only —
never deletes an existing app. Downloaded archives are removed after a successful
extract (pass --keep-archives to retain them); nothing else is touched.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys

SPLUNK_HOME = os.environ.get("SPLUNK_HOME", "/opt/splunk")

# URLs + md5s verified live against the splunk/botsvN READMEs. botsv1 publishes no
# md5, so its entry carries None and is integrity-checked by size/extract success.
# READMEs: https://github.com/splunk/botsv{1,2,3}
DATASETS: dict[str, tuple[str, str | None]] = {
    "botsv1": (
        "https://s3.amazonaws.com/botsdataset/botsv1/splunk-pre-indexed/botsv1_data_set.tgz",
        None,
    ),
    "botsv2": (
        "https://s3.amazonaws.com/botsdataset/botsv2/botsv2_data_set.tgz",
        "fd2673726c96e97a39fc03119d6686c6",
    ),
    "botsv3": (
        "https://botsdataset.s3.amazonaws.com/botsv3/botsv3_data_set.tgz",
        "d7ccca99a01cff070dff3c139cdc10eb",
    ),
}

APPS_DIR = os.path.join(SPLUNK_HOME, "etc", "apps")


def md5sum(path: str) -> str:
    h = hashlib.md5()  # noqa: S324 - integrity check against a published hash, not security
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def already_installed(index: str) -> bool:
    return os.path.isdir(APPS_DIR) and any(index in d for d in os.listdir(APPS_DIR))


def remote_size(url: str) -> int:
    """Content-Length via curl. Splunk's bundled python3.9 has no ssl module, so
    curl is the only HTTPS client guaranteed present on the Splunk host."""
    out = subprocess.run(["curl", "-sIL", url], check=False, capture_output=True, text=True).stdout
    sizes = [
        line.split(":", 1)[1].strip()
        for line in out.splitlines()
        if line.lower().startswith("content-length:")
    ]
    return int(sizes[-1]) if sizes else 0  # last hop wins (S3 redirects)


def download(url: str, dest: str) -> bool:
    """curl -C - so a multi-GB pull resumes instead of restarting on a blip."""
    want = remote_size(url)
    if os.path.exists(dest) and want and os.path.getsize(dest) == want:
        print(f"[cached] {dest} ({want / 1e9:.2f} GB)")
        return True
    print(f"[dl] {url} -> {dest} ({want / 1e9:.2f} GB)")
    for attempt in range(1, 4):
        rc = subprocess.run(
            ["curl", "-fL", "--retry", "5", "--retry-delay", "5", "-C", "-", "-o", dest, url],
            check=False,
        ).returncode
        if rc == 0 and (not want or os.path.getsize(dest) == want):
            return True
        print(f"[retry {attempt}/3] curl rc={rc}")
    return False


def free_bytes(path: str) -> int:
    return shutil.disk_usage(path).free


def install(index: str, url: str, want_md5: str | None, workdir: str, keep: bool) -> bool:
    if already_installed(index):
        print(f"[skip] {index}: app dir already present under {APPS_DIR}")
        pin_retention(index)  # so a re-run repairs retention on an older install
        return True
    tgz = os.path.join(workdir, f"{index}_data_set.tgz")
    need = remote_size(url) * 2  # archive + extracted copy
    if free_bytes(workdir) < need:
        print(
            f"[FAIL] {index}: need ~{need / 1e9:.1f} GB free, have {free_bytes(workdir) / 1e9:.1f} GB"
        )
        return False
    if not download(url, tgz):
        print(f"[FAIL] {index}: download failed")
        return False
    if want_md5:
        got = md5sum(tgz)
        if got != want_md5:
            print(f"[FAIL] {index}: md5 {got} != {want_md5}")
            return False
        print(f"[ok] {index}: md5 verified")
    print(f"[extract] {index} -> {APPS_DIR}")
    rc = subprocess.run(["tar", "-xzf", tgz, "-C", APPS_DIR], check=False).returncode
    if rc != 0:
        print(f"[FAIL] {index}: tar rc={rc}")
        return False
    if not keep:
        os.remove(tgz)
    pin_retention(index)
    print(f"[installed] {index}")
    return True


def pin_retention(index: str) -> None:
    """Stop Splunk aging the corpus out from under us.

    Each dataset ships ``frozenTimePeriodInSecs = 377395200`` (~12y) in its
    ``default/indexes.conf``, measured from the event timestamps — which for BOTS
    v1 are from 2016. Left alone the buckets silently freeze (and are deleted,
    since no coldToFrozenDir is set) years after install. A ``local/`` override
    raises the ceiling without editing the shipped default.
    """
    app = next((d for d in os.listdir(APPS_DIR) if index in d), None)
    if not app:
        return
    local = os.path.join(APPS_DIR, app, "local")
    os.makedirs(local, exist_ok=True)
    conf = os.path.join(local, "indexes.conf")
    if os.path.exists(conf):
        return
    with open(conf, "w") as f:
        f.write(f"[{index}]\n# 100y — corpus is historical by nature; never age it out.\n")
        f.write("frozenTimePeriodInSecs = 3155760000\n")
    print(f"[retention] {index}: pinned via {conf}")


def restart_splunk() -> None:
    cmd = [os.path.join(SPLUNK_HOME, "bin", "splunk"), "restart"]
    pw = os.environ.get("SPLUNK_PASSWORD")
    if pw:
        cmd += ["-auth", f"{os.environ.get('SPLUNK_USERNAME', 'admin')}:{pw}"]
    print("[restart] splunkd — indexes come online after this")
    subprocess.run(cmd, check=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", choices=sorted(DATASETS), help="repeatable")
    ap.add_argument("--workdir", default="/tmp")
    ap.add_argument("--keep-archives", action="store_true")
    ap.add_argument("--no-restart", action="store_true")
    a = ap.parse_args()

    if not os.path.isdir(APPS_DIR):
        print(f"[FAIL] {APPS_DIR} not found — run this on the Splunk host, or set SPLUNK_HOME")
        return 2

    targets = {k: v for k, v in DATASETS.items() if not a.only or k in a.only}
    results = {i: install(i, u, m, a.workdir, a.keep_archives) for i, (u, m) in targets.items()}
    if not a.no_restart and any(results.values()):
        restart_splunk()
    for index, ok in sorted(results.items()):
        print(f"{'OK  ' if ok else 'FAIL'} {index}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
