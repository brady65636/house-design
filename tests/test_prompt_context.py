import json
import unittest
from pathlib import Path

from prompt_context import build_skill_context, build_system_prompt


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PromptContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scene_manifest = json.loads(
            (PROJECT_ROOT / "scene_manifest.json").read_text(encoding="utf-8")
        )
        cls.asset_manifest = json.loads(
            (PROJECT_ROOT / "asset_manifest.json").read_text(encoding="utf-8")
        )
        cls.skill_context = build_skill_context(
            PROJECT_ROOT
            / "skills"
            / "residential-aesthetic-design"
            / "SKILL.md"
        )
        cls.prompt = build_system_prompt(cls.scene_manifest, cls.asset_manifest)

    def test_uses_active_v4_house_summary(self) -> None:
        self.assertIn("house_spacious_yunkuo_135_v4", self.prompt)
        self.assertIn("11 个可设计空间", self.prompt)
        self.assertIn("55 个唯一设计目标", self.prompt)
        self.assertIn("完整横厅客厅：room_id=open_public", self.prompt)
        self.assertIn("7.6米南向开放阳台：room_id=south_panorama_balcony", self.prompt)

    def test_does_not_embed_legacy_house_or_target_ids(self) -> None:
        self.assertNotIn("house_2b2l_90_v1", self.prompt)
        self.assertNotIn("wall_face_001", self.prompt)
        self.assertNotIn("surface_floor_living_room", self.prompt)
        self.assertIn("精确 target_id 一律以工具返回为准", self.prompt)

    def test_asset_counts_come_from_manifest(self) -> None:
        self.assertIn("项目当前共有 87 个真实资产或预设", self.prompt)
        self.assertIn("wall_paint：60 个", self.prompt)
        self.assertIn("wallpaper：8 个", self.prompt)
        self.assertIn("wood_floor：6 个", self.prompt)
        self.assertIn("tile：8 个", self.prompt)
        self.assertIn("ceiling：5 个", self.prompt)
        self.assertIn("asset_manifest 只保存资产 id、category 和 brief 索引", self.prompt)
        self.assertIn("get_asset_by_category(category)", self.prompt)
        self.assertIn("get_asset_card_by_id(asset_id)", self.prompt)
        self.assertNotIn("get_asset_by_category(category, limit)", self.prompt)

    def test_manifest_contract_failures_are_explicit(self) -> None:
        with self.assertRaisesRegex(ValueError, "house_id"):
            build_system_prompt({}, self.asset_manifest)

    def test_skill_can_be_fixed_injected_into_system_prompt(self) -> None:
        prompt = build_system_prompt(
            self.scene_manifest,
            self.asset_manifest,
            skill_context=self.skill_context,
        )
        self.assertIn("固定注入的住宅审美设计 Skill", prompt)
        self.assertIn("人类批准闸门", prompt)
        self.assertIn("未获得明确批准前，不调用任何会修改 Scheme", prompt)


if __name__ == "__main__":
    unittest.main()
