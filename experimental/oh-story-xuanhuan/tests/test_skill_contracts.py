#!/usr/bin/env python3
"""Static safety checks for isolated Xuanhuan skills (no external dependencies)."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class SkillContracts(unittest.TestCase):
    def test_independent_entrypoints(self):
        for skill in ("xuanhuan-outline", "xuanhuan-write"):
            text = (ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"))
            self.assertIn(f"name: {skill}", text)
            self.assertIn("references/", text)

    def test_outline_preserves_upstream_required_fields(self):
        text = (ROOT / "skills/xuanhuan-outline/references/outline-contract.md").read_text(encoding="utf-8")
        fields = ["核心事件", "字数目标", "字数口径", "单元ID/位置",
                  "目标情绪", "主角目标/关键选择", "章首钩子", "爽点", "本章禁止提前释放"]
        for field in fields:
            with self.subTest(field=field):
                self.assertIn("- " + field + "：", text)
        for heading in ("#### 内容概括（五段式）", "#### 情节安排（多线）",
                        "#### 人物关系和出场顺序", "#### 情节细化"):
            self.assertIn(heading, text)

    def test_no_direct_tracking_mutation(self):
        text = (ROOT / "skills/xuanhuan-write/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("不得直接改", text)
        self.assertIn("chapter commit", text)
        self.assertIn("Alpha", text)

if __name__ == "__main__":
    unittest.main()
