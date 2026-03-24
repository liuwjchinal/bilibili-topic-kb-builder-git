from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .collector import BilibiliCollector
from .config import load_config
from .normalizer import (
    build_video_record,
    is_since_allowed,
    merge_records,
    record_needs_refresh,
    summary_has_required_fields,
)
from .planner import DEFAULT_ORDERS, build_search_tasks, load_custom_keywords
from .space_collector import fetch_space_playlist, fetch_space_records, is_tutorial_video
from .store import CatalogStore


def _make_run_id() -> str:
    return datetime.now(tz=timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="B站虚幻引擎教程知识库爬虫")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="执行全量或增量采集")
    run_parser.add_argument("--pages", type=int, default=None)
    run_parser.add_argument("--keywords-file", type=str, default=None)
    run_parser.add_argument("--keyword", action="append", default=None)
    run_parser.add_argument("--output-dir", type=str, default=None)
    run_parser.add_argument("--resume", action="store_true")
    run_parser.add_argument("--browser-fallback", action="store_true")
    run_parser.add_argument("--since", type=str, default=None)
    run_parser.add_argument("--orders", type=str, default="default,pubdate")

    resume_parser = subparsers.add_parser("resume", help="从 current_run.json 继续执行")
    resume_parser.add_argument("--output-dir", type=str, default=None)
    resume_parser.add_argument("--browser-fallback", action="store_true")

    export_parser = subparsers.add_parser("export", help="根据现有 JSONL 重新导出")
    export_parser.add_argument("--output-dir", type=str, default=None)

    validate_parser = subparsers.add_parser("validate", help="校验环境与配置")
    validate_parser.add_argument("--output-dir", type=str, default=None)

    space_parser = subparsers.add_parser("space", help="抓取指定 UP 主空间下的全部视频")
    space_parser.add_argument("--space-url", required=True, type=str)
    space_parser.add_argument("--uploader-name", required=True, type=str)
    space_parser.add_argument("--output-dir", type=str, default=None)
    space_parser.add_argument("--browser-debug-url", type=str, default=None)
    space_parser.add_argument("--refresh-playlist", action="store_true")
    space_parser.add_argument("--detail-workers", type=int, default=None)

    retry_space_parser = subparsers.add_parser(
        "retry-space-failed",
        help="根据失败 BV 列表重试空间详情补采",
    )
    retry_space_parser.add_argument("--uploader-name", required=True, type=str)
    retry_space_parser.add_argument("--output-dir", type=str, default=None)
    retry_space_parser.add_argument("--detail-workers", type=int, default=None)

    return parser.parse_args()


def _resolve_orders(orders_text: str) -> list[str]:
    result: list[str] = []
    for value in (part.strip() for part in orders_text.split(",")):
        if not value:
            continue
        result.append("" if value == "default" else value)
    return result or DEFAULT_ORDERS


def _export_catalog_with_guard(records: list, output_dir: Path) -> dict:
    try:
        from .exporter import export_catalog

        return export_catalog(records, output_dir)
    except Exception as exc:
        return {"error": str(exc)}


def run_crawler(args: argparse.Namespace) -> int:
    config = load_config(
        output_dir=args.output_dir,
        pages=args.pages,
        keywords_file=args.keywords_file,
        browser_fallback=args.browser_fallback,
        since=args.since,
    )
    config.ensure_directories()
    store = CatalogStore(config)
    collector = BilibiliCollector(config)
    records = store.load_catalog()

    completed_ids: set[str] = set()
    if args.resume:
        resumed = store.resume_tasks()
        if resumed is None:
            print("没有找到可续跑的 current_run.json，将启动新任务。")
            run_id = _make_run_id()
            custom_keywords = load_custom_keywords(config.keywords_file)
            if args.keyword:
                custom_keywords.extend(args.keyword)
            tasks = build_search_tasks(
                pages=config.pages,
                custom_keywords=custom_keywords,
                orders=_resolve_orders(args.orders),
                include_default=not bool(args.keyword),
            )
            store.initialize_run(run_id, tasks)
        else:
            run_id, tasks, completed_ids = resumed
    else:
        run_id = _make_run_id()
        custom_keywords = load_custom_keywords(config.keywords_file)
        if args.keyword:
            custom_keywords.extend(args.keyword)
        tasks = build_search_tasks(
            pages=config.pages,
            custom_keywords=custom_keywords,
            orders=_resolve_orders(args.orders),
            include_default=not bool(args.keyword),
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

    for task in tasks:
        if task.task_id in completed_ids:
            continue
        counters["searched_tasks"] += 1
        try:
            summaries = collector.search_videos(task)
            task_results = 0
            for summary in summaries:
                existing = records.get(summary.bvid)
                if existing is not None and not record_needs_refresh(existing):
                    existing.query_keywords = sorted(set(existing.query_keywords + [task.keyword]))
                    existing.source_pages = sorted(
                        set(existing.source_pages + [f"{task.order_label}:{task.page}"])
                    )
                    existing.crawl_time = _utc_now_iso()
                    existing.run_id = run_id
                    counters["skipped_existing"] += 1
                    task_results += 1
                    continue

                record = build_video_record(
                    summary=summary,
                    detail=None,
                    tag_names=[],
                    task=task,
                    run_id=run_id,
                    crawl_time=_utc_now_iso(),
                )
                if not summary_has_required_fields(summary) or record_needs_refresh(record):
                    try:
                        detail = collector.fetch_video_detail(summary.bvid)
                        tags = []
                        if not summary.tag_text:
                            tags = collector.fetch_video_tags(summary.bvid)
                        record = build_video_record(
                            summary=summary,
                            detail=detail,
                            tag_names=tags,
                            task=task,
                            run_id=run_id,
                            crawl_time=_utc_now_iso(),
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
            store.update_task_status(task, status="completed", result_count=task_results)
            counters["completed_tasks"] += 1
        except Exception as exc:
            store.update_task_status(task, status="failed", error=str(exc))
            counters["failed_tasks"] += 1

    store.save_catalog(records.values())
    store.save_seen_index(records.values())
    export_paths = _export_catalog_with_guard(list(records.values()), config.output_dir)

    summary = {
        "run_id": run_id,
        "finished_at": _utc_now_iso(),
        "counters": counters,
        "export_paths": export_paths,
        "catalog_size": len([record for record in records.values() if record.status != "filtered_irrelevant"]),
    }
    store.finalize_run(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if counters["failed_tasks"] == 0 else 1


def resume_crawler(args: argparse.Namespace) -> int:
    run_args = argparse.Namespace(
        command="run",
        pages=None,
        keywords_file=None,
        keyword=None,
        output_dir=args.output_dir,
        resume=True,
        browser_fallback=args.browser_fallback,
        since=None,
        orders="default,pubdate",
    )
    return run_crawler(run_args)


def export_existing(args: argparse.Namespace) -> int:
    config = load_config(output_dir=args.output_dir)
    config.ensure_directories()
    store = CatalogStore(config)
    records = list(store.load_catalog().values())
    if not records:
        print("未找到现有 JSONL 数据。")
        return 1
    export_paths = _export_catalog_with_guard(records, config.output_dir)
    print(json.dumps(export_paths, ensure_ascii=False, indent=2))
    return 0


def export_space_checkpoint(output_dir: Path, uploader_name: str) -> dict:
    checkpoint_path = output_dir / "space_records_checkpoint.jsonl"
    if not checkpoint_path.exists():
        raise RuntimeError("未找到空间抓取 checkpoint。")
    from .models import VideoRecord

    records = []
    for line in checkpoint_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(VideoRecord.from_json_dict(json.loads(line)))
    tutorial_records = [
        record for record in records if is_tutorial_video(record.title, record.desc_excerpt)
    ]

    all_exports = _export_catalog_with_guard(records, output_dir)
    tutorial_dir = output_dir / "tutorial_only"
    tutorial_dir.mkdir(parents=True, exist_ok=True)
    tutorial_exports = _export_catalog_with_guard(tutorial_records, tutorial_dir)
    return {
        "uploader_name": uploader_name,
        "fetched_records": len(records),
        "tutorial_records": len(tutorial_records),
        "all_exports": all_exports,
        "tutorial_exports": tutorial_exports,
    }


def validate_environment(args: argparse.Namespace) -> int:
    config = load_config(output_dir=args.output_dir)
    config.ensure_directories()
    checks = {
        "output_dir": str(config.output_dir.resolve()),
        "node_bin": config.node_bin,
        "browser_fallback_enabled": config.browser_fallback,
        "browser_debug_url": config.browser_debug_url,
        "detail_workers": config.detail_workers,
        "pages": config.pages,
        "catalog_exists": config.catalog_jsonl_path.exists(),
        "keywords_file_exists": config.keywords_file.exists() if config.keywords_file else False,
    }
    try:
        BilibiliCollector(config).fetch_video_detail("BV1qYSvBHELW")
        checks["detail_api_probe"] = "ok"
    except Exception as exc:
        checks["detail_api_probe"] = f"failed: {exc}"
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0


def _load_failed_bvids(failed_records_path: Path) -> list[str]:
    if not failed_records_path.exists():
        return []
    bvids: list[str] = []
    for line in failed_records_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        bvid = str(payload.get("bvid") or "").strip()
        if bvid:
            bvids.append(bvid)
    return bvids


def run_space_crawler(args: argparse.Namespace) -> int:
    config = load_config(output_dir=args.output_dir)
    config.ensure_directories()
    run_id = _make_run_id()
    browser_debug_url = args.browser_debug_url or config.browser_debug_url
    detail_workers = args.detail_workers or config.detail_workers
    playlist_path = config.output_dir / "space_playlist.json"
    checkpoint_path = config.output_dir / "space_records_checkpoint.jsonl"
    failed_records_path = config.output_dir / "space_failed_bvids.jsonl"
    started_at = time.perf_counter()
    playlist_started_at = time.perf_counter()
    playlist = fetch_space_playlist(
        args.space_url,
        playlist_path,
        browser_debug_url=browser_debug_url,
        refresh=args.refresh_playlist,
    )
    playlist_elapsed = time.perf_counter() - playlist_started_at
    detail_started_at = time.perf_counter()
    records = fetch_space_records(
        bvids=playlist.bvids,
        uploader_query=args.uploader_name,
        run_id=run_id,
        checkpoint_path=checkpoint_path,
        max_retries=config.max_retries,
        detail_workers=detail_workers,
        connect_timeout=config.detail_connect_timeout,
        read_timeout=config.detail_read_timeout,
        failed_records_path=failed_records_path,
        request_headers=config.request_headers,
        progress_label="fetched",
    )
    detail_elapsed = time.perf_counter() - detail_started_at

    store = CatalogStore(config)
    export_started_at = time.perf_counter()
    store.save_catalog(records)
    store.save_seen_index(records)
    export_summary = export_space_checkpoint(config.output_dir, args.uploader_name)
    export_elapsed = time.perf_counter() - export_started_at
    total_elapsed = time.perf_counter() - started_at
    summary = {
        "run_id": run_id,
        "space_url": args.space_url,
        "uploader_name": args.uploader_name,
        "playlist_mid": playlist.mid,
        "playlist_count": playlist.playlist_count,
        "playlist_source": playlist.source,
        "fetched_records": export_summary["fetched_records"],
        "tutorial_records": export_summary["tutorial_records"],
        "detail_workers": detail_workers,
        "failed_bvids_path": str(failed_records_path),
        "timing": {
            "playlist_seconds": round(playlist_elapsed, 3),
            "detail_seconds": round(detail_elapsed, 3),
            "export_seconds": round(export_elapsed, 3),
            "total_seconds": round(total_elapsed, 3),
            "total_minutes": round(total_elapsed / 60, 2),
        },
        "all_exports": export_summary["all_exports"],
        "tutorial_exports": export_summary["tutorial_exports"],
    }
    summary_path = config.runs_dir / f"{run_id}_space_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def retry_space_failed(args: argparse.Namespace) -> int:
    config = load_config(output_dir=args.output_dir)
    config.ensure_directories()
    run_id = _make_run_id()
    detail_workers = args.detail_workers or config.detail_workers
    checkpoint_path = config.output_dir / "space_records_checkpoint.jsonl"
    failed_records_path = config.output_dir / "space_failed_bvids.jsonl"
    bvids = _load_failed_bvids(failed_records_path)
    if not bvids:
        print(json.dumps({"run_id": run_id, "message": "没有待重试的失败 BV。"}, ensure_ascii=False, indent=2))
        return 0

    started_at = time.perf_counter()
    before_records = 0
    if checkpoint_path.exists():
        before_records = len([line for line in checkpoint_path.read_text(encoding="utf-8").splitlines() if line.strip()])
    retry_failed_path = config.output_dir / "space_failed_bvids_retry.jsonl"
    retry_started_at = time.perf_counter()
    records = fetch_space_records(
        bvids=bvids,
        uploader_query=args.uploader_name,
        run_id=run_id,
        checkpoint_path=checkpoint_path,
        max_retries=config.max_retries,
        detail_workers=detail_workers,
        connect_timeout=config.detail_connect_timeout,
        read_timeout=config.detail_read_timeout,
        failed_records_path=retry_failed_path,
        request_headers=config.request_headers,
        progress_label="retried",
    )
    retry_elapsed = time.perf_counter() - retry_started_at
    after_records = len(records)

    store = CatalogStore(config)
    export_started_at = time.perf_counter()
    store.save_catalog(records)
    store.save_seen_index(records)
    export_summary = export_space_checkpoint(config.output_dir, args.uploader_name)
    export_elapsed = time.perf_counter() - export_started_at

    if retry_failed_path.exists():
        failed_records_path.write_text(retry_failed_path.read_text(encoding="utf-8"), encoding="utf-8")
        retry_failed_path.unlink()

    remaining_failed = _load_failed_bvids(failed_records_path)
    total_elapsed = time.perf_counter() - started_at
    summary = {
        "run_id": run_id,
        "uploader_name": args.uploader_name,
        "retried_bvids": len(bvids),
        "recovered_records": max(0, after_records - before_records),
        "remaining_failed_bvids": len(remaining_failed),
        "detail_workers": detail_workers,
        "timing": {
            "retry_seconds": round(retry_elapsed, 3),
            "export_seconds": round(export_elapsed, 3),
            "total_seconds": round(total_elapsed, 3),
            "total_minutes": round(total_elapsed / 60, 2),
        },
        "all_exports": export_summary["all_exports"],
        "tutorial_exports": export_summary["tutorial_exports"],
    }
    summary_path = config.runs_dir / f"{run_id}_retry_space_failed_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "run":
        return run_crawler(args)
    if args.command == "resume":
        return resume_crawler(args)
    if args.command == "export":
        return export_existing(args)
    if args.command == "validate":
        return validate_environment(args)
    if args.command == "space":
        return run_space_crawler(args)
    if args.command == "retry-space-failed":
        return retry_space_failed(args)
    raise ValueError(f"未知命令: {args.command}")
