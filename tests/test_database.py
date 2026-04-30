import sqlite3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
from pathlib import Path
import database

def _tmp_db(tmp_path):
    database.DB_PATH = Path(tmp_path) / "test.db"
    database.init_db()
    return database.get_conn()

def test_new_columns_exist(tmp_path):
    conn = _tmp_db(tmp_path)
    cur = conn.execute("PRAGMA table_info(jobs)")
    cols = {row['name'] for row in cur.fetchall()}
    assert 'role_archetype' in cols, "role_archetype column missing"
    assert 'fit_score' in cols, "fit_score column missing"
    conn.close()

def test_save_job_extracts_fields(tmp_path):
    conn = _tmp_db(tmp_path)
    conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        ("testuser", "salt:hash")
    )
    conn.commit()
    user_id = conn.execute("SELECT id FROM users WHERE username='testuser'").fetchone()['id']

    result = {
        "company_name": "Acme",
        "role_title": "Senior PM",
        "verdict": "worth_considering",
        "verdict_summary": "Good fit.",
        "zero_list_hit": False,
        "zero_list_reason": None,
        "zero_list_evidence": None,
        "yellow_list_hit": False,
        "yellow_list_reason": None,
        "triage": {
            "status": "ok", "findings": "Good role.", "evidence": None,
            "ghost_job_risk": "low", "ghost_job_signals": None,
            "role_archetype": "pm"
        },
        "layers": {
            "product": {"status": "ok", "findings": "Fine.", "evidence": None,
                        "compensation_signal": "undisclosed", "compensation_note": None},
            "business": {"status": "ok", "findings": "Fine.", "evidence": None,
                         "compensation_signal": "undisclosed", "compensation_note": None},
            "reputation": {"status": "ok", "findings": "Fine.", "evidence": None},
            "values": {"status": "ok", "findings": "Fine.", "evidence": None},
        },
        "fit": {
            "status": "ok", "score": 4.2,
            "strengths": "Strong PM background.",
            "gaps": "No SaaS experience.",
            "improve": "Emphasize discovery work."
        },
        "gut_feeling": "Looks solid."
    }

    database.save_job(user_id, result, source_url="https://example.com/job/1")
    conn2 = database.get_conn()
    row = conn2.execute("SELECT * FROM jobs WHERE user_id=?", (user_id,)).fetchone()
    assert row['role_archetype'] == 'pm', f"Expected 'pm', got {row['role_archetype']}"
    assert abs(row['fit_score'] - 4.2) < 0.01, f"Expected 4.2, got {row['fit_score']}"
    conn2.close()

if __name__ == '__main__':
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        test_new_columns_exist(tmp)
        test_save_job_extracts_fields(tmp)
    print("All tests passed.")
