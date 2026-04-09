import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bilibili_unreal_kb.space_collector import (
    extract_bvids_from_hrefs,
    fetch_space_playlist_with_ytdlp,
    is_tutorial_video,
)


class SpaceCollectorTests(unittest.TestCase):
    def test_is_tutorial_video(self) -> None:
        self.assertTrue(is_tutorial_video("虚幻引擎5 入门教程", ""))
        self.assertTrue(is_tutorial_video("UE5 Workshop 回放", ""))
        self.assertFalse(is_tutorial_video("新作预告片", "cinematic trailer"))

    def test_extract_bvids_from_hrefs(self) -> None:
        hrefs = [
            "https://www.bilibili.com/video/BV1AB411c7mD",
            "https://space.bilibili.com/138827797/video",
            "https://www.bilibili.com/video/BV1AB411c7mD?p=2",
            "https://www.bilibili.com/video/BV1xy4y1z7Q1",
        ]
        self.assertEqual(
            extract_bvids_from_hrefs(hrefs),
            ["BV1AB411c7mD", "BV1xy4y1z7Q1"],
        )

    def test_fetch_space_playlist_with_ytdlp_uses_python_api(self) -> None:
        class FakeYDL:
            def __init__(self, options) -> None:
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def extract_info(self, space_url: str, download: bool = False):
                self.space_url = space_url
                self.download = download
                return {
                    "id": "138827797",
                    "entries": [
                        {"id": "BV1AB411c7mD"},
                        None,
                        {"id": "BV1xy4y1z7Q1"},
                    ],
                }

        with TemporaryDirectory() as temp_dir:
            output_json_path = Path(temp_dir) / "space_playlist.json"
            with patch("bilibili_unreal_kb.space_collector.YoutubeDL", FakeYDL):
                result = fetch_space_playlist_with_ytdlp(
                    space_url="https://space.bilibili.com/138827797/video",
                    output_json_path=output_json_path,
                    max_attempts=1,
                )

        self.assertEqual(result.mid, "138827797")
        self.assertEqual(result.bvids, ["BV1AB411c7mD", "BV1xy4y1z7Q1"])
        self.assertEqual(result.source, "yt_dlp")


if __name__ == "__main__":
    unittest.main()
