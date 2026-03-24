from __future__ import annotations

import json
import random
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .browser_fallback import search_with_playwright
from .config import AppConfig
from .models import SearchTask, SearchVideoSummary
from .parser import SearchParseError, parse_search_page_with_node, parse_search_page_with_regex

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


class BilibiliCollector:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._last_request_at = 0.0
        self._session = requests.Session() if requests is not None else None
        if self._session is not None:
            self._session.headers.update(config.request_headers)

    def _throttle(self) -> None:
        now = time.monotonic()
        delay = random.uniform(self.config.min_delay, self.config.max_delay)
        elapsed = now - self._last_request_at
        if self._last_request_at and elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_at = time.monotonic()

    def _should_retry(self, exc: Exception) -> bool:
        if isinstance(exc, HTTPError):
            return exc.code in {408, 429, 500, 502, 503, 504}
        return isinstance(exc, URLError)

    def _request_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        target = f"{url}?{urlencode(params)}" if params else url
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            self._throttle()
            try:
                if self._session is not None:
                    response = self._session.get(target, timeout=self.config.timeout)
                    response.raise_for_status()
                    response.encoding = response.encoding or "utf-8"
                    return response.text
                request = Request(target, headers=self.config.request_headers)
                with urlopen(request, timeout=self.config.timeout) as response:
                    return response.read().decode("utf-8", errors="replace")
            except Exception as exc:  # pragma: no cover
                last_error = exc
                if attempt >= self.config.max_retries or not self._should_retry(exc):
                    break
                time.sleep(min(10, (2 ** (attempt - 1)) + random.random()))
        if last_error is None:
            raise RuntimeError(f"请求失败: {target}")
        raise last_error

    def _request_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return json.loads(self._request_text(url, params=params))

    def search_videos(self, task: SearchTask) -> list[SearchVideoSummary]:
        query = {"keyword": task.keyword, "page": task.page}
        if task.order:
            query["order"] = task.order
        html = self._request_text("https://search.bilibili.com/all", params=query)
        errors: list[str] = []
        for parser in (
            lambda content: parse_search_page_with_node(content, node_bin=self.config.node_bin),
            parse_search_page_with_regex,
        ):
            try:
                return parser(html)
            except SearchParseError as exc:
                errors.append(str(exc))
        if self.config.browser_fallback:
            return search_with_playwright(task, headless=self.config.browser_headless)
        raise SearchParseError("；".join(errors))

    def fetch_video_detail(self, bvid: str) -> dict[str, Any]:
        payload = self._request_json(
            "https://api.bilibili.com/x/web-interface/view",
            params={"bvid": bvid},
        )
        if payload.get("code") != 0:
            raise RuntimeError(f"获取详情失败: {bvid}, code={payload.get('code')}")
        return payload["data"]

    def fetch_video_tags(self, bvid: str) -> list[str]:
        payload = self._request_json(
            "https://api.bilibili.com/x/tag/archive/tags",
            params={"bvid": bvid},
        )
        if payload.get("code") != 0:
            return []
        return [item.get("tag_name", "").strip() for item in payload.get("data") or [] if item.get("tag_name")]
