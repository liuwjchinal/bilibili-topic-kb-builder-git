from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable

from .config import AppConfig
from .models import SearchTask, VideoRecord


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class CatalogStore:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.current_run_path = config.state_dir / "current_run.json"
        self.last_run_path = config.state_dir / "last_run.json"
        self.seen_index_path = config.state_dir / "seen_videos.json"
        self.failure_log_path = config.state_dir / "failures.jsonl"

    def load_catalog(self) -> dict[str, VideoRecord]:
        if not self.config.catalog_jsonl_path.exists():
            return {}
        records: dict[str, VideoRecord] = {}
        for line in self.config.catalog_jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = VideoRecord.from_json_dict(json.loads(line))
            records[record.unique_key] = record
        return records

    def save_catalog(self, records: Iterable[VideoRecord]) -> None:
        lines = [json.dumps(record.to_json_dict(), ensure_ascii=False) for record in records]
        self.config.catalog_jsonl_path.write_text("\n".join(lines), encoding="utf-8")

    def save_seen_index(self, records: Iterable[VideoRecord]) -> None:
        payload = {
            record.unique_key: {
                "bvid": record.bvid,
                "title": record.title,
                "primary_category": record.primary_category,
                "status": record.status,
                "last_run_id": record.run_id,
                "last_crawl_time": record.crawl_time,
            }
            for record in records
        }
        self.seen_index_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def initialize_run(self, run_id: str, tasks: list[SearchTask]) -> None:
        payload = {
            "run_id": run_id,
            "started_at": utc_now_iso(),
            "tasks": {
                task.task_id: {
                    "status": "pending",
                    "keyword": task.keyword,
                    "page": task.page,
                    "order": task.order,
                }
                for task in tasks
            },
        }
        self.current_run_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_current_run(self) -> dict | None:
        if not self.current_run_path.exists():
            return None
        return json.loads(self.current_run_path.read_text(encoding="utf-8"))

    def update_task_status(
        self,
        task: SearchTask,
        status: str,
        result_count: int = 0,
        error: str = "",
    ) -> None:
        payload = self.load_current_run()
        if payload is None:
            return
        payload["tasks"][task.task_id].update(
            {
                "status": status,
                "result_count": result_count,
                "updated_at": utc_now_iso(),
            }
        )
        if error:
            payload["tasks"][task.task_id]["error"] = error
            with self.failure_log_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "task_id": task.task_id,
                            "keyword": task.keyword,
                            "page": task.page,
                            "order": task.order,
                            "error": error,
                            "failed_at": utc_now_iso(),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        self.current_run_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def finalize_run(self, summary: dict) -> None:
        summary_path = self.config.runs_dir / f"{summary['run_id']}_summary.json"
        if self.current_run_path.exists():
            payload = json.loads(self.current_run_path.read_text(encoding="utf-8"))
            payload["finished_at"] = utc_now_iso()
            payload["summary_path"] = str(summary_path)
            summary["run_state"] = payload
            self.current_run_path.unlink()
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.last_run_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def resume_tasks(self) -> tuple[str, list[SearchTask], set[str]] | None:
        payload = self.load_current_run()
        if payload is None:
            return None
        tasks: list[SearchTask] = []
        completed: set[str] = set()
        for task_id, data in payload["tasks"].items():
            task = SearchTask(
                keyword=data["keyword"],
                page=int(data["page"]),
                order=data.get("order", ""),
            )
            tasks.append(task)
            if data.get("status") == "completed":
                completed.add(task_id)
        return payload["run_id"], tasks, completed
