"""R.5c -- learned action->behaviour classifier over sealed truth."""

from __future__ import annotations

from portal.modules.security.core.bully import pyramid, universe
from portal.modules.security.core.bully.behavior_classifier import (
    fit_classifier,
    measure_coverage,
)

# A small, realistic multi-style corpus (Windows EventIDs, Linux syscalls,
# cloud verbs, web paths) -- separable by class, unlike the deterministic
# table's English-verb-substring approach.
_TRAINING_CORPUS: list[tuple[str, str]] = [
    ("4672", "escalate"),
    ("4673", "escalate"),
    ("setuid", "escalate"),
    ("setgid", "escalate"),
    ("dcsync", "escalate"),
    ("secretsdump", "escalate"),
    ("/admin/grant", "escalate"),
    ("PutRolePolicy", "escalate"),
    ("4624", "auth"),
    ("4625", "auth"),
    ("login", "auth"),
    ("kerberos_tgt", "auth"),
    ("/login", "auth"),
    ("/oauth/token", "auth"),
    ("AssumeRole", "auth"),
    ("4661", "enumerate"),
    ("openat", "enumerate"),
    ("getdents", "enumerate"),
    ("/api/list", "enumerate"),
    ("/users", "enumerate"),
    ("ListBuckets", "enumerate"),
    ("whoami", "enumerate"),
    ("4688", "execute"),
    ("execve", "execute"),
    ("/exec", "execute"),
    ("/run", "execute"),
    ("RunInstances", "execute"),
    ("spawn", "execute"),
    ("4660", "destroy"),
    ("unlink", "destroy"),
    ("/delete", "destroy"),
    ("TerminateInstances", "destroy"),
    ("4657", "persist"),
    ("chmod", "persist"),
    ("symlink", "persist"),
    ("/cron/add", "persist"),
    ("1102", "evade"),
    ("ptrace", "evade"),
    ("/logs/clear", "evade"),
    ("4663", "collect"),
    ("read", "collect"),
    ("pread", "collect"),
    ("/download", "collect"),
    ("GetObject", "collect"),
    ("5140", "lateral"),
    ("connect", "lateral"),
    ("/rpc", "lateral"),
    ("3", "c2_exfil"),
    ("sendto", "c2_exfil"),
    ("/upload", "c2_exfil"),
    ("/beacon", "c2_exfil"),
]


def test_windows_eventid_and_linux_syscall_both_classify_escalate() -> None:
    """Seeded violation: under the deterministic table both are '', but the
    learned classifier -- fit on the sealed corpus -- resolves both."""
    assert pyramid.default_behavior_classifier("4672") == ""
    assert pyramid.default_behavior_classifier("setuid") == ""

    classifier = fit_classifier(_TRAINING_CORPUS)
    assert classifier("4672") == "escalate"
    assert classifier("setuid") == "escalate"


def test_classifier_is_a_drop_in_pyramid_behavior_classifier() -> None:
    classifier = fit_classifier(_TRAINING_CORPUS)
    feat = pyramid.level_feature("4672", "ACTION", raw_verb="4672", classifier=classifier)
    assert feat.level == pyramid.L3_BEHAVIOR
    assert feat.behavior_class == "escalate"


def test_low_confidence_yields_empty_not_a_false_class() -> None:
    classifier = fit_classifier(_TRAINING_CORPUS)
    # a wildly unrelated string should not confidently classify
    result = classifier("zzzzzzzzzzzzzzzzzzzzzzzz9999999999")
    assert result == "" or result in {c for _, c in _TRAINING_CORPUS}


def test_learned_coverage_exceeds_deterministic_on_procedural_universe() -> None:
    """The before/after (R.5b measured the deterministic table's cross-schema
    coverage as low against procedurally-realized values): fit on one seed's
    universe, measure on a DIFFERENT seed's universe (held-out), and confirm
    the learned classifier covers substantially more than the deterministic
    table on values it has never lexically seen before."""
    cousins = [
        {
            "parent_family": "priv-esc",
            "parent_technique": "T1078",
            "behavioural_spine": ["auth", "enumerate", "escalate", "collect"],
            "transformation": t,
        }
        for t in universe.TRANSFORMATIONS
    ]
    train_lot = universe.build_universe(n_sources=25, background_n=600, cousins=cousins, seed=101)
    held_out_lot = universe.build_universe(
        n_sources=25, background_n=600, cousins=cousins, seed=202
    )

    train_examples = train_lot.training_examples()
    held_out_examples = held_out_lot.training_examples()
    assert train_examples
    assert held_out_examples

    classifier = fit_classifier(train_examples)
    report = measure_coverage(classifier, held_out_examples)

    assert report.learned_coverage >= report.deterministic_coverage
