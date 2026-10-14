#!/usr/bin/env node
'use strict';
// DPO-only outline validator. Exit 0 valid, 1 invalid outline, 2 usage/I-O.
const fs=require('fs'), path=require('path');
const args=process.argv.slice(2),json=args.includes('--json');
function opt(k){const p=args.indexOf(k);return p<0?null:args[p+1]}
function emit(o,code){process.stdout.write((json?JSON.stringify(o,null,2):JSON.stringify(o))+'\n');process.exitCode=code}
if(args.includes('--supply')){emit({status:'unsupported',error_code:'DPO_SUPPLY_CHECK_MIGRATION',message:'旧供给检查需迁移至 DPO 单元验证器；不允许假报通过'},2)}
else {
const proj=opt('--project'),chapter=opt('--chapter');
let paths=args.filter(x=>!x.startsWith('--')&&!['--json','--project','--chapter'].includes(x)).filter(x=>x!==proj&&x!==chapter);
if(proj&&chapter){
 const dir=path.join(proj,'大纲');if(fs.existsSync(dir))paths=fs.readdirSync(dir).filter(f=>{let m=f.match(/^细纲_第0*(\d+)章.*\.md$/);return m&&+m[1]===+chapter}).map(f=>path.join(dir,f))
}
if(!paths.length){emit({status:'invalid',error_code:'OUTLINE_NOT_FOUND',issues:['missing outline'],repair_scope:['细纲路径']},2)}
else{
let reports=paths.map(file=>{
if(!fs.existsSync(file))return {file,issues:['file not found']};
const s=fs.readFileSync(file,'utf8').replace(/^\uFEFF/,'');
const headings=['章节控制','〖人物状态〗','〖前情〗','〖事件骨架〗','〖写作要求〗','长篇追踪约束'];
const issues=[],blocks={};for(let i=0;i<headings.length;i++){
const escaped=headings[i].replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const re=new RegExp('^##\\s*'+escaped+'\\s*$','m');const match=re.exec(s);
if(!match){issues.push('缺标题：'+headings[i]);continue}
const start=match.index+match[0].length;const next=s.indexOf('\n## ',start);blocks[headings[i]]=s.slice(start,next===-1?s.length:next).trim();
if(!blocks[headings[i]])issues.push('空内容：'+headings[i]);
}
for(const k of ['所属卷','剧情单元','目标字数','字数口径','视角','章节目标','目标情绪','章尾停笔点']){
if(!new RegExp('^\\s*[-*]\\s*'+k+'\\s*[：:]\\s*\\S+','m').test(blocks['章节控制']||''))issues.push('缺章节控制字段：'+k)
}
if(!/visible_chars_v1/.test(blocks['章节控制']||''))issues.push('字数口径必须为 visible_chars_v1');
if(!/^\s*\d+[.、]\s*\S+/m.test(blocks['〖事件骨架〗']||''))issues.push('事件骨架必须含编号的动作');
if(!/^#\s*第\s*\d+\s*章/.test(s))issues.push('缺章节标题');
return {file,issues};
});
emit({status:reports.every(r=>r.issues.length===0)?'ready':'invalid',reports,repair_scope:reports.flatMap(r=>r.issues)},reports.some(r=>r.issues.length)?1:0)
}
}
