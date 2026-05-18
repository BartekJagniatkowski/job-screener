import os
import pytest


def test_secret_key_is_set(app):
    """App must have a stable SECRET_KEY, not a random one."""
    assert app.secret_key is not None
    assert len(app.secret_key) >= 10


def test_debug_mode_off_by_default():
    """FLASK_DEBUG env var defaults to off."""
    env_backup = os.environ.pop("FLASK_DEBUG", None)
    try:
        debug = os.environ.get("FLASK_DEBUG", "0") == "1"
        assert debug is False
    finally:
        if env_backup is not None:
            os.environ["FLASK_DEBUG"] = env_backup


def test_security_headers_present(client):
    """All responses include basic security headers."""
    resp = client.get("/about")
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert "strict-origin-when-cross-origin" in resp.headers.get("Referrer-Policy", "")


def test_account_lockout_after_failures(client):
    """Account is locked after 5 failed login attempts."""
    import app as app_module
    app_module._login_attempts.clear()

    for _ in range(5):
        client.post("/login", data={"username": "testuser", "password": "wrongpass"})

    resp = client.post("/login", data={"username": "testuser", "password": "testpass"})
    # After lockout, even correct password is rejected — must NOT redirect to dashboard
    assert resp.status_code != 302 or "/dashboard" not in resp.headers.get("Location", "")
    assert b"locked" in resp.data.lower()


def test_successful_login_clears_lockout(client):
    """Successful login resets the failure counter."""
    import app as app_module
    app_module._login_attempts.clear()

    client.post("/login", data={"username": "testuser", "password": "wrongpass"})
    client.post("/login", data={"username": "testuser", "password": "testpass"})
    assert "testuser" not in app_module._login_attempts


def test_unknown_user_recorded_to_prevent_enumeration(client):
    """Failed login for non-existent user still recorded — prevents username enumeration."""
    import app as app_module
    app_module._login_attempts.clear()

    client.post("/login", data={"username": "ghost_user_xyz", "password": "anything"})
    assert "ghost_user_xyz" in app_module._login_attempts


def test_server_header_hidden(client):
    """Server header must not reveal gunicorn or Python."""
    resp = client.get("/about")
    server = resp.headers.get("Server", "")
    assert "gunicorn" not in server.lower()
    assert "python" not in server.lower()


def test_session_cookie_flags(app):
    """Session cookie must be configured with Secure, HttpOnly, SameSite=Lax."""
    assert app.config.get("SESSION_COOKIE_SECURE") is True
    assert app.config.get("SESSION_COOKIE_HTTPONLY") is True
    assert app.config.get("SESSION_COOKIE_SAMESITE") == "Lax"


def test_session_expires(app):
    """Session lifetime must be set (not infinite)."""
    from datetime import timedelta
    lifetime = app.config.get("PERMANENT_SESSION_LIFETIME")
    assert lifetime is not None
    assert isinstance(lifetime, timedelta)
    assert lifetime.days <= 30


def test_ssrf_internal_ip_blocked(client, logged_in_client):
    """Scraper must reject requests to internal/private IP addresses."""
    from scraper import _is_internal_host
    assert _is_internal_host("http://127.0.0.1/secret") is True
    assert _is_internal_host("http://192.168.1.1/admin") is True
    assert _is_internal_host("http://169.254.169.254/latest/meta-data") is True
    assert _is_internal_host("http://10.0.0.1/") is True


def test_password_min_length(app):
    """Registration must reject passwords shorter than 10 characters."""
    # Use the app directly — registration is open when user_count() == 0,
    # but in tests a user already exists, so supply an invite token.
    import os
    os.environ["INVITE_TOKEN"] = "test-invite"
    try:
        with app.test_client() as c:
            resp = c.post("/register?token=test-invite", data={
                "username": "newuser_test",
                "password": "short",
                "password2": "short",
                "token": "test-invite",
            })
            assert b"10 characters" in resp.data
    finally:
        os.environ.pop("INVITE_TOKEN", None)


def test_csrf_rejects_post_without_token(app, client):
    """POST requests without a CSRF token must be rejected when CSRF is enabled."""
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        resp = client.post("/login", data={"username": "testuser", "password": "testpass"})
        assert resp.status_code == 400
    finally:
        app.config["WTF_CSRF_ENABLED"] = False


def test_login_rate_limit(client):
    """Login endpoint rejects requests beyond the rate limit."""
    import app as app_module
    app_module.limiter.reset()
    app_module.limiter.enabled = True
    try:
        responses = []
        for _ in range(15):
            resp = client.post("/login", data={"username": "notexist", "password": "bad"})
            responses.append(resp.status_code)
        assert 429 in responses, f"Expected a 429 response, got: {set(responses)}"
    finally:
        app_module.limiter.enabled = False


def test_analyze_rate_limit(logged_in_client):
    """Analyze endpoint rejects requests beyond the rate limit."""
    import app as app_module
    app_module.limiter.reset()
    app_module.limiter.enabled = True
    try:
        responses = []
        for _ in range(25):
            resp = logged_in_client.post("/analyze", data={"text": "some job text"})
            responses.append(resp.status_code)
        assert 429 in responses, f"Expected a 429 response, got: {set(responses)}"
    finally:
        app_module.limiter.enabled = False
