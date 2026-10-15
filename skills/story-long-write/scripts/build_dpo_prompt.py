#!/usr/bin/env python3
"""Build DPO four-section chapter prompt from a validated outline and actual story state."""
import argparse,json,re,sys
from pathlib import Path
SYS="你是一名中文长篇小说写作助手，只输出小说正文。"
SECTIONS=("〖人物状态〗","〖前情〗","〖事件骨架〗","〖写作要求〗")
def section(txt,name):
    m=re.search(r"^##\s*"+re.escape(name)+r"\s*$",txt,re.M)
    if not m: raise ValueError("缺少章节区域 "+name)
    n=re.search(r"^##\s+",txt[m.end():],re.M)
    value=txt[m.end():m.end()+n.start() if n else len(txt)].strip()
    if not value:raise ValueError("空章节区域 "+name)
    return value
def field(txt,label):
    m=re.search(r"^\s*[-*]\s*"+re.escape(label)+r"[：:]\s*(.+)$",txt,re.M)
    if not m:raise ValueError("缺章节字段 "+label)
    return m.group(1).strip()
def chapter_file(folder,n):
    found=[]
    if folder.is_dir():
        for f in folder.glob("细纲_第*章*.md"):
            m=re.match(r"细纲_第0*(\d+)章",f.name)
            if m and int(m.group(1))==n:found.append(f)
    if len(found)!=1:raise ValueError("细纲路径不唯一或不存在：第%d章"%n)
    return found[0]
def tail_of_previous(project,n):
    if n==1:return ""
    folder=project/"正文"
    files=[f for f in folder.glob("第*章*.md") if (m:=re.match(r"第0*(\d+)章",f.name)) and int(m.group(1))==n-1]
    if len(files)!=1:raise ValueError("缺上一章正文或存在重复：第%d章"%(n-1))
    body=files[0].read_text(encoding="utf-8-sig")
    return body[-600:]
def run(root,n):
    f=chapter_file(root/"大纲",n)
    src=f.read_text(encoding="utf-8-sig")
    pieces={name:section(src,name) for name in SECTIONS}
    ctrl=section(src,"章节控制")
    constraints=section(src,"长篇追踪约束")
    goal=field(ctrl,"字数目标")
    metric=field(ctrl,"字数口径")
    if metric!="visible_chars_v1":raise ValueError("不支持的字数口径")
    ending=field(ctrl,"章尾停笔点")
    unit=field(ctrl,"剧情单元")
    state_file=root/"追踪"/"上下文.md"
    if not state_file.is_file():raise ValueError("缺追踪/上下文.md")
    state=state_file.read_text(encoding="utf-8-sig").strip()
    for key in ("核心角色状态","当前位置","活跃伏笔","长期约束","近三章速记","下一章承诺","连贯性风险"):
        if not re.search(r"^##\s*"+key+r"\s*$",state,re.M):raise ValueError("追踪上下文缺栏目："+key)
    prev=tail_of_previous(root,n)
    # The controller needs to reconcile timeline/realm details, not silently auto-override facts.
    # A compact authoritative state excerpt is provided alongside the prompt, not as verbatim prose input.
    before=pieces["〖前情〗"]
    if prev:before+="\n\n【上一章原文结尾（用于衔接，不要重复照抄）】\n"+prev
    pieces["〖前情〗"]=before
    pieces["〖写作要求〗"]+="\n全章目标："+goal+"字（visible_chars_v1）\n结束动作："+ending
    user="\n\n".join(name+"\n"+pieces[name] for name in SECTIONS)
    return dict(system=SYS,user=user,writer_mode="dpo_only",chapter=n,source_outline=str(f),
                source_tracking=str(state_file),volume_unit=unit,
                controller_facts={"tracking_context":state,"long_term_constraints":constraints},
                requires_controller_review=True,
                review_items=["核对追踪人物状态与细纲","核对卷纲单元与底牌","核对境界/物资与角色卡","确认本章不可提前释放项","确认写手收到的 User 只有四段式"])
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--project",required=True);a.add_argument("--chapter",required=True,type=int)
    a.add_argument("--out",nargs="?",const="auto",default=None)
    v=a.parse_args()
    try:
        root=Path(v.project)
        result=run(root,v.chapter)
        s=json.dumps(result,ensure_ascii=False,indent=2)
        if v.out is not None:
            dest=root/".story"/"work"/("第%03d章"%v.chapter)/"dpo_prompt.json" if v.out=="auto" else Path(v.out)
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(s+"\n",encoding="utf-8")
        print(s)
    except (OSError,ValueError) as e:print("ERROR: "+str(e),file=sys.stderr);sys.exit(2)
if __name__=="__main__":main()
