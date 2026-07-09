from cli import job_matches_filter


def _row(**overrides):
    base = {
        "verdict": "worth_considering",
        "verdict_confirmed": 1,
        "applied": 0,
        "interview_scheduled": 0,
        "offer_received": 0,
        "company_rejected": 0,
    }
    base.update(overrides)
    return base


def test_applied_worth_considering_job_matches_applied_not_worth_considering():
    row = _row(verdict="worth_considering", applied=1)
    assert job_matches_filter(row, "applied")
    assert not job_matches_filter(row, "worth_considering")


def test_applied_rejected_job_matches_applied_not_rejected():
    row = _row(verdict="rejected", applied=1)
    assert job_matches_filter(row, "applied")
    assert not job_matches_filter(row, "rejected")


def test_company_rejected_job_matches_company_rejected_not_applied():
    row = _row(verdict="worth_considering", applied=1, company_rejected=1)
    assert job_matches_filter(row, "company_rejected")
    assert not job_matches_filter(row, "applied")


def test_interview_job_matches_interview_not_applied():
    row = _row(verdict="worth_considering", applied=1, interview_scheduled=1)
    assert job_matches_filter(row, "interview")
    assert not job_matches_filter(row, "applied")


def test_untouched_verdict_matches_own_verdict():
    row = _row(verdict="warning")
    assert job_matches_filter(row, "warning")
    assert not job_matches_filter(row, "applied")


def test_all_matches_everything():
    assert job_matches_filter(_row(applied=1, company_rejected=1), "all")


def test_unconfirmed_rejected_matches_rejected_soft_not_rejected():
    row = _row(verdict="rejected", verdict_confirmed=0)
    assert job_matches_filter(row, "rejected_soft")
    assert not job_matches_filter(row, "rejected")


def test_confirmed_rejected_matches_rejected_not_rejected_soft():
    row = _row(verdict="rejected", verdict_confirmed=1)
    assert job_matches_filter(row, "rejected")
    assert not job_matches_filter(row, "rejected_soft")
