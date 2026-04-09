from __future__ import annotations

import textwrap
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from bilibili_unreal_kb.packs import (
    clear_pack_cache,
    create_pack_from_payload,
    get_pack,
    list_pack_templates,
    list_packs,
    validate_pack_payload,
)
from bilibili_unreal_kb.planner import build_search_tasks


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
      pages: 3
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


class PackTests(unittest.TestCase):
    def test_load_builtin_packs(self) -> None:
        slugs = [pack.slug for pack in list_packs()]
        self.assertIn("unreal-core", slugs)
        self.assertIn("lyra", slugs)

    def test_lyra_pack_contains_expected_categories(self) -> None:
        pack = get_pack("lyra")
        category_names = [category.name for category in pack.categories]
        self.assertIn("GAS/Ability System", category_names)
        self.assertIn("Experience/GameFeature", category_names)

    def test_lyra_family_packs_ship_with_context_filters(self) -> None:
        for slug in ("lyra", "lyra-ai-behaviour"):
            pack = get_pack(slug)
            self.assertTrue(pack.gates.context_any, slug)
            self.assertNotIn("Lyra", pack.search.core_terms, slug)
            self.assertEqual(pack.domain.key, "game-dev-unreal", slug)
            self.assertTrue(pack.domain.block_partition_keywords, slug)
            self.assertIn("演奏", pack.domain.block_partition_keywords, slug)

    def test_build_search_tasks_for_lyra_uses_default_pages(self) -> None:
        tasks = build_search_tasks(pages=None, pack_slug="lyra")
        self.assertFalse(any(task.keyword == "Lyra" for task in tasks))
        self.assertTrue(any(task.keyword == "Lyra CommonUI" for task in tasks))
        self.assertTrue(all(task.page in {1, 2} for task in tasks[:8]))

    def test_create_pack_from_payload_writes_yaml_and_reloads(self) -> None:
        payload = {
            "slug": "lyra-ui-focus",
            "display_name": "Lyra UI Focus",
            "description": "Lyra UI learning videos.",
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
                {"id": "ui-commonui", "name": "UI/CommonUI", "keywords": ["commonui", "hud"], "priority": 10},
                {"id": "menu-flow", "name": "Menu Flow", "keywords": ["menu", "frontend"], "priority": 20},
            ],
        }

        with temporary_pack_dir() as pack_dir:
            pack = create_pack_from_payload(payload)
            self.assertEqual(pack.slug, "lyra-ui-focus")
            self.assertEqual(pack.search.orders, ["", "pubdate"])
            self.assertEqual(pack.search.pages, 2)
            self.assertIn("commonui", pack.gates.context_any)
            self.assertEqual(pack.domain.key, "game-dev-unreal")
            self.assertIn("音乐", pack.domain.block_partition_keywords)
            self.assertTrue((pack_dir / "lyra-ui-focus.yaml").exists())

            clear_pack_cache()
            reloaded = get_pack("lyra-ui-focus")
            self.assertEqual(reloaded.display_name, "Lyra UI Focus")
            self.assertEqual(reloaded.categories[0].id, "ui-commonui")

    def test_list_pack_templates_returns_full_payloads(self) -> None:
        with temporary_pack_dir():
            templates = list_pack_templates()
            template = next(item for item in templates if item["slug"] == "lyra")
            self.assertEqual(template["search"]["orders"], ["default", "pubdate"])
            self.assertEqual(template["search"]["pages"], 2)
            self.assertEqual(template["domain"]["key"], "game-dev-unreal")
            self.assertEqual(template["categories"][0]["id"], "gas")

    def test_validate_pack_payload_rejects_invalid_slug(self) -> None:
        with temporary_pack_dir():
            with self.assertRaisesRegex(ValueError, "slug must match"):
                validate_pack_payload(
                    {
                        "slug": "Lyra UI",
                        "display_name": "Bad Slug",
                        "base_template_slug": "lyra",
                        "search": {"core_terms": ["Lyra"]},
                        "gates": {},
                        "categories": [{"id": "gas", "name": "GAS", "keywords": ["gas"], "priority": 10}],
                    }
                )

    def test_validate_pack_payload_rejects_duplicate_slug(self) -> None:
        with temporary_pack_dir():
            with self.assertRaisesRegex(FileExistsError, "pack already exists"):
                validate_pack_payload(
                    {
                        "slug": "lyra",
                        "display_name": "Lyra Copy",
                        "base_template_slug": "lyra",
                        "search": {"core_terms": ["Lyra"]},
                        "gates": {},
                        "categories": [{"id": "gas-copy", "name": "GAS", "keywords": ["gas"], "priority": 10}],
                    }
                )

    def test_validate_pack_payload_rejects_empty_core_terms(self) -> None:
        with temporary_pack_dir():
            with self.assertRaisesRegex(ValueError, "search.core_terms"):
                validate_pack_payload(
                    {
                        "slug": "lyra-empty",
                        "display_name": "Lyra Empty",
                        "base_template_slug": "lyra",
                        "search": {"core_terms": []},
                        "gates": {},
                        "categories": [{"id": "gas-copy", "name": "GAS", "keywords": ["gas"], "priority": 10}],
                    }
                )

    def test_validate_pack_payload_rejects_duplicate_category_ids(self) -> None:
        with temporary_pack_dir():
            with self.assertRaisesRegex(ValueError, "duplicate category id"):
                validate_pack_payload(
                    {
                        "slug": "lyra-dup-category",
                        "display_name": "Lyra Dup Category",
                        "base_template_slug": "lyra",
                        "search": {"core_terms": ["Lyra"]},
                        "gates": {},
                        "categories": [
                            {"id": "gas", "name": "GAS", "keywords": ["gas"], "priority": 10},
                            {"id": "gas", "name": "GAS 2", "keywords": ["ability"], "priority": 20},
                        ],
                    }
                )


if __name__ == "__main__":
    unittest.main()
