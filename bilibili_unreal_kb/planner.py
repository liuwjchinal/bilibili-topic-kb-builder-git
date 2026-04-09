from __future__ import annotations

from pathlib import Path

from .models import SearchTask
from .packs import PackDefinition, get_pack

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
    return _dedupe_keep_order([line.strip() for line in path.read_text(encoding="utf-8").splitlines()])


def _resolve_pack(pack: PackDefinition | None, pack_slug: str | None) -> PackDefinition:
    if pack is not None:
        return pack
    return get_pack(pack_slug or "unreal-core")


def build_keyword_queries(
    custom_keywords: list[str] | None = None,
    include_default: bool = True,
    *,
    pack: PackDefinition | None = None,
    pack_slug: str | None = None,
) -> list[str]:
    resolved_pack = _resolve_pack(pack, pack_slug)
    queries: list[str] = []
    if include_default:
        for core in resolved_pack.search.core_terms:
            queries.append(core)
            for teaching in resolved_pack.search.expansion_terms:
                queries.append(f"{core} {teaching}")
        queries.extend(resolved_pack.search.custom_queries)
    if custom_keywords:
        queries.extend(custom_keywords)
    return _dedupe_keep_order(queries)


def build_search_tasks(
    pages: int | None,
    custom_keywords: list[str] | None = None,
    orders: list[str] | None = None,
    include_default: bool = True,
    *,
    pack: PackDefinition | None = None,
    pack_slug: str | None = None,
) -> list[SearchTask]:
    resolved_pack = _resolve_pack(pack, pack_slug)
    resolved_orders = orders or resolved_pack.search.orders or DEFAULT_ORDERS
    resolved_pages = max(1, pages if pages is not None else resolved_pack.search.pages)
    queries = build_keyword_queries(
        custom_keywords=custom_keywords,
        include_default=include_default,
        pack=resolved_pack,
    )
    tasks: list[SearchTask] = []
    for keyword in queries:
        for order in resolved_orders:
            for page in range(1, resolved_pages + 1):
                tasks.append(SearchTask(keyword=keyword, page=page, order=order))
    return tasks
