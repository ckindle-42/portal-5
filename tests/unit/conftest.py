"""Unit-test-specific pytest configuration.

Ensures prometheus_client can initialize on platforms without /dev/shm
(e.g. macOS) by setting PROMETHEUS_MULTIPROC_DIR to a valid temp directory
before any test module imports. Also patches lifespan background tasks
that fail during fixture teardown.
"""

import os
import tempfile
from pathlib import Path

import pytest

# NERC CIP standard PDFs are deliberately gitignored (cip_register.py's
# fetch_pdfs: "Public record; not committed (the register JSON is the
# committed artifact)"). Operators fetch them locally; CI never does. These
# tests fall through to assessment_source._pdf_parent_requirement's raw-PDF
# recovery path (only reached for a table Part whose parent R-level node
# isn't in the register) and fail with FileNotFoundError for a reason that
# has nothing to do with the change under test. Listed explicitly rather
# than caught generically: pytest fixtures can't intercept a test's own
# exception via try/except-around-yield (verified — pluggy does not route it
# through the generator), and several of these tests swallow the
# FileNotFoundError themselves (assessment_runs' background-worker run
# converts it into a FAILED status, compliance_gaps' sync path into
# {"error": ...}), so there is no single exception type to hook generically
# even with the correct mechanism.
#
# The list covers only the swallowers. A test that lets the FileNotFoundError
# out is skipped automatically by `_skip_when_the_cip_pdf_corpus_is_absent`
# below, so a newly added one does not have to be remembered here — the list
# going stale is what broke CI on 82854d0c (`test_alignment_invalid_no_longer_
# gates_the_verdict`). Regenerate it with:
#   mv portal/modules/compliance/data/cip_pdfs /tmp/backup && mkdir -p portal/modules/compliance/data/cip_pdfs
#   uv run pytest tests/unit -k compliance -q --tb=no | grep '^FAILED ' | awk '{print $2}' | sort -u
#   rm -rf portal/modules/compliance/data/cip_pdfs && mv /tmp/backup portal/modules/compliance/data/cip_pdfs
_CIP_PDF_DIR = (
    Path(__file__).resolve().parents[2] / "portal" / "modules" / "compliance" / "data" / "cip_pdfs"
)
_CIP_PDFS_PRESENT = _CIP_PDF_DIR.is_dir() and any(_CIP_PDF_DIR.glob("*.pdf"))
_CIP_PDF_DEPENDENT_TESTS = frozenset(
    Path(__file__).with_name("cip_pdf_dependent_tests.txt").read_text().split()
)


def pytest_collection_modifyitems(config, items: list) -> None:
    if _CIP_PDFS_PRESENT:
        return
    skip = pytest.mark.skip(reason="NERC CIP PDF corpus not fetched locally")
    for item in items:
        if item.nodeid in _CIP_PDF_DEPENDENT_TESTS:
            item.add_marker(skip)


def pytest_configure(config) -> None:
    """Set up PROMETHEUS_MULTIPROC_DIR before collection begins.

    prometheus_client initialises mmap-backed metric files at import time.
    On Linux this defaults to /dev/shm; on macOS that path does not exist
    and import crashes with FileNotFoundError. Create a temp directory that
    works cross-platform.
    """
    if "PROMETHEUS_MULTIPROC_DIR" not in os.environ:
        mp_dir = Path(tempfile.gettempdir()) / "portal5_pytest_metrics"
        mp_dir.mkdir(parents=True, exist_ok=True)
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = str(mp_dir)

    # Prevent lifespan background tasks (health loop, state save) from
    # being created during TestClient teardown — they fail in test mode.
    os.environ["UNIT_TEST_MODE"] = "1"

    _patch_pdf_parent_requirement_when_the_corpus_is_absent()


def _patch_pdf_parent_requirement_when_the_corpus_is_absent() -> None:
    """Turn the missing-PDF FileNotFoundError into a skip, wherever it surfaces.

    `_pdf_parent_requirement` is the one place the gitignored corpus is read,
    so replacing it reports the real reason instead of a FileNotFoundError
    naming a path CI is never meant to have. `Skipped` derives from
    `BaseException`, not `Exception`, so the callers that swallow the original
    with a bare `except Exception` cannot swallow this one.

    Done in `pytest_configure`, for the whole session, rather than in an
    autouse fixture: pytest sets up higher-scoped fixtures first, so a
    function-scoped patch is not yet in place when a module-scoped fixture
    builds its context. That is how CI still errored at the setup of
    `test_compliance_vertical_slice.py::TestSharedContext` after the fixture
    version landed. Nothing restores the patch, which is correct — without the
    corpus the real function cannot do anything but raise.

    Still not covered: a call made on a worker thread, where the Skipped
    propagates into the worker instead of the test. Those stay on the node-id
    list, or carry their own skipif.
    """
    if _CIP_PDFS_PRESENT:
        return
    from portal.modules.compliance.core import assessment_source

    def _corpus_not_fetched(*_args: object, **_kwargs: object) -> None:
        pytest.skip("NERC CIP PDF corpus not fetched locally")

    assessment_source._pdf_parent_requirement = _corpus_not_fetched  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def _the_admission_gate_never_reads_this_machine(monkeypatch):
    """A unit test's verdict may not depend on how loaded the host is.

    `concurrency._last_memory_pct` is a module global the health cycle fills
    from a real `vm_stat`, and the admission gate 503s anything above the
    threshold. A TestClient lifespan runs that cycle, so on a busy machine
    (measured at 98% during a parallel run) every later request in that worker
    is rejected — `test_anthropic_non_streaming_success_returns_message` got
    503 instead of 200 twice, looking exactly like a flaky test. Being a
    module global, one test's poll poisons the rest of the worker.

    Both ends are pinned. Resetting the global alone is not enough: the health
    cycle runs *during* the test and writes the real figure back over it, so
    `monitor.memory_pct` — the one function that reads this machine — is
    stubbed too. The gate itself still runs, and a test that wants to exercise
    it can set the value itself.
    """
    from portal.platform.inference.router import concurrency, monitor

    monkeypatch.setattr(monitor, "memory_pct", lambda: 0.0)
    monkeypatch.setattr(concurrency, "_last_memory_pct", 0.0)


@pytest.fixture(autouse=True)
def _never_write_the_live_compliance_store(tmp_path, monkeypatch):
    """A unit test may not touch the operator's real compliance store.

    Found the hard way in BILATERAL_CORPUS_V1 P3: the hermetic NERC-sync test
    exercised a code path that constructs ``Repository()`` with no argument, and
    ``Repository``'s default is the production database. A tmp_path fixture's
    glossary page landed in the live store as a real revision with real
    sections, and the only reason it was caught was a census count being one
    higher than the term count.

    The redirect is on the BOUND DEFAULT, not on the module constant: the
    constant is the declaration that the mapping store and the repository share
    one canonical file, and a test asserts exactly that. A test that wants a
    store still passes its own path; a test that forgets gets a scratch file
    instead of the operator's data.
    """
    from portal.modules.compliance.core import mapping_store as _ms
    from portal.modules.compliance.core import repository as _repo

    scratch = tmp_path / "compliance_store_scratch.db"
    monkeypatch.setattr(_repo.Repository.__init__, "__defaults__", (scratch,))
    if _ms.MappingStore.__init__.__defaults__:
        monkeypatch.setattr(_ms.MappingStore.__init__, "__defaults__", (scratch,))
