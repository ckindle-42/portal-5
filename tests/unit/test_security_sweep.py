from pathlib import Path

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
