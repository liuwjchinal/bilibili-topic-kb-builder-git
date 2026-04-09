from __future__ import annotations

from urllib.parse import urlencode

from .models import SearchTask, SearchVideoSummary


def search_with_playwright(task: SearchTask, headless: bool = True) -> list[SearchVideoSummary]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "未安装 playwright。请执行 `pip install -r requirements-optional.txt` 后再启用浏览器兜底。"
        ) from exc

    query = {"keyword": task.keyword, "page": task.page}
    if task.order:
        query["order"] = task.order
    url = f"https://search.bilibili.com/all?{urlencode(query)}"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=45000)
        payload = page.evaluate(
            """() => {
                const response = window.__pinia?.searchResponse?.searchAllResponse;
                const bucket = (response?.result || []).find((item) => item.result_type === 'video');
                return bucket?.data || [];
            }"""
        )
        browser.close()

    results: list[SearchVideoSummary] = []
    for item in payload:
        bvid = item.get("bvid")
        if not bvid:
            continue
        results.append(
            SearchVideoSummary(
                bvid=bvid,
                aid=item.get("aid"),
                title=item.get("title", "").replace("<em class=\"keyword\">", "").replace("</em>", ""),
                link=f"https://www.bilibili.com/video/{bvid}",
                author=item.get("author", ""),
                duration_text=item.get("duration", ""),
                play_count=item.get("play"),
                description=item.get("description", ""),
                tag_text=item.get("tag", ""),
                publish_text=item.get("pubstr", ""),
                partition_name=item.get("typename", ""),
                partition_id=item.get("typeid") or item.get("tid"),
            )
        )
    return results
