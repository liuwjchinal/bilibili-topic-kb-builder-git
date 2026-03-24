import unittest

from bilibili_unreal_kb.exporter import build_frontend_payload
from bilibili_unreal_kb.models import VideoRecord


class ExporterTests(unittest.TestCase):
    def test_build_frontend_payload_groups_categories(self) -> None:
        record = VideoRecord(
            video_id="1",
            bvid="BV1",
            title="UE5 蓝图入门",
            link="https://www.bilibili.com/video/BV1",
            duration_seconds=600,
            duration_text="10:00",
            uploader="测试UP",
            play_count=1200,
            publish_time="2024-01-01T00:00:00+00:00",
            query_keywords=["UE5 蓝图"],
            source_pages=["default:1"],
            primary_category="蓝图系统",
            secondary_categories=[],
            category_confidence=0.9,
            match_keywords=["蓝图"],
            tags=["UE5", "蓝图"],
            desc_excerpt="desc",
            crawl_time="2026-03-23T00:00:00+00:00",
            run_id="run_a",
            status="ok",
        )
        payload = build_frontend_payload([record])
        self.assertEqual(payload["summary"]["total_videos"], 1)
        self.assertEqual(payload["summary"]["total_categories"], 1)
        self.assertEqual(payload["categories"][0]["name"], "蓝图系统")
        self.assertEqual(payload["videos"][0]["title"], "UE5 蓝图入门")


if __name__ == "__main__":
    unittest.main()
