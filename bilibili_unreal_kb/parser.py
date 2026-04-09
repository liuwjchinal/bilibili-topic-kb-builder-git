from __future__ import annotations

import json
import re

from .models import SearchVideoSummary


class SearchParseError(RuntimeError):
    pass


def _decode_js_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace("\\/", "/").replace("\\n", "\n").replace("\\r", "\r")


def _strip_html_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "").strip()


def _find_matching_delimiter(text: str, start: int, open_char: str, close_char: str) -> int:
    depth = 0
    in_string = False
    escape = False
    quote_char = ""
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote_char:
                in_string = False
            continue
        if char in {'"', "'"}:
            in_string = True
            quote_char = char
            continue
        if char == open_char:
            depth += 1
            continue
        if char == close_char:
            depth -= 1
            if depth == 0:
                return index
    return -1


def _extract_pinia_script(html: str) -> str:
    marker = "window.__pinia="
    start = html.find(marker)
    if start == -1:
        raise SearchParseError("未找到 window.__pinia。")
    end = html.find("</script>", start)
    if end == -1:
        raise SearchParseError("未找到 pinia 脚本结束位置。")
    return html[start + len(marker) : end].strip()


def _split_js_args(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False
    escape = False
    quote_char = ""
    for char in text:
        if in_string:
            current.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote_char:
                in_string = False
            continue
        if char in {'"', "'"}:
            in_string = True
            quote_char = char
            current.append(char)
            continue
        if char in "([{":
            depth += 1
            current.append(char)
            continue
        if char in ")]}":
            depth -= 1
            current.append(char)
            continue
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        parts.append("".join(current).strip())
    return [part for part in parts if part]


def _parse_simple_js_literal(token: str) -> tuple[str, object] | None:
    token = token.strip()
    if not token:
        return None
    if token.startswith('"') and token.endswith('"'):
        return "string", _decode_js_string(token[1:-1])
    if token.startswith("'") and token.endswith("'"):
        return "string", token[1:-1].encode("utf-8").decode("unicode_escape")
    if re.fullmatch(r"-?\d+", token):
        return "number", int(token)
    if token == "true":
        return "boolean", True
    if token == "false":
        return "boolean", False
    if token == "null":
        return "null", None
    return None


def _extract_iife_bindings(script: str) -> dict[str, tuple[str, object]]:
    function_match = re.match(r"\(function\((?P<params>.*?)\)\{", script, re.S)
    if not function_match:
        return {}
    params = [part.strip() for part in function_match.group("params").split(",") if part.strip()]
    body_start = function_match.end() - 1
    body_end = _find_matching_delimiter(script, body_start, "{", "}")
    if body_end == -1:
        return {}
    args_start = script.find("(", body_end + 1)
    if args_start == -1:
        return {}
    args_end = _find_matching_delimiter(script, args_start, "(", ")")
    if args_end == -1:
        return {}
    args_text = script[args_start + 1 : args_end]
    args = _split_js_args(args_text)
    bindings: dict[str, tuple[str, object]] = {}
    for name, raw_value in zip(params, args):
        parsed = _parse_simple_js_literal(raw_value)
        if parsed is not None:
            bindings[name] = parsed
    return bindings


def _extract_video_object_strings(script: str) -> list[str]:
    objects: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r'bvid:"(BV[0-9A-Za-z]+)"', script):
        bvid = match.group(1)
        if bvid in seen:
            continue
        start = script.rfind("{", 0, match.start())
        if start == -1:
            continue
        end = _find_matching_delimiter(script, start, "{", "}")
        if end == -1:
            continue
        seen.add(bvid)
        objects.append(script[start : end + 1])
    return objects


def _extract_field_token(
    object_text: str,
    field_name: str,
    bindings: dict[str, tuple[str, object]],
) -> tuple[str, object] | None:
    pattern = re.compile(
        rf"{re.escape(field_name)}:(?P<value>\"(?:\\.|[^\"])*\"|-?\d+|[A-Za-z_$][\w$]*)"
    )
    match = pattern.search(object_text)
    if not match:
        return None
    token = match.group("value")
    if token.startswith('"'):
        return "string", _decode_js_string(token[1:-1])
    if re.fullmatch(r"-?\d+", token):
        return "number", int(token)
    return bindings.get(token)


def _extract_string_field(
    object_text: str,
    field_name: str,
    bindings: dict[str, tuple[str, object]],
) -> str:
    value = _extract_field_token(object_text, field_name, bindings)
    if value is None:
        return ""
    token_type, token_value = value
    return str(token_value) if token_type == "string" else ""


def _extract_int_field(
    object_text: str,
    field_name: str,
    bindings: dict[str, tuple[str, object]],
) -> int | None:
    value = _extract_field_token(object_text, field_name, bindings)
    if value is None:
        return None
    token_type, token_value = value
    if token_type == "number":
        return int(token_value)
    if token_type == "string" and str(token_value).isdigit():
        return int(str(token_value))
    return None


def parse_search_page_with_pure_python(html: str) -> list[SearchVideoSummary]:
    script = _extract_pinia_script(html)
    bindings = _extract_iife_bindings(script)
    object_strings = _extract_video_object_strings(script)
    if not object_strings:
        raise SearchParseError("未能从 pinia 状态中提取视频对象。")

    results: list[SearchVideoSummary] = []
    for object_text in object_strings:
        bvid = _extract_string_field(object_text, "bvid", bindings)
        if not bvid:
            continue
        results.append(
            SearchVideoSummary(
                bvid=bvid,
                aid=_extract_int_field(object_text, "aid", bindings),
                title=_strip_html_tags(_extract_string_field(object_text, "title", bindings)),
                link=f"https://www.bilibili.com/video/{bvid}",
                author=_extract_string_field(object_text, "author", bindings),
                duration_text=_extract_string_field(object_text, "duration", bindings),
                play_count=_extract_int_field(object_text, "play", bindings),
                description=_strip_html_tags(_extract_string_field(object_text, "description", bindings)),
                tag_text=_extract_string_field(object_text, "tag", bindings),
                publish_text=_extract_string_field(object_text, "pubstr", bindings),
                partition_name=_extract_string_field(object_text, "typename", bindings),
                partition_id=_extract_int_field(object_text, "typeid", bindings)
                or _extract_int_field(object_text, "tid", bindings),
            )
        )
    if not results:
        raise SearchParseError("未能从 pinia 状态中提取视频列表。")
    return results


def parse_search_page_with_regex(html: str) -> list[SearchVideoSummary]:
    pattern = re.compile(
        r'bvid:"(?P<bvid>BV[0-9A-Za-z]+)".{0,2500}?'
        r'title:"(?P<title>(?:\\.|[^"])*)".{0,4000}?'
        r'description:"(?P<description>(?:\\.|[^"])*)".{0,2000}?'
        r'duration:"(?P<duration>[^"]*)".{0,2000}?'
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
