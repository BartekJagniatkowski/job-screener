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


def test_analyze_repairs_stray_quote_inside_string_value():
    # Model quoted "eco-friendly" inline without escaping it -- breaks a
    # naive json.loads with "Expecting ',' delimiter".
    broken_json = (
        '{"company_name": "Decathlon", '
        '"verdict_summary": "To globalny retailer, ktory nazywa siebie "eco-friendly" pracodawca.", '
        '"verdict": "rejected"}'
    )

    def fake_post_api(payload_bytes, api_key):
        return {"content": [{"type": "text", "text": broken_json}]}

    with patch("analyzer._post_api", side_effect=fake_post_api):
        result = analyzer.analyze(_user(), "some listing", "text", "fake-key")

    assert result["company_name"] == "Decathlon"
    assert "eco-friendly" in result["verdict_summary"]
    assert result["verdict"] == "rejected"


def test_escape_json_string_controls_repairs_stray_quote():
    broken = '{"a": "he said "hi" to me"}'
    repaired = analyzer._escape_json_string_controls(broken)
    assert json.loads(repaired) == {"a": 'he said "hi" to me'}


def test_escape_json_string_controls_escapes_literal_newline():
    broken = '{"a": "line one\nline two"}'
    repaired = analyzer._escape_json_string_controls(broken)
    assert json.loads(repaired) == {"a": "line one\nline two"}
