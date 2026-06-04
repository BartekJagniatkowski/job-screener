from analyzer import SYSTEM_TEMPLATE


def test_system_template_has_reality_check_section():
    assert 'REALITY CHECK' in SYSTEM_TEMPLATE


def test_system_template_has_reality_check_json_field():
    assert '"reality_check"' in SYSTEM_TEMPLATE


def test_system_template_has_callouts_field():
    assert '"callouts"' in SYSTEM_TEMPLATE


def test_system_template_has_phrase_and_plain_fields():
    assert '"phrase"' in SYSTEM_TEMPLATE
    assert '"plain"' in SYSTEM_TEMPLATE


def test_reality_check_field_after_gut_feeling():
    pos_gut = SYSTEM_TEMPLATE.index('"gut_feeling"')
    pos_rc  = SYSTEM_TEMPLATE.index('"reality_check"')
    assert pos_gut < pos_rc


def test_reality_check_instruction_before_format():
    pos_rc_section = SYSTEM_TEMPLATE.index('REALITY CHECK')
    pos_format     = SYSTEM_TEMPLATE.index('FORMAT — ONLY this JSON')
    assert pos_rc_section < pos_format


import json
import pytest
from database import get_conn


def _insert_job(raw_dict):
    """Insert a minimal job row into the shared test DB and return its id."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO jobs (user_id, company, role, verdict, verdict_confirmed, raw_json) "
            "VALUES (1, 'Acme', 'Test Role', 'worth_considering', 1, ?)",
            (json.dumps(raw_dict),),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def test_partial_renders_reality_check_when_present(logged_in_client, app):
    rc = {
        "summary": "A role for someone who enjoys writing documents no one will read.",
        "callouts": [
            {"phrase": "scalable and repeatable", "plain": "writing processes nobody currently follows"},
            {"phrase": "principal-level IC", "plain": "senior title, no budget, no team"},
        ],
    }
    job_id = _insert_job({"reality_check": rc, "triage": {}, "layers": {}, "fit": {}})
    resp = logged_in_client.get(f"/job/{job_id}/partial")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Reality check" in html
    assert "reality-check-card" in html
    assert "scalable and repeatable" in html
    assert "writing processes nobody currently follows" in html
    assert "principal-level IC" in html


def test_partial_omits_reality_check_when_absent(logged_in_client, app):
    job_id = _insert_job({"triage": {}, "layers": {}, "fit": {}})
    resp = logged_in_client.get(f"/job/{job_id}/partial")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Reality check" not in html
    assert "reality-check-card" not in html


def test_partial_renders_summary_only_when_callouts_empty(logged_in_client, app):
    rc = {
        "summary": "Clear job description, no decoding needed.",
        "callouts": [],
    }
    job_id = _insert_job({"reality_check": rc, "triage": {}, "layers": {}, "fit": {}})
    resp = logged_in_client.get(f"/job/{job_id}/partial")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Reality check" in html
    assert "Clear job description, no decoding needed." in html
    assert "reality-check-divider" not in html


def test_detail_renders_reality_check_when_present(logged_in_client, app):
    rc = {
        "summary": "Detail page check.",
        "callouts": [
            {"phrase": "synergy-driven", "plain": "nobody knows what this means"},
        ],
    }
    job_id = _insert_job({"reality_check": rc, "triage": {}, "layers": {}, "fit": {}})
    # /job/<id> now redirects to /dashboard?job=<id>
    resp = logged_in_client.get(f"/job/{job_id}")
    assert resp.status_code in (301, 302)
    # Verify the partial endpoint (used by dashboard modal) shows reality check
    resp = logged_in_client.get(f"/job/{job_id}/partial")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Reality check" in html
    assert "reality-check-card" in html
    assert "synergy-driven" in html
