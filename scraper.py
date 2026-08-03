"""
scraper.py — URL normalization and the internal-host SSRF guard.

Job listing URLs are no longer fetched on the user's behalf (most job
boards block scraping anyway) — the web app stores them as reference
links only, and the CLI requires pasted text. `_is_internal_host` is
still live: fetcher.py's RSS fetcher uses it to guard each hop of its
own redirect-follow loop.
"""

import ipaddress
import socket
from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse

_PRIVATE_NETWORKS = [
    ipaddress.ip_network(n) for n in [
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        "127.0.0.0/8", "169.254.0.0/16", "0.0.0.0/8",
        "::1/128", "fc00::/7", "fe80::/10",
    ]
]


def _is_internal_host(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return True  # malformed URL — fail closed
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(host))
    except socket.gaierror:
        return False  # host doesn't resolve; the fetch will fail on its own
    except Exception:
        return True  # unexpected error — fail closed
    return any(ip in net for net in _PRIVATE_NETWORKS)


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
