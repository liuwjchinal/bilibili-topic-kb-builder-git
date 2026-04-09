import unittest

from bilibili_unreal_kb.planner import build_keyword_queries, build_search_tasks


class PlannerTests(unittest.TestCase):
    def test_build_keyword_queries_contains_core_matrix(self) -> None:
        queries = build_keyword_queries()
        self.assertIn("UE5 教程", queries)
        self.assertIn("虚幻引擎 蓝图", queries)
        self.assertEqual(len(queries), len(set(queries)))

    def test_build_search_tasks_expands_pages_and_orders(self) -> None:
        tasks = build_search_tasks(pages=2, custom_keywords=["UE5 Niagara"], orders=["", "pubdate"])
        self.assertEqual(tasks[0].page, 1)
        self.assertIn("UE5 Niagara", [task.keyword for task in tasks])
        self.assertTrue(any(task.order == "pubdate" for task in tasks))

    def test_lyra_pack_uses_focused_queries(self) -> None:
        queries = build_keyword_queries(pack_slug="lyra")
        self.assertNotIn("Lyra", queries)
        self.assertIn("Lyra Starter Game 教程", queries)
        self.assertIn("Lyra CommonUI", queries)


if __name__ == "__main__":
    unittest.main()
