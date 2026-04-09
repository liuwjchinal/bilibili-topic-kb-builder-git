from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}
ACTIVE_JOB_STATUSES = {"queued", "running"}


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


@dataclass(frozen=True)
class SnapshotRecord:
    id: int
    pack_slug: str
    job_id: str
    created_at: str
    output_dir: str
    payload: dict
    exports: dict
    summary: dict


class RuntimeDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def init_schema(self) -> None:
        connection = self._connect()
        try:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS pack_state (
                        pack_slug TEXT PRIMARY KEY,
                        last_snapshot_id INTEGER,
                        last_job_id TEXT,
                        last_job_status TEXT,
                        last_refreshed_at TEXT,
                        last_error_code TEXT,
                        last_error_message TEXT,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS jobs (
                        id TEXT PRIMARY KEY,
                        pack_slug TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        finished_at TEXT,
                        error_code TEXT,
                        error_message TEXT,
                        counters_json TEXT,
                        meta_json TEXT,
                        cancel_requested INTEGER NOT NULL DEFAULT 0,
                        snapshot_id INTEGER
                    );

                    CREATE TABLE IF NOT EXISTS job_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS job_previews (
                        job_id TEXT PRIMARY KEY,
                        payload_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pack_slug TEXT NOT NULL,
                        job_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        output_dir TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        exports_json TEXT NOT NULL,
                        summary_json TEXT NOT NULL
                    );
                    """
                )
        finally:
            connection.close()

    def recover_incomplete_jobs(self) -> int:
        now = utc_now_iso()
        connection = self._connect()
        try:
            with connection:
                interrupted_rows = connection.execute(
                    """
                    SELECT id, pack_slug
                    FROM jobs
                    WHERE status IN ('queued', 'running')
                    """
                ).fetchall()
                cursor = connection.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed',
                        finished_at = ?,
                        error_code = COALESCE(error_code, 'process_restart'),
                        error_message = COALESCE(error_message, 'Job interrupted by process restart')
                    WHERE status IN ('queued', 'running')
                    """,
                    (now,),
                )
                recovered = cursor.rowcount
                process_restart_rows = connection.execute(
                    """
                    SELECT id, pack_slug
                    FROM jobs
                    WHERE error_code = 'process_restart'
                    """
                ).fetchall()
                if process_restart_rows:
                    interrupted_job_ids = [row["id"] for row in process_restart_rows]
                    connection.executemany(
                        """
                        DELETE FROM job_previews
                        WHERE job_id = ?
                        """,
                        [(job_id,) for job_id in interrupted_job_ids],
                    )
                if recovered:
                    connection.executemany(
                        """
                        INSERT INTO pack_state (
                            pack_slug, last_job_id, last_job_status, last_error_code, last_error_message, updated_at
                        ) VALUES (?, ?, 'failed', 'process_restart', 'Job interrupted by process restart', ?)
                        ON CONFLICT(pack_slug) DO UPDATE SET
                            last_job_id = excluded.last_job_id,
                            last_job_status = excluded.last_job_status,
                            last_error_code = excluded.last_error_code,
                            last_error_message = excluded.last_error_message,
                            updated_at = excluded.updated_at
                        """,
                        [(row["pack_slug"], row["id"], now) for row in interrupted_rows],
                    )
                connection.execute(
                    """
                    UPDATE pack_state
                    SET last_job_status = 'failed',
                        last_error_code = 'process_restart',
                        last_error_message = 'Job interrupted by process restart',
                        updated_at = ?
                    WHERE last_job_id IN (
                        SELECT id FROM jobs WHERE error_code = 'process_restart'
                    )
                    """,
                    (now,),
                )
            return recovered
        finally:
            connection.close()

    def _row_to_job(self, row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        return {
            "id": row["id"],
            "pack_slug": row["pack_slug"],
            "status": row["status"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "error_code": row["error_code"],
            "error_message": row["error_message"],
            "counters": _loads(row["counters_json"], {}),
            "meta": _loads(row["meta_json"], {}),
            "cancel_requested": bool(row["cancel_requested"]),
            "snapshot_id": row["snapshot_id"],
        }

    def create_job(self, pack_slug: str, meta: dict | None = None) -> dict:
        job_id = uuid.uuid4().hex
        now = utc_now_iso()
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO jobs (
                        id, pack_slug, status, created_at, counters_json, meta_json, cancel_requested
                    ) VALUES (?, ?, 'queued', ?, ?, ?, 0)
                    """,
                    (job_id, pack_slug, now, _dumps({}), _dumps(meta or {})),
                )
                connection.execute(
                    """
                    INSERT INTO pack_state (
                        pack_slug, last_job_id, last_job_status, updated_at
                    ) VALUES (?, ?, 'queued', ?)
                    ON CONFLICT(pack_slug) DO UPDATE SET
                        last_job_id = excluded.last_job_id,
                        last_job_status = excluded.last_job_status,
                        updated_at = excluded.updated_at
                    """,
                    (pack_slug, job_id, now),
                )
            return self.get_job(job_id) or {}
        finally:
            connection.close()

    def get_job(self, job_id: str) -> dict | None:
        connection = self._connect()
        try:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return self._row_to_job(row)
        finally:
            connection.close()

    def get_active_job(self, pack_slug: str) -> dict | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM jobs
                WHERE pack_slug = ? AND status IN ('queued', 'running')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (pack_slug,),
            ).fetchone()
            return self._row_to_job(row)
        finally:
            connection.close()

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        counters: dict | None = None,
        meta: dict | None = None,
        snapshot_id: int | None = None,
    ) -> dict | None:
        fields: list[str] = []
        values: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if started_at is not None:
            fields.append("started_at = ?")
            values.append(started_at)
        if finished_at is not None:
            fields.append("finished_at = ?")
            values.append(finished_at)
        if error_code is not None:
            fields.append("error_code = ?")
            values.append(error_code)
        if error_message is not None:
            fields.append("error_message = ?")
            values.append(error_message)
        if counters is not None:
            fields.append("counters_json = ?")
            values.append(_dumps(counters))
        if meta is not None:
            fields.append("meta_json = ?")
            values.append(_dumps(meta))
        if snapshot_id is not None:
            fields.append("snapshot_id = ?")
            values.append(snapshot_id)
        if not fields:
            return self.get_job(job_id)

        now = utc_now_iso()
        values.append(job_id)
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?",
                    tuple(values),
                )
                row = connection.execute("SELECT pack_slug, status FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if row is not None:
                    connection.execute(
                        """
                        INSERT INTO pack_state (
                            pack_slug, last_job_id, last_job_status, updated_at
                        ) VALUES (?, ?, ?, ?)
                        ON CONFLICT(pack_slug) DO UPDATE SET
                            last_job_id = excluded.last_job_id,
                            last_job_status = excluded.last_job_status,
                            updated_at = excluded.updated_at
                        """,
                        (row["pack_slug"], job_id, row["status"], now),
                    )
            return self.get_job(job_id)
        finally:
            connection.close()

    def request_cancel(self, job_id: str) -> dict | None:
        connection = self._connect()
        try:
            with connection:
                connection.execute("UPDATE jobs SET cancel_requested = 1 WHERE id = ?", (job_id,))
            return self.get_job(job_id)
        finally:
            connection.close()

    def is_cancel_requested(self, job_id: str) -> bool:
        connection = self._connect()
        try:
            row = connection.execute("SELECT cancel_requested FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return bool(row["cancel_requested"]) if row is not None else False
        finally:
            connection.close()

    def append_job_event(self, job_id: str, event_type: str, payload: dict) -> int:
        now = utc_now_iso()
        connection = self._connect()
        try:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO job_events (job_id, event_type, created_at, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (job_id, event_type, now, _dumps(payload)),
                )
            return int(cursor.lastrowid)
        finally:
            connection.close()

    def get_job_events(self, job_id: str, after_id: int = 0) -> list[dict]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM job_events
                WHERE job_id = ? AND id > ?
                ORDER BY id ASC
                """,
                (job_id, after_id),
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "job_id": row["job_id"],
                    "event_type": row["event_type"],
                    "created_at": row["created_at"],
                    "payload": _loads(row["payload_json"], {}),
                }
                for row in rows
            ]
        finally:
            connection.close()

    def replace_job_preview(self, job_id: str, payload: dict) -> None:
        now = utc_now_iso()
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO job_previews (job_id, payload_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    (job_id, _dumps(payload), now),
                )
        finally:
            connection.close()

    def get_job_preview(self, job_id: str) -> dict | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT payload_json, updated_at FROM job_previews WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            payload = _loads(row["payload_json"], {})
            payload["_updated_at"] = row["updated_at"]
            return payload
        finally:
            connection.close()

    def clear_job_preview(self, job_id: str) -> None:
        connection = self._connect()
        try:
            with connection:
                connection.execute("DELETE FROM job_previews WHERE job_id = ?", (job_id,))
        finally:
            connection.close()

    def create_snapshot(
        self,
        *,
        pack_slug: str,
        job_id: str,
        payload: dict,
        output_dir: str,
        exports: dict,
        summary: dict,
    ) -> SnapshotRecord:
        now = utc_now_iso()
        connection = self._connect()
        try:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO snapshots (
                        pack_slug, job_id, created_at, output_dir, payload_json, exports_json, summary_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (pack_slug, job_id, now, output_dir, _dumps(payload), _dumps(exports), _dumps(summary)),
                )
                snapshot_id = int(cursor.lastrowid)
                connection.execute(
                    """
                    INSERT INTO pack_state (
                        pack_slug, last_snapshot_id, last_job_id, last_job_status,
                        last_refreshed_at, last_error_code, last_error_message, updated_at
                    ) VALUES (?, ?, ?, 'succeeded', ?, NULL, NULL, ?)
                    ON CONFLICT(pack_slug) DO UPDATE SET
                        last_snapshot_id = excluded.last_snapshot_id,
                        last_job_id = excluded.last_job_id,
                        last_job_status = excluded.last_job_status,
                        last_refreshed_at = excluded.last_refreshed_at,
                        last_error_code = NULL,
                        last_error_message = NULL,
                        updated_at = excluded.updated_at
                    """,
                    (pack_slug, snapshot_id, job_id, now, now),
                )
            return SnapshotRecord(
                id=snapshot_id,
                pack_slug=pack_slug,
                job_id=job_id,
                created_at=now,
                output_dir=output_dir,
                payload=payload,
                exports=exports,
                summary=summary,
            )
        finally:
            connection.close()

    def get_current_snapshot(self, pack_slug: str) -> SnapshotRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT s.*
                FROM snapshots s
                JOIN pack_state p ON p.last_snapshot_id = s.id
                WHERE p.pack_slug = ?
                """,
                (pack_slug,),
            ).fetchone()
            if row is None:
                return None
            return SnapshotRecord(
                id=row["id"],
                pack_slug=row["pack_slug"],
                job_id=row["job_id"],
                created_at=row["created_at"],
                output_dir=row["output_dir"],
                payload=_loads(row["payload_json"], {}),
                exports=_loads(row["exports_json"], {}),
                summary=_loads(row["summary_json"], {}),
            )
        finally:
            connection.close()

    def get_pack_state(self, pack_slug: str) -> dict | None:
        connection = self._connect()
        try:
            row = connection.execute("SELECT * FROM pack_state WHERE pack_slug = ?", (pack_slug,)).fetchone()
            if row is None:
                return None
            return dict(row)
        finally:
            connection.close()

    def list_pack_states(self) -> dict[str, dict]:
        connection = self._connect()
        try:
            rows = connection.execute("SELECT * FROM pack_state").fetchall()
            return {row["pack_slug"]: dict(row) for row in rows}
        finally:
            connection.close()

    def record_pack_failure(
        self,
        pack_slug: str,
        *,
        job_id: str,
        job_status: str,
        error_code: str,
        error_message: str,
    ) -> None:
        now = utc_now_iso()
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO pack_state (
                        pack_slug, last_job_id, last_job_status, last_error_code, last_error_message, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(pack_slug) DO UPDATE SET
                        last_job_id = excluded.last_job_id,
                        last_job_status = excluded.last_job_status,
                        last_error_code = excluded.last_error_code,
                        last_error_message = excluded.last_error_message,
                        updated_at = excluded.updated_at
                    """,
                    (pack_slug, job_id, job_status, error_code, error_message, now),
                )
        finally:
            connection.close()
