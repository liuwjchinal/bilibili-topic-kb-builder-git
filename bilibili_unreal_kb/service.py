from __future__ import annotations

import asyncio
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse

from .config import DEFAULT_PACK_SLUG, AppConfig, default_pack_output_dir, load_config
from .exporter import WEBAPP_DIR, build_frontend_payload, export_catalog
from .models import VideoRecord
from .packs import (
    PackDefinition,
    clear_pack_cache,
    create_pack_from_payload,
    get_pack,
    list_pack_templates,
    list_packs,
)
from .runtime_db import ACTIVE_JOB_STATUSES, FINAL_JOB_STATUSES, RuntimeDatabase, utc_now_iso
from .store import CatalogStore
from .topic_pipeline import PipelineHooks, categorize_error, run_topic_pipeline


SERVICE_BOOTSTRAP_JS = """
window.__BILIBILI_KB_DATA__ = null;
window.__BILIBILI_KB_SERVICE__ = { apiBase: "/api" };
""".strip()


class KnowledgeBaseService:
    def __init__(self, config: AppConfig | None = None, runtime_db: RuntimeDatabase | None = None) -> None:
        self.base_config = config or load_config(pack_slug=DEFAULT_PACK_SLUG)
        self.runtime_db = runtime_db or RuntimeDatabase(self.base_config.database_path)
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}

    def startup(self) -> None:
        self.base_config.root_output_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_db.init_schema()
        self.runtime_db.recover_incomplete_jobs()
        self._import_legacy_snapshot_if_needed()

    def final_output_dir(self, pack_slug: str) -> Path:
        return default_pack_output_dir(self.base_config.root_output_dir, pack_slug)

    def staging_output_dir(self, pack_slug: str, job_id: str) -> Path:
        return self.base_config.root_output_dir / "service-jobs" / pack_slug / job_id

    def build_config(self, pack_slug: str, output_dir: Path | None = None) -> AppConfig:
        resolved_output_dir = output_dir or self.final_output_dir(pack_slug)
        config = load_config(output_dir=str(resolved_output_dir), pack_slug=pack_slug)
        config.root_output_dir = self.base_config.root_output_dir
        config.database_path = self.base_config.database_path
        return config

    def _make_snapshot_meta(
        self,
        *,
        pack: PackDefinition,
        mode: str,
        status: str,
        job_id: str | None,
        summary: dict | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        output_dir: str | None = None,
    ) -> dict:
        summary = summary or {}
        pack_state = self.runtime_db.get_pack_state(pack.slug) or {}
        last_error = None
        effective_error_code = error_code or pack_state.get("last_error_code")
        effective_error_message = error_message or pack_state.get("last_error_message")
        if effective_error_code or effective_error_message:
            last_error = {"code": effective_error_code, "message": effective_error_message}
        return {
            "mode": mode,
            "status": status,
            "job_id": job_id,
            "run_id": summary.get("run_id"),
            "pack_slug": pack.slug,
            "catalog_size": summary.get("catalog_size", 0),
            "counters": summary.get("counters", {}),
            "task_index": summary.get("task_index"),
            "total_tasks": summary.get("total_tasks"),
            "finished_at": summary.get("finished_at"),
            "last_refreshed_at": pack_state.get("last_refreshed_at"),
            "last_error": last_error,
            "output_dir": output_dir,
        }

    def _empty_payload(self, pack: PackDefinition) -> dict:
        snapshot_meta = self._make_snapshot_meta(
            pack=pack,
            mode="empty",
            status="idle",
            job_id=None,
            summary={"catalog_size": 0, "counters": {}},
        )
        return {
            "pack": {
                "slug": pack.slug,
                "display_name": pack.display_name,
                "description": pack.description,
                "domain_key": pack.domain.key,
                "domain_label": pack.domain.display_name,
            },
            "generated_at": "",
            "summary": {
                "total_videos": 0,
                "total_categories": 0,
                "total_uploaders": 0,
                "total_duration_seconds": 0,
                "total_duration_text": "0秒",
            },
            "categories": [],
            "videos": [],
            "snapshot": snapshot_meta,
        }

    def _write_summary_file(self, output_dir: Path, summary: dict) -> Path:
        runs_dir = output_dir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        summary_path = runs_dir / f"{summary['run_id']}_summary.json"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary_path

    def _finalize_staging_run(self, job_config: AppConfig, summary: dict) -> None:
        CatalogStore(job_config).finalize_run(summary)

    def _import_legacy_snapshot_if_needed(self) -> None:
        if self.runtime_db.get_current_snapshot(DEFAULT_PACK_SLUG) is not None:
            return

        candidates = [
            self.base_config.root_output_dir / "unreal_tutorials.jsonl",
            self.base_config.root_output_dir / "videos.jsonl",
        ]
        legacy_path = next((path for path in candidates if path.exists()), None)
        if legacy_path is None:
            return

        records: list[VideoRecord] = []
        for line in legacy_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            records.append(VideoRecord.from_json_dict(json.loads(line)))
        if not records:
            return

        pack = get_pack(DEFAULT_PACK_SLUG)
        final_output_dir = self.final_output_dir(pack.slug)
        final_output_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "run_id": "legacy-import",
            "pack_slug": pack.slug,
            "catalog_size": len(records),
            "counters": {"imported_records": len(records)},
            "finished_at": utc_now_iso(),
            "status": "imported",
        }
        snapshot_meta = self._make_snapshot_meta(
            pack=pack,
            mode="snapshot",
            status="imported",
            job_id="legacy-import",
            summary=summary,
            output_dir=str(final_output_dir),
        )
        exports = export_catalog(records, final_output_dir, pack=pack, snapshot_meta=snapshot_meta)
        payload = build_frontend_payload(records, pack=pack, snapshot_meta=snapshot_meta)
        self.runtime_db.create_snapshot(
            pack_slug=pack.slug,
            job_id="legacy-import",
            payload=payload,
            output_dir=str(final_output_dir),
            exports=exports,
            summary=summary,
        )
        self._write_summary_file(final_output_dir, summary)

    def list_pack_payloads(self) -> list[dict]:
        states = self.runtime_db.list_pack_states()
        payloads: list[dict] = []
        for pack in list_packs():
            snapshot = self.runtime_db.get_current_snapshot(pack.slug)
            active_job = self.runtime_db.get_active_job(pack.slug)
            state = states.get(pack.slug) or {}
            payloads.append(
                {
                    "slug": pack.slug,
                    "display_name": pack.display_name,
                    "description": pack.description,
                    "last_refreshed_at": state.get("last_refreshed_at"),
                    "last_error": {
                        "code": state.get("last_error_code"),
                        "message": state.get("last_error_message"),
                    }
                    if state.get("last_error_code") or state.get("last_error_message")
                    else None,
                    "snapshot_id": snapshot.id if snapshot is not None else None,
                    "snapshot_generated_at": snapshot.payload.get("generated_at") if snapshot is not None else None,
                    "active_job": active_job,
                }
            )
        return payloads

    def list_pack_template_payloads(self) -> list[dict]:
        return list_pack_templates()

    def create_pack(self, payload: dict[str, Any]) -> dict:
        with self._lock:
            pack = create_pack_from_payload(payload)
            clear_pack_cache()
            packs = list_packs()
        if not any(item.slug == pack.slug for item in packs):
            raise RuntimeError(f"pack reload failed: {pack.slug}")
        return {
            "pack": {
                "slug": pack.slug,
                "display_name": pack.display_name,
                "description": pack.description,
            },
            "output_dir": str(self.final_output_dir(pack.slug)),
            "has_snapshot": False,
        }

    def _load_preview_payload(self, job_id: str) -> dict | None:
        preview = self.runtime_db.get_job_preview(job_id)
        if preview is None:
            return None

        job = self.runtime_db.get_job(job_id)
        if job is None:
            return None
        if job.get("error_code") == "process_restart":
            return None

        snapshot_meta = dict(preview.get("snapshot") or {})
        snapshot_meta["job_id"] = job_id
        snapshot_meta["status"] = job.get("status", snapshot_meta.get("status"))
        if job.get("finished_at"):
            snapshot_meta["finished_at"] = job["finished_at"]
        if job.get("error_code") or job.get("error_message"):
            snapshot_meta["last_error"] = {
                "code": job.get("error_code"),
                "message": job.get("error_message"),
            }
        preview["snapshot"] = snapshot_meta
        return preview

    def resolve_pack_payload(self, pack_slug: str, mode: str = "auto") -> dict:
        pack = get_pack(pack_slug)
        active_job = self.runtime_db.get_active_job(pack_slug)
        snapshot = self.runtime_db.get_current_snapshot(pack_slug)
        state = self.runtime_db.get_pack_state(pack_slug) or {}

        payload: dict
        resolved_mode = "snapshot"
        if mode in {"auto", "preview"} and active_job is not None:
            preview = self._load_preview_payload(active_job["id"])
            if preview is not None:
                payload = dict(preview)
                payload.pop("_updated_at", None)
                resolved_mode = "preview"
            elif snapshot is not None:
                payload = dict(snapshot.payload)
            else:
                payload = self._empty_payload(pack)
                resolved_mode = "empty"
        elif mode in {"auto", "preview"} and state.get("last_job_id") and state.get("last_job_status") in {"failed", "cancelled"}:
            preview = self._load_preview_payload(str(state["last_job_id"]))
            if preview is not None:
                payload = dict(preview)
                payload.pop("_updated_at", None)
                resolved_mode = "preview"
            elif snapshot is not None:
                payload = dict(snapshot.payload)
            else:
                payload = self._empty_payload(pack)
                resolved_mode = "empty"
        elif snapshot is not None:
            payload = dict(snapshot.payload)
        else:
            payload = self._empty_payload(pack)
            resolved_mode = "empty"

        last_error = None
        if state.get("last_error_code") or state.get("last_error_message"):
            last_error = {
                "code": state.get("last_error_code"),
                "message": state.get("last_error_message"),
            }
        payload["mode"] = resolved_mode
        payload["job"] = active_job
        payload["last_error"] = last_error
        payload["exports"] = snapshot.exports if snapshot is not None else {}
        return payload

    def start_refresh(self, pack_slug: str) -> dict:
        get_pack(pack_slug)
        with self._lock:
            active_job = self.runtime_db.get_active_job(pack_slug)
            if active_job is not None:
                return active_job
            job = self.runtime_db.create_job(pack_slug, meta={"requested_via": "service"})
            self.runtime_db.append_job_event(
                job["id"],
                "job_queued",
                {"job_id": job["id"], "pack_slug": pack_slug, "status": "queued"},
            )
            thread = threading.Thread(
                target=self._run_refresh_job,
                args=(job["id"], pack_slug),
                name=f"bilibili-refresh-{pack_slug}",
                daemon=True,
            )
            self._threads[pack_slug] = thread
            thread.start()
            return self.runtime_db.get_job(job["id"]) or job

    def cancel_job(self, job_id: str) -> dict:
        job = self.runtime_db.request_cancel(job_id)
        if job is None:
            raise KeyError(job_id)
        self.runtime_db.append_job_event(
            job_id,
            "job_cancel_requested",
            {"job_id": job_id, "pack_slug": job["pack_slug"], "status": job["status"]},
        )
        return job

    def _store_preview(
        self,
        job_id: str,
        pack: PackDefinition,
        records: list[VideoRecord],
        progress: dict,
        *,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        snapshot_meta = self._make_snapshot_meta(
            pack=pack,
            mode="preview",
            status=status,
            job_id=job_id,
            summary=progress,
            error_code=error_code,
            error_message=error_message,
            output_dir=str(self.staging_output_dir(pack.slug, job_id)),
        )
        payload = build_frontend_payload(records, pack=pack, snapshot_meta=snapshot_meta)
        self.runtime_db.replace_job_preview(job_id, payload)
        self.runtime_db.update_job(job_id, status=status, counters=progress.get("counters", {}), meta=progress)

    def _update_preview(self, job_id: str, pack: PackDefinition, records: list[VideoRecord], progress: dict) -> None:
        self._store_preview(job_id, pack, records, progress, status="running")

    def _run_refresh_job(self, job_id: str, pack_slug: str) -> None:
        pack = get_pack(pack_slug)
        started_at = utc_now_iso()
        staging_dir = self.staging_output_dir(pack_slug, job_id)
        job_config = self.build_config(pack_slug, staging_dir)
        job_config.ensure_directories()
        final_output_dir = self.final_output_dir(pack_slug)
        final_output_dir.mkdir(parents=True, exist_ok=True)

        self.runtime_db.update_job(job_id, status="running", started_at=started_at)
        self.runtime_db.append_job_event(
            job_id,
            "job_started",
            {"job_id": job_id, "pack_slug": pack_slug, "status": "running", "started_at": started_at},
        )

        clear_preview = False
        try:
            result = run_topic_pipeline(
                config=job_config,
                pack=pack,
                hooks=PipelineHooks(
                    emit=lambda event_type, payload: self.runtime_db.append_job_event(job_id, event_type, payload),
                    is_cancelled=lambda: self.runtime_db.is_cancel_requested(job_id),
                    update_preview=lambda records, progress: self._update_preview(job_id, pack, records, progress),
                ),
            )
            summary = dict(result.summary)
            self._finalize_staging_run(job_config, summary)

            if self.runtime_db.is_cancel_requested(job_id):
                summary["status"] = "cancelled"
                self._store_preview(
                    job_id,
                    pack,
                    result.records,
                    summary,
                    status="cancelled",
                    error_code="cancelled",
                    error_message="Refresh cancelled by user.",
                )
                self.runtime_db.update_job(
                    job_id,
                    status="cancelled",
                    finished_at=utc_now_iso(),
                    counters=summary.get("counters", {}),
                    error_code="cancelled",
                    error_message="Refresh cancelled by user.",
                    meta=summary,
                )
                self.runtime_db.record_pack_failure(
                    pack_slug,
                    job_id=job_id,
                    job_status="cancelled",
                    error_code="cancelled",
                    error_message="Refresh cancelled by user.",
                )
                self.runtime_db.append_job_event(
                    job_id,
                    "run_cancelled",
                    {"job_id": job_id, "pack_slug": pack_slug, "summary": summary},
                )
                self._write_summary_file(final_output_dir, summary)
                return

            failed_tasks = int(summary.get("counters", {}).get("failed_tasks", 0))
            if failed_tasks > 0:
                error_message = f"{failed_tasks} search tasks failed during refresh."
                summary["status"] = "failed"
                self._store_preview(
                    job_id,
                    pack,
                    result.records,
                    summary,
                    status="failed",
                    error_code="task_failure",
                    error_message=error_message,
                )
                self.runtime_db.update_job(
                    job_id,
                    status="failed",
                    finished_at=utc_now_iso(),
                    counters=summary.get("counters", {}),
                    error_code="task_failure",
                    error_message=error_message,
                    meta=summary,
                )
                self.runtime_db.record_pack_failure(
                    pack_slug,
                    job_id=job_id,
                    job_status="failed",
                    error_code="task_failure",
                    error_message=error_message,
                )
                self.runtime_db.append_job_event(
                    job_id,
                    "run_failed",
                    {
                        "job_id": job_id,
                        "pack_slug": pack_slug,
                        "error_category": "task_failure",
                        "error": error_message,
                        "summary": summary,
                    },
                )
                self._write_summary_file(final_output_dir, summary)
                return

            summary["status"] = "succeeded"
            snapshot_meta = self._make_snapshot_meta(
                pack=pack,
                mode="snapshot",
                status="succeeded",
                job_id=job_id,
                summary=summary,
                output_dir=str(final_output_dir),
            )
            exports = export_catalog(result.records, final_output_dir, pack=pack, snapshot_meta=snapshot_meta)
            summary["export_paths"] = exports
            payload = build_frontend_payload(result.records, pack=pack, snapshot_meta=snapshot_meta)
            snapshot = self.runtime_db.create_snapshot(
                pack_slug=pack_slug,
                job_id=job_id,
                payload=payload,
                output_dir=str(final_output_dir),
                exports=exports,
                summary=summary,
            )
            self.runtime_db.update_job(
                job_id,
                status="succeeded",
                finished_at=utc_now_iso(),
                counters=summary.get("counters", {}),
                snapshot_id=snapshot.id,
                meta=summary,
            )
            self.runtime_db.append_job_event(
                job_id,
                "run_succeeded",
                {
                    "job_id": job_id,
                    "pack_slug": pack_slug,
                    "summary": summary,
                    "snapshot_id": snapshot.id,
                },
            )
            self._write_summary_file(final_output_dir, summary)
            clear_preview = True
        except Exception as exc:
            error_code = categorize_error(exc)
            error_message = str(exc)
            self.runtime_db.update_job(
                job_id,
                status="failed",
                finished_at=utc_now_iso(),
                error_code=error_code,
                error_message=error_message,
            )
            self.runtime_db.record_pack_failure(
                pack_slug,
                job_id=job_id,
                job_status="failed",
                error_code=error_code,
                error_message=error_message,
            )
            self.runtime_db.append_job_event(
                job_id,
                "run_failed",
                {
                    "job_id": job_id,
                    "pack_slug": pack_slug,
                    "error_category": error_code,
                    "error": error_message,
                },
            )
        finally:
            if clear_preview:
                self.runtime_db.clear_job_preview(job_id)
            with self._lock:
                self._threads.pop(pack_slug, None)


def create_app(service: KnowledgeBaseService | None = None) -> FastAPI:
    resolved_service = service or KnowledgeBaseService()
    
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        resolved_service.startup()
        yield

    app = FastAPI(title="Bilibili Knowledge Base Service", lifespan=lifespan)
    app.state.kb_service = resolved_service

    @app.get("/api/packs")
    async def get_packs() -> list[dict]:
        return resolved_service.list_pack_payloads()

    @app.get("/api/pack-templates")
    async def get_pack_templates() -> list[dict]:
        return resolved_service.list_pack_template_payloads()

    @app.post("/api/packs", status_code=201)
    async def post_pack(payload: dict[str, Any]) -> dict:
        try:
            return resolved_service.create_pack(payload)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/packs/{pack_slug}/snapshot")
    async def get_pack_snapshot(pack_slug: str) -> dict:
        try:
            payload = resolved_service.resolve_pack_payload(pack_slug, mode="snapshot")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {key: value for key, value in payload.items() if key != "videos"}

    @app.get("/api/packs/{pack_slug}/videos")
    async def get_pack_videos(pack_slug: str, mode: str = "auto") -> dict:
        try:
            return resolved_service.resolve_pack_payload(pack_slug, mode=mode)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/packs/{pack_slug}/categories")
    async def get_pack_categories(pack_slug: str, mode: str = "auto") -> dict:
        try:
            payload = resolved_service.resolve_pack_payload(pack_slug, mode=mode)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "pack": payload["pack"],
            "summary": payload["summary"],
            "categories": payload["categories"],
            "snapshot": payload["snapshot"],
            "mode": payload["mode"],
            "job": payload["job"],
            "last_error": payload["last_error"],
        }

    @app.post("/api/packs/{pack_slug}/refresh")
    async def post_refresh(pack_slug: str) -> dict:
        try:
            return resolved_service.start_refresh(pack_slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/packs/{pack_slug}/exports")
    async def get_pack_exports(pack_slug: str) -> dict:
        try:
            get_pack(pack_slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        snapshot = resolved_service.runtime_db.get_current_snapshot(pack_slug)
        return {
            "pack_slug": pack_slug,
            "exports": snapshot.exports if snapshot is not None else {},
            "snapshot": snapshot.summary if snapshot is not None else None,
        }

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str) -> dict:
        job = resolved_service.runtime_db.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
        preview = resolved_service.runtime_db.get_job_preview(job_id)
        return {
            **job,
            "has_preview": preview is not None,
            "preview_updated_at": preview.get("_updated_at") if preview is not None else None,
        }

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str) -> dict:
        try:
            return resolved_service.cancel_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown job: {job_id}") from exc

    @app.get("/api/jobs/{job_id}/events")
    async def stream_job_events(request: Request, job_id: str, after_id: int = 0) -> StreamingResponse:
        if resolved_service.runtime_db.get_job(job_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")

        header_after = request.headers.get("last-event-id")
        if header_after and header_after.isdigit():
            after_id = max(after_id, int(header_after))

        async def event_stream() -> Any:
            cursor = after_id
            while True:
                events = resolved_service.runtime_db.get_job_events(job_id, after_id=cursor)
                for event in events:
                    cursor = int(event["id"])
                    yield (
                        f"id: {event['id']}\n"
                        f"event: {event['event_type']}\n"
                        f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    )

                job = resolved_service.runtime_db.get_job(job_id)
                if job is None:
                    yield "event: error\ndata: {\"message\":\"job disappeared\"}\n\n"
                    break
                if job["status"] in FINAL_JOB_STATUSES and not events:
                    break
                if await request.is_disconnected():
                    break
                await asyncio.sleep(1.0)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEBAPP_DIR / "index.html")

    @app.get("/app.js")
    async def app_js() -> FileResponse:
        return FileResponse(WEBAPP_DIR / "app.js", media_type="application/javascript")

    @app.get("/styles.css")
    async def styles_css() -> FileResponse:
        return FileResponse(WEBAPP_DIR / "styles.css", media_type="text/css")

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/data.js")
    async def data_js() -> PlainTextResponse:
        return PlainTextResponse(SERVICE_BOOTSTRAP_JS, media_type="application/javascript")

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"ok": True})

    return app
