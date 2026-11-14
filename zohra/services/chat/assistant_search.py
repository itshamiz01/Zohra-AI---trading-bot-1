"""Bounded public web/news search, separate from all trading agents."""
import ipaddress
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value, limit):
    parser = _PlainText()
    parser.feed(str(value or "")[:limit * 3])
    return " ".join(" ".join(parser.parts).split())[:limit]


def public_source_url(value):
    if not isinstance(value, str) or len(value) > 2048 or re.search(r"[\s\\\x00-\x1f]", value):
        return None
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower().rstrip(".")
        if url.scheme not in {"http", "https"} or url.username or url.password or url.port not in {None, 80, 443}:
            return None
        if "." not in host or host.endswith((".localhost", ".local", ".internal", ".test")):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            if not re.fullmatch(r"[a-z0-9.-]+", host) or host.replace(".", "").isdigit():
                return None
        return value
    except ValueError:
        return None


def _search_provider(query, kind, max_results, recency):
    # Explicit providers avoid unrelated extract/P2P features. TLS stays on.
    from ddgs import DDGS
    client = DDGS(timeout=8, verify=True)
    method = client.news if kind == "news" else client.text
    return method(query, region="us-en", safesearch="moderate", backend="bing,brave" if kind == "web" else "bing,yahoo",
                  timelimit=recency, max_results=max_results)


def search_web(query, kind="web", max_results=5, recency=None):
    if not isinstance(query, str) or not query.strip() or len(query) > 400:
        return {"status": "invalid", "error": "A public search query of 1 to 400 characters is required."}
    if kind not in {"web", "news"} or recency not in {None, "d", "w", "m", "y"}:
        return {"status": "invalid", "error": "Invalid search type or recency."}
    if kind == "news" and recency == "y":
        return {"status": "invalid", "error": "News recency supports day, week, or month."}
    if not isinstance(max_results, int) or isinstance(max_results, bool) or not 1 <= max_results <= 5:
        return {"status": "invalid", "error": "Search is limited to 1 to 5 results."}
    if re.search(r"(?:sk-|gsk_|AIza)[A-Za-z0-9_-]{20,}|\b(?:password|api[_ -]?key|access[_ -]?token|account[_ -]?number|iban)\s*[:=]|\b\d{10,}\b|[\w.+-]+@[\w.-]+\.[a-z]{2,}", query, re.I):
        return {"status": "blocked", "error": "Do not send credentials or private account/contact details to public search."}
    now = datetime.now(timezone.utc)
    result = {"provider": "DDGS public metasearch", "kind": kind,
              "retrieved_at": now.isoformat(), "results": [],
              "evidence": "Search snippets only; full pages have not been read or independently verified. Publication dates are reported by search engines, not independently checked."}
    try:
        rows = _search_provider(query.strip(), kind, max_results, recency)
    except Exception:
        return {**result, "status": "unavailable", "error": "Public search is unavailable or rate-limited. Do not invent results."}
    seen = set()
    for row in (rows or [])[:20]:
        if not isinstance(row, dict):
            continue
        url = public_source_url(row.get("url") or row.get("href"))
        if not url or url in seen:
            continue
        title = plain_text(row.get("title"), 240)
        if not title:
            continue
        published_at = plain_text(row.get("date"), 80) or None
        if kind == "news" and published_at:
            try:
                published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                published = published.replace(tzinfo=timezone.utc) if published.tzinfo is None else published
                age = now - published
                if age < timedelta(days=-1) or (recency and age > timedelta(days={"d": 1, "w": 7, "m": 31}[recency])):
                    continue
            except ValueError:
                pass
        seen.add(url)
        result["results"].append({"title": title, "url": url,
            "snippet": plain_text(row.get("body"), 900),
            "published_at": published_at,
            "publisher": plain_text(row.get("source"), 120) or urlsplit(url).hostname})
        if len(result["results"]) == max_results:
            break
    return {**result, "status": "ok" if result["results"] else "no_results"}
