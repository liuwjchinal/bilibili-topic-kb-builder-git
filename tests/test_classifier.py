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

    def test_classify_lyra_gas_video(self) -> None:
        result = classify_video(
            title="Lyra GAS AbilitySet 结构拆解",
            description="Gameplay Ability System 中 AbilitySet 的关系",
            tags=["Lyra", "GAS"],
            query_keyword="Lyra GAS",
            pack_slug="lyra",
        )
        self.assertEqual(result.primary_category, "GAS/Ability System")

    def test_lyra_pack_filters_unrelated_product_video(self) -> None:
        classification = classify_video(
            title="和来CX12与孔声Lyra12天琴座的音色差异你听的出来吗",
            description="欢迎自行感受并评论区留言",
            tags=["口琴", "评测"],
            query_keyword="Lyra",
            pack_slug="lyra",
        )
        self.assertTrue(
            should_filter_irrelevant(
                "和来CX12与孔声Lyra12天琴座的音色差异你听的出来吗",
                "欢迎自行感受并评论区留言",
                ["口琴", "评测"],
                classification=classification,
                pack_slug="lyra",
            )
        )

    def test_lyra_pack_keeps_unreal_tutorial_context(self) -> None:
        classification = classify_video(
            title="【UE教程】从零开始的Lyra动画蓝图制作+解析",
            description="Lyra 动画蓝图教程，讲解 UE5 角色动画和 ABP",
            tags=["UE5", "Lyra", "动画蓝图"],
            query_keyword="Lyra 动画蓝图",
            pack_slug="lyra",
        )
        self.assertFalse(
            should_filter_irrelevant(
                "【UE教程】从零开始的Lyra动画蓝图制作+解析",
                "Lyra 动画蓝图教程，讲解 UE5 角色动画和 ABP",
                ["UE5", "Lyra", "动画蓝图"],
                classification=classification,
                pack_slug="lyra",
            )
        )
        self.assertEqual(classification.primary_category, "Blueprint/Animation")

    def test_lyra_ai_behaviour_pack_filters_unrelated_product_video(self) -> None:
        classification = classify_video(
            title="微雪【百元性价比之王】幸狐 Luckfox Lyra Ultra 瑞芯微 RK3506B Linux开发板 8G",
            description="今天看看 Lyra Ultra 开发板的体验",
            tags=["开发板", "Linux"],
            query_keyword="Lyra AI",
            pack_slug="lyra-ai-behaviour",
        )
        self.assertTrue(
            should_filter_irrelevant(
                "微雪【百元性价比之王】幸狐 Luckfox Lyra Ultra 瑞芯微 RK3506B Linux开发板 8G",
                "今天看看 Lyra Ultra 开发板的体验",
                ["开发板", "Linux"],
                classification=classification,
                pack_slug="lyra-ai-behaviour",
            )
        )

    def test_unreal_pack_filters_music_partition_even_with_keyword_hits(self) -> None:
        classification = classify_video(
            title="UE5 蓝图演奏速通",
            description="蓝图只是歌曲名的一部分",
            tags=["UE5"],
            query_keyword="UE5 蓝图",
            pack_slug="unreal-core",
        )
        self.assertTrue(
            should_filter_irrelevant(
                "UE5 蓝图演奏速通",
                "蓝图只是歌曲名的一部分",
                ["UE5"],
                classification=classification,
                partition_name="音乐",
                pack_slug="unreal-core",
            )
        )

    def test_irrelevant_filter_needs_both_signals(self) -> None:
        self.assertFalse(should_filter_irrelevant("UE5 搞笑蓝图整活", "", ["UE5"]))
        self.assertTrue(should_filter_irrelevant("动漫整活合集", "reaction", []))


if __name__ == "__main__":
    unittest.main()
