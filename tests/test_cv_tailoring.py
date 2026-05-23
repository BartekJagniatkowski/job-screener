import pytest


def test_cv_tailoring_column_exists(app):
    from database import get_conn
    with get_conn() as conn:
        cols = {r['name'] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    assert 'cv_tailoring' in cols


def test_save_and_get_cv_tailoring(logged_in_client, sample_job_id):
    from database import save_cv_tailoring, get_cv_tailoring, get_user
    user = get_user("testuser")
    content = "## What to emphasise\n- Leadership experience"
    result = save_cv_tailoring(sample_job_id, user["id"], content)
    assert result is True
    retrieved = get_cv_tailoring(sample_job_id, user["id"])
    assert retrieved == content


def test_get_returns_none_when_empty(logged_in_client, sample_job_id):
    from database import get_cv_tailoring, get_user
    user = get_user("testuser")
    result = get_cv_tailoring(sample_job_id, user["id"])
    assert result is None


def test_save_returns_false_for_wrong_user(logged_in_client, sample_job_id):
    from database import save_cv_tailoring
    result = save_cv_tailoring(sample_job_id, 99999, "content")
    assert result is False


def test_save_overwrites_existing(logged_in_client, sample_job_id):
    from database import save_cv_tailoring, get_cv_tailoring, get_user
    user = get_user("testuser")
    save_cv_tailoring(sample_job_id, user["id"], "first version")
    save_cv_tailoring(sample_job_id, user["id"], "second version")
    assert get_cv_tailoring(sample_job_id, user["id"]) == "second version"
