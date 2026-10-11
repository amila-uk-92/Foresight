"""Interchangeable collectors. Public Fed RSS is a forward source, not an archive."""
import html
import re
from email.utils import parsedate_to_datetime
from typing import Protocol
import xml.etree.ElementTree as ET
import httpx
from backend.app.news.contracts import ArticleInput


class NewsSource(Protocol):
    key: str
    def collect(self, check): ...


class FederalReserveRSS:
    key = "federal-reserve"
    url = "https://www.federalreserve.gov/feeds/press_all.xml"
    def collect(self, check=lambda: None):
        check()
        with httpx.Client(timeout=25, follow_redirects=False) as client:
            r = client.get(self.url, headers={"User-Agent": "ForesightResearch/2.0"})
            r.raise_for_status()
        if len(r.content) > 2_000_000 or b"<!DOCTYPE" in r.content.upper():
            raise ValueError("Unsafe or oversized feed")
        rows = []
        for item in ET.fromstring(r.content).findall("./channel/item")[:100]:
            check()
            date = item.findtext("pubDate")
            if not date:
                continue
            rows.append(ArticleInput(
                provider_article_id=item.findtext("guid") or item.findtext("link"),
                url=item.findtext("link"), publisher="Federal Reserve Board",
                headline=item.findtext("title") or "Federal Reserve release",
                text=html.unescape(re.sub(r"<[^>]*>", " ", item.findtext("description") or "")),
                published_at=parsedate_to_datetime(date).isoformat(), content_scope="snippet",
                rights="Public Federal Reserve RSS payload; no linked article scraping; verify reuse terms for redistribution.",
            ))
        return rows


SOURCES = {FederalReserveRSS.key: FederalReserveRSS()}


def register_news_source(source):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", source.key):
        raise ValueError("Invalid news source key")
    SOURCES[source.key] = source
