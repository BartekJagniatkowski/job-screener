import json
from unittest.mock import patch
import analyzer


def _user():
    return {"cv": "", "zero_list": "", "yellow_list": "", "criteria": ""}


def _fake_post_api_factory(captured):
    def fake_post_api(payload_bytes, api_key):
        captured["payload"] = json.loads(payload_bytes)
        return {"content": [{"type": "text", "text": '{"company_name": "Unknown", "verdict": "rejected"}'}]}
    return fake_post_api


def test_analyze_truncates_long_pasted_text():
    long_text = "x" * 50000
    captured = {}
    with patch("analyzer._post_api", side_effect=_fake_post_api_factory(captured)):
        analyzer.analyze(_user(), long_text, "text", "fake-key")

    user_msg = captured["payload"]["messages"][0]["content"]
    assert len(user_msg) < 13000  # <job_listing> tag overhead + 12000 cap, generous margin


def test_analyze_truncates_long_text_in_url_mode():
    long_text = "y" * 50000  # doesn't start with "http" — hits the "URL mode but text provided" branch
    captured = {}
    with patch("analyzer._post_api", side_effect=_fake_post_api_factory(captured)):
        analyzer.analyze(_user(), long_text, "url", "fake-key")

    user_msg = captured["payload"]["messages"][0]["content"]
    assert len(user_msg) < 13000


def test_analyze_does_not_truncate_short_pasted_text():
    short_text = "Senior Engineer role at Acme Corp. Remote. Python required."
    captured = {}
    with patch("analyzer._post_api", side_effect=_fake_post_api_factory(captured)):
        analyzer.analyze(_user(), short_text, "text", "fake-key")

    user_msg = captured["payload"]["messages"][0]["content"]
    assert short_text in user_msg


def test_analyze_does_not_truncate_url():
    url = "https://example.com/jobs/12345"
    captured = {}
    with patch("analyzer._post_api", side_effect=_fake_post_api_factory(captured)):
        analyzer.analyze(_user(), url, "url", "fake-key")

    user_msg = captured["payload"]["messages"][0]["content"]
    assert url in user_msg
