import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tempfile
from pathlib import Path
import database

def _seed_db(tmp_path):
    database.DB_PATH = Path(tmp_path) / "test.db"
    database.init_db()
    conn = database.get_conn()
    conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        ("u", "s:h")
    )
    conn.commit()
    uid = conn.execute("SELECT id FROM users WHERE username='u'").fetchone()['id']
    rows = [
        # verdict, confirmed, applied, company_rejected, triage_s, product_s, business_s, reputation_s, values_s, fit_s, fit_score, role_archetype
        ('worth_considering', 1, 0, 0, 'ok',      'ok',      'ok',      'ok',      'ok',      'ok',      4.5, 'pm'),
        ('worth_considering', 1, 1, 0, 'ok',      'warning', 'ok',      'ok',      'ok',      'ok',      4.0, 'pm'),
        ('warning',           1, 0, 0, 'warning',  'ok',      'ok',      'ok',      'ok',      'warning', 3.2, 'engineering'),
        ('rejected',          1, 0, 0, 'flag',     'flag',    'ok',      'ok',      'ok',      'flag',    1.5, 'engineering'),
        ('rejected',          0, 0, 0, 'ok',       'ok',      'ok',      'flag',    'ok',      'ok',      2.0, 'data'),
        ('worth_considering', 1, 1, 1, 'ok',       'ok',      'ok',      'ok',      'ok',      'ok',      4.1, 'pm'),
    ]
    for r in rows:
        conn.execute("""
            INSERT INTO jobs (user_id, verdict, verdict_confirmed, applied, company_rejected,
                triage_status, product_status, business_status, reputation_status, values_status,
                fit_status, fit_score, role_archetype, company, role)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (uid, *r, 'Co', 'Role'))
    conn.commit()
    conn.close()
    return uid

def test_verdict_distribution(tmp_path):
    uid = _seed_db(tmp_path)
    data = database.get_analytics(uid)
    vd = data['verdict_distribution']
    assert vd['worth_considering'] == 3
    assert vd['warning'] == 1
    assert vd['rejected_confirmed'] == 1
    assert vd['rejected_soft'] == 1

def test_funnel(tmp_path):
    uid = _seed_db(tmp_path)
    data = database.get_analytics(uid)
    f = data['funnel']
    assert f['total'] == 6
    assert f['applied'] == 2
    assert f['company_rejected'] == 1

def test_layer_flags(tmp_path):
    uid = _seed_db(tmp_path)
    data = database.get_analytics(uid)
    lf = data['layer_flags']
    assert lf['triage']['flag'] == 1
    assert lf['product']['flag'] == 1
    assert lf['reputation']['flag'] == 1

def test_fit_score_avg(tmp_path):
    uid = _seed_db(tmp_path)
    data = database.get_analytics(uid)
    assert data['fit_score_avg'] is not None
    assert 3.0 < data['fit_score_avg'] < 4.0

def test_archetype_distribution(tmp_path):
    uid = _seed_db(tmp_path)
    data = database.get_analytics(uid)
    ad = data['archetype_distribution']
    assert ad.get('pm', 0) == 3
    assert ad.get('engineering', 0) == 2

if __name__ == '__main__':
    import tempfile
    tests = [test_verdict_distribution, test_funnel, test_layer_flags, test_fit_score_avg, test_archetype_distribution]
    for t in tests:
        with tempfile.TemporaryDirectory() as tmp:
            t(tmp)
            print(f"  PASS: {t.__name__}")
    print("All analytics tests passed.")
