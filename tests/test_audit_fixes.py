import hashlib
import database
from database import get_conn, get_user, save_job, check_duplicate, get_job


def _uid():
    return get_user("testuser")["id"]


def test_save_job_rejects_unknown_model_values():
    bad = {
        "company_name": "Evil", "role_title": "R", "verdict": '"><img src=x onerror=alert(1)>',
        "triage": {"status": '"><script>'},
        "layers": {"product": {"status": "bogus"}, "business": {"status": "flag"}},
        "fit": {"status": "ok"},
    }
    job = get_job(save_job(_uid(), bad, source_text="bad-values listing"), _uid())
    assert job["verdict"] == "warning"
    assert job["triage_status"] == ""
    assert job["product_status"] == ""
    assert job["business_status"] == "flag"
    assert job["fit_status"] == "ok"


def test_reanalyze_updates_in_place_and_keeps_status():
    first = {"company_name": "A", "role_title": "Old", "verdict": "warning"}
    job_id = save_job(_uid(), first, source_url="https://x.example/1", source_text="in-place listing")
    with get_conn() as conn:
        conn.execute("UPDATE jobs SET applied=1, notes='keep me' WHERE id=?", (job_id,))
        before = conn.execute("SELECT COUNT(*) FROM jobs WHERE user_id=?", (_uid(),)).fetchone()[0]

    second = {"company_name": "A", "role_title": "New", "verdict": "worth_considering"}
    returned = save_job(_uid(), second, source_url="https://x.example/1",
                        source_text="in-place listing", replace_job_id=job_id)

    assert returned == job_id
    job = get_job(job_id, _uid())
    assert job["role"] == "New" and job["verdict"] == "worth_considering"
    assert job["applied"] == 1 and job["notes"] == "keep me"
    with get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM jobs WHERE user_id=?", (_uid(),)).fetchone()[0] == before


def test_duplicate_found_by_text_when_saved_with_url():
    save_job(_uid(), {"company_name": "B", "verdict": "warning"},
             source_url="https://y.example/2", source_text="Same text, saved with a URL")
    assert check_duplicate(_uid(), "Same text, saved with a URL") is not None


def test_legacy_password_hash_verifies_and_is_upgraded_on_login(client):
    salt = "ab" * 16
    legacy = f"{salt}:{hashlib.sha256((salt + 'testpassword').encode()).hexdigest()}"
    assert database.verify_password("testpassword", legacy)
    assert database.needs_rehash(legacy)
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash=? WHERE username='testuser'", (legacy,))
    resp = client.post("/login", data={"username": "testuser", "password": "testpassword"})
    assert resp.status_code == 302
    stored = get_user("testuser")["password_hash"]
    assert not database.needs_rehash(stored)
    assert database.verify_password("testpassword", stored)


def test_discover_analyze_rejects_item_without_text(logged_in_client):
    with get_conn() as conn:
        conn.execute("INSERT INTO feeds (user_id, type, source, label) VALUES (?, 'rss', 'https://f.example', 'f')",
                     (_uid(),))
        feed_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO feed_items (feed_id, user_id, external_id, title, url, description, source_hash) "
            "VALUES (?, ?, 'e1', 't', 'https://f.example/1', '', 'hash-no-text')",
            (feed_id, _uid()),
        )
        item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    resp = logged_in_client.post(f"/discover/{item_id}/analyze")
    assert resp.status_code == 400
