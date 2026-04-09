import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from bilibili_unreal_kb.runtime_db import RuntimeDatabase


class RuntimeDatabaseTests(unittest.TestCase):
    def test_create_job_append_events_and_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db = RuntimeDatabase(Path(temp_dir) / "app.db")
            db.init_schema()

            job = db.create_job("unreal-core", {"requested_via": "test"})
            self.assertEqual(job["status"], "queued")

            event_id = db.append_job_event(job["id"], "job_started", {"job_id": job["id"]})
            self.assertGreater(event_id, 0)
            self.assertEqual(len(db.get_job_events(job["id"])), 1)

            snapshot = db.create_snapshot(
                pack_slug="unreal-core",
                job_id=job["id"],
                payload={"summary": {"total_videos": 1}, "videos": [], "categories": [], "snapshot": {}},
                output_dir=temp_dir,
                exports={"jsonl": "videos.jsonl"},
                summary={"run_id": "run_test", "catalog_size": 1},
            )
            self.assertGreater(snapshot.id, 0)
            current = db.get_current_snapshot("unreal-core")
            self.assertIsNotNone(current)
            self.assertEqual(current.exports["jsonl"], "videos.jsonl")

    def test_recover_incomplete_jobs_clears_process_restart_previews(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db = RuntimeDatabase(Path(temp_dir) / "app.db")
            db.init_schema()

            job = db.create_job("lyra", {"requested_via": "test"})
            db.update_job(job["id"], status="running", started_at="2026-04-09T00:00:00+00:00")
            db.replace_job_preview(
                job["id"],
                {
                    "summary": {"total_videos": 2},
                    "videos": [{"title": "stale"}],
                    "categories": [],
                    "snapshot": {"status": "running", "job_id": job["id"]},
                },
            )

            recovered = db.recover_incomplete_jobs()
            self.assertEqual(recovered, 1)

            refreshed_job = db.get_job(job["id"])
            self.assertIsNotNone(refreshed_job)
            self.assertEqual(refreshed_job["status"], "failed")
            self.assertEqual(refreshed_job["error_code"], "process_restart")
            self.assertIsNone(db.get_job_preview(job["id"]))

            pack_state = db.get_pack_state("lyra")
            self.assertIsNotNone(pack_state)
            self.assertEqual(pack_state["last_job_status"], "failed")
            self.assertEqual(pack_state["last_error_code"], "process_restart")

    def test_recover_incomplete_jobs_does_not_clobber_newer_successful_pack_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db = RuntimeDatabase(Path(temp_dir) / "app.db")
            db.init_schema()

            interrupted_job = db.create_job("unreal-core", {"requested_via": "test"})
            db.update_job(interrupted_job["id"], status="running", started_at="2026-04-09T00:00:00+00:00")
            db.replace_job_preview(
                interrupted_job["id"],
                {
                    "summary": {"total_videos": 1},
                    "videos": [{"title": "stale"}],
                    "categories": [],
                    "snapshot": {"status": "running", "job_id": interrupted_job["id"]},
                },
            )

            recovered = db.recover_incomplete_jobs()
            self.assertEqual(recovered, 1)

            succeeded_job = db.create_job("unreal-core", {"requested_via": "test"})
            snapshot = db.create_snapshot(
                pack_slug="unreal-core",
                job_id=succeeded_job["id"],
                payload={"summary": {"total_videos": 2}, "videos": [], "categories": [], "snapshot": {}},
                output_dir=temp_dir,
                exports={"jsonl": "videos.jsonl"},
                summary={"run_id": "run_ok", "catalog_size": 2},
            )
            self.assertGreater(snapshot.id, 0)
            db.update_job(
                succeeded_job["id"],
                status="succeeded",
                finished_at="2026-04-09T00:01:00+00:00",
                snapshot_id=snapshot.id,
            )

            recovered_again = db.recover_incomplete_jobs()
            self.assertEqual(recovered_again, 0)

            pack_state = db.get_pack_state("unreal-core")
            self.assertIsNotNone(pack_state)
            self.assertEqual(pack_state["last_snapshot_id"], snapshot.id)
            self.assertEqual(pack_state["last_job_id"], succeeded_job["id"])
            self.assertEqual(pack_state["last_job_status"], "succeeded")
            self.assertIsNone(pack_state["last_error_code"])


if __name__ == "__main__":
    unittest.main()
