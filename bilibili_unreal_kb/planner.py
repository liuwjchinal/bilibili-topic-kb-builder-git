from __future__ import annotations

from pathlib import Path

from .models import SearchTask

CORE_KEYWORDS = ["虚幻引擎", "UE4", "UE5", "Unreal Engine"]
TEACHING_KEYWORDS = ["教程", "入门", "实战", "蓝图", "材质", "动画", "AI", "性能优化"]
DEFAULT_ORDERS = ["", "pubdate"]


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = " ".join(item.split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def load_custom_keywords(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    return _dedupe_keep_order(
        [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    )


def build_keyword_queries(
    custom_keywords: list[str] | None = None,
    include_default: bool = True,
) -> list[str]:
    queries: list[str] = []
    if include_default:
        for core in CORE_KEYWORDS:
            queries.append(core)
            for teaching in TEACHING_KEYWORDS:
                queries.append(f"{core} {teaching}")
    if custom_keywords:
        queries.extend(custom_keywords)
    return _dedupe_keep_order(queries)


def build_search_tasks(
    pages: int,
    custom_keywords: list[str] | None = None,
    orders: list[str] | None = None,
    include_default: bool = True,
) -> list[SearchTask]:
    resolved_orders = orders or DEFAULT_ORDERS
    queries = build_keyword_queries(custom_keywords=custom_keywords, include_default=include_default)
    tasks: list[SearchTask] = []
    for keyword in queries:
        for order in resolved_orders:
            for page in range(1, max(1, pages) + 1):
                tasks.append(SearchTask(keyword=keyword, page=page, order=order))
    return tasks
