import pytest
from database import get_jobs, get_conn, get_user


def _insert_jobs(user_id, count):
    with get_conn() as conn:
        for i in range(count):
            conn.execute(
                """INSERT INTO jobs (user_id, company, role, verdict, verdict_confirmed, analyzed_at)
                   VALUES (?, ?, ?, 'worth_considering', 1, date('now'))""",
                (user_id, f"Corp{i}", f"Role{i}"),
            )


def test_get_jobs_no_limit_returns_all(app):
    user = get_user("testuser")
    _insert_jobs(user["id"], 5)
    all_jobs = get_jobs(user["id"])
    limited = get_jobs(user["id"], limit=2)
    assert len(all_jobs) > len(limited)
    assert len(limited) == 2


def test_history_redirects_to_dashboard(logged_in_client):
    resp = logged_in_client.get("/history")
    assert resp.status_code in (301, 302)
    assert resp.headers["Location"].endswith("/dashboard")


def test_job_redirect_uses_dashboard(logged_in_client, sample_job_id):
    resp = logged_in_client.get(f"/job/{sample_job_id}")
    assert resp.status_code in (301, 302)
    location = resp.headers["Location"]
    assert "/dashboard" in location
    assert f"job={sample_job_id}" in location


def test_dashboard_has_cmd_zone(logged_in_client):
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 200
    assert b"cmd-zone" in resp.data


def test_dashboard_passes_api_key_flag(logged_in_client):
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 200


def test_nav_has_no_history_link(logged_in_client):
    resp = logged_in_client.get("/dashboard")
    assert b'href="/history"' not in resp.data
    assert b'url_for(&#39;history&#39;)' not in resp.data


def test_nav_has_no_analyze_link(logged_in_client):
    resp = logged_in_client.get("/dashboard")
    html = resp.data.decode()
    # "Analyze" link text should not appear in nav
    assert '>Analyze<' not in html
