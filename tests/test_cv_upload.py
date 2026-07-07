import io

import app as app_module


def test_cv_upload_success(logged_in_client):
    data = {"cv_file": (io.BytesIO(b"Senior Engineer, 10 years"), "cv.txt")}
    resp = logged_in_client.post(
        "/settings/cv_upload", data=data, content_type="multipart/form-data"
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["text"] == "Senior Engineer, 10 years"


def test_cv_upload_unsupported_extension(logged_in_client):
    data = {"cv_file": (io.BytesIO(b"whatever"), "cv.rtf")}
    resp = logged_in_client.post(
        "/settings/cv_upload", data=data, content_type="multipart/form-data"
    )
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_cv_upload_no_file(logged_in_client):
    resp = logged_in_client.post(
        "/settings/cv_upload", data={}, content_type="multipart/form-data"
    )
    assert resp.status_code == 400


def test_cv_upload_oversized_file(logged_in_client):
    big = b"a" * 3_000_000  # over the 2MB MAX_CONTENT_LENGTH cap
    data = {"cv_file": (io.BytesIO(big), "cv.txt")}
    resp = logged_in_client.post(
        "/settings/cv_upload", data=data, content_type="multipart/form-data"
    )
    assert resp.status_code == 413


def test_cv_upload_rate_limited(logged_in_client):
    app_module.limiter.enabled = True
    try:
        responses = []
        for _ in range(11):
            data = {"cv_file": (io.BytesIO(b"some cv text"), "cv.txt")}
            r = logged_in_client.post(
                "/settings/cv_upload", data=data, content_type="multipart/form-data"
            )
            responses.append(r.status_code)
        assert 429 in responses, f"Expected a 429 response, got: {set(responses)}"
    finally:
        app_module.limiter.enabled = False
