import unittest

from bilibili_unreal_kb.classifier import classify_video, should_filter_irrelevant


class ClassifierTests(unittest.TestCase):
    def test_classify_blueprint_video(self) -> None:
        result = classify_video(
            title="UE5 蓝图系统入门教程",
            description="从蓝图节点开始讲解角色交互",
            tags=["UE5", "蓝图"],
            query_keyword="UE5 蓝图",
        )
        self.assertEqual(result.primary_category, "蓝图系统")
        self.assertGreater(result.confidence, 0.5)

    def test_classify_material_video(self) -> None:
        result = classify_video(
            title="Unreal Engine 材质与渲染进阶",
            description="包含 Lumen 和材质球案例",
            tags=["材质", "渲染"],
            query_keyword="Unreal Engine 材质",
        )
        self.assertEqual(result.primary_category, "材质与渲染")

    def test_irrelevant_filter_needs_both_signals(self) -> None:
        self.assertFalse(should_filter_irrelevant("UE5 搞笑蓝图整活", "", ["UE5"]))
        self.assertTrue(should_filter_irrelevant("动漫整活合集", "reaction", []))


if __name__ == "__main__":
    unittest.main()
