from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class CategoryRule:
    id: str
    name: str
    keywords: list[str]
    priority: int


@dataclass(frozen=True)
class SearchPackConfig:
    core_terms: list[str]
    expansion_terms: list[str]
    custom_queries: list[str]
    orders: list[str]
    pages: int


@dataclass(frozen=True)
class GateConfig:
    must_have_any: list[str] = field(default_factory=list)
    context_any: list[str] = field(default_factory=list)
    irrelevant_keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DomainConfig:
    key: str = ""
    display_name: str = ""
    allow_partition_keywords: list[str] = field(default_factory=list)
    block_partition_keywords: list[str] = field(default_factory=list)
    required_context_any: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PackDefinition:
    slug: str
    display_name: str
    description: str
    search: SearchPackConfig
    gates: GateConfig
    categories: list[CategoryRule]
    domain: DomainConfig = field(default_factory=DomainConfig)


PACKS_DIR = Path(__file__).resolve().parent.parent / "config" / "packs"
DEFAULT_PACK_SLUG = "unreal-core"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}$")


def _ensure_text_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field_name} must be a list of non-empty strings")
    return [item.strip() for item in value]


def _normalize_text_list(value: object, field_name: str, *, required: bool) -> list[str]:
    if value is None or value == "":
        value = []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of non-empty strings")
    normalized = [str(item).strip() for item in value if str(item).strip()]
    if required and not normalized:
        raise ValueError(f"{field_name} must contain at least one item")
    return normalized


def _normalize_required_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


def _normalize_slug(value: object, field_name: str) -> str:
    slug = _normalize_required_text(value, field_name).lower()
    if not SLUG_RE.fullmatch(slug):
        raise ValueError(f"{field_name} must match {SLUG_RE.pattern}")
    return slug


def _normalize_category_payloads(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("categories must be a non-empty list")

    categories: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError("categories entries must be mappings")
        category_id = _normalize_slug(item.get("id"), f"categories[{index}].id")
        if category_id in seen_ids:
            raise ValueError(f"duplicate category id: {category_id}")
        seen_ids.add(category_id)
        name = _normalize_required_text(item.get("name"), f"categories[{index}].name")
        keywords = _normalize_text_list(item.get("keywords"), f"categories[{index}].keywords", required=True)
        try:
            priority = int(item.get("priority"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"categories[{index}].priority must be an integer") from exc
        categories.append(
            {
                "id": category_id,
                "name": name,
                "keywords": keywords,
                "priority": priority,
            }
        )
    return categories


def _load_pack_file(path: Path) -> PackDefinition:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a mapping")

    search_payload = payload.get("search") or {}
    gates_payload = payload.get("gates") or {}
    domain_payload = payload.get("domain") or {}
    categories_payload = payload.get("categories") or []
    if not isinstance(search_payload, dict) or not isinstance(gates_payload, dict) or not isinstance(domain_payload, dict):
        raise ValueError(f"{path.name} search/gates/domain must be mappings")
    if not isinstance(categories_payload, list) or not categories_payload:
        raise ValueError(f"{path.name} categories must be a non-empty list")

    categories: list[CategoryRule] = []
    seen_category_ids: set[str] = set()
    for item in categories_payload:
        if not isinstance(item, dict):
            raise ValueError(f"{path.name} category entries must be mappings")
        category_id = _normalize_slug(item.get("id") or "", f"{path.name}:category.id")
        if category_id in seen_category_ids:
            raise ValueError(f"{path.name} category ids must be unique")
        seen_category_ids.add(category_id)
        category_name = str(item.get("name") or "").strip()
        if not category_name:
            raise ValueError(f"{path.name}:{category_id}:name must be non-empty")
        categories.append(
            CategoryRule(
                id=category_id,
                name=category_name,
                keywords=_ensure_text_list(item.get("keywords") or [], f"{path.name}:{category_id}:keywords"),
                priority=int(item.get("priority") or 999),
            )
        )

    orders = _ensure_text_list(search_payload.get("orders") or ["default", "pubdate"], f"{path.name}:orders")
    slug = _normalize_slug(payload.get("slug") or path.stem, f"{path.name}:slug")
    display_name = _normalize_required_text(payload.get("display_name") or path.stem, f"{path.name}:display_name")
    return PackDefinition(
        slug=slug,
        display_name=display_name,
        description=str(payload.get("description") or "").strip(),
        search=SearchPackConfig(
            core_terms=_ensure_text_list(search_payload.get("core_terms") or [], f"{path.name}:core_terms"),
            expansion_terms=_ensure_text_list(search_payload.get("expansion_terms") or [], f"{path.name}:expansion_terms")
            if search_payload.get("expansion_terms")
            else [],
            custom_queries=_ensure_text_list(search_payload.get("custom_queries") or [], f"{path.name}:custom_queries")
            if search_payload.get("custom_queries")
            else [],
            orders=["" if item == "default" else item for item in orders],
            pages=max(1, int(search_payload.get("pages") or 1)),
        ),
        gates=GateConfig(
            must_have_any=_ensure_text_list(gates_payload.get("must_have_any") or [], f"{path.name}:must_have_any")
            if gates_payload.get("must_have_any")
            else [],
            context_any=_ensure_text_list(gates_payload.get("context_any") or [], f"{path.name}:context_any")
            if gates_payload.get("context_any")
            else [],
            irrelevant_keywords=_ensure_text_list(
                gates_payload.get("irrelevant_keywords") or [],
                f"{path.name}:irrelevant_keywords",
            )
            if gates_payload.get("irrelevant_keywords")
            else [],
        ),
        domain=DomainConfig(
            key=str(domain_payload.get("key") or "").strip(),
            display_name=str(domain_payload.get("display_name") or domain_payload.get("name") or "").strip(),
            allow_partition_keywords=_ensure_text_list(
                domain_payload.get("allow_partition_keywords") or [],
                f"{path.name}:domain.allow_partition_keywords",
            )
            if domain_payload.get("allow_partition_keywords")
            else [],
            block_partition_keywords=_ensure_text_list(
                domain_payload.get("block_partition_keywords") or [],
                f"{path.name}:domain.block_partition_keywords",
            )
            if domain_payload.get("block_partition_keywords")
            else [],
            required_context_any=_ensure_text_list(
                domain_payload.get("required_context_any") or [],
                f"{path.name}:domain.required_context_any",
            )
            if domain_payload.get("required_context_any")
            else [],
        ),
        categories=categories,
    )


def pack_to_payload(pack: PackDefinition) -> dict[str, Any]:
    return {
        "slug": pack.slug,
        "display_name": pack.display_name,
        "description": pack.description,
        "search": {
            "core_terms": list(pack.search.core_terms),
            "expansion_terms": list(pack.search.expansion_terms),
            "custom_queries": list(pack.search.custom_queries),
            "orders": ["default" if not item else item for item in pack.search.orders],
            "pages": pack.search.pages,
        },
        "gates": {
            "must_have_any": list(pack.gates.must_have_any),
            "context_any": list(pack.gates.context_any),
            "irrelevant_keywords": list(pack.gates.irrelevant_keywords),
        },
        "domain": {
            "key": pack.domain.key,
            "display_name": pack.domain.display_name,
            "allow_partition_keywords": list(pack.domain.allow_partition_keywords),
            "block_partition_keywords": list(pack.domain.block_partition_keywords),
            "required_context_any": list(pack.domain.required_context_any),
        },
        "categories": [
            {
                "id": category.id,
                "name": category.name,
                "keywords": list(category.keywords),
                "priority": category.priority,
            }
            for category in pack.categories
        ],
    }


def _pack_file_path(slug: str) -> Path:
    return PACKS_DIR / f"{slug}.yaml"


def clear_pack_cache() -> None:
    load_packs.cache_clear()


@lru_cache(maxsize=1)
def load_packs() -> dict[str, PackDefinition]:
    packs: dict[str, PackDefinition] = {}
    for path in sorted(PACKS_DIR.glob("*.yaml")):
        pack = _load_pack_file(path)
        if pack.slug in packs:
            raise ValueError(f"duplicate pack slug: {pack.slug}")
        packs[pack.slug] = pack
    if DEFAULT_PACK_SLUG not in packs:
        raise ValueError(f"default pack {DEFAULT_PACK_SLUG} is missing")
    return packs


def get_pack(slug: str = DEFAULT_PACK_SLUG) -> PackDefinition:
    packs = load_packs()
    if slug not in packs:
        raise KeyError(f"unknown pack: {slug}")
    return packs[slug]


def list_packs() -> list[PackDefinition]:
    return list(load_packs().values())


def list_pack_templates() -> list[dict[str, Any]]:
    return [pack_to_payload(pack) for pack in list_packs()]


def validate_pack_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a mapping")

    base_template_slug = _normalize_slug(payload.get("base_template_slug"), "base_template_slug")
    base_template = get_pack(base_template_slug)

    slug = _normalize_slug(payload.get("slug"), "slug")
    if slug in load_packs() or _pack_file_path(slug).exists():
        raise FileExistsError(f"pack already exists: {slug}")

    display_name = _normalize_required_text(payload.get("display_name"), "display_name")
    description = str(payload.get("description") or "").strip()

    search_payload = payload.get("search") or {}
    if not isinstance(search_payload, dict):
        raise ValueError("search must be a mapping")
    gates_payload = payload.get("gates") or {}
    if not isinstance(gates_payload, dict):
        raise ValueError("gates must be a mapping")
    domain_payload = payload.get("domain")
    if domain_payload is not None and not isinstance(domain_payload, dict):
        raise ValueError("domain must be a mapping")

    normalized = {
        "slug": slug,
        "display_name": display_name,
        "description": description,
        "search": {
            "core_terms": _normalize_text_list(search_payload.get("core_terms"), "search.core_terms", required=True),
            "expansion_terms": _normalize_text_list(
                search_payload.get("expansion_terms"), "search.expansion_terms", required=False
            ),
            "custom_queries": _normalize_text_list(
                search_payload.get("custom_queries"), "search.custom_queries", required=False
            ),
            "orders": pack_to_payload(base_template)["search"]["orders"],
            "pages": base_template.search.pages,
        },
        "gates": {
            "must_have_any": _normalize_text_list(gates_payload.get("must_have_any"), "gates.must_have_any", required=False),
            "context_any": _normalize_text_list(
                gates_payload.get("context_any")
                if isinstance(gates_payload, dict) and "context_any" in gates_payload
                else base_template.gates.context_any,
                "gates.context_any",
                required=False,
            ),
            "irrelevant_keywords": _normalize_text_list(
                gates_payload.get("irrelevant_keywords"),
                "gates.irrelevant_keywords",
                required=False,
            ),
        },
        "domain": {
            "key": _normalize_required_text(
                (domain_payload or {}).get("key")
                if isinstance(domain_payload, dict) and "key" in domain_payload
                else base_template.domain.key,
                "domain.key",
            )
            if ((domain_payload or {}).get("key") if isinstance(domain_payload, dict) else base_template.domain.key)
            else "",
            "display_name": str(
                (domain_payload or {}).get("display_name")
                if isinstance(domain_payload, dict) and "display_name" in domain_payload
                else base_template.domain.display_name
            ).strip(),
            "allow_partition_keywords": _normalize_text_list(
                (domain_payload or {}).get("allow_partition_keywords")
                if isinstance(domain_payload, dict) and "allow_partition_keywords" in domain_payload
                else base_template.domain.allow_partition_keywords,
                "domain.allow_partition_keywords",
                required=False,
            ),
            "block_partition_keywords": _normalize_text_list(
                (domain_payload or {}).get("block_partition_keywords")
                if isinstance(domain_payload, dict) and "block_partition_keywords" in domain_payload
                else base_template.domain.block_partition_keywords,
                "domain.block_partition_keywords",
                required=False,
            ),
            "required_context_any": _normalize_text_list(
                (domain_payload or {}).get("required_context_any")
                if isinstance(domain_payload, dict) and "required_context_any" in domain_payload
                else base_template.domain.required_context_any,
                "domain.required_context_any",
                required=False,
            ),
        },
        "categories": _normalize_category_payloads(payload.get("categories")),
    }
    return normalized


def create_pack_from_payload(payload: object) -> PackDefinition:
    normalized = validate_pack_payload(payload)
    path = _pack_file_path(normalized["slug"])
    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(normalized, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    clear_pack_cache()
    try:
        return get_pack(str(normalized["slug"]))
    except Exception:
        if path.exists():
            path.unlink()
        clear_pack_cache()
        raise
