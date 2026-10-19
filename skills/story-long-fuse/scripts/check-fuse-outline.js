#!/usr/bin/env node
'use strict';
// 融合细纲增量校验器：在 DPO 格式校验之外，校验借鉴锚点段。
// 与 check-go-outline.js 的差异：
//  - 段名「借鉴锚点」而非「换皮对照」
//  - 情节点来源标注为「来源:{书}」，单源占比按来源书统计，任一源书 >50% 报错
//  - 高重合点（功能表⚠）必须有重做标注
// 退出码：0 通过，1 融合字段有问题，2 用法/IO 错误。
// 用法：node check-fuse-outline.js --project {书目录} --chapter {N}
const fs=require('fs'), path=require('path');
const args=process.argv.slice(2),json=args.includes('--json');
function opt(k){const p=args.indexOf(k);return p<0?null:args[p+1]}
function emit(o,code){process.stdout.write((json?JSON.stringify(o,null,2):JSON.stringify(o))+'\n');process.exitCode=code}
function re_exec(txt,re){let m;while((m=re.exec(txt))!==null){if(m.index===re.lastIndex)re.lastIndex++;if(m[0].trim())return m}return null}
function section(s,heading){const m=re_exec(s,new RegExp('^##\\s*'+heading.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'\\s*$','m'));if(!m)return null;const st=m.index+m[0].length;const nx=s.indexOf('\n## ',st);return s.slice(st,nx===-1?s.length:nx)}
const proj=opt('--project'),chapter=opt('--chapter');
if(!proj||!chapter){emit({status:'invalid',error_code:'FUSE_USAGE',issues:['需要 --project 和 --chapter'],repair_scope:['参数']},2)}
else{
 const dir=path.join(proj,'大纲');
 const files=fs.existsSync(dir)?fs.readdirSync(dir).filter(f=>{let m=f.match(/^细纲_第0*(\d+)章.*\.md$/);return m&&+m[1]===+chapter}):[];
 if(!files.length){emit({status:'invalid',error_code:'OUTLINE_NOT_FOUND',issues:['缺细纲：第'+chapter+'章'],repair_scope:['大纲']},2)}
 const file=path.join(dir,files[0]);
 const s=fs.readFileSync(file,'utf8').replace(/^﻿/,'');
 const issues=[];
 // 提取借鉴锚点段
 const anchor=section(s,'借鉴锚点');
 if(!anchor){issues.push('缺借鉴锚点段');emit({status:'invalid',error_code:'FUSE_NO_ANCHOR',issues,repair_scope:['借鉴锚点']},1)}
 // 字段校验
 for(const k of ['功能表引用','逐点对照','爽点位置','章尾钩子','单源占比','高重合点重做','最像风险与拉开手段','禁用原书名词']){
   if(!new RegExp('^\\s*[-*]\\s*'+k,'m').test(anchor))issues.push('借鉴锚点缺字段：'+k);
 }
 // 逐点对照点数 vs 事件骨架点数
 const ppoints=(anchor.match(/^  - P\d+\s*\[/gm)||[]).length;
 const skel=section(s,'〖事件骨架〗')||'';
 const spoints=(skel.match(/^\s*\d+[.、]\s*\S+/gm)||[]).length;
 if(ppoints!==spoints)issues.push('逐点对照点数('+ppoints+')与事件骨架点数('+spoints+')不一致');
 // 单源占比：优先读显式声明「A:x%/B:y%」；否则按逐点「来源:{书}」统计
 let srcStats={};
 const decl=anchor.match(/单源占比[：:]\s*(.+)/);
 if(decl){
   for(const mm of decl[1].matchAll(/([A-Z])\s*[:：]\s*(\d+(?:\.\d+)?)\s*%/g)){
     const v=parseFloat(mm[2]);srcStats[mm[1]]=v;
     if(v>50)issues.push('单源占比超限：源书'+mm[1]+'='+v+'% >50%');
   }
 }
 if(!Object.keys(srcStats).length){
   const srcs=anchor.match(/来源\s*[:：]\s*([A-Za-z一-鿿]{1,12})/g)||[];
   const cnt={};for(const t of srcs){const m=t.match(/来源\s*[:：]\s*(.+)/);if(m)cnt[m[1]]=(cnt[m[1]]||0)+1}
   const total=Object.values(cnt).reduce((a,b)=>a+b,0);
   if(total>0){for(const k in cnt){const pct=Math.round(cnt[k]/total*100);srcStats[k]=pct;if(pct>50)issues.push('单源占比超限：源书'+k+'='+pct+'% >50%（按逐点来源统计）')}}
   if(!Object.keys(srcStats).length)issues.push('无法统计单源占比：逐点对照缺「来源:{书}」标注');
 }
 // 跨源拼接：本章来源书必须 ≥2 本（第1章也适用）
 if(Object.keys(srcStats).length<2)issues.push('跨源拼接不足：本章机制来源少于2本源书');
 // 高重合点重做：字段值为「无」或含「已重做/重做幅度」才算合规
 const hi=anchor.match(/高重合点重做[：:]\s*(.+)/);
 if(hi){const v=hi[1].trim();if(!/^(无|无。?)$/.test(v)&&!/已重做|重做幅度/.test(v))issues.push('高重合点重做标注不合规：应为「无」或注明重做幅度（含「已重做/重做幅度」）')}
 // 禁用原书名词：提取列表，检查是否泄漏进四段式
 const banm=anchor.match(/禁用原书名词[：:]\s*(.+)/);
 const banned=banm?banm[1].split(/[、,，]/).map(x=>x.trim()).filter(Boolean):[];
 if(!banned.length)issues.push('禁用原书名词列表为空');
 const four=['〖人物状态〗','〖前情〗','〖事件骨架〗','〖写作要求〗'];
 const fourText=four.map(h=>section(s,h)||'').join('\n');
 for(const b of banned){if(fourText.includes(b))issues.push('原书名词泄漏进四段式：'+b)}
 emit({status:issues.length?'invalid':'ready',file,issues,repair_scope:issues,fuse_fields:{banned_count:banned.length,point_count:spoints,source_share:srcStats}},issues.length?1:0);
}
