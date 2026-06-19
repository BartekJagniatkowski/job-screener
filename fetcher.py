"""
fetcher.py — fetch job listings from external feeds (Remotive, Lever, Greenhouse, RSS)
Returns list of dicts: {external_id, title, company, url, description}
"""

import re
import requests
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import urljoin
from scraper import _is_internal_host

_TIMEOUT = 10


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(s or "")).strip()


def fetch_remoteok(tag: str) -> list[dict]:
    resp = requests.get(
        "https://remoteok.com/api",
        params={"tag": tag},
        timeout=_TIMEOUT,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    resp.raise_for_status()
    return [
        {
            "external_id": str(j["id"]),
            "title": j.get("position", ""),
            "company": j.get("company", ""),
            "url": j.get("url", ""),
            "description": _strip_html(j.get("description", "")),
        }
        for j in resp.json()
        if isinstance(j, dict) and j.get("position") and j.get("url")
    ]


def _lever_description(j: dict) -> str:
    parts = [j.get("descriptionPlain", "") or ""]
    for lst in j.get("lists", []):
        parts.append(lst.get("text", ""))
        for item in lst.get("content", []):
            parts.append(f"- {_strip_html(item)}")
    return "\n".join(p for p in parts if p).strip()


def fetch_lever(company_slug: str) -> list[dict]:
    resp = requests.get(
        f"https://api.lever.co/v0/postings/{company_slug}",
        params={"mode": "json"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return [
        {
            "external_id": j["id"],
            "title": j.get("text", ""),
            "company": company_slug,
            "url": j.get("hostedUrl", ""),
            "description": _lever_description(j),
        }
        for j in resp.json()
        if j.get("hostedUrl")
    ]


def fetch_greenhouse(company_slug: str) -> list[dict]:
    resp = requests.get(
        f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs",
        params={"content": "true"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return [
        {
            "external_id": str(j["id"]),
            "title": j.get("title", ""),
            "company": company_slug,
            "url": j.get("absolute_url", ""),
            "description": _strip_html(j.get("content", "")),
        }
        for j in resp.json().get("jobs", [])
        if j.get("absolute_url")
    ]


def fetch_rss(feed_url: str) -> list[dict]:
    url = feed_url
    resp = None
    for _ in range(5):
        if _is_internal_host(url):
            raise ValueError("Internal URLs are not allowed.")
        resp = requests.get(url, timeout=_TIMEOUT, allow_redirects=False)
        if resp.is_redirect:
            url = urljoin(url, resp.headers["Location"])
            continue
        resp.raise_for_status()
        break
    else:
        raise ValueError("Too many redirects.")

    root = ET.fromstring(resp.content)
    items = []
    for item in root.findall(".//item"):
        link = item.findtext("link", "").strip()
        if not link:
            continue
        items.append({
            "external_id": link,
            "title": item.findtext("title", ""),
            "company": "",
            "url": link,
            "description": _strip_html(item.findtext("description", "")),
        })
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("a:entry", ns):
        link_el = entry.find("a:link", ns)
        link = (link_el.get("href", "") if link_el is not None else "").strip()
        if not link:
            continue
        desc = _strip_html(
            entry.findtext("a:summary", "", ns) or
            entry.findtext("a:content", "", ns) or ""
        )
        items.append({
            "external_id": link,
            "title": entry.findtext("a:title", "", ns),
            "company": "",
            "url": link,
            "description": desc,
        })
    return items


def fetch_feed(feed: dict) -> list[dict]:
    dispatch = {
        "remoteok": fetch_remoteok,
        "lever": fetch_lever,
        "greenhouse": fetch_greenhouse,
        "rss": fetch_rss,
    }
    fn = dispatch.get(feed["type"])
    return fn(feed["source"]) if fn else []
