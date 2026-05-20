import pytest


def test_password_change_success(logged_in_client):
    resp = logged_in_client.post("/settings/password", data={
        "current_password": "testpassword",
        "new_password": "newpassword123",
        "new_password2": "newpassword123",
    })
    assert resp.status_code == 302
    # can still log in with new password
    c2 = logged_in_client.application.test_client()
    r = c2.post("/login", data={"username": "testuser", "password": "newpassword123"})
    assert r.status_code == 302
    # restore for other tests
    restore = logged_in_client.post("/settings/password", data={
        "current_password": "newpassword123",
        "new_password": "testpassword",
        "new_password2": "testpassword",
    })
    assert restore.status_code == 302


def test_password_change_wrong_current(logged_in_client):
    resp = logged_in_client.post("/settings/password", data={
        "current_password": "wrongpass",
        "new_password": "newpassword123",
        "new_password2": "newpassword123",
    })
    assert resp.status_code == 200
    assert b"incorrect" in resp.data.lower()


def test_password_change_mismatch(logged_in_client):
    resp = logged_in_client.post("/settings/password", data={
        "current_password": "testpassword",
        "new_password": "newpassword123",
        "new_password2": "different456",
    })
    assert resp.status_code == 200
    assert b"match" in resp.data.lower()


def test_password_change_too_short(logged_in_client):
    resp = logged_in_client.post("/settings/password", data={
        "current_password": "testpassword",
        "new_password": "short",
        "new_password2": "short",
    })
    assert resp.status_code == 200
    assert b"10" in resp.data


def test_password_change_nine_chars_rejected(logged_in_client):
    resp = logged_in_client.post("/settings/password", data={
        "current_password": "testpassword",
        "new_password": "ninechars",
        "new_password2": "ninechars",
    })
    assert resp.status_code == 200
    assert b"10" in resp.data


def test_password_change_requires_login(client):
    resp = client.post("/settings/password", data={
        "current_password": "testpassword",
        "new_password": "newpassword123",
        "new_password2": "newpassword123",
    })
    assert resp.status_code in (302, 401)
