#!/usr/bin/env python3
"""Convert a legacy Oh Story outline to DPO-only outline. Dry run by default."""
import argparse,re,sys
from pathlib import Path
def capture(s,key):
 m=re.search(r"^\s*[-*]\s*"+re.escape(key)+r"\s*[：:]\s*(.*)$",s,re.M)
 return m.group(1).strip() if m else ""
def subsection(s,heading):
 m=re.search(r"^#{3,4}\s*"+re.escape(heading)+r"\s*$",s,re.M)
 if not m:return ""
 v=s[m.end():];end=re.search(r"^#{2,4}\s",v,re.M)
 return v[:end.start() if end else len(v)].strip()
def convert(original):
 if "## 〖事件骨架〗" in original:raise ValueError("输入已是 DPO 格式")
 heading=re.search(r"^#{1,3}\s*(?:第\s*\d+\s*章)[：:]?\s*(.+)$",original,re.M)
 if not heading:raise ValueError("未找到章节标题")
 events=[]
 table=subsection(original,"情节细化")
 for line in table.splitlines():
  cols=[c.strip() for c in line.strip().strip("|").split("|")]
  if len(cols)>=2 and re.fullmatch(r"\d+",cols[0]) and cols[1]:
   events.append(cols[1])
 if not events:raise ValueError("旧细纲缺可提取的具体情节点；停止转换")
 target=capture(original,"字数目标");metric=capture(original,"字数口径")
 if not target or "visible_chars_v1" not in metric:raise ValueError("缺旧版字数目标或口径；停止转换")
 unit=capture(original,"单元ID/位置")
 if not unit:raise ValueError("缺单元ID；停止转换")
 forbidden=capture(original,"本章禁止提前释放") or "【待作者核实】"
 ending=capture(original,"章尾钩子") or "【待作者核实】"
 emotion=capture(original,"目标情绪") or "【待作者核实】"
 goal=capture(original,"主角目标/关键选择") or "【待作者核实】"
 overview=subsection(original,"内容概括")
 relationship=subsection(original,"人物关系和出场顺序")
 title=heading.group(1).strip()
 number=re.search(r"第\s*(\d+)\s*章",heading.group(0)).group(1)
 return f"""# 第{number}章：{title}

## 章节控制
- 所属卷：【待作者确认】
- 剧情单元：{unit}
- 字数目标：{target}
- 字数口径：visible_chars_v1
- 视角：{capture(original,'视角/信息差') or '【待作者确认】'}
- 章节目标：{goal}
- 目标情绪：{emotion}
- 章尾停笔点：{ending}

## 〖人物状态〗
{relationship or '【待作者核实人物当前境界、位置和状态】'}

## 〖前情〗
{overview or '【待作者核实具体前情和场景状态】'}

## 〖事件骨架〗
"""+"\n".join(f"{i}. {e}" for i,e in enumerate(events,1))+f"""

## 〖写作要求〗
- 禁止提前释放：{forbidden}
- 结束位置：{ending}
- 写作需符合已批准卷纲与人物设定，不增加剧情事实。

## 长篇追踪约束
- 本章已有设定与伏笔，以追踪权威状态为准。
- 待核实：境界、道具、关系和未兑现承诺。
"""
def main():
 p=argparse.ArgumentParser();p.add_argument("source");p.add_argument("--write",action="store_true")
 a=p.parse_args();src=Path(a.source)
 try:
  if not src.is_file():raise ValueError("未找到细纲")
  raw=src.read_text(encoding="utf-8-sig");out=convert(raw)
  if a.write:
   bak=src.with_suffix(src.suffix+".before-dpo.bak")
   if bak.exists():raise ValueError("备份已存在，拒绝覆盖："+str(bak))
   bak.write_text(raw,encoding="utf-8")
   src.write_text(out,encoding="utf-8")
   print("已迁移："+str(src)+"\n备份："+str(bak))
  else:print(out)
 except (ValueError,OSError) as e:print("ERROR: "+str(e),file=sys.stderr);sys.exit(2)
if __name__=="__main__":main()
