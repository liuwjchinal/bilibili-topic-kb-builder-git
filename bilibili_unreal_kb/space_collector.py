from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import requests

from .models import SearchVideoSummary, SearchTask, VideoRecord
from .normalizer import build_video_record

TUTORIAL_KEYWORDS = [
    "教程",
    "教学",
    "指南",
    "入门",
    "课程",
    "课堂",
    "训练营",
    "讲座",
    "公开课",
    "工作流",
    "开发日志",
    "分享",
    "回放",
    "webinar",
    "workshop",
    "masterclass",
    "tips",
    "quick start",
    "how to",
]

BV_PATTERN = re.compile(r"/video/(BV[0-9A-Za-z]+)")
_THREAD_LOCAL = threading.local()


@dataclass
class SpacePlaylistResult:
    mid: str
    playlist_count: int
    bvids: list[str]
    source: str = "unknown"


def _read_cached_playlist(output_json_path: Path) -> SpacePlaylistResult | None:
    if not output_json_path.exists():
        return None
    payload = json.loads(output_json_path.read_text(encoding="utf-8"))
    entries = payload.get("entries") or []
    bvids = [entry["id"] for entry in entries if entry and entry.get("id")]
    return SpacePlaylistResult(
        mid=str(payload.get("id") or ""),
        playlist_count=int(payload.get("playlist_count") or len(bvids)),
        bvids=bvids,
        source=str(payload.get("source") or "cache"),
    )


def _write_playlist_payload(
    *,
    output_json_path: Path,
    space_url: str,
    mid: str,
    bvids: list[str],
    source: str,
) -> SpacePlaylistResult:
    entries = [
        {
            "id": bvid,
            "url": f"https://www.bilibili.com/video/{bvid}",
        }
        for bvid in bvids
    ]
    payload = {
        "id": mid,
        "webpage_url": space_url,
        "playlist_count": len(bvids),
        "entries": entries,
        "source": source,
    }
    output_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return SpacePlaylistResult(mid=mid, playlist_count=len(bvids), bvids=bvids, source=source)


def _extract_mid_from_space_url(space_url: str) -> str:
    match = re.search(r"space\.bilibili\.com/(\d+)", space_url)
    return match.group(1) if match else ""


def extract_bvids_from_hrefs(hrefs: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for href in hrefs:
        match = BV_PATTERN.search(href)
        if not match:
            continue
        bvid = match.group(1)
        if bvid in seen:
            continue
        seen.add(bvid)
        result.append(bvid)
    return result


def fetch_space_playlist_with_browser(
    *,
    space_url: str,
    output_json_path: Path,
    browser_debug_url: str,
    scroll_pause_seconds: float = 1.0,
    max_idle_rounds: int = 5,
    max_scroll_rounds: int = 300,
) -> SpacePlaylistResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "未安装 playwright。请执行 `pip install -r requirements-optional.txt` 并运行 "
            "`playwright install chromium` 后再使用浏览器空间抓取。"
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(browser_debug_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        try:
            page.goto(space_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            collected: list[str] = []
            last_height = 0
            idle_rounds = 0
            for _ in range(max_scroll_rounds):
                hrefs = page.evaluate(
                    """() => Array.from(
                        document.querySelectorAll('a[href*="/video/BV"]'),
                        (node) => node.href || ''
                    )"""
                )
                collected = extract_bvids_from_hrefs(hrefs)
                height = page.evaluate(
                    "() => document.scrollingElement ? document.scrollingElement.scrollHeight : document.body.scrollHeight"
                )
                page.evaluate(
                    "() => window.scrollTo(0, document.scrollingElement ? document.scrollingElement.scrollHeight : document.body.scrollHeight)"
                )
                page.wait_for_timeout(int(scroll_pause_seconds * 1000))
                next_hrefs = page.evaluate(
                    """() => Array.from(
                        document.querySelectorAll('a[href*="/video/BV"]'),
                        (node) => node.href || ''
                    )"""
                )
                next_collected = extract_bvids_from_hrefs(next_hrefs)
                next_height = page.evaluate(
                    "() => document.scrollingElement ? document.scrollingElement.scrollHeight : document.body.scrollHeight"
                )
                if len(next_collected) == len(collected) and next_height == last_height == height:
                    idle_rounds += 1
                else:
                    idle_rounds = 0
                collected = next_collected
                last_height = next_height
                if idle_rounds >= max_idle_rounds:
                    break
            if not collected:
                raise RuntimeError("浏览器空间页未提取到任何 BV 号，请确认当前 Chrome 已登录且空间页可正常加载。")
            return _write_playlist_payload(
                output_json_path=output_json_path,
                space_url=space_url,
                mid=_extract_mid_from_space_url(space_url),
                bvids=collected,
                source="browser_cdp",
            )
        finally:
            page.close()


def fetch_space_playlist_with_ytdlp(
    *,
    space_url: str,
    output_json_path: Path,
    max_attempts: int = 8,
) -> SpacePlaylistResult:
    cmd = [
        "python",
        "-m",
        "yt_dlp",
        "--socket-timeout",
        "60",
        "--flat-playlist",
        "--ignore-errors",
        "--dump-single-json",
        space_url,
    ]
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if stdout.startswith("{") and '"entries"' in stdout:
            payload = json.loads(stdout)
            entries = payload.get("entries") or []
            bvids = [entry["id"] for entry in entries if entry and entry.get("id")]
            return _write_playlist_payload(
                output_json_path=output_json_path,
                space_url=space_url,
                mid=str(payload.get("id") or ""),
                bvids=bvids,
                source="yt_dlp",
            )
        last_error = stderr or stdout or f"yt-dlp failed with code {result.returncode}"
        time.sleep(min(20, attempt * 3))
    raise RuntimeError(f"无法获取空间播放列表: {last_error}")


def fetch_space_playlist(
    space_url: str,
    output_json_path: Path,
    max_attempts: int = 8,
    browser_debug_url: str = "",
    refresh: bool = False,
) -> SpacePlaylistResult:
    if not refresh:
        cached = _read_cached_playlist(output_json_path)
        if cached is not None:
            return cached
    if browser_debug_url:
        return fetch_space_playlist_with_browser(
            space_url=space_url,
            output_json_path=output_json_path,
            browser_debug_url=browser_debug_url,
        )
    return fetch_space_playlist_with_ytdlp(
        space_url=space_url,
        output_json_path=output_json_path,
        max_attempts=max_attempts,
    )


def is_tutorial_video(title: str, description: str = "") -> bool:
    text = f"{title} {description}".lower()
    return any(keyword.lower() in text for keyword in TUTORIAL_KEYWORDS)


def _get_thread_session(headers: dict[str, str]) -> requests.Session:
    session = getattr(_THREAD_LOCAL, "space_session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(headers)
        _THREAD_LOCAL.space_session = session
    return session


def _load_checkpoint_records(checkpoint_path: Path | None) -> tuple[list[VideoRecord], dict[str, VideoRecord]]:
    records: list[VideoRecord] = []
    existing_map: dict[str, VideoRecord] = {}
    if checkpoint_path and checkpoint_path.exists():
        for line in checkpoint_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = VideoRecord.from_json_dict(json.loads(line))
            existing_map[record.bvid] = record
            records.append(record)
    return records, existing_map


def _build_detail_record(
    *,
    bvid: str,
    index: int,
    uploader_query: str,
    run_id: str,
    request_headers: dict[str, str],
    max_retries: int,
    connect_timeout: float,
    read_timeout: float,
) -> tuple[VideoRecord | None, str | None]:
    session = _get_thread_session(request_headers)
    payload = None
    last_error: str | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = session.get(
                "https://api.bilibili.com/x/web-interface/view",
                params={"bvid": bvid},
                timeout=(connect_timeout, read_timeout),
            )
            payload = response.json()
            if payload.get("code") == 0 and payload.get("data"):
                break
            last_error = f"code={payload.get('code')}"
        except Exception as exc:
            payload = None
            last_error = str(exc)
        if attempt < max_retries:
            time.sleep(min(3.0, 0.5 * attempt))
    if not payload or payload.get("code") != 0 or not payload.get("data"):
        return None, last_error or "empty payload"

    detail = payload["data"]
    task = SearchTask(keyword=uploader_query, page=1, order="space")
    summary = SearchVideoSummary(
        bvid=bvid,
        aid=detail.get("aid"),
        title=detail.get("title", ""),
        link=f"https://www.bilibili.com/video/{bvid}",
        author=(detail.get("owner") or {}).get("name", ""),
        duration_text="",
        play_count=(detail.get("stat") or {}).get("view"),
        description=detail.get("desc", ""),
        tag_text="",
        publish_text="",
    )
    record = build_video_record(
        summary=summary,
        detail=detail,
        tag_names=[],
        task=task,
        run_id=run_id,
        crawl_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    record.source_pages = [f"space:{index}"]
    return record, None


def fetch_space_records(
    bvids: list[str],
    uploader_query: str,
    run_id: str,
    checkpoint_path: Path | None = None,
    max_retries: int = 4,
    detail_workers: int = 6,
    connect_timeout: float = 5.0,
    read_timeout: float = 8.0,
    failed_records_path: Path | None = None,
    request_headers: dict[str, str] | None = None,
    progress_label: str = "fetched",
) -> list[VideoRecord]:
    records, existing_map = _load_checkpoint_records(checkpoint_path)
    headers = request_headers or {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.bilibili.com/",
    }
    pending = [(index, bvid) for index, bvid in enumerate(bvids, start=1) if bvid not in existing_map]
    if not pending:
        return records

    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, detail_workers)) as executor:
        future_map = {
            executor.submit(
                _build_detail_record,
                bvid=bvid,
                index=index,
                uploader_query=uploader_query,
                run_id=run_id,
                request_headers=headers,
                max_retries=max_retries,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
            ): (index, bvid)
            for index, bvid in pending
        }
        completed = 0
        total = len(pending)
        for future in as_completed(future_map):
            index, bvid = future_map[future]
            record, error = future.result()
            completed += 1
            if record is None:
                failures.append({"bvid": bvid, "error": error or "unknown"})
            else:
                records.append(record)
                if checkpoint_path:
                    with checkpoint_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(record.to_json_dict(), ensure_ascii=False) + "\n")
            if completed % 200 == 0 or completed == total:
                print(f"{progress_label} {completed}/{total}")

    if failed_records_path:
        failed_records_path.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in failures),
            encoding="utf-8",
        )
    return records
