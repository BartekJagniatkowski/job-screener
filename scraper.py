"""
scraper.py — fetches job listing content from URLs
Returns (text, error_code, error_detail) where error_code is:
  None       — success
  'timeout'  — server did not respond in time
  'notfound' — page not found (404)
  'blocked'  — page exists but blocks access (403, JS, empty content)
  'network'  — other network error
"""

import ipaddress
import socket
import urllib.request
import urllib.error
import re
from html.parser import HTMLParser
from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse

_PRIVATE_NETWORKS = [
    ipaddress.ip_network(n) for n in [
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        "127.0.0.0/8", "169.254.0.0/16", "0.0.0.0/8",
        "::1/128", "fc00::/7", "fe80::/10",
    ]
]


class _RedirectTo(Exception):
    """Raised by _NoRedirect to surface a redirect target without following it."""
    def __init__(self, url):
        super().__init__(url)
        self.url = url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise _RedirectTo(newurl)


_opener = urllib.request.build_opener(_NoRedirect)


def _is_internal_host(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        ip = ipaddress.ip_address(socket.gethostbyname(host))
        return any(ip in net for net in _PRIVATE_NETWORKS)
    except Exception:
        return False


# Query string parameters to strip from URL (all lowercase — compared via k.lower())
_STRIP_PARAMS = {
    # generic tracking
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'utm_id', 'utm_source_platform', 'utm_creative_format', 'utm_marketing_tactic',
    # LinkedIn
    'refid', 'trackingid', 'originalsubdomain',
    # Indeed
    'from', 'vjk', 'jsa',
    # generic
    'ref', 'source', 'src', 'referrer', 'origin',
    'fbclid', 'gclid', 'msclkid', 'dclid', 'twclid',
    'mc_eid', 'mc_cid',
    '_ga', '_gl',
}


def normalize_url(url: str) -> str:
    """
    Remove tracking parameters and noise from URL.
    Preserves job-board-specific parameters (e.g. jobId, currentJobId).
    """
    if not url:
        return url
    url = url.strip()
    if not url:
        return url
    if not url.startswith('http'):
        return url  # user pasted content directly
    try:
        parsed = urlparse(url.strip())
        # strip fragment (#...) — always noise
        # filter query parameters
        clean_params = [
            (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False)
            if k.lower() not in _STRIP_PARAMS
        ]
        clean = parsed._replace(
            query=urlencode(clean_params),
            fragment=''
        )
        return urlunparse(clean)
    except Exception:
        return url.strip()


class _TextExtractor(HTMLParser):
    """Extracts text from HTML, skipping scripts, styles, and metadata."""

    SKIP_TAGS = {'script', 'style', 'head', 'noscript', 'svg', 'iframe'}

    def __init__(self):
        super().__init__()
        self._skip = 0
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self.chunks.append(stripped)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    text = '\n'.join(parser.chunks)
    # compress multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _looks_like_js_wall(html: str, text: str) -> bool:
    """Heuristics for detecting pages that require JavaScript."""
    html_lower = html.lower()
    signals = [
        'enable javascript', 'javascript is required', 'javascript is disabled',
        'please enable javascript', 'noscript', 'cf-browser-verification',
        'challenge-platform', '__cf_chl', 'recaptcha',
    ]
    return any(s in html_lower for s in signals) or (len(html) > 5000 and len(text) < 200)


# Domains that always block scraping — return blocked without attempting a request
BLOCKED_DOMAINS = {
    'linkedin.com', 'www.linkedin.com',
    'indeed.com', 'pl.indeed.com', 'www.indeed.com',
    'glassdoor.com', 'www.glassdoor.com',
    'pracuj.pl', 'www.pracuj.pl',
    'nofluffjobs.com', 'www.nofluffjobs.com',
    'justjoin.it', 'www.justjoin.it',
}

BLOCKED_DOMAIN_MSG = {
    'linkedin.com': 'LinkedIn requires login and blocks automated access. Copy the job description manually.',
    'indeed.com': 'Indeed blocks automated access. Copy the job description manually.',
    'glassdoor.com': 'Glassdoor requires login. Copy the job description manually.',
    'pracuj.pl': 'Pracuj.pl blocks automated access. Copy the job description manually.',
    'nofluffjobs.com': 'NoFluffJobs blocks automated access. Copy the job description manually.',
    'justjoin.it': 'JustJoin.it blocks automated access. Copy the job description manually.',
}

def fetch(url: str, timeout: int = 12) -> tuple:
    """
    Fetch job listing content from a URL.
    Returns: (text: str|None, error_code: str|None, error_detail: str|None)
    """
    try:
        domain = urlparse(url).netloc.lower()
    except Exception:
        domain = ''
    base_domain = '.'.join(domain.split('.')[-2:]) if domain else ''
    if domain in BLOCKED_DOMAINS or base_domain in BLOCKED_DOMAINS:
        msg = BLOCKED_DOMAIN_MSG.get(domain) or BLOCKED_DOMAIN_MSG.get(base_domain) or               'This site blocks automated access. Copy the job description manually.'
        return None, 'blocked', msg

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/122.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,*/*;q=0.9',
        'Accept-Language': 'en,pl;q=0.9',
    }

    current_url = url
    resp = None
    for _ in range(5):
        if _is_internal_host(current_url):
            return None, 'blocked', 'Access to internal network addresses is not allowed.'
        req = urllib.request.Request(current_url, headers=headers)
        try:
            resp = _opener.open(req, timeout=timeout)
            break
        except _RedirectTo as r:
            current_url = r.url
            continue
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, 'notfound', f'Page not found (HTTP {e.code})'
            if e.code in (401, 403, 429):
                return None, 'blocked', f'Access blocked (HTTP {e.code})'
            return None, 'network', f'HTTP error {e.code}'
        except urllib.error.URLError as e:
            reason = str(e.reason)
            if 'timed out' in reason.lower() or 'timeout' in reason.lower():
                return None, 'timeout', 'Server did not respond in time (timeout)'
            return None, 'network', f'Network error: {reason}'
        except TimeoutError:
            return None, 'timeout', 'Server did not respond in time (timeout)'
        except Exception as e:
            return None, 'network', f'Unexpected error: {str(e)}'
    else:
        return None, 'network', 'Too many redirects'

    with resp:
        content_type = resp.headers.get('Content-Type', '')
        if 'text/html' not in content_type and 'text/plain' not in content_type:
            return None, 'blocked', f'Unsupported content type: {content_type}'
        html = resp.read().decode('utf-8', errors='replace')
        max_size = 5 * 1024 * 1024  # 5MB
        if len(html) > max_size:
            return None, 'blocked', f'Page returned too much content: {len(html)} bytes (likely requires JavaScript)'

    text = _html_to_text(html)

    if _looks_like_js_wall(html, text):
        return None, 'blocked', 'Page requires JavaScript or uses bot protection (Cloudflare, etc.)'

    if len(text) < 100:
        return None, 'blocked', 'Page did not return readable content — likely requires login or JavaScript'

    return text, None, None