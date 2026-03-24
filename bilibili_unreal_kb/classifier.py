from __future__ import annotations

import re

from .models import ClassificationResult

CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("C++/插件开发", ["c++", "cpp", "插件", "plugin", "源码", "编辑器扩展", "引擎源码"]),
    ("性能优化", ["优化", "性能", "profiling", "optimization", "卡顿", "内存"]),
    ("特效/Niagara", ["niagara", "特效", "vfx", "粒子", "fx"]),
    ("材质与渲染", ["材质", "material", "shader", "渲染", "光照", "lumen", "nanite"]),
    ("动画系统", ["动画", "animation", "anim", "骨骼", "montage", "retarget"]),
    ("AI 系统", ["ai", "人工智能", "行为树", "黑板", "navigation", "navmesh"]),
    ("蓝图系统", ["蓝图", "blueprint", "bp节点", "可视化脚本"]),
    ("UI/UMG", ["umg", "ui", "界面", "widget", "hud"]),
    ("物理系统", ["物理", "physics", "碰撞", "ragdoll", "布料"]),
    ("关卡/场景", ["关卡", "场景", "landscape", "地形", "world partition", "环境"]),
    ("游戏开发实战", ["实战", "案例", "项目", "fps", "rpg", "demo", "项目开发"]),
    ("工具链/工作流", ["工作流", "pipeline", "版本控制", "perforce", "git", "导入", "构建"]),
    ("基础入门", ["入门", "新手", "基础", "beginner", "零基础", "教程"]),
]

IRRELEVANT_KEYWORDS = {
    "搞笑",
    "整活",
    "鬼畜",
    "音乐",
    "舞蹈",
    "动漫",
    "影视",
    "reaction",
    "asmr",
}

UE_HINT_KEYWORDS = {
    "虚幻",
    "unreal",
    "ue4",
    "ue5",
    "蓝图",
    "niagara",
    "材质",
    "umg",
}


def _contains(text: str, keyword: str) -> bool:
    normalized = keyword.lower()
    if re.fullmatch(r"[a-z0-9+.#-]+", normalized):
        pattern = rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])"
        return re.search(pattern, text) is not None
    return normalized in text


def classify_video(
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    query_keyword: str = "",
) -> ClassificationResult:
    tags = tags or []
    title_text = f" {title.lower()} "
    desc_text = f" {description.lower()} "
    query_text = f" {query_keyword.lower()} "
    tag_text = f" {' '.join(tag.lower() for tag in tags)} "

    scores: list[tuple[str, int, list[str]]] = []
    for category, keywords in CATEGORY_RULES:
        score = 0
        matched: list[str] = []
        for keyword in keywords:
            if _contains(title_text, keyword.lower()):
                score += 3
                matched.append(keyword)
            if _contains(query_text, keyword.lower()):
                score += 2
                matched.append(keyword)
            if _contains(tag_text, keyword.lower()):
                score += 2
                matched.append(keyword)
            if _contains(desc_text, keyword.lower()):
                score += 1
                matched.append(keyword)
        if score > 0:
            scores.append((category, score, sorted(set(matched))))

    if not scores:
        return ClassificationResult(
            primary_category="其他",
            secondary_categories=[],
            confidence=0.25,
            matched_keywords=[],
        )

    priority = {name: index for index, (name, _) in enumerate(CATEGORY_RULES)}
    scores.sort(key=lambda item: (-item[1], priority.get(item[0], 999)))
    primary_category, primary_score, matched_keywords = scores[0]
    secondary_categories = [category for category, score, _ in scores[1:4] if score >= max(2, primary_score - 2)]
    second_score = scores[1][1] if len(scores) > 1 else 0
    confidence = min(0.95, 0.35 + primary_score * 0.06 + max(primary_score - second_score, 0) * 0.03)
    return ClassificationResult(
        primary_category=primary_category,
        secondary_categories=secondary_categories,
        confidence=round(confidence, 2),
        matched_keywords=matched_keywords,
    )


def should_filter_irrelevant(title: str, description: str, tags: list[str] | None = None) -> bool:
    tags = tags or []
    text = f"{title} {description} {' '.join(tags)}".lower()
    has_ue_hint = any(keyword in text for keyword in UE_HINT_KEYWORDS)
    has_irrelevant_hint = any(keyword in text for keyword in IRRELEVANT_KEYWORDS)
    return has_irrelevant_hint and not has_ue_hint
