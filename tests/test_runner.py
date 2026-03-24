import tempfile
import unittest
from pathlib import Path

from bilibili_unreal_kb.runner import _load_failed_bvids


class RunnerTests(unittest.TestCase):
    def test_load_failed_bvids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            failed_path = Path(tmp_dir) / "space_failed_bvids.jsonl"
            failed_path.write_text(
                '{"bvid":"BV1abc"}\n{"bvid":"BV2def","error":"timeout"}\n{"error":"missing"}\n',
                encoding="utf-8",
            )
            self.assertEqual(_load_failed_bvids(failed_path), ["BV1abc", "BV2def"])


if __name__ == "__main__":
    unittest.main()
