from database.enums import FragmentJobStatus
from api.schemas import FragmentRunnerClaimIn

def test_fragment_job_statuses():
    assert FragmentJobStatus.QUEUED.value == "QUEUED"
    assert FragmentJobStatus.CAPTURED.value == "CAPTURED"

def test_runner_claim_schema():
    assert FragmentRunnerClaimIn(runner_id="runner-1").runner_id == "runner-1"
