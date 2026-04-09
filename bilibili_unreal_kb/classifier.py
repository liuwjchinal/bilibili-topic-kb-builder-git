from __future__ import annotations

import re

from .models import ClassificationResult
from .packs import PackDefinition, get_pack

OTHER_CATEGORY_NAMES = {"其它", "其他", "鍏跺畠"}


def _contains(text: str, keyword: str) -> bool:
    normalized = keyword.lower().strip()
    if not normalized:
        return False
    if re.fullmatch(r"[a-z0-9+.#\-_/ ]+", normalized):
        escaped = re.escape(normalized).replace(r"\ ", r"\s+")
        pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
        return re.search(pattern, text) is not None
    return normalized in text


def _resolve_pack(pack: PackDefinition | None, pack_slug: str | None) -> PackDefinition:
    if pack is not None:
        return pack
    return get_pack(pack_slug or "unreal-core")


def _matches_any(text: str, keywords: list[str]) -> bool:
    return any(_contains(text, keyword.lower()) for keyword in keywords)


def classify_video(
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    query_keyword: str = "",
    *,
    pack: PackDefinition | None = None,
    pack_slug: str | None = None,
) -> ClassificationResult:
    resolved_pack = _resolve_pack(pack, pack_slug)
    tags = tags or []

    title_text = f" {title.lower()} "
    desc_text = f" {description.lower()} "
    query_text = f" {query_keyword.lower()} "
    tag_text = f" {' '.join(tag.lower() for tag in tags)} "

    scores: list[tuple[str, int, list[str], int]] = []
    for category in resolved_pack.categories:
        score = 0
        matched: list[str] = []
        for keyword in category.keywords:
            keyword_text = keyword.lower()
            if _contains(title_text, keyword_text):
                score += 3
                matched.append(keyword)
            if _contains(query_text, keyword_text):
                score += 2
                matched.append(keyword)
            if _contains(tag_text, keyword_text):
                score += 2
                matched.append(keyword)
            if _contains(desc_text, keyword_text):
                score += 1
                matched.append(keyword)
        if score > 0:
            scores.append((category.name, score, sorted(set(matched)), category.priority))

    if not scores:
        return ClassificationResult(
            primary_category="其它",
            secondary_categories=[],
            confidence=0.25,
            matched_keywords=[],
        )

    scores.sort(key=lambda item: (-item[1], item[3], item[0]))
    primary_category, primary_score, matched_keywords, _ = scores[0]
    second_score = scores[1][1] if len(scores) > 1 else 0
    secondary_categories = [
        category for category, score, _, _ in scores[1:4] if score >= max(2, primary_score - 2)
    ]
    confidence = min(0.95, 0.35 + primary_score * 0.06 + max(primary_score - second_score, 0) * 0.03)
    return ClassificationResult(
        primary_category=primary_category,
        secondary_categories=secondary_categories,
        confidence=round(confidence, 2),
        matched_keywords=matched_keywords,
    )


def should_filter_irrelevant(
    title: str,
    description: str,
    tags: list[str] | None = None,
    classification: ClassificationResult | None = None,
    partition_name: str = "",
    partition_id: int | None = None,
    *,
    pack: PackDefinition | None = None,
    pack_slug: str | None = None,
) -> bool:
    resolved_pack = _resolve_pack(pack, pack_slug)
    tags = tags or []
    text = f" {title.lower()} {description.lower()} {' '.join(tag.lower() for tag in tags)} "
    partition_text = f" {(partition_name or '').lower()} "
    has_gate = (
        True
        if not resolved_pack.gates.must_have_any
        else _matches_any(text, resolved_pack.gates.must_have_any)
    )
    has_context = (
        True
        if not resolved_pack.gates.context_any
        else _matches_any(text, resolved_pack.gates.context_any)
    )
    has_irrelevant_hint = _matches_any(text, resolved_pack.gates.irrelevant_keywords)
    domain_context_keywords = resolved_pack.domain.required_context_any or resolved_pack.gates.context_any
    has_domain_context = True if not domain_context_keywords else _matches_any(text, domain_context_keywords)
    is_blocked_partition = bool(partition_name) and _matches_any(
        partition_text,
        resolved_pack.domain.block_partition_keywords,
    )
    is_allowed_partition = (
        True
        if not resolved_pack.domain.allow_partition_keywords or not partition_name
        else _matches_any(partition_text, resolved_pack.domain.allow_partition_keywords)
    )

    if is_blocked_partition:
        return True
    if resolved_pack.domain.allow_partition_keywords and partition_name and not is_allowed_partition and not has_domain_context:
        return True
    if resolved_pack.gates.must_have_any and not has_gate:
        return True
    if has_irrelevant_hint and not has_gate:
        return True
    if has_gate and not has_context:
        return True
    if (
        classification is not None
        and resolved_pack.gates.context_any
        and not has_context
        and classification.primary_category in OTHER_CATEGORY_NAMES
        and classification.confidence <= 0.35
    ):
        return True
    return False
