import importlib
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
pipeline = importlib.import_module("chapter_pipeline")
generator = importlib.import_module("generate_dpo_draft")
backend = importlib.import_module("preflight_dpo_writer")
exporter = importlib.import_module("export_claude_writer")


class Response:
    def __init__(self, value):
        self.value = json.dumps(value).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self):
        return self.value


class RuntimeTest(unittest.TestCase):
    def test_missing_required_setting_context_stops_before_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "追踪").mkdir()
            (project / "追踪" / "_tracking-state.json").write_text("{}", encoding="utf-8")
            (project / "设定").mkdir()
            (project / "设定" / "世界.md").write_text("时代：架空王朝。", encoding="utf-8")
            outline = project / "outline.md"
            context = project / "context.md"
            outline.write_text("outline", encoding="utf-8")
            context.write_text("context", encoding="utf-8")
            compiled = {"system": pipeline.build_dpo_prompt.SYS, "user": "〖人物状态〗\n甲\n〖前情〗\n旧事\n〖事件骨架〗\n1. 初验\n2. 复核\n〖写作要求〗\n全章目标：1000字", "chapter": 1,
                        "source_outline": str(outline), "source_tracking": str(context), "review_items": []}
            args = Namespace(project=project, chapter=1, mode="append", endpoint="http://localhost",
                             init_input=None, prepare_only=True, generate_prepared=False)
            ready = Namespace(stdout=json.dumps({"status": "ready"}), stderr="", returncode=0)
            with patch.object(pipeline, "check_backend", return_value=(generator.DEFAULT_MODEL, [])), \
                 patch.object(pipeline.tracking_commit, "check_project", return_value={"last_committed_chapter": 0, "state_revision": 0}), \
                 patch.object(pipeline.build_dpo_prompt, "run", return_value=compiled), \
                 patch.object(pipeline.shutil, "which", return_value="node"), \
                 patch.object(pipeline.subprocess, "run", return_value=ready) as process:
                report, code = pipeline.run(args)
                self.assertEqual(code, 2)
                self.assertEqual(report["stage"], "context_prepare")
                self.assertTrue(Path(report["context_template"]).is_file())
                self.assertEqual(process.call_count, 1)

    def test_setting_retrieval_only_injects_verified_selected_excerpt(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            settings = project / "设定"
            settings.mkdir()
            source = settings / "世界.md"
            source.write_text("时代：架空王朝。\n终局秘密：不能交给本章写手。\n", encoding="utf-8")
            work = project / ".story" / "work" / "第001章"
            work.mkdir(parents=True)
            manifest = work / "dpo_context.json"
            doc = {"schema_version": 1, "setting_excerpts": [{"source": "设定/世界.md", "text": "时代：架空王朝。"}]}
            manifest.write_text(json.dumps(doc), encoding="utf-8")
            excerpts, _ = pipeline.build_dpo_prompt.chapter_context(project, 1)
            self.assertEqual(excerpts[0]["text"], "时代：架空王朝。")
            self.assertNotIn("终局秘密", json.dumps(excerpts, ensure_ascii=False))
            doc["setting_excerpts"][0]["text"] = "时代：现代都市。"
            manifest.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "原文不一致"):
                pipeline.build_dpo_prompt.chapter_context(project, 1)
            doc["setting_excerpts"][0] = {"source": "../outside.md", "text": "outside"}
            manifest.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "本书设定目录"):
                pipeline.build_dpo_prompt.chapter_context(project, 1)

    def test_revision_keeps_controller_reviewed_prompt_and_rejects_stale_state(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "追踪").mkdir()
            (project / "追踪" / "_tracking-state.json").write_text("{}", encoding="utf-8")
            outline = project / "outline.md"
            context = project / "context.md"
            outline.write_text("approved outline", encoding="utf-8")
            context.write_text("current context", encoding="utf-8")
            compiled = {"system": pipeline.build_dpo_prompt.SYS, "user": "〖人物状态〗\n甲\n〖前情〗\n旧事\n〖事件骨架〗\n1. 初验\n2. 复核\n〖写作要求〗\n全章目标：1000字", "chapter": 1,
                        "source_outline": str(outline), "source_tracking": str(context), "review_items": []}
            args = Namespace(project=project, chapter=1, mode="revision", endpoint="http://localhost",
                             init_input=None, prepare_only=True, generate_prepared=False)
            state = {"last_committed_chapter": 1, "state_revision": 0}
            ready = Namespace(stdout=json.dumps({"status": "ready"}), stderr="", returncode=0)
            blocked = Namespace(stdout=json.dumps({"status": "blocked", "errors": ["quality failed"]}), stderr="", returncode=2)
            with patch.object(pipeline, "check_backend", return_value=(generator.DEFAULT_MODEL, [])), \
                 patch.object(pipeline.tracking_commit, "check_project", return_value=state), \
                 patch.object(pipeline.build_dpo_prompt, "run", return_value=compiled), \
                 patch.object(pipeline.shutil, "which", return_value="node"), \
                 patch.object(pipeline.subprocess, "run", return_value=ready) as process:
                report, code = pipeline.run(args)
                self.assertEqual(code, 0)
                prompt_path = Path(report["prompt"])
                reviewed = dict(compiled, user=compiled["user"] + "\n主控核验后的要求。")
                prompt_path.write_text(json.dumps(reviewed), encoding="utf-8")
                before = prompt_path.read_bytes()
                args.prepare_only, args.generate_prepared = False, True
                process.side_effect = [ready, blocked]
                _, code = pipeline.run(args)
                self.assertEqual(code, 2)
                self.assertEqual(prompt_path.read_bytes(), before)
                state["state_revision"] = 1
                process.side_effect = None
                with self.assertRaisesRegex(ValueError, "发生变化"):
                    pipeline.run(args)

    def test_init_reports_original_schema_failures_together(self):
        errors = pipeline.init_shape_errors({
            "context": {"active_character_names": ["甲", "乙"]},
            "character_snapshots": {"甲": {"身份": "收尸人", "goal": ""}},
        })
        self.assertTrue(any("乙" in error and "缺少快照" in error for error in errors))
        self.assertTrue(any("身份" in error for error in errors))
        self.assertTrue(any("goal" in error for error in errors))

    def test_book_lock_blocks_overlap_and_releases(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            with pipeline.project_lock(project):
                with self.assertRaises(ValueError):
                    with pipeline.project_lock(project):
                        self.fail("overlapping generation must be refused")
            with pipeline.project_lock(project):
                pass

    def test_default_chapter_keeps_all_beats_in_one_prompt(self):
        prompt = "〖人物状态〗\n甲\n〖前情〗\n旧事\n〖事件骨架〗\n1. 收尸\n2. 认领\n〖写作要求〗\n全章目标：2500字"
        self.assertEqual(generator.scene_prompts(prompt, 1), [prompt])
        self.assertTrue(generator.repeated_prose("甲" * 80 + "甲" * 80))
        sentence = "脖子上的伤口整齐但背部的伤口破碎，表面还沾着沟渠里的污泥"
        self.assertTrue(generator.repeated_prose(sentence + "。又核对衣物。" + sentence + "。"))
        self.assertFalse(generator.repeated_prose("他点头。她也点头。他点头。"))

    def test_alias_alone_cannot_pass_adapter_check(self):
        with patch.object(backend, "urlopen", side_effect=[
            Response({"model_alias": generator.DEFAULT_MODEL}), Response([]),
        ]):
            with self.assertRaisesRegex(ValueError, "LoRA"):
                backend.check_backend("http://localhost:8088", generator.DEFAULT_MODEL)

    def test_generation_uses_card_sampling_and_disables_thinking(self):
        response = {"model": generator.DEFAULT_MODEL, "choices": [{"message": {"content": "正文"}, "finish_reason": "stop"}]}
        with patch.object(generator, "urlopen", return_value=Response(response)) as http:
            generator.request_scene("http://localhost:8088", generator.DEFAULT_MODEL, "系统", "四段式", 6500,
                                    [{"id": 3, "scale": 1.0, "path": "writer.gguf"}])
        payload = json.loads(http.call_args.args[0].data)
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(payload["repeat_penalty"], 1.05)
        self.assertEqual(payload["min_p"], 0)
        self.assertEqual(payload["lora"], [{"id": 3, "scale": 1.0}])
        self.assertEqual([item["role"] for item in payload["messages"]], ["system", "user"])
        with patch.object(generator, "urlopen", return_value=Response(response)) as http:
            generator.request_scene("http://localhost:8088", generator.DEFAULT_MODEL, "系统", "场景", 2400,
                                    [{"id": 3, "scale": .35}],
                                    sampling={"temperature": .65, "repeat_penalty": 1.1})
        payload = json.loads(http.call_args.args[0].data)
        self.assertEqual(payload["lora"], [{"id": 3, "scale": .35}])
        self.assertNotIn("speculative.n_max", payload)
        self.assertEqual(payload["temperature"], .65)

    def test_writer_export_preserves_role_and_restricts_prose_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            agent = Path(temp) / "narrative-writer.md"
            agent.write_text('---\nname: narrative-writer\ndescription: "写手"\nmodel: inherit\ntools: [Read, Bash, PowerShell]\nmaxTurns: 8\n---\n只调用管线。\n', encoding="utf-8")
            definition = exporter.definition(agent)["narrative-writer"]
            self.assertEqual(definition["model"], "inherit")
            self.assertNotIn("Write", definition["tools"])
            self.assertIn("只调用管线", definition["prompt"])

    def test_invalid_plan_finishes_with_blocked_report(self):
        with tempfile.TemporaryDirectory() as directory:
            book = Path(directory)
            work = book / '.story' / 'work' / '第001章'
            work.mkdir(parents=True)
            prompt = {'system': '正文', 'user': '〖人物状态〗\n甲\n〖前情〗\n无\n〖事件骨架〗\n1. 核验\n〖写作要求〗\n全章目标：1000字'}
            (work/'dpo_prompt.json').write_text(json.dumps(prompt), encoding='utf-8')
            (work/'dpo_scene_plan.json').write_text('{}', encoding='utf-8')
            with patch.object(sys, 'argv', ['generate_dpo_draft.py', '--project', str(book), '--chapter', '1']), \
                 patch.object(generator, 'check_backend', return_value=(generator.DEFAULT_MODEL, [])), \
                 patch('builtins.print'):
                self.assertEqual(generator.main(), 2)
            report = json.loads((work/'dpo_report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'blocked')
            self.assertTrue(report['errors'])
            self.assertIsNone(report['draft_sha256'])


if __name__ == "__main__":
    unittest.main()
