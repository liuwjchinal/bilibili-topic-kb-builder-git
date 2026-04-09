from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Callable, Iterable, Sequence

from .collector import BilibiliCollector
from .config import AppConfig
from .models import SearchTask, VideoRecord
from .normalizer import (
    build_video_record,
    is_since_allowed,
    merge_records,
    record_needs_refresh,
    summary_has_required_fields,
)
from .packs import PackDefinition
from .planner import build_search_tasks, load_custom_keywords
from .store import CatalogStore


def _make_run_id() -> str:
    return datetime.now(tz=timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def categorize_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "412" in message or "429" in message or "rate" in message:
        return "rate_limit"
    if "parse" in message or "pinia" in message:
        return "parse"
    if "detail" in message or "view?bvid" in message:
        return "detail_api"
    if "ssl" in message or "timeout" in message or "connection" in message or "network" in message:
        return "network"
    return "network"


@dataclass
class PipelineHooks:
    emit: Callable[[str, dict], None] | None = None
    is_cancelled: Callable[[], bool] | None = None
    update_preview: Callable[[list[VideoRecord], dict], None] | None = None

    def publish(self, event_type: str, payload: dict) -> None:
        if self.emit is not None:
            self.emit(event_type, payload)

    def cancelled(self) -> bool:
        return bool(self.is_cancelled and self.is_cancelled())

    def preview(self, records: list[VideoRecord], summary: dict) -> None:
        if self.update_preview is not None:
            self.update_preview(records, summary)


@dataclass
class TopicPipelineResult:
    run_id: str
    summary: dict
    records: list[VideoRecord]


def _save_intermediate(store: CatalogStore, records: Iterable[VideoRecord]) -> None:
    records_list = list(records)
    store.save_catalog(records_list)
    store.save_seen_index(records_list)


def run_topic_pipeline(
    *,
    config: AppConfig,
    pack: PackDefinition,
    keyword_overrides: Sequence[str] | None = None,
    orders: Sequence[str] | None = None,
    resume: bool = False,
    hooks: PipelineHooks | None = None,
) -> TopicPipelineResult:
    resolved_hooks = hooks or PipelineHooks()
    config.ensure_directories()
    store = CatalogStore(config)
    collector = BilibiliCollector(config)
    records = store.load_catalog()

    completed_ids: set[str] = set()
    if resume:
        resumed = store.resume_tasks()
        if resumed is None:
            run_id = _make_run_id()
            custom_keywords = load_custom_keywords(config.keywords_file)
            if keyword_overrides:
                custom_keywords.extend(keyword_overrides)
            tasks = build_search_tasks(
                pages=config.pages,
                custom_keywords=custom_keywords,
                orders=list(orders) if orders else None,
                include_default=not bool(keyword_overrides),
                pack=pack,
            )
            store.initialize_run(run_id, tasks)
        else:
            run_id, tasks, completed_ids = resumed
    else:
        run_id = _make_run_id()
        custom_keywords = load_custom_keywords(config.keywords_file)
        if keyword_overrides:
            custom_keywords.extend(keyword_overrides)
        tasks = build_search_tasks(
            pages=config.pages,
            custom_keywords=custom_keywords,
            orders=list(orders) if orders else None,
            include_default=not bool(keyword_overrides),
            pack=pack,
        )
        store.initialize_run(run_id, tasks)

    counters = {
        "searched_tasks": 0,
        "completed_tasks": 0,
        "failed_tasks": 0,
        "new_records": 0,
        "updated_records": 0,
        "filtered_records": 0,
        "skipped_existing": 0,
    }
    total_tasks = len(tasks)
    last_preview_at = 0.0

    def emit_preview(*, task_index: int | None, task: SearchTask | None, force: bool = False) -> None:
        nonlocal last_preview_at
        now = time.monotonic()
        if not force and (now - last_preview_at) < 1.0:
            return
        resolved_hooks.preview(
            list(records.values()),
            {
                "run_id": run_id,
                "pack_slug": pack.slug,
                "counters": counters,
                "catalog_size": len(records),
                "task_index": task_index,
                "total_tasks": total_tasks,
                "current_task_id": task.task_id if task is not None else None,
                "current_keyword": task.keyword if task is not None else None,
                "current_order": task.order_label if task is not None else None,
                "current_page": task.page if task is not None else None,
            },
        )
        last_preview_at = now

    resolved_hooks.publish(
        "run_started",
        {"run_id": run_id, "pack_slug": pack.slug, "total_tasks": total_tasks, "output_dir": str(config.output_dir)},
    )
    emit_preview(task_index=0, task=None, force=True)

    for task_index, task in enumerate(tasks, start=1):
        if task.task_id in completed_ids:
            continue
        if resolved_hooks.cancelled():
            break
        counters["searched_tasks"] += 1
        resolved_hooks.publish(
            "task_started",
            {
                "run_id": run_id,
                "task_id": task.task_id,
                "task_index": task_index,
                "total_tasks": total_tasks,
                "keyword": task.keyword,
                "page": task.page,
                "order": task.order_label,
            },
        )
        emit_preview(task_index=task_index, task=task, force=True)
        try:
            summaries = collector.search_videos(task)
            task_results = 0
            for summary in summaries:
                if resolved_hooks.cancelled():
                    emit_preview(task_index=task_index, task=task, force=True)
                    break
                existing = records.get(summary.bvid)
                if existing is not None and not record_needs_refresh(existing):
                    existing.query_keywords = sorted(set(existing.query_keywords + [task.keyword]))
                    existing.source_pages = sorted(set(existing.source_pages + [f"{task.order_label}:{task.page}"]))
                    existing.crawl_time = _utc_now_iso()
                    existing.run_id = run_id
                    counters["skipped_existing"] += 1
                    task_results += 1
                    emit_preview(task_index=task_index, task=task)
                    continue

                record = build_video_record(
                    summary=summary,
                    detail=None,
                    tag_names=[],
                    task=task,
                    run_id=run_id,
                    crawl_time=_utc_now_iso(),
                    pack=pack,
                )
                if not summary_has_required_fields(summary) or record_needs_refresh(record):
                    try:
                        detail = collector.fetch_video_detail(summary.bvid)
                        tags = collector.fetch_video_tags(summary.bvid) if not summary.tag_text else []
                        record = build_video_record(
                            summary=summary,
                            detail=detail,
                            tag_names=tags,
                            task=task,
                            run_id=run_id,
                            crawl_time=_utc_now_iso(),
                            pack=pack,
                        )
                    except Exception:
                        record.status = "needs_review"
                if not is_since_allowed(record.publish_time, config.since):
                    counters["filtered_records"] += 1
                    continue
                if record.status == "filtered_irrelevant":
                    counters["filtered_records"] += 1
                    continue
                if existing is not None:
                    records[record.unique_key] = merge_records(existing, record)
                    counters["updated_records"] += 1
                else:
                    records[record.unique_key] = record
                    counters["new_records"] += 1
                task_results += 1
                emit_preview(task_index=task_index, task=task)

            if resolved_hooks.cancelled():
                emit_preview(task_index=task_index, task=task, force=True)
                break

            store.update_task_status(task, status="completed", result_count=task_results)
            counters["completed_tasks"] += 1
            _save_intermediate(store, records.values())
            emit_preview(task_index=task_index, task=task, force=True)
            resolved_hooks.publish(
                "task_completed",
                {
                    "run_id": run_id,
                    "task_id": task.task_id,
                    "task_index": task_index,
                    "total_tasks": total_tasks,
                    "result_count": task_results,
                    "counters": counters,
                    "catalog_size": len(records),
                },
            )
        except Exception as exc:
            category = categorize_error(exc)
            store.update_task_status(task, status="failed", error=str(exc))
            counters["failed_tasks"] += 1
            resolved_hooks.publish(
                "task_failed",
                {
                    "run_id": run_id,
                    "task_id": task.task_id,
                    "task_index": task_index,
                    "total_tasks": total_tasks,
                    "error": str(exc),
                    "error_category": category,
                    "counters": counters,
                },
            )
            emit_preview(task_index=task_index, task=task, force=True)

    _save_intermediate(store, records.values())
    emit_preview(task_index=total_tasks, task=None, force=True)
    summary = {
        "run_id": run_id,
        "pack_slug": pack.slug,
        "finished_at": _utc_now_iso(),
        "counters": counters,
        "catalog_size": len([record for record in records.values() if record.status != "filtered_irrelevant"]),
    }
    return TopicPipelineResult(run_id=run_id, summary=summary, records=list(records.values()))
