#!/usr/bin/env python3
"""DPO-only structured prompt compiler. Does not call a model or change story state."""
import argparse
import json
import re
import sys
from pathlib import Path

SYSTEM = "你是一名中文长篇小说写作助手，只输出小说正文。"
TITLES = ("〖人物状态〗", "〖前情〗", "〖事件骨架〗", "〖写作要求〗")
def section(source, name):
    pattern = r"^##\s*" + re.escape(name) + r"\s*$"
    m = re.search(pattern, source, re.M)
    if not m: raise ValueError("缺 DPO 细纲区域：" + name)
    end = re.search(r"^##\s+", source[m.end():], re.M)
    result = source[m.end():m.end()+end.start() if end else len(source)].strip()
    if not result: raise ValueError("DPO 细纲区域为空：" + name)
    return result
def field(s, label):
    m=re.search(r"^\s*[-*]\s*"+re.escape(label)+r"\s*[：:]\s*(.+)$",s,re.M)
    return m.group(1).strip() if m else ""
def locate(root,n):
    folder=root/"大纲"
    for f in sorted(folder.glob("细纲_第*章*.md")):
        m=re.match(r"细纲_第0*(\d+)章",f.name)
        if m and int(m.group(1))==n:return f
    raise ValueError("细纲不存在：第%d章" % n)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--project",required=True)
    p.add_argument("--chapter",required=True,type=int)
    p.add_argument("--out",nargs="?",const="auto",default=None)
    a=p.parse_args()
    try:
        project=Path(a.project)
        file=locate(project,a.chapter)
        src=file.read_text(encoding="utf-8-sig")
        data={name:section(src,name) for name in TITLES}
        control=section(src,"章节控制")
        tracking=project/"追踪"/"上下文.md"
        if not tracking.is_file():raise ValueError("追踪/上下文.md 不存在，禁止无状态生成")
        state=tracking.read_text(encoding="utf-8-sig")
        if not state.strip():raise ValueError("追踪上下文为空")
        # Do not silently override DPO outline with truncated or invented state.
        # Host controller must adjudicate conflicts and supply relevant facts.
        char=field(control,"视角")
        goal=field(control,"目标字数")
        ending=field(control,"章尾停笔点")
        user="\n\n".join("## "+name+"\n"+data[name] for name in TITLES)
        user += "\n- 字数目标："+goal+"（visible_chars_v1）\n- 章尾停笔点："+ending
        result={"system":SYSTEM,"user":user,"source_outline":str(file),
                "writer_mode":"dpo_only","chapter":a.chapter,
                "requires_controller_review":True,
                "review_items":["最新追踪人物状态","当前卷纲边界","上一章结尾","角色设定","伏笔","本书文风"],
                "viewpoint":char}
        out=json.dumps(result,ensure_ascii=False,indent=2)
        if a.out is not None:
            target=(project/".story"/"work"/f"第{a.chapter:03d}章"/"dpo_prompt.json") if a.out=="auto" else Path(a.out)
            target.parent.mkdir(parents=True,exist_ok=True);target.write_text(out+"\n",encoding="utf-8")
        print(out)
    except (ValueError,OSError) as e:
        print("ERROR: "+str(e),file=sys.stderr);sys.exit(2)
if __name__=="__main__":main()
