from worker import run_job


def test_worker():
    assert run_job(4)["status"] == "queued"
