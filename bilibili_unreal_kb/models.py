from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SearchTask:
    keyword: str
    page: int
    order: str = ""

    @property
    def order_label(self) -> str:
        return self.order or "default"

    @property
    def task_id(self) -> str:
        return f"{self.keyword}::{self.order_label}::{self.page}"

    def to_dict(self) -> dict[str, Any]:
        return {"keyword": self.keyword, "page": self.page, "order": self.order}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchTask":
        return cls(
            keyword=data["keyword"],
            page=int(data["page"]),
            order=data.get("order", ""),
        )


@dataclass
class SearchVideoSummary:
    bvid: str
    aid: int | None = None
    title: str = ""
    link: str = ""
    author: str = ""
    duration_text: str = ""
    play_count: int | None = None
    description: str = ""
    tag_text: str = ""
    publish_text: str = ""
    partition_name: str = ""
    partition_id: int | None = None


@dataclass
class ClassificationResult:
    primary_category: str
    secondary_categories: list[str]
    confidence: float
    matched_keywords: list[str]


@dataclass
class VideoRecord:
    video_id: str
    bvid: str
    title: str
    link: str
    duration_seconds: int
    duration_text: str
    uploader: str
    play_count: int
    publish_time: str
    query_keywords: list[str] = field(default_factory=list)
    source_pages: list[str] = field(default_factory=list)
    primary_category: str = "其它"
    secondary_categories: list[str] = field(default_factory=list)
    category_confidence: float = 0.0
    match_keywords: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    desc_excerpt: str = ""
    platform_partition_name: str = ""
    platform_partition_id: int | None = None
    cover_url: str = ""
    uploader_avatar_url: str = ""
    crawl_time: str = ""
    run_id: str = ""
    status: str = "ok"

    @property
    def unique_key(self) -> str:
        return self.bvid or self.link

    def to_export_row(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "bvid": self.bvid,
            "title": self.title,
            "link": self.link,
            "duration_seconds": self.duration_seconds,
            "duration_text": self.duration_text,
            "uploader": self.uploader,
            "play_count": self.play_count,
            "publish_time": self.publish_time,
            "query_keyword": "; ".join(self.query_keywords),
            "source_page": "; ".join(self.source_pages),
            "primary_category": self.primary_category,
            "secondary_categories": "; ".join(self.secondary_categories),
            "category_confidence": round(self.category_confidence, 2),
            "match_keywords": "; ".join(self.match_keywords),
            "tags": "; ".join(self.tags),
            "desc_excerpt": self.desc_excerpt,
            "platform_partition_name": self.platform_partition_name,
            "platform_partition_id": self.platform_partition_id or "",
            "cover_url": self.cover_url,
            "uploader_avatar_url": self.uploader_avatar_url,
            "crawl_time": self.crawl_time,
            "run_id": self.run_id,
            "status": self.status,
        }

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "VideoRecord":
        return cls(**data)
