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

    def iter_content(self, chunk_size):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i:i + chunk_size]

    def close(self):
        pass


def test_fetch_rss_blocks_redirect_to_internal_host(monkeypatch):
    def fake_is_internal(url):
        return "169.254" in url

    monkeypatch.setattr(fetcher, "_is_internal_host", fake_is_internal)

    def fake_get(url, **kwargs):
        return _FakeResp(location="http://169.254.169.254/latest/meta-data/")

    monkeypatch.setattr(fetcher.requests, "get", fake_get)

    with pytest.raises(ValueError, match="Internal URLs"):
        fetcher.fetch_rss("https://feeds.example/rss")


def test_fetch_rss_too_many_redirects(monkeypatch):
    monkeypatch.setattr(fetcher, "_is_internal_host", lambda url: False)

    def fake_get(url, **kwargs):
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

    def fake_get(url, **kwargs):
        return _FakeResp(content=_SAMPLE_RSS)

    monkeypatch.setattr(fetcher.requests, "get", fake_get)

    items = fetcher.fetch_rss("https://feeds.example/rss")

    assert len(items) == 1
    assert items[0]["title"] == "Senior Engineer"
    assert items[0]["url"] == "https://target.example/jobs/1"


def test_fetch_rss_rejects_oversized_body(monkeypatch):
    monkeypatch.setattr(fetcher, "_is_internal_host", lambda url: False)
    big = b"x" * (fetcher._MAX_BYTES + 1)
    monkeypatch.setattr(fetcher.requests, "get", lambda url, **kw: _FakeResp(content=big))

    with pytest.raises(ValueError, match="too large"):
        fetcher.fetch_rss("https://feeds.example/rss")


def test_fetch_rss_rejects_entity_declarations(monkeypatch):
    monkeypatch.setattr(fetcher, "_is_internal_host", lambda url: False)
    bomb = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel/></rss>'
    monkeypatch.setattr(fetcher.requests, "get", lambda url, **kw: _FakeResp(content=bomb))

    with pytest.raises(ValueError, match="entity"):
        fetcher.fetch_rss("https://feeds.example/rss")


@pytest.mark.parametrize("url", [
    "http://[::1]/feed",
    "http://[::ffff:127.0.0.1]/feed",
    "http://127.0.0.1/feed",
    "http://localhost/feed",
])
def test_is_internal_host_blocks_loopback_forms(url):
    from scraper import _is_internal_host
    assert _is_internal_host(url)
