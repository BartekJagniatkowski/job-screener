import os
import tempfile
import pathlib
import pytest

# Create temp DB and patch DB_PATH before app is imported
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)

import database
database.DB_PATH = pathlib.Path(_db_path)

import app as _app_module
from app import app as flask_app


@pytest.fixture(scope="session")
def app():
    flask_app.config.update({"TESTING": True, "SECRET_KEY": "test-secret"})
    _app_module.API_KEY = "test-api-key"
    from database import init_db
    init_db()
    # Create a test user (user_id=1)
    from database import create_user
    try:
        create_user("testuser", "testpass")
    except Exception:
        pass  # already exists from a prior run
    yield flask_app
    os.unlink(_db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_in_client(client):
    client.post("/login", data={"username": "testuser", "password": "testpass"})
    return client
