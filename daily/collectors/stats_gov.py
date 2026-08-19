from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from daily.collectors.base import Collector, DiscoveredItem
from daily.models import Document, utc_now


ARTICLE_RE = re.compile(r"/sj/(?:zxfb|sjjd|zxfbhjd|xwfbh)/.*?t\d{8}_\d+\.html$")
DATE_IN_URL_RE = re.compile(r"/t(\d{4})(\d{2})(\d{2})_")
DATE_TEXT_RE = re.compile(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?")
TIME_TEXT_RE = re.compile(r"20\d{2}[年./-]\d{1,2}[月./-]\d{1,2}日?\s+(\d{1,2}:\d{2})")


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url)
    path = re.sub(r"/{2,}", "/", parts.path)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


class StatsGovCollector(Collector):
    source_id = "stats_gov"
    source_name = "国家统计局"
    channel = "economy"

    def __init__(self, list_urls: list[str], timeout: int = 25, retries: int = 3,
                 user_agent: str = "DailyIntelligence/0.1", max_documents: int = 30):
        self.list_urls = list_urls
        self.timeout = timeout
        self.retries = retries
        self.max_documents = max_documents
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Language": "zh-CN,zh;q=0.9"})

    def _get(self, url: str) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                response.encoding = response.apparent_encoding or "utf-8"
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(0.5 * (2 ** attempt))
        raise RuntimeError(f"国家统计局请求失败: {url}: {last_error}")

    def discover(self) -> list[DiscoveredItem]:
        found: dict[str, DiscoveredItem] = {}
        errors: list[str] = []
        for list_url in self.list_urls:
            try:
                soup = BeautifulSoup(self._get(list_url).text, "html.parser")
            except Exception as exc:
                errors.append(str(exc))
                continue
            for anchor in soup.select("a[href]"):
                url = canonicalize_url(urljoin(list_url, anchor.get("href", "")))
                if not ARTICLE_RE.search(urlsplit(url).path):
                    continue
                title = anchor.get_text(" ", strip=True)
                date_match = DATE_IN_URL_RE.search(url)
                publish_date = "-".join(date_match.groups()) if date_match else None
                found[url] = DiscoveredItem(url=url, title=title, publish_date=publish_date)
        if not found and errors:
            raise RuntimeError("; ".join(errors))
        return sorted(found.values(), key=lambda x: (x.publish_date or "", x.url), reverse=True)[:self.max_documents]

    def collect(self, item: DiscoveredItem) -> Document:
        response = self._get(item.url)
        soup = BeautifulSoup(response.text, "html.parser")
        title_node = soup.select_one("h1")
        page_title = soup.title.get_text(" ", strip=True).removesuffix(" - 国家统计局") if soup.title else ""
        title = (title_node.get_text(" ", strip=True) if title_node else "") or page_title or item.title
        content_node = soup.select_one(".TRS_Editor, .trs_editor_view, .txt-content, .detail-text-content, .article-content, .content, #zoom")
        if content_node is None:
            content_node = soup.select_one("body")
        if content_node is None:
            raise ValueError(f"无法定位正文: {item.url}")
        for node in content_node.select("script, style, nav, .share"):
            node.decompose()
        content = "\n".join(line.strip() for line in content_node.get_text("\n").splitlines() if line.strip())
        if not title or len(content) < 30:
            raise ValueError(f"正文过短或缺少标题: {item.url}")
        page_text = soup.get_text(" ", strip=True)
        date_match = DATE_TEXT_RE.search(page_text)
        publish_date = item.publish_date
        if date_match:
            publish_date = f"{int(date_match.group(1)):04d}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
        time_match = TIME_TEXT_RE.search(page_text)
        publish_time = time_match.group(1) if time_match else None
        canonical = canonicalize_url(item.url)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        document_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
        related = []
        for anchor in content_node.select("a[href]"):
            related_url = canonicalize_url(urljoin(item.url, anchor.get("href", "")))
            if ARTICLE_RE.search(urlsplit(related_url).path) and related_url != canonical:
                related.append(related_url)
        return Document(
            id=document_id, channel=self.channel, source_id=self.source_id,
            source_name=self.source_name, url=item.url, canonical_url=canonical,
            title=title, publish_date=publish_date, publish_time=publish_time,
            crawl_time=utc_now(), content=content, content_hash=content_hash,
            department=self.source_name, related_urls=sorted(set(related)),
            raw_metadata={"http_status": response.status_code, "content_type": response.headers.get("content-type", "")},
        )
