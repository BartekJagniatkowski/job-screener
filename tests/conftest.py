import os
import tempfile
import pathlib
import pytest

# Set required env vars before importing app
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests-only")

# Create temp DB and patch DB_PATH before app is imported
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)

import database
database.DB_PATH = pathlib.Path(_db_path)

import app as _app_module
from app import app as flask_app


@pytest.fixture(scope="session")
def app():
    flask_app.config.update({"TESTING": True, "WTF_CSRF_ENABLED": False})
    _app_module.limiter.enabled = False
    _app_module.API_KEY = "test-api-key"
    from database import init_db
    init_db()
    from database import create_user
    try:
        create_user("testuser", "testpassword")
    except Exception:
        pass
    yield flask_app
    os.unlink(_db_path)


@pytest.fixture(autouse=True)
def _reset_analyses_table(app):
    """Clear `analyses` before every test.

    The DB is session-scoped and shared by the whole suite; a test that
    creates a row via create_analysis()/POST /analyze without ever moving it
    past pending/running permanently eats one of the 3 concurrent-analysis
    slots (see run_analyze()'s MAX_CONCURRENT check) for every later test.
    """
    from database import get_conn
    with get_conn() as conn:
        conn.execute("DELETE FROM analyses")


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_in_client(client):
    client.post("/login", data={"username": "testuser", "password": "testpassword"})
    return client


@pytest.fixture
def sample_job_id(app):
    """Create a minimal job row for the test user and return its id."""
    from database import get_conn, get_user
    user = get_user("testuser")
    assert user is not None
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO jobs (user_id, company, role, verdict, verdict_confirmed, analyzed_at)
               VALUES (?, 'Test Corp', 'Test Role', 'worth_considering', 1, date('now'))""",
            (user["id"],),
        )
        job_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return job_id
