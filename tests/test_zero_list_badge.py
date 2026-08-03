import pytest
from database import get_conn, get_user


def _make_job(app, verdict, verdict_confirmed, zero_list_hit):
    user = get_user("testuser")
    assert user is not None
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO jobs (user_id, company, role, verdict, verdict_confirmed,
                                 zero_list_hit, analyzed_at)
               VALUES (?, 'Big Pharma Co', 'Any Role', ?, ?, ?, date('now'))""",
            (user["id"], verdict, verdict_confirmed, zero_list_hit),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def test_zero_list_hit_shows_zero_list_badge_not_user_rejected(logged_in_client, app):
    job_id = _make_job(app, "rejected", 1, 1)
    resp = logged_in_client.get(f"/job/{job_id}/partial")
    html = resp.get_data(as_text=True)
    assert "Zero list" in html
    assert "User rejected" not in html


def test_manual_confirm_without_zero_list_hit_still_shows_user_rejected(logged_in_client, app):
    job_id = _make_job(app, "rejected", 1, 0)
    resp = logged_in_client.get(f"/job/{job_id}/partial")
    html = resp.get_data(as_text=True)
    assert "User rejected" in html
    assert "Zero list" not in html


def test_unconfirmed_ai_rejection_still_shows_ai_rejected(logged_in_client, app):
    job_id = _make_job(app, "rejected", 0, 0)
    resp = logged_in_client.get(f"/job/{job_id}/partial")
    html = resp.get_data(as_text=True)
    assert "AI rejected" in html
