import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "storyctl.py"
spec = importlib.util.spec_from_file_location("storyctl_dpo_test", SCRIPT)
storyctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storyctl)


class DpoProvenanceTest(unittest.TestCase):
    def fixture(self, project):
        storyctl._dpo_evidence_module()
        work=storyctl.chapter_work_dir(project,1)
        work.mkdir(parents=True)
        prompt=work/'dpo_prompt.json'
        prompt.write_text(json.dumps({'writer_mode':'dpo_only'}),encoding='utf-8')
        draft=work/'dpo_draft.md'
        draft.write_text('本地生成稿。\n',encoding='utf-8')
        body=project/'body.md'
        body.write_bytes(draft.read_bytes())
        plan=work/'dpo_scene_plan.json'
        plan.write_text('{}',encoding='utf-8')
        report={'status':'ready','model':'qwen3.8-27b-udq4-xuanhuan-dpo','finish_reason':'stop',
                'draft_sha256':hashlib.sha256(draft.read_bytes()).hexdigest(),
                'prompt_sha256':hashlib.sha256(prompt.read_bytes()).hexdigest(),
                'scene_plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest()}
        (work/'dpo_report.json').write_text(json.dumps(report),encoding='utf-8')
        txn=project/'transaction.json'
        txn.write_text(json.dumps({'chapter':1,'mode':'append'}),encoding='utf-8')
        return work,body,txn

    def commit(self, project, body, txn):
        tracking=MagicMock()
        tracking.apply_transaction.return_value={'last_committed_chapter':1,'wordcount_records':{'1':{}}}
        check={'status':'ready','quality':{'status':'pass'},'length':{'status':'internal_pass'}}
        with patch.object(storyctl,'chapter_check',return_value=check), \
             patch.object(storyctl,'_project_files',return_value=(None,body,1000,None)), \
             patch.object(storyctl,'build_project_wordcount_record',return_value={}), \
             patch.object(storyctl,'_tracking_module',return_value=tracking):
            result=storyctl.chapter_commit(project,1,txn,accept_current_length=False)
        return result,tracking

    def test_commit_archives_before_cleanup_and_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp)
            work,body,txn=self.fixture(project)
            result,tracking=self.commit(project,body,txn)
            self.assertTrue(result['tracking_committed'])
            self.assertFalse(work.exists())
            archive=Path(result['dpo_evidence_archive'])
            self.assertTrue((archive/'dpo_prompt.json').is_file())
            storyctl._check_dpo_provenance(project,1,body)
            body.write_text('手改正文。',encoding='utf-8')
            with self.assertRaisesRegex(storyctl.ChapterRefused,'逐字一致'):
                storyctl._check_dpo_provenance(project,1,body)
            tracking.apply_transaction.assert_called_once()

    def test_archive_failure_never_commits_or_removes_work(self):
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp)
            work,body,txn=self.fixture(project)
            tracking=MagicMock()
            with patch.object(storyctl.dpo_evidence,'archive_work',side_effect=OSError('disk failure')), \
                 patch.object(storyctl,'_tracking_call') as apply:
                with self.assertRaisesRegex(storyctl.ChapterRefused,'未提交追踪'):
                    self.commit(project,body,txn)
                apply.assert_not_called()
            self.assertTrue(work.is_dir())

    def test_pointer_failure_preserves_live_work_after_durable_commit(self):
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp)
            work,body,txn=self.fixture(project)
            with patch.object(storyctl.dpo_evidence,'publish',side_effect=OSError('pointer failure')):
                result,_=self.commit(project,body,txn)
            self.assertTrue(result['tracking_committed'])
            self.assertTrue(work.exists())
            self.assertIsNone(result['work_dir_removed'])
            storyctl._check_dpo_provenance(project,1,body)

    def test_dpo_outline_without_any_evidence_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp)
            outline=project/'outline.md'
            outline.write_text('〖事件骨架〗\n1. 核验',encoding='utf-8')
            body=project/'body.md'
            body.write_text('正文',encoding='utf-8')
            with self.assertRaisesRegex(storyctl.ChapterRefused,'不能因临时目录已清理'):
                storyctl._check_dpo_provenance(project,1,body,outline)

    def test_failed_or_changed_draft_cannot_enter_chapter_check(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            work = storyctl.chapter_work_dir(project, 1)
            work.mkdir(parents=True)
            prompt = work / "dpo_prompt.json"
            prompt.write_text(json.dumps({"writer_mode": "dpo_only"}), encoding="utf-8")
            draft = work / "dpo_draft.md"
            draft.write_text("本地模型生成的正文\n", encoding="utf-8")
            body = project / "body.md"
            body.write_bytes(draft.read_bytes())
            report = work / "dpo_report.json"

            with self.assertRaisesRegex(storyctl.ChapterRefused, "缺少本地 DPO"):
                storyctl._check_dpo_provenance(project, 1, body)

            data = {
                "status": "blocked", "model": "qwen3.8-27b-udq4-xuanhuan-dpo", "finish_reason": "stop",
                "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest(),
                "draft_sha256": hashlib.sha256(draft.read_bytes()).hexdigest(),
            }
            report.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(storyctl.ChapterRefused, "未通过生成门禁"):
                storyctl._check_dpo_provenance(project, 1, body)

            data["status"] = "ready"
            report.write_text(json.dumps(data), encoding="utf-8")
            storyctl._check_dpo_provenance(project, 1, body)
            plan = work / "dpo_scene_plan.json"
            plan.write_text("{}", encoding="utf-8")
            data["scene_plan_sha256"] = hashlib.sha256(plan.read_bytes()).hexdigest()
            report.write_text(json.dumps(data), encoding="utf-8")
            storyctl._check_dpo_provenance(project, 1, body)
            plan.write_text('{"changed": true}', encoding="utf-8")
            with self.assertRaisesRegex(storyctl.ChapterRefused, "分场计划已变化"):
                storyctl._check_dpo_provenance(project, 1, body)
            del data["scene_plan_sha256"]
            report.write_text(json.dumps(data), encoding="utf-8")
            body.write_text("主会话改写的正文\n", encoding="utf-8")
            with self.assertRaisesRegex(storyctl.ChapterRefused, "逐字一致"):
                storyctl._check_dpo_provenance(project, 1, body)


if __name__ == "__main__":
    unittest.main()
