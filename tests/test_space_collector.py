import unittest

from bilibili_unreal_kb.space_collector import extract_bvids_from_hrefs, is_tutorial_video


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


if __name__ == "__main__":
    unittest.main()
