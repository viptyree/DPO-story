#!/usr/bin/env python3
"""DPO-only outline and prompt integration smoke test (stdlib, node required)."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
S=ROOT/"skills"/"story-long-write"/"scripts"

class DPOOnlySmoke(unittest.TestCase):
    def test_contract_compiler(self):
        if not shutil.which("node"):
            self.skipTest("node unavailable")
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/"大纲").mkdir();(p/"追踪").mkdir()
            (p/"追踪"/"上下文.md").write_text("## 核心角色状态\n许渡尚未破境",encoding="utf-8")
            (p/"大纲"/"细纲_第001章.md").write_text("""# 第1章：山门将碎时，他踏进了废渠

## 章节控制
- 所属卷：第一卷
- 剧情单元：L1-01
- 目标字数：2500
- 字数口径：visible_chars_v1
- 视角：第三人称紧贴许渡
- 章节目标：踏入废渠
- 目标情绪：窒息转为希望
- 章尾停笔点：钉尖将触石

## 〖人物状态〗
许渡：尚未破境。

## 〖前情〗
山门将碎。

## 〖事件骨架〗
1. 谢寒川封住脉口。
2. 许渡听见活脉。
3. 沈照霜补阵。
4. 许渡下渠，钉尖落下之前停笔。

## 〖写作要求〗
不得揭露战局胜负。

## 长篇追踪约束
不得新增力量规则。
""",encoding="utf-8")
            a=subprocess.run(["node",str(S/"check-outline-contract.js"),"--json","--project",str(p),"--chapter","1"],capture_output=True,text=True,encoding="utf-8")
            self.assertEqual(a.returncode,0,a.stdout+" "+a.stderr)
            b=subprocess.run([sys.executable,str(S/"build_dpo_prompt.py"),"--project",str(p),"--chapter","1","--out"],capture_output=True,text=True,encoding="utf-8")
            self.assertEqual(b.returncode,0,b.stderr)
            j=json.loads(b.stdout);self.assertEqual(j["writer_mode"],"dpo_only")
            for k in ("〖人物状态〗","〖前情〗","〖事件骨架〗","〖写作要求〗"):self.assertIn(k,j["user"])
            self.assertNotIn("长篇追踪约束",j["user"])
            self.assertTrue((p/".story/work/第001章/dpo_prompt.json").is_file())
    def test_rejects_old_outline(self):
        if not shutil.which("node"):self.skipTest("node unavailable")
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/"大纲").mkdir()
            (p/"大纲/细纲_第001章.md").write_text("# 第1章 旧\n- 核心事件：旧格式",encoding="utf-8")
            a=subprocess.run(["node",str(S/"check-outline-contract.js"),"--json","--project",str(p),"--chapter","1"],capture_output=True,text=True,encoding="utf-8")
            self.assertNotEqual(a.returncode,0)

if __name__=="__main__":unittest.main()
