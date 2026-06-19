import pytest
import scraper


def test_fetch_blocks_redirect_to_internal_host(monkeypatch):
    """A redirect to a private IP must be blocked, not followed."""
    calls = {"n": 0}

    def fake_is_internal(url):
        calls["n"] += 1
        return calls["n"] > 1  # initial URL passes; redirect target is internal

    monkeypatch.setattr(scraper, "_is_internal_host", fake_is_internal)

    def fake_open(req, timeout=None):
        raise scraper._RedirectTo("http://169.254.169.254/latest/meta-data/")

    monkeypatch.setattr(scraper._opener, "open", fake_open)

    text, err, detail = scraper.fetch("https://attacker.example/redirect")

    assert text is None
    assert err == "blocked"
    assert calls["n"] == 2


class _FakeResponse:
    def __init__(self, html: str):
        self._html = html.encode("utf-8")
        self.headers = {"Content-Type": "text/html"}

    def read(self):
        return self._html

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def test_fetch_follows_redirect_to_external_host(monkeypatch):
    """A redirect to another public host must still succeed."""
    monkeypatch.setattr(scraper, "_is_internal_host", lambda url: False)
    calls = {"n": 0}

    def fake_open(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise scraper._RedirectTo("https://target.example/jobs/123/")
        body = "<html><body>" + ("word " * 50) + "</body></html>"
        return _FakeResponse(body)

    monkeypatch.setattr(scraper._opener, "open", fake_open)

    text, err, detail = scraper.fetch("https://short.example/abc")

    assert err is None
    assert text is not None
    assert calls["n"] == 2


def test_fetch_too_many_redirects(monkeypatch):
    """A redirect chain longer than 5 hops must not hang or loop forever."""
    monkeypatch.setattr(scraper, "_is_internal_host", lambda url: False)

    def fake_open(req, timeout=None):
        raise scraper._RedirectTo("https://loop.example/next")

    monkeypatch.setattr(scraper._opener, "open", fake_open)

    text, err, detail = scraper.fetch("https://loop.example/start")

    assert text is None
    assert err == "network"
    assert "redirect" in detail.lower()
