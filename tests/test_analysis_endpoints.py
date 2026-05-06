from unittest.mock import patch, MagicMock
from database import create_analysis, update_analysis_status, get_conn


def test_analyze_returns_analysis_id(logged_in_client):
    with patch("app._run_analysis_bg"):
        with patch("app.threading") as mock_threading:
            mock_threading.Thread.return_value = MagicMock()
            resp = logged_in_client.post("/analyze", data={"text": "Some job listing text here"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "analysis_id" in data
    assert len(data["analysis_id"]) == 36
    assert "result" not in data


def test_analyze_spawns_thread(logged_in_client):
    with patch("app.threading") as mock_threading:
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        logged_in_client.post("/analyze", data={"text": "Some job listing"})
    mock_threading.Thread.assert_called_once()
    mock_thread.start.assert_called_once()


def test_analysis_status_pending(logged_in_client, app):
    analysis_id = create_analysis(user_id=1, source_label="Figma PM")
    resp = logged_in_client.get(f"/analysis_status/{analysis_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "pending"
    assert data["source_label"] == "Figma PM"
    assert data["result_job_id"] is None


def test_analysis_status_done_includes_job_fields(logged_in_client, app):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO jobs (user_id, company, role, verdict, verdict_confirmed) "
            "VALUES (1, 'Figma', 'Senior PM', 'worth_considering', 1)"
        )
        job_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    analysis_id = create_analysis(user_id=1, source_label="Figma PM")
    update_analysis_status(analysis_id, "done", result_job_id=job_id)
    resp = logged_in_client.get(f"/analysis_status/{analysis_id}")
    data = resp.get_json()
    assert data["status"] == "done"
    assert data["result_job_id"] == job_id
    assert data["company"] == "Figma"
    assert data["verdict"] == "worth_considering"


def test_analysis_status_wrong_user_returns_404(logged_in_client, app):
    analysis_id = create_analysis(user_id=999, source_label="Other user")
    resp = logged_in_client.get(f"/analysis_status/{analysis_id}")
    assert resp.status_code == 404


def test_analysis_status_nonexistent_returns_404(logged_in_client):
    resp = logged_in_client.get("/analysis_status/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
