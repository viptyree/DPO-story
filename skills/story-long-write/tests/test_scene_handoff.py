import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scene_handoff as handoff


class HandoffTest(unittest.TestCase):
    def fixture(self, work):
        prompt = {"system": "正文", "user": "〖人物状态〗\n甲\n〖前情〗\n旧案\n〖事件骨架〗\n1. 认尸\n2. 留尸\n〖写作要求〗\n全章目标：1000字\n篇幅安排：完整章节\n结束动作：空白\n- 保持关系"}
        (work / "dpo_prompt.json").write_text(json.dumps(prompt), encoding="utf-8")
        sha = handoff.digest((work / "dpo_prompt.json").read_bytes())
        plan = {"schema_version": 1, "prompt_sha256": sha, "scenes": [
            {"start_state": "尚未认尸", "end_state": "已经认出", "target_chars": 500, "beats": [{"id": 1, "action": "妻子认出丈夫"}]},
            {"start_state": "已经认出", "end_state": "暂留复验", "target_chars": 500, "beats": [{"id": 2, "action": "提出复验"}]},
        ]}
        (work / "dpo_scene_plan.json").write_text(json.dumps(plan), encoding="utf-8")
        return prompt, sha, plan

    def test_prompt_has_only_local_target_and_verified_context(self):
        with tempfile.TemporaryDirectory() as directory:
            prompt, _, plan = self.fixture(Path(directory))
            user = handoff.make_prompt(prompt, plan["scenes"][1], ["妻子已经认出丈夫"], "她点头。")
            self.assertNotIn("全章目标", user)
            self.assertNotIn("完整章节", user)
            self.assertNotIn("均已完成", user)
            self.assertIn("约500字", user)
            self.assertIn("她点头。", user)

    def test_plan_cannot_omit_or_repeat_beats(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            prompt, sha, plan = self.fixture(work)
            plan["scenes"][1]["beats"][0]["id"] = 1
            path = work / "dpo_scene_plan.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "覆盖"):
                handoff.load_plan(path, prompt, sha)

    def test_scene_requirements_cannot_drop_canon_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            prompt, _, plan = self.fixture(Path(directory))
            prompt["user"] += "\n- 禁止提前释放：死者真名\n- 必须沿用的事实：失名仅抹姓名"
            scene = dict(plan["scenes"][0], requirements=["动作短促"])
            user = handoff.make_prompt(prompt, scene, [], "")
            self.assertIn("禁止提前释放：死者真名", user)
            self.assertIn("必须沿用的事实：失名仅抹姓名", user)
            self.assertNotIn("结束动作：空白", user)

    def test_generation_pauses_and_only_reviewed_facts_reach_next_scene(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            prompt, sha, plan = self.fixture(work)
            calls = []
            def request(*args, **kwargs):
                calls.append(args[3])
                return "妻子认出了丈夫。" + "动作细节。" * 90, "stop", "model"
            def write(path, text):
                path.write_text(text, encoding="utf-8", newline="\n")
            def run():
                return handoff.advance(work, prompt, sha, "model", [], request, write, lambda _: False, len, "http://local", 1000)
            accepted, report, _ = run()
            self.assertEqual(accepted, [])
            self.assertEqual(report["status"], "awaiting_scene_review")
            self.assertEqual(report["scenes"], 2)
            run()
            self.assertEqual(len(calls), 1)  # no silent retry and no second scene
            draft = Path(report["output"]).read_text(encoding="utf-8")
            quote = "妻子认出了丈夫。"
            review = {"schema_version": 1, "status": "pass", "request_sha256": report["request_sha256"],
                      "draft_sha256": report["scene_draft_sha256"], "issues": [],
                      "completed_beats": [{"id": 1, "evidence": quote}],
                      "checks": {key: {"pass": True, "evidence": quote} for key in handoff.CHECKS},
                      "established_facts": [{"fact": "妻子已认出丈夫", "evidence": quote}]}
            self.assertIn(quote, draft)
            Path(report["review"]).write_text(json.dumps(review), encoding="utf-8")
            accepted, second, _ = run()
            self.assertEqual(len(accepted), 1)
            self.assertEqual(second["scene"], 2)
            self.assertGreater(second["characters"], second["scene_characters"])
            self.assertIn("妻子已认出丈夫", calls[-1])
            self.assertIn(f"约{1000 - len(accepted[0])}字", calls[-1])
            self.assertEqual(len(calls), 2)
            Path(report["output"]).write_text("被改写的正文", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "更改"):
                run()

    def test_review_cannot_invent_evidence_or_accept_issues(self):
        scene = {"beats": [{"id": 1}]}
        review = {"schema_version": 1, "status": "pass", "request_sha256": "r", "draft_sha256": "d", "issues": [],
                  "completed_beats": [{"id": 1, "evidence": "不存在的原句"}]}
        with self.assertRaisesRegex(ValueError, "原句"):
            handoff.validate_review(review, scene, "正文", "r", "d")
        review["issues"] = ["姓名错乱"]
        with self.assertRaisesRegex(ValueError, "未解决"):
            handoff.validate_review(review, scene, "正文", "r", "d")

    def test_rejected_review_reports_blocked_without_another_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            prompt, sha, _ = self.fixture(work)
            calls = []
            def request(*args, **kwargs):
                calls.append(1)
                return "认尸动作。" * 90, "stop", "model"
            def write(path, text):
                path.write_text(text, encoding="utf-8", newline="\n")
            def run():
                return handoff.advance(work, prompt, sha, "model", [], request, write, lambda _: False, len, "http://local", 1000)
            _, report, _ = run()
            Path(report["review"]).write_text(json.dumps({"status": "fail", "issues": ["人物失语对象错误"]}), encoding="utf-8")
            accepted, rejected, _ = run()
            self.assertEqual(accepted, [])
            self.assertEqual(len(calls), 1)
            self.assertEqual(rejected["status"], "blocked")
            self.assertIn("人物失语对象错误", rejected["errors"])
            self.assertEqual(rejected["output"], report["output"])

    def test_explanations_are_separate_from_verbatim_evidence(self):
        text = "妻子站在遗体旁。"
        review = {"schema_version": 1, "status": "pass", "request_sha256": "r", "draft_sha256": "d", "issues": [],
                  "completed_beats": [{"id": 1, "evidence": text}],
                  "checks": {key: {"pass": True, "evidence": text, "reason": "说明写在这里"} for key in handoff.CHECKS},
                  "established_facts": [{"fact": "妻子仍在场", "evidence": text}]}
        self.assertEqual(handoff.validate_review(review, {"beats": [{"id": 1}]}, text, "r", "d"), ["妻子仍在场"])
        review["checks"]["canon"]["evidence"] += "（主控的解释）"
        with self.assertRaisesRegex(ValueError, "原句"):
            handoff.validate_review(review, {"beats": [{"id": 1}]}, text, "r", "d")

    def test_plan_template_requires_review_and_cannot_disable_dpo(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            prompt, sha, plan = self.fixture(work)
            path = work / "dpo_scene_plan.json"
            path.write_text(json.dumps(handoff.plan_template(prompt, sha)), encoding="utf-8")
            with self.assertRaises(ValueError):
                handoff.load_plan(path, prompt, sha)
            plan["lora_scale"] = 0
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "适配器强度"):
                handoff.load_plan(path, prompt, sha)
            plan.pop("lora_scale")
            plan["sampling"] = {"speculative_n_max": 0}
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "不支持单请求"):
                handoff.load_plan(path, prompt, sha)


if __name__ == "__main__":
    unittest.main()
