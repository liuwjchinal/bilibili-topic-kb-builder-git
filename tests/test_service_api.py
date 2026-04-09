from __future__ import annotations

import textwrap
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from bilibili_unreal_kb.config import AppConfig
from bilibili_unreal_kb.models import VideoRecord
from bilibili_unreal_kb.packs import clear_pack_cache
from bilibili_unreal_kb.runtime_db import RuntimeDatabase
from bilibili_unreal_kb.service import KnowledgeBaseService, create_app
from bilibili_unreal_kb.topic_pipeline import TopicPipelineResult


UNREAL_CORE_FIXTURE = textwrap.dedent(
    """
    slug: unreal-core
    display_name: Unreal Core
    description: Unreal learning videos.
    search:
      core_terms:
        - UE5
      expansion_terms:
        - blueprint
      custom_queries: []
      orders:
        - default
        - pubdate
      pages: 2
    gates:
      must_have_any:
        - ue5
      irrelevant_keywords:
        - asmr
    domain:
      key: game-dev-unreal
      display_name: 游戏开发/虚幻
      allow_partition_keywords:
        - 知识
        - 计算机技术
      block_partition_keywords:
        - 音乐
        - 演奏
      required_context_any:
        - ue5
    categories:
      - id: blueprint
        name: Blueprint
        priority: 10
        keywords:
          - blueprint
    """
).strip()

LYRA_FIXTURE = textwrap.dedent(
    """
    slug: lyra
    display_name: Lyra
    description: Lyra learning videos.
    search:
      core_terms:
        - Lyra Starter Game
        - UE5 Lyra
      expansion_terms:
        - GAS
        - 教程
      custom_queries:
        - Lyra CommonUI
      orders:
        - default
        - pubdate
      pages: 2
    gates:
      must_have_any:
        - lyra
      context_any:
        - ue5
        - unreal
        - tutorial
        - 教程
        - commonui
        - gas
      irrelevant_keywords:
        - valorant
    domain:
      key: game-dev-unreal
      display_name: 游戏开发/虚幻
      allow_partition_keywords:
        - 知识
        - 计算机技术
        - 单机游戏
      block_partition_keywords:
        - 音乐
        - 演奏
      required_context_any:
        - lyra
        - ue5
        - commonui
    categories:
      - id: gas
        name: GAS/Ability System
        priority: 10
        keywords:
          - gas
      - id: experience
        name: Experience/GameFeature
        priority: 20
        keywords:
          - experience
    """
).strip()


@contextmanager
def temporary_pack_dir() -> Path:
    with TemporaryDirectory() as temp_dir:
        pack_dir = Path(temp_dir)
        (pack_dir / "unreal-core.yaml").write_text(UNREAL_CORE_FIXTURE, encoding="utf-8")
        (pack_dir / "lyra.yaml").write_text(LYRA_FIXTURE, encoding="utf-8")
        with patch("bilibili_unreal_kb.packs.PACKS_DIR", pack_dir):
            clear_pack_cache()
            try:
                yield pack_dir
            finally:
                clear_pack_cache()


def make_record() -> VideoRecord:
    return VideoRecord(
        video_id="1",
        bvid="BV1TEST",
        title="UE5 蓝图入门",
        link="https://www.bilibili.com/video/BV1TEST",
        duration_seconds=600,
        duration_text="10:00",
        uploader="测试UP",
        play_count=1000,
        publish_time="2024-01-01T00:00:00+00:00",
        query_keywords=["UE5 蓝图"],
        source_pages=["default:1"],
        primary_category="蓝图系统",
        secondary_categories=[],
        category_confidence=0.9,
        match_keywords=["蓝图"],
        tags=["UE5", "蓝图"],
        desc_excerpt="蓝图教学",
        crawl_time="2026-04-09T00:00:00+00:00",
        run_id="run_test",
        status="ok",
    )


class ServiceApiTests(unittest.TestCase):
    def build_service(self, temp_dir: str) -> KnowledgeBaseService:
        root = Path(temp_dir) / "output"
        config = AppConfig(
            root_output_dir=root,
            output_dir=root / "packs" / "unreal-core",
            database_path=root / "app.db",
            pack_slug="unreal-core",
        )
        return KnowledgeBaseService(config=config, runtime_db=RuntimeDatabase(config.database_path))

    def test_get_pack_templates_returns_builtin_templates(self) -> None:
        with TemporaryDirectory() as temp_dir, temporary_pack_dir():
            service = self.build_service(temp_dir)
            service.runtime_db.init_schema()
            app = create_app(service)
            with TestClient(app) as client:
                response = client.get("/api/pack-templates")
                self.assertEqual(response.status_code, 200)
                slugs = [item["slug"] for item in response.json()]
                self.assertEqual(slugs, ["lyra", "unreal-core"])
                lyra = next(item for item in response.json() if item["slug"] == "lyra")
                self.assertEqual(lyra["domain"]["key"], "game-dev-unreal")

    def test_create_pack_endpoint_creates_empty_pack(self) -> None:
        with TemporaryDirectory() as temp_dir, temporary_pack_dir():
            service = self.build_service(temp_dir)
            app = create_app(service)
            payload = {
                "slug": "lyra-ui-focus",
                "display_name": "Lyra UI Focus",
                "description": "Lyra UI videos.",
                "base_template_slug": "lyra",
                "search": {
                    "core_terms": ["Lyra UI"],
                    "expansion_terms": ["CommonUI", "HUD"],
                    "custom_queries": ["Lyra HUD"],
                },
                "gates": {
                    "must_have_any": ["lyra", "commonui"],
                    "irrelevant_keywords": ["valorant"],
                },
                "categories": [
                    {"id": "ui-commonui", "name": "UI/CommonUI", "keywords": ["commonui", "hud"], "priority": 10}
                ],
            }

            with TestClient(app) as client:
                create_response = client.post("/api/packs", json=payload)
                self.assertEqual(create_response.status_code, 201)
                self.assertFalse(create_response.json()["has_snapshot"])

                pack_list = client.get("/api/packs")
                self.assertEqual(pack_list.status_code, 200)
                slugs = [item["slug"] for item in pack_list.json()]
                self.assertIn("lyra-ui-focus", slugs)

                empty_payload = client.get("/api/packs/lyra-ui-focus/videos")
                self.assertEqual(empty_payload.status_code, 200)
                self.assertEqual(empty_payload.json()["mode"], "empty")
                self.assertEqual(empty_payload.json()["summary"]["total_videos"], 0)
                self.assertEqual(empty_payload.json()["pack"]["domain_key"], "game-dev-unreal")

    def test_create_pack_endpoint_rejects_duplicate_slug(self) -> None:
        with TemporaryDirectory() as temp_dir, temporary_pack_dir():
            service = self.build_service(temp_dir)
            app = create_app(service)

            with TestClient(app) as client:
                response = client.post(
                    "/api/packs",
                    json={
                        "slug": "lyra",
                        "display_name": "Lyra Copy",
                        "description": "",
                        "base_template_slug": "lyra",
                        "search": {"core_terms": ["Lyra"]},
                        "gates": {},
                        "categories": [{"id": "gas-copy", "name": "GAS", "keywords": ["gas"], "priority": 10}],
                    },
                )
                self.assertEqual(response.status_code, 409)

    def test_create_pack_endpoint_rejects_invalid_payload(self) -> None:
        with TemporaryDirectory() as temp_dir, temporary_pack_dir():
            service = self.build_service(temp_dir)
            app = create_app(service)

            with TestClient(app) as client:
                response = client.post(
                    "/api/packs",
                    json={
                        "slug": "bad slug",
                        "display_name": "Bad Slug",
                        "description": "",
                        "base_template_slug": "lyra",
                        "search": {"core_terms": []},
                        "gates": {},
                        "categories": [],
                    },
                )
                self.assertEqual(response.status_code, 422)

    def test_refresh_creates_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir, temporary_pack_dir():
            service = self.build_service(temp_dir)
            app = create_app(service)
            result = TopicPipelineResult(
                run_id="run_test",
                summary={
                    "run_id": "run_test",
                    "pack_slug": "unreal-core",
                    "finished_at": "2026-04-09T00:00:00+00:00",
                    "catalog_size": 1,
                    "counters": {
                        "searched_tasks": 1,
                        "completed_tasks": 1,
                        "failed_tasks": 0,
                        "new_records": 1,
                        "updated_records": 0,
                        "filtered_records": 0,
                        "skipped_existing": 0,
                    },
                },
                records=[make_record()],
            )

            with patch("bilibili_unreal_kb.service.run_topic_pipeline", return_value=result), patch(
                "bilibili_unreal_kb.service.export_catalog",
                return_value={
                    "jsonl": "videos.jsonl",
                    "csv": "videos.csv",
                    "xlsx": "videos.xlsx",
                    "index": "index.md",
                    "web_index": "web/index.html",
                },
            ):
                with TestClient(app) as client:
                    refresh = client.post("/api/packs/unreal-core/refresh")
                    self.assertEqual(refresh.status_code, 200)
                    job_id = refresh.json()["id"]

                    for _ in range(20):
                        job = client.get(f"/api/jobs/{job_id}").json()
                        if job["status"] == "succeeded":
                            break
                        time.sleep(0.05)

                    snapshot = client.get("/api/packs/unreal-core/snapshot")
                    self.assertEqual(snapshot.status_code, 200)
                    self.assertEqual(snapshot.json()["summary"]["total_videos"], 1)

                    exports = client.get("/api/packs/unreal-core/exports")
                    self.assertEqual(exports.status_code, 200)
                    self.assertEqual(exports.json()["exports"]["jsonl"], "videos.jsonl")

    def test_refresh_reuses_active_job(self) -> None:
        with TemporaryDirectory() as temp_dir, temporary_pack_dir():
            service = self.build_service(temp_dir)
            app = create_app(service)

            def fake_pipeline(**kwargs):
                time.sleep(0.2)
                return TopicPipelineResult(
                    run_id="run_test",
                    summary={
                        "run_id": "run_test",
                        "pack_slug": "unreal-core",
                        "finished_at": "2026-04-09T00:00:00+00:00",
                        "catalog_size": 1,
                        "counters": {
                            "searched_tasks": 1,
                            "completed_tasks": 1,
                            "failed_tasks": 0,
                            "new_records": 1,
                            "updated_records": 0,
                            "filtered_records": 0,
                            "skipped_existing": 0,
                        },
                    },
                    records=[make_record()],
                )

            with patch("bilibili_unreal_kb.service.run_topic_pipeline", side_effect=fake_pipeline), patch(
                "bilibili_unreal_kb.service.export_catalog",
                return_value={"jsonl": "videos.jsonl"},
            ):
                with TestClient(app) as client:
                    first = client.post("/api/packs/unreal-core/refresh")
                    second = client.post("/api/packs/unreal-core/refresh")
                    self.assertEqual(first.status_code, 200)
                    self.assertEqual(second.status_code, 200)
                    self.assertEqual(first.json()["id"], second.json()["id"])
                    job_id = first.json()["id"]
                    for _ in range(20):
                        job = client.get(f"/api/jobs/{job_id}").json()
                        if job["status"] in {"succeeded", "failed", "cancelled"}:
                            break
                        time.sleep(0.05)
                    for _ in range(20):
                        if not service._threads:
                            break
                        time.sleep(0.05)

    def test_cancel_keeps_preview_payload(self) -> None:
        with TemporaryDirectory() as temp_dir, temporary_pack_dir():
            service = self.build_service(temp_dir)
            app = create_app(service)

            def fake_pipeline(**kwargs):
                time.sleep(0.2)
                return TopicPipelineResult(
                    run_id="run_cancelled",
                    summary={
                        "run_id": "run_cancelled",
                        "pack_slug": "unreal-core",
                        "finished_at": "2026-04-09T00:00:00+00:00",
                        "catalog_size": 1,
                        "counters": {
                            "searched_tasks": 1,
                            "completed_tasks": 0,
                            "failed_tasks": 0,
                            "new_records": 1,
                            "updated_records": 0,
                            "filtered_records": 0,
                            "skipped_existing": 0,
                        },
                    },
                    records=[make_record()],
                )

            with patch("bilibili_unreal_kb.service.run_topic_pipeline", side_effect=fake_pipeline):
                with TestClient(app) as client:
                    refresh = client.post("/api/packs/unreal-core/refresh")
                    job_id = refresh.json()["id"]
                    cancel = client.post(f"/api/jobs/{job_id}/cancel")
                    self.assertEqual(cancel.status_code, 200)

                    for _ in range(20):
                        job = client.get(f"/api/jobs/{job_id}").json()
                        if job["status"] == "cancelled":
                            break
                        time.sleep(0.05)

                    for _ in range(20):
                        if not service._threads:
                            break
                        time.sleep(0.05)

                    payload = client.get("/api/packs/unreal-core/videos").json()
                    self.assertEqual(payload["mode"], "preview")
                    self.assertEqual(payload["snapshot"]["status"], "cancelled")
                    self.assertEqual(payload["summary"]["total_videos"], 1)

    def test_process_restart_preview_is_hidden_from_payload(self) -> None:
        with TemporaryDirectory() as temp_dir, temporary_pack_dir():
            service = self.build_service(temp_dir)
            app = create_app(service)

            with TestClient(app) as client:
                job = service.runtime_db.create_job("lyra", {"requested_via": "test"})
                job_id = job["id"]
                service.runtime_db.update_job(
                    job_id,
                    status="failed",
                    finished_at="2026-04-09T00:00:00+00:00",
                    error_code="process_restart",
                    error_message="Job interrupted by process restart",
                )
                service.runtime_db.replace_job_preview(
                    job_id,
                    {
                        "pack": {"slug": "lyra", "display_name": "Lyra", "description": "Lyra learning videos."},
                        "generated_at": "2026-04-09T00:00:00+00:00",
                        "summary": {"total_videos": 99, "total_categories": 1, "total_uploaders": 1, "total_duration_seconds": 1, "total_duration_text": "1秒"},
                        "categories": [],
                        "videos": [{"title": "stale preview"}],
                        "snapshot": {"mode": "preview", "status": "running", "job_id": job_id},
                    },
                )

                payload = client.get("/api/packs/lyra/videos").json()
                self.assertEqual(payload["mode"], "empty")
                self.assertEqual(payload["summary"]["total_videos"], 0)

    def test_snapshot_endpoint_returns_committed_snapshot_not_preview(self) -> None:
        with TemporaryDirectory() as temp_dir, temporary_pack_dir():
            service = self.build_service(temp_dir)
            service.runtime_db.init_schema()
            app = create_app(service)

            committed_payload = {
                "pack": {"slug": "unreal-core", "display_name": "Unreal Core", "description": "Unreal learning videos."},
                "generated_at": "2026-04-09T00:00:00+00:00",
                "summary": {
                    "total_videos": 1,
                    "total_categories": 1,
                    "total_uploaders": 1,
                    "total_duration_seconds": 600,
                    "total_duration_text": "10分钟",
                },
                "categories": [{"name": "Blueprint", "count": 1, "total_duration_seconds": 600, "total_duration_text": "10分钟"}],
                "videos": [{"title": "committed"}],
                "snapshot": {"mode": "snapshot", "status": "succeeded"},
            }
            snapshot = service.runtime_db.create_snapshot(
                pack_slug="unreal-core",
                job_id="job_snapshot",
                payload=committed_payload,
                output_dir=temp_dir,
                exports={"jsonl": "videos.jsonl"},
                summary={"run_id": "run_snapshot", "catalog_size": 1},
            )
            self.assertGreater(snapshot.id, 0)
            preview_job = service.runtime_db.create_job("unreal-core", {"requested_via": "test"})
            service.runtime_db.update_job(
                preview_job["id"],
                status="cancelled",
                finished_at="2026-04-09T00:10:00+00:00",
                error_code="cancelled",
                error_message="Refresh cancelled by user.",
            )
            service.runtime_db.replace_job_preview(
                preview_job["id"],
                {
                    "pack": committed_payload["pack"],
                    "generated_at": "2026-04-09T00:10:00+00:00",
                    "summary": {
                        "total_videos": 99,
                        "total_categories": 1,
                        "total_uploaders": 1,
                        "total_duration_seconds": 999,
                        "total_duration_text": "99分钟",
                    },
                    "categories": [],
                    "videos": [{"title": "preview"}],
                    "snapshot": {"mode": "preview", "status": "cancelled", "job_id": preview_job["id"]},
                },
            )

            with TestClient(app) as client:
                payload = client.get("/api/packs/unreal-core/snapshot").json()
                self.assertEqual(payload["mode"], "snapshot")
                self.assertEqual(payload["summary"]["total_videos"], 1)
                self.assertEqual(payload["snapshot"]["status"], "succeeded")
                self.assertNotIn("videos", payload)

    def test_favicon_endpoint_returns_no_content(self) -> None:
        with TemporaryDirectory() as temp_dir, temporary_pack_dir():
            service = self.build_service(temp_dir)
            app = create_app(service)

            with TestClient(app) as client:
                response = client.get("/favicon.ico")
                self.assertEqual(response.status_code, 204)


if __name__ == "__main__":
    unittest.main()
