from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from .models import SearchVideoSummary


class SearchParseError(RuntimeError):
    pass


def _decode_js_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace("\\/", "/").replace("\\n", "\n")


def _strip_html_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "").strip()


def parse_search_page_with_node(html: str, node_bin: str = "node") -> list[SearchVideoSummary]:
    with tempfile.NamedTemporaryFile("w", suffix=".html", encoding="utf-8", delete=False) as handle:
        handle.write(html)
        html_path = Path(handle.name)
    node_script = """
const fs = require('fs');
const filePath = process.argv[1];
const html = fs.readFileSync(filePath, 'utf8');
const start = html.indexOf('window.__pinia=');
if (start === -1) {
  console.error('pinia-state-not-found');
  process.exit(12);
}
const end = html.indexOf('</script>', start);
if (end === -1) {
  console.error('pinia-script-not-found');
  process.exit(13);
}
const script = html.slice(start, end);
global.window = {};
eval(script);
const response = window.__pinia?.searchResponse?.searchAllResponse;
if (!response) {
  console.error('search-response-not-found');
  process.exit(14);
}
const videoBucket = (response.result || []).find((item) => item.result_type === 'video');
console.log(JSON.stringify(videoBucket?.data || []));
"""
    try:
        completed = subprocess.run(
            [node_bin, "-e", node_script, str(html_path)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:  # pragma: no cover
        raise SearchParseError("未找到 node，可改用浏览器兜底或安装 Node.js。") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() or exc.stdout.strip()
        raise SearchParseError(f"Node 解析搜索页失败: {stderr}") from exc
    finally:
        html_path.unlink(missing_ok=True)
    payload = json.loads(completed.stdout or "[]")
    results: list[SearchVideoSummary] = []
    for item in payload:
        bvid = item.get("bvid")
        if not bvid:
            continue
        results.append(
            SearchVideoSummary(
                bvid=bvid,
                aid=item.get("aid"),
                title=_strip_html_tags(item.get("title", "")),
                link=f"https://www.bilibili.com/video/{bvid}",
                author=item.get("author", ""),
                duration_text=item.get("duration", ""),
                play_count=item.get("play"),
                description=_strip_html_tags(item.get("description", "")),
                tag_text=item.get("tag", ""),
                publish_text=item.get("pubstr", ""),
            )
        )
    return results


def parse_search_page_with_regex(html: str) -> list[SearchVideoSummary]:
    pattern = re.compile(
        r'bvid:"(?P<bvid>BV[0-9A-Za-z]+)".{0,500}?aid:(?P<aid>\d+).{0,1200}?'
        r'title:"(?P<title>(?:\\.|[^"])*)".{0,2500}?'
        r'description:"(?P<description>(?:\\.|[^"])*)".{0,1000}?'
        r'duration:"(?P<duration>[^"]*)".{0,1200}?'
        r'pubstr:"(?P<pubstr>[^"]*)"',
        re.S,
    )
    results: list[SearchVideoSummary] = []
    seen: set[str] = set()
    for match in pattern.finditer(html):
        bvid = match.group("bvid")
        if bvid in seen:
            continue
        seen.add(bvid)
        results.append(
            SearchVideoSummary(
                bvid=bvid,
                aid=int(match.group("aid")),
                title=_strip_html_tags(_decode_js_string(match.group("title"))),
                link=f"https://www.bilibili.com/video/{bvid}",
                duration_text=_decode_js_string(match.group("duration")),
                description=_strip_html_tags(_decode_js_string(match.group("description"))),
                publish_text=_decode_js_string(match.group("pubstr")),
            )
        )
    if not results:
        raise SearchParseError("未能从搜索页中提取视频列表。")
    return results
