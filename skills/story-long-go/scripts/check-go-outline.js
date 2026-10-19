#!/usr/bin/env node
'use strict';
// 换皮细纲增量校验器：在 DPO 格式校验之外，校验换皮对照段。
// 退出码：0 通过，1 换皮字段有问题，2 用法/IO 错误。
// 用法：node check-go-outline.js --project {书目录} --chapter {N} [--source {拆文库章节目录}]
const fs=require('fs'), path=require('path');
const args=process.argv.slice(2),json=args.includes('--json');
function opt(k){const p=args.indexOf(k);return p<0?null:args[p+1]}
function emit(o,code){process.stdout.write((json?JSON.stringify(o,null,2):JSON.stringify(o))+'\n');process.exitCode=code}
const proj=opt('--project'),chapter=opt('--chapter'),source=opt('--source');
if(!proj||!chapter){emit({status:'invalid',error_code:'GO_USAGE',issues:['需要 --project 和 --chapter'],repair_scope:['参数']},2)}
else{
 const dir=path.join(proj,'大纲');
 const files=fs.existsSync(dir)?fs.readdirSync(dir).filter(f=>{let m=f.match(/^细纲_第0*(\d+)章.*\.md$/);return m&&+m[1]===+chapter}):[];
 if(!files.length){emit({status:'invalid',error_code:'OUTLINE_NOT_FOUND',issues:['缺细纲：第'+chapter+'章'],repair_scope:['大纲']},2)}
 const file=path.join(dir,files[0]);
 const s=fs.readFileSync(file,'utf8').replace(/^\uFEFF/,'');
 const issues=[];
 // 提取换皮对照段
 const m=re_exec(s,/^##\s*换皮对照\s*$/m);
 if(!m){issues.push('缺换皮对照段');emit({status:'invalid',error_code:'GO_NO_SKIN',issues,repair_scope:['换皮对照']},1)}
 const start=m.index+m[0].length;
 const next=s.indexOf('\n## ',start);
 const skin=s.slice(start,next===-1?s.length:next).trim();
 // 字段校验
 for(const k of ['对标章节','原书情节点数','情节点对照','功能位','爽点位置','禁用原书名词']){
   if(!new RegExp('^\\s*[-*]\\s*'+k,'m').test(skin))issues.push('换皮对照缺字段：'+k);
 }
 // 情节点对照点数
 const pcount=(skin.match(/^  - P\d+：/gm)||[]).length;
 const declared=(skin.match(/原书情节点数[：:]\s*(\d+)/)||[])[1];
 if(declared&&+declared!==pcount)issues.push('情节点对照点数('+pcount+')与原书情节点数('+declared+')不一致');
 // 禁用原书名词：提取列表，检查是否泄漏进四段式
 const banm=skin.match(/禁用原书名词[：:]\s*(.+)/);
 const banned=banm?banm[1].split(/[、,，]/).map(x=>x.trim()).filter(Boolean):[];
 // 四段式区域
 const four=['〖人物状态〗','〖前情〗','〖事件骨架〗','〖写作要求〗'];
 const fourText=four.map(h=>{const mm=re_exec(s,new RegExp('^##\\s*'+h.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'\\s*$','m'));if(!mm)return'';const st=mm.index+mm[0].length;const nx=s.indexOf('\n## ',st);return s.slice(st,nx===-1?s.length:nx)}).join('\n');
 for(const b of banned){if(fourText.includes(b))issues.push('原书名词泄漏进四段式：'+b)}
 // 事件骨架点数应与原书情节点数一致
 const skel=re_exec(s,/^##\s*〖事件骨架〗\s*$/m);
 if(skel){const st=skel.index+skel[0].length;const nx=s.indexOf('\n## ',st);const skelText=s.slice(st,nx===-1?s.length:nx);const spoints=(skelText.match(/^\s*\d+[.、]\s*\S+/gm)||[]).length;
   if(declared&&spoints!==+declared)issues.push('事件骨架点数('+spoints+')与原书情节点数('+declared+')不一致')}
 emit({status:issues.length? 'invalid':'ready',file,issues,repair_scope:issues,skin_fields:{banned_count:banned.length,point_count:pcount}},issues.length?1:0);
}
function re_exec(txt,re){let m;while((m=re.exec(txt))!==null){if(m.index===re.lastIndex)re.lastIndex++;if(m[0].trim())return m}return null}
