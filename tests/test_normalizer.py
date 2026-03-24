import unittest

from bilibili_unreal_kb.models import SearchTask, SearchVideoSummary, VideoRecord
from bilibili_unreal_kb.normalizer import (
    build_video_record,
    duration_text_to_seconds,
    merge_records,
    seconds_to_duration_text,
)


class NormalizerTests(unittest.TestCase):
    def test_duration_roundtrip(self) -> None:
        seconds = duration_text_to_seconds("1:02:03")
        self.assertEqual(seconds, 3723)
        self.assertEqual(seconds_to_duration_text(seconds), "1:02:03")

    def test_build_video_record(self) -> None:
        summary = SearchVideoSummary(
            bvid="BVTEST123456",
            title="UE5 蓝图入门",
            link="https://www.bilibili.com/video/BVTEST123456",
            duration_text="12:00",
        )
        detail = {
            "aid": 100,
            "title": "UE5 蓝图入门",
            "duration": 720,
            "pubdate": 1704067200,
            "owner": {"name": "测试UP"},
            "stat": {"view": 1024},
            "desc": "讲解蓝图基础节点",
        }
        task = SearchTask(keyword="UE5 蓝图", page=1, order="")
        record = build_video_record(summary, detail, ["UE5", "蓝图"], task, "run_x", "2026-03-23T00:00:00+00:00")
        self.assertEqual(record.primary_category, "蓝图系统")
        self.assertEqual(record.play_count, 1024)

    def test_merge_records_accumulates_queries(self) -> None:
        base = VideoRecord(
            video_id="1",
            bvid="BV1",
            title="UE5 入门",
            link="https://www.bilibili.com/video/BV1",
            duration_seconds=60,
            duration_text="1:00",
            uploader="UP",
            play_count=100,
            publish_time="2024-01-01T00:00:00+00:00",
            query_keywords=["UE5 教程"],
            source_pages=["default:1"],
            primary_category="基础入门",
            secondary_categories=[],
            category_confidence=0.5,
            match_keywords=["教程"],
            tags=["UE5"],
            desc_excerpt="a",
            crawl_time="2026-03-23T00:00:00+00:00",
            run_id="run_a",
            status="ok",
        )
        incoming = VideoRecord.from_json_dict(base.to_json_dict())
        incoming.query_keywords = ["UE5 入门"]
        incoming.source_pages = ["pubdate:1"]
        incoming.play_count = 200
        merged = merge_records(base, incoming)
        self.assertIn("UE5 教程", merged.query_keywords)
        self.assertIn("UE5 入门", merged.query_keywords)
        self.assertEqual(merged.play_count, 200)


if __name__ == "__main__":
    unittest.main()
