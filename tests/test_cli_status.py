from cli import status_label


def _row(**overrides):
    base = {
        "verdict": "worth_considering",
        "applied": 0,
        "interview_scheduled": 0,
        "offer_received": 0,
        "company_rejected": 0,
    }
    base.update(overrides)
    return base


def test_worth_considering_shows_verdict():
    label, color = status_label(_row())
    assert label == "WORTH_CONSIDERING"
    assert color


def test_applied_overrides_verdict():
    label, color = status_label(_row(applied=1))
    assert label == "APPLIED"


def test_applied_worth_considering_are_visually_distinct():
    applied_label, applied_color = status_label(_row(applied=1))
    worth_label, worth_color = status_label(_row())
    assert applied_label != worth_label


def test_interview_overrides_applied():
    label, _ = status_label(_row(applied=1, interview_scheduled=1))
    assert label == "INTERVIEW"


def test_offer_overrides_everything():
    label, _ = status_label(_row(applied=1, interview_scheduled=1, offer_received=1))
    assert label == "OFFER"


def test_company_rejected_overrides_applied():
    label, _ = status_label(_row(applied=1, company_rejected=1))
    assert label == "COMPANY_REJECTED"
