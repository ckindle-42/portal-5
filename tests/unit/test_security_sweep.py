import json
import subprocess
from pathlib import Path

from scripts import security_sweep as s
from scripts.security_sweep import (
    PackageRef,
    _docker_findings,
    _lock_packages,
    alert_required,
    default_output_dir,
    query_batches,
    severity_from_score,
)


def test_query_batches_deduplicate_versions_and_use_ecosystem_names():
    packages = [
        PackageRef("Soupsieve", "2.9.2", "PyPI", ("uv.lock",)),
        PackageRef("soupsieve", "2.9.2", "PyPI", ("portal/.venv",)),
        PackageRef("undici", "6.21.0", "npm", ("npx-cache",)),
    ]

    assert query_batches(packages, batch_size=2) == [
        [
            {"package": {"name": "Soupsieve", "ecosystem": "PyPI"}, "version": "2.9.2"},
            {"package": {"name": "undici", "ecosystem": "npm"}, "version": "6.21.0"},
        ]
    ]


def test_score_to_severity_uses_cvss_thresholds():
    assert severity_from_score("9.8") == "CRITICAL"
    assert severity_from_score("8.1") == "HIGH"
    assert severity_from_score("5.4") == "MODERATE"
    assert severity_from_score("not-a-score") == "UNKNOWN"


def test_alert_includes_malware_and_critical_but_not_high():
    assert alert_required([{"id": "MAL-2026-42", "severity": "LOW"}])
    assert alert_required([{"id": "CVE-2026-1", "severity": "CRITICAL"}])
    assert not alert_required([{"id": "CVE-2026-2", "severity": "HIGH"}])


def test_lock_inventory_preserves_python_fork_markers(tmp_path):
    lock = tmp_path / "uv.lock"
    lock.write_text(
        '[[package]]\nname = "soupsieve"\nversion = "2.10"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        "resolution-markers = [\"python_full_version < '3.11.5'\"]\n\n"
    )

    assert _lock_packages(lock) == [
        PackageRef("soupsieve", "2.10", "PyPI", ("uv.lock (python_full_version < '3.11.5')",))
    ]


def test_default_report_dir_is_outside_the_repo(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    report_dir = default_output_dir()
    assert report_dir == tmp_path / ".portal5" / "security"
    assert "docs/security" not in str(report_dir)
    plist = Path(__file__).resolve().parents[2] / "deploy/launchd/com.portal5.security-sweep.plist"
    text = plist.read_text(encoding="utf-8")
    assert "--output-dir __HOME__/.portal5/security" in text
    assert "docs/security" not in text


def test_docker_findings_keep_image_severity_and_fixed_version():
    data = {
        "results": [
            {
                "packages": [
                    {
                        "package": {
                            "name": "musl",
                            "version": "1.2.5-r3",
                            "ecosystem": "Alpine:v3.20",
                        },
                        "groups": [
                            {
                                "ids": ["GHSA-1234"],
                                "aliases": ["MAL-2026-42"],
                                "max_severity": "9.8",
                            }
                        ],
                        "vulnerabilities": [
                            {
                                "id": "GHSA-1234",
                                "aliases": ["MAL-2026-42"],
                                "summary": "malicious package advisory",
                                "affected": [
                                    {
                                        "package": {"name": "musl", "ecosystem": "Alpine:v3.20"},
                                        "ranges": [
                                            {"events": [{"introduced": "0"}, {"fixed": "1.2.5-r4"}]}
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        ]
    }

    findings, package_count = _docker_findings(data, ["alpine:3.20"])

    assert package_count == 1
    assert findings[0]["severity"] == "CRITICAL"
    assert findings[0]["fixed"] == "1.2.5-r4"
    assert findings[0]["source"] == "docker image alpine:3.20"
    assert alert_required(findings)


def test_parse_image_inspect_prefers_repo_digest_and_merges_tags():
    out = 'id1\t["alpine@sha256:d1"]\talpine:3.20 alpine:latest \nid2\t[]\tlocal-built:latest \n'

    assert s._parse_image_inspect(out) == {
        "alpine@sha256:d1": ["alpine:3.20", "alpine:latest"],
        "id2": ["local-built:latest"],
    }


def test_classify_image_and_dockerfile_hint():
    assert s.classify_image(["portal-5-mcp-documents:latest"]) == "ours"
    assert s.classify_image(["portal5-open-webui:v0.13.0-hardened"]) == "ours"
    assert s.classify_image(["alpine:3.20"]) == "upstream"
    assert s.dockerfile_hint(["portal-5-portal-pipeline:latest"]) == "Dockerfile.pipeline"
    assert s.dockerfile_hint(["portal-5-mcp-documents:latest"]) == "Dockerfile.mcp"
    assert s.dockerfile_hint(["portal-5-browser-mcp:latest"]) == "deploy/browser-mcp/Dockerfile"
    assert (
        s.dockerfile_hint(["portal5-open-webui:v0.13.0-hardened"])
        == "deploy/portal-5/Dockerfile.openwebui (OPENWEBUI_VERSION arg)"
    )


def test_latest_upstream_tags_skips_non_dockerhub():
    assert s.latest_upstream_tags("ghcr.io/open-webui/open-webui:main") == ""
    assert s.latest_upstream_tags("some/other/registry/image:tag") == ""


SCANNER_JSON = {
    "results": [
        {
            "packages": [
                {
                    "package": {"name": "musl", "version": "1.2.5-r3", "ecosystem": "Alpine:v3.20"},
                    "groups": [{"ids": ["GHSA-1"], "aliases": [], "max_severity": "8.1"}],
                    "vulnerabilities": [
                        {
                            "id": "GHSA-1",
                            "aliases": [],
                            "summary": "s",
                            "affected": [
                                {
                                    "package": {"name": "musl", "ecosystem": "Alpine:v3.20"},
                                    "ranges": [
                                        {"events": [{"introduced": "0"}, {"fixed": "1.2.5-r4"}]}
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    ]
}


def _docker_fake_run(calls):
    def fake_run(argv, capture_output=True, text=True, timeout=None, check=None):
        calls.append(argv)
        if "ls" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="alpine:3.20\tid1\n")
        if "inspect" in argv:
            return subprocess.CompletedProcess(
                argv, 0, stdout='id1\t["alpine@sha256:d1"]\talpine:3.20 \n'
            )
        output = Path(argv[argv.index("--output-file") + 1])
        output.write_text(json.dumps(SCANNER_JSON))
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")

    return fake_run


def test_scan_docker_images_caches_by_digest_and_skips_unchanged(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(s.subprocess, "run", _docker_fake_run(calls))
    monkeypatch.setattr(
        s.shutil, "which", lambda name: "scanner" if name == "osv-scanner" else "/usr/bin/docker"
    )
    monkeypatch.setattr(s, "_scanner_version", lambda scanner: "osv-scanner 2.7.1")
    monkeypatch.setattr(s, "latest_upstream_tags", lambda ref: "3.21.3")
    cache = tmp_path / "cache.json"

    findings, stats, errors, triage = s.scan_docker_images("/usr/bin/docker", cache)

    assert errors == []
    assert calls.count([c for c in calls if c[0] == "scanner"][0]) == 1
    assert stats == {"images": 1, "scanned": 1, "cached": 0, "packages": 1}
    assert findings[0]["severity"] == "HIGH"
    assert findings[0]["source"] == "docker image alpine:3.20"
    assert triage[0]["ownership"] == "upstream"

    findings2, stats2, errors2, _ = s.scan_docker_images("/usr/bin/docker", cache)

    assert calls.count([c for c in calls if c[0] == "scanner"][0]) == 1
    assert stats2 == {"images": 1, "scanned": 0, "cached": 1, "packages": 1}
    assert findings2 == findings
    assert errors2 == []


def test_scan_docker_images_timeout_records_error_and_does_not_cache(tmp_path, monkeypatch):
    def fake_run(argv, capture_output=True, text=True, timeout=None, check=None):
        if "ls" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="alpine:3.20\tid1\n")
        if "inspect" in argv:
            return subprocess.CompletedProcess(
                argv, 0, stdout='id1\t["alpine@sha256:d1"]\talpine:3.20 \n'
            )
        raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout or 0)

    monkeypatch.setattr(s.subprocess, "run", fake_run)
    monkeypatch.setattr(
        s.shutil, "which", lambda name: "scanner" if name == "osv-scanner" else "/usr/bin/docker"
    )
    monkeypatch.setattr(s, "_scanner_version", lambda scanner: "osv-scanner 2.7.1")
    cache = tmp_path / "cache.json"

    findings, stats, errors, triage = s.scan_docker_images("/usr/bin/docker", cache, 60)

    assert findings == [] and triage == []
    assert stats["scanned"] == 0 and stats["images"] == 1
    assert len(errors) == 1 and "timed out" in errors[0]
    assert not cache.exists() or json.loads(cache.read_text())["images"] == {}


def test_build_image_triage_splits_ours_from_upstream(monkeypatch):
    monkeypatch.setattr(s, "latest_upstream_tags", lambda ref: "3.21.3, 3.21.2")
    keys = {"k1": ["portal-5-portal-pipeline:latest"], "k2": ["alpine:3.20"]}
    rows_by_key = {
        "k1": [
            {
                "id": "CVE-1",
                "severity": "CRITICAL",
                "package": "apt",
                "ecosystem": "Debian:13",
                "version": "3.0.4",
                "fixed": "",
                "ids": "CVE-1",
                "summary": "",
                "source": "docker image portal-5-portal-pipeline:latest",
            }
        ],
        "k2": [
            {
                "id": "GHSA-2",
                "severity": "HIGH",
                "package": "musl",
                "ecosystem": "Alpine:v3.20",
                "version": "1.2.5-r3",
                "fixed": "1.2.5-r4",
                "ids": "GHSA-2",
                "summary": "",
                "source": "docker image alpine:3.20",
            }
        ],
    }

    triage = s.build_image_triage(rows_by_key, keys)
    by_image = {row["image"]: row for row in triage}

    assert by_image["portal-5-portal-pipeline:latest"]["ownership"] == "ours"
    assert "Dockerfile.pipeline" in by_image["portal-5-portal-pipeline:latest"]["action"]
    assert by_image["alpine:3.20"]["ownership"] == "upstream"
    assert "3.21.3" in by_image["alpine:3.20"]["action"]
    assert by_image["alpine:3.20"]["high"] == "1"
    assert by_image["portal-5-portal-pipeline:latest"]["critical"] == "1"


def test_compute_delta_new_carried_resolved():
    rows = [
        {
            "ecosystem": "PyPI",
            "package": "a",
            "version": "1",
            "id": "X-1",
            "severity": "HIGH",
            "source": "s",
        },
        {
            "ecosystem": "PyPI",
            "package": "b",
            "version": "2",
            "id": "X-2",
            "severity": "LOW",
            "source": "s",
        },
    ]
    prior = {
        "date": "2026-11-12",
        "findings": [
            {"ecosystem": "PyPI", "package": "b", "version": "2", "id": "X-2"},
            {"ecosystem": "PyPI", "package": "c", "version": "3", "id": "X-3"},
        ],
    }

    delta = s.compute_delta(rows, prior)
    baseline = s.compute_delta(rows, None)

    assert [row["package"] for row in delta["new"]] == ["a"]
    assert [row["package"] for row in delta["carried"]] == ["b"]
    assert [row["package"] for row in delta["resolved"]] == ["c"]
    assert delta["previous_date"] == "2026-11-12"
    assert baseline["baseline"] is True and len(baseline["new"]) == 2


def test_save_findings_state_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    rows = [
        {
            "ecosystem": "PyPI",
            "package": "a",
            "version": "1",
            "id": "X-1",
            "severity": "HIGH",
            "source": "s",
        }
    ]

    s.save_findings_state(path, "2026-11-19", rows)
    data = s.load_previous_findings(path)
    delta = s.compute_delta([dict(row) for row in rows], data)

    assert data is not None and data["date"] == "2026-11-19"
    assert delta["carried"] and not delta["new"] and not delta["resolved"]


def test_brew_security_split_flags_advisory_hits(monkeypatch):
    def fake_post_json(url, body):
        results = []
        for query in body["queries"]:
            hit = query["package"]["name"] == "curl" and query["package"]["ecosystem"].startswith(
                "Alpine"
            )
            results.append({"vulns": [{"id": "CVE-2026-1"}]} if hit else {"vulns": []})
        return {"results": results}

    monkeypatch.setattr(s, "_post_json", fake_post_json)
    rows = [
        {"name": "curl", "installed": "8.16.0", "current": "8.17.0"},
        {"name": "pkgconf", "installed": "2.4.0", "current": "2.5.0"},
    ]

    security, routine, errors = s.brew_security_split(rows)

    assert errors == []
    assert [row["name"] for row in security] == ["curl"]
    assert security[0]["advisories"] == "CVE-2026-1"
    assert [row["name"] for row in routine] == ["pkgconf"]


def test_pinned_version_scope_aware():
    assert s._pinned_version("@scope/name@1.2.3") == "1.2.3"
    assert s._pinned_version("@scope/name") == ""
    assert s._pinned_version("pkg@2.0") == "2.0"
    assert s._pinned_version("pkg") == ""
    assert s._package_name("@scope/name@1.2.3") == "@scope/name"
    assert s._package_name("@scope/name") == "@scope/name"
    assert s._package_name("pkg@2.0") == "pkg"
    assert s._package_name("pkg") == "pkg"


def test_npx_pin_rows_flags_floating_and_stale(tmp_path, monkeypatch):
    config = tmp_path / "portal.yaml"
    config.write_text(
        "mcp_fleet:\n"
        "  - id: fs\n"
        "    command:\n"
        "      command: ['npx', '-y', '@modelcontextprotocol/server-filesystem', '/tmp']\n"
        "  - id: ctx7\n"
        "    command:\n"
        "      command: ['npx', '-y', '@upstash/context7-mcp@1.2.3', '--transport', 'stdio']\n"
    )
    monkeypatch.setattr(s, "_npm_latest", lambda pkg: "1.2.4" if "context7" in pkg else "0.7.0")

    rows, errors = s.npx_pin_rows(config)
    by_service = {row["service"]: row for row in rows}

    assert errors == []
    assert by_service["fs"]["status"] == "floating"
    assert by_service["fs"]["pinned"] == "" and by_service["fs"]["latest"] == "0.7.0"
    assert by_service["ctx7"]["status"] == "stale pin"
    assert by_service["ctx7"]["pinned"] == "1.2.3"
