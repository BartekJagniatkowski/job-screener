import pytest
import fetcher


class _FakeResp:
    def __init__(self, location=None, content=b""):
        self.headers = {"Location": location} if location else {}
        self.content = content
        self._is_redirect = location is not None

    @property
    def is_redirect(self):
        return self._is_redirect

    def raise_for_status(self):
        pass


def test_fetch_rss_blocks_redirect_to_internal_host(monkeypatch):
    def fake_is_internal(url):
        return "169.254" in url

    monkeypatch.setattr(fetcher, "_is_internal_host", fake_is_internal)

    def fake_get(url, timeout=None, allow_redirects=None):
        return _FakeResp(location="http://169.254.169.254/latest/meta-data/")

    monkeypatch.setattr(fetcher.requests, "get", fake_get)

    with pytest.raises(ValueError, match="Internal URLs"):
        fetcher.fetch_rss("https://feeds.example/rss")


def test_fetch_rss_too_many_redirects(monkeypatch):
    monkeypatch.setattr(fetcher, "_is_internal_host", lambda url: False)

    def fake_get(url, timeout=None, allow_redirects=None):
        return _FakeResp(location="https://loop.example/next")

    monkeypatch.setattr(fetcher.requests, "get", fake_get)

    with pytest.raises(ValueError, match="Too many redirects"):
        fetcher.fetch_rss("https://loop.example/start")


_SAMPLE_RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Senior Engineer</title>
    <link>https://target.example/jobs/1</link>
    <description>Build things.</description>
  </item>
</channel></rss>"""


def test_fetch_rss_parses_items_with_no_redirect(monkeypatch):
    monkeypatch.setattr(fetcher, "_is_internal_host", lambda url: False)

    def fake_get(url, timeout=None, allow_redirects=None):
        return _FakeResp(content=_SAMPLE_RSS)

    monkeypatch.setattr(fetcher.requests, "get", fake_get)

    items = fetcher.fetch_rss("https://feeds.example/rss")

    assert len(items) == 1
    assert items[0]["title"] == "Senior Engineer"
    assert items[0]["url"] == "https://target.example/jobs/1"
