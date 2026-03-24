from __future__ import annotations

import re
from datetime import date, datetime, timezone

from .classifier import classify_video, should_filter_irrelevant
from .models import SearchTask, SearchVideoSummary, VideoRecord


def strip_markup(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "").strip()


def duration_text_to_seconds(value: str) -> int:
    if not value:
        return 0
    parts = [int(part) for part in value.split(":")]
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def seconds_to_duration_text(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def epoch_to_iso8601(value: int | None) -> str:
    if not value:
        return ""
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def publish_text_to_iso8601(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        return f"{cleaned}T00:00:00+00:00"
    return ""


def is_since_allowed(publish_time: str, since: date | None) -> bool:
    if since is None or not publish_time:
        return True
    return publish_time[:10] >= since.isoformat()


def build_video_record(
    summary: SearchVideoSummary,
    detail: dict | None,
    tag_names: list[str],
    task: SearchTask,
    run_id: str,
    crawl_time: str,
) -> VideoRecord:
    detail = detail or {}
    title = strip_markup(detail.get("title") or summary.title)
    description = (detail.get("desc") or summary.description or "").strip()
    tags = [tag.strip() for tag in tag_names if tag.strip()]
    if not tags and summary.tag_text:
        tags = [tag.strip() for tag in summary.tag_text.split(",") if tag.strip()]
    classification = classify_video(
        title=title,
        description=description,
        tags=tags,
        query_keyword=task.keyword,
    )
    duration_seconds = int(detail.get("duration") or duration_text_to_seconds(summary.duration_text))
    uploader = (detail.get("owner") or {}).get("name") or summary.author
    play_count = int((detail.get("stat") or {}).get("view") or summary.play_count or 0)
    publish_time = epoch_to_iso8601(detail.get("pubdate")) or publish_text_to_iso8601(summary.publish_text)
    desc_excerpt = description.replace("\r", " ").replace("\n", " ").strip()[:240]

    status = "ok"
    if any(not field for field in [title, summary.bvid, uploader, publish_time]) or classification.confidence < 0.45:
        status = "needs_review"
    if should_filter_irrelevant(title, description, tags):
        status = "filtered_irrelevant"

    return VideoRecord(
        video_id=str(detail.get("aid") or summary.aid or summary.bvid),
        bvid=summary.bvid,
        title=title,
        link=summary.link or f"https://www.bilibili.com/video/{summary.bvid}",
        duration_seconds=duration_seconds,
        duration_text=seconds_to_duration_text(duration_seconds),
        uploader=uploader,
        play_count=play_count,
        publish_time=publish_time,
        query_keywords=[task.keyword],
        source_pages=[f"{task.order_label}:{task.page}"],
        primary_category=classification.primary_category,
        secondary_categories=classification.secondary_categories,
        category_confidence=classification.confidence,
        match_keywords=classification.matched_keywords,
        tags=tags,
        desc_excerpt=desc_excerpt,
        crawl_time=crawl_time,
        run_id=run_id,
        status=status,
    )


def summary_has_required_fields(summary: SearchVideoSummary) -> bool:
    return all(
        [
            summary.bvid,
            strip_markup(summary.title),
            summary.author,
            summary.duration_text,
            publish_text_to_iso8601(summary.publish_text),
        ]
    )


def merge_records(existing: VideoRecord, incoming: VideoRecord) -> VideoRecord:
    merged = VideoRecord.from_json_dict(existing.to_json_dict())
    merged.query_keywords = sorted(set(existing.query_keywords + incoming.query_keywords))
    merged.source_pages = sorted(set(existing.source_pages + incoming.source_pages))
    merged.secondary_categories = sorted(set(existing.secondary_categories + incoming.secondary_categories))
    merged.match_keywords = sorted(set(existing.match_keywords + incoming.match_keywords))
    merged.tags = sorted(set(existing.tags + incoming.tags))
    merged.crawl_time = incoming.crawl_time or existing.crawl_time
    merged.run_id = incoming.run_id or existing.run_id
    merged.play_count = max(existing.play_count, incoming.play_count)
    if len(incoming.desc_excerpt) > len(existing.desc_excerpt):
        merged.desc_excerpt = incoming.desc_excerpt
    if incoming.category_confidence >= existing.category_confidence:
        merged.primary_category = incoming.primary_category
        merged.category_confidence = incoming.category_confidence
    if existing.status != "ok":
        merged.status = incoming.status
    if not merged.duration_seconds and incoming.duration_seconds:
        merged.duration_seconds = incoming.duration_seconds
        merged.duration_text = incoming.duration_text
    return merged


def record_needs_refresh(record: VideoRecord) -> bool:
    return record.status != "ok" or not all(
        [record.title, record.bvid, record.uploader, record.publish_time, record.primary_category]
    )
