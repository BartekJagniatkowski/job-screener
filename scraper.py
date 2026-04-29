"""
scraper.py — pobieranie treści ogłoszeń z URL
Zwraca (text, error_code, error_detail) gdzie error_code to:
  None       — sukces
  'timeout'  — serwer nie odpowiedział w czasie
  'notfound' — strona nie istnieje (404)
  'blocked'  — strona istnieje ale blokuje dostęp (403, JS, pusta treść)
  'network'  — inny błąd sieciowy
"""

import urllib.request
import urllib.error
import re
from html.parser import HTMLParser
from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse


# Parametry query string do usunięcia z URL (wszystkie lowercase — porównanie przez k.lower())
_STRIP_PARAMS = {
    # tracking ogólny
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'utm_id', 'utm_source_platform', 'utm_creative_format', 'utm_marketing_tactic',
    # LinkedIn
    'refid', 'trackingid', 'originalsubdomain',
    # Indeed
    'from', 'vjk', 'jsa',
    # ogólne
    'ref', 'source', 'src', 'referrer', 'origin',
    'fbclid', 'gclid', 'msclkid', 'dclid', 'twclid',
    'mc_eid', 'mc_cid',
    '_ga', '_gl',
}


def normalize_url(url: str) -> str:
    """
    Usuwa parametry śledzące i śmieci z URL.
    Zachowuje parametry specyficzne dla job boardów (np. jobId, currentJobId).
    """
    if not url:
        return url
    url = url.strip()
    if not url:
        return url
    if not url.startswith('http'):
        return url  # użytkownik wkleił treść
    try:
        parsed = urlparse(url.strip())
        # usuń fragment (#...) — zawsze śmieć
        # filtruj parametry query
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
    """Wyodrębnia tekst z HTML pomijając skrypty, style i metadane."""

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
    # kompresuj wielokrotne puste linie
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _looks_like_js_wall(html: str, text: str) -> bool:
    """Heurystyki wykrywające strony wymagające JavaScriptu."""
    html_lower = html.lower()
    signals = [
        'enable javascript',
        'javascript is required',
        'javascript is disabled',
        'please enable javascript',
        'noscript',
        'cf-browser-verification',
        'challenge-platform',   # Cloudflare
        '__cf_chl',             # Cloudflare challenge
        'recaptcha',
    ]
    for s in signals:
        if s in html_lower:
            return True
    # Bardzo mała treść przy dużym HTML = prawdopodobnie JS wall
    if len(html) > 5000 and len(text) < 200:
        return True
    return False


# Domeny które zawsze blokują scraping — zwracamy blocked bez próby pobierania
BLOCKED_DOMAINS = {
    'linkedin.com', 'www.linkedin.com',
    'indeed.com', 'pl.indeed.com', 'www.indeed.com',
    'glassdoor.com', 'www.glassdoor.com',
    'pracuj.pl', 'www.pracuj.pl',
    'nofluffjobs.com', 'www.nofluffjobs.com',
    'justjoin.it', 'www.justjoin.it',
}

BLOCKED_DOMAIN_MSG = {
    'linkedin.com': 'LinkedIn wymaga zalogowania i blokuje automatyczny dostęp. Skopiuj treść ogłoszenia ręcznie.',
    'indeed.com': 'Indeed blokuje automatyczny dostęp. Skopiuj treść ogłoszenia ręcznie.',
    'glassdoor.com': 'Glassdoor wymaga zalogowania. Skopiuj treść ogłoszenia ręcznie.',
    'pracuj.pl': 'Pracuj.pl blokuje automatyczny dostęp. Skopiuj treść ogłoszenia ręcznie.',
    'nofluffjobs.com': 'NoFluffJobs blokuje automatyczny dostęp. Skopiuj treść ogłoszenia ręcznie.',
    'justjoin.it': 'JustJoin.it blokuje automatyczny dostęp. Skopiuj treść ogłoszenia ręcznie.',
}

def _get_domain(url: str) -> str:
    """Wyodrębnij domenę z URL."""
    try:
        return urlparse(url).netloc.lower()
    except Exception as e:
        print(f"Warning: Could not parse URL '{url}': {e}")
        return ''


def fetch(url: str, timeout: int = 12) -> tuple:
    """
    Pobiera treść ogłoszenia z URL.
    Zwraca: (text: str|None, error_code: str|None, error_detail: str|None)
    """
    # sprawdź znane domeny blokujące przed próbą połączenia
    domain = _get_domain(url)
    base_domain = '.'.join(domain.split('.')[-2:]) if domain else ''
    if domain in BLOCKED_DOMAINS or base_domain in BLOCKED_DOMAINS:
        msg = BLOCKED_DOMAIN_MSG.get(domain) or BLOCKED_DOMAIN_MSG.get(base_domain) or               'Ta strona blokuje automatyczny dostęp. Skopiuj treść ogłoszenia ręcznie.'
        return None, 'blocked', msg

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/122.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,*/*;q=0.9',
        'Accept-Language': 'pl,en;q=0.9',
    }

    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get('Content-Type', '')
            if 'text/html' not in content_type and 'text/plain' not in content_type:
                return None, 'blocked', f'Nieobsługiwany typ treści: {content_type}'
            html = resp.read().decode('utf-8', errors='replace')
            max_size = 5 * 1024 * 1024  # 5MB
            if len(html) > max_size:
                return None, 'blocked', f'Strona zwróciła zbyt dużą treść: {len(html)} bytes (prawdopodobnie wymaga JavaScript)'

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, 'notfound', f'Strona nie istnieje (HTTP {e.code})'
        if e.code in (401, 403, 429):
            return None, 'blocked', f'Dostęp zablokowany (HTTP {e.code})'
        return None, 'network', f'Błąd HTTP {e.code}'

    except urllib.error.URLError as e:
        reason = str(e.reason)
        if 'timed out' in reason.lower() or 'timeout' in reason.lower():
            return None, 'timeout', 'Serwer nie odpowiedział w czasie (timeout)'
        return None, 'network', f'Błąd sieci: {reason}'

    except TimeoutError:
        return None, 'timeout', 'Serwer nie odpowiedział w czasie (timeout)'

    except Exception as e:
        return None, 'network', f'Nieoczekiwany błąd: {str(e)}'

    text = _html_to_text(html)

    if _looks_like_js_wall(html, text):
        return None, 'blocked', 'Strona wymaga JavaScript lub stosuje ochronę przed botami (Cloudflare itp.)'

    if len(text) < 100:
        return None, 'blocked', 'Strona nie zwróciła czytelnej treści — prawdopodobnie wymaga logowania lub JavaScript'

    return text, None, None