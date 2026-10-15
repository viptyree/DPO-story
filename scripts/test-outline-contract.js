#!/usr/bin/env node
'use strict'
// DPO-only structural contract; old nine-field fixtures are deliberately unsupported.
const assert=require('assert'),fs=require('fs'),os=require('os'),path=require('path')
const {spawnSync}=require('child_process')
const verifier=path.join(__dirname,'../skills/story-long-write/scripts/check-outline-contract.js')
const root=fs.mkdtempSync(path.join(os.tmpdir(),'dpo-outline-'))
const good=`# 第21章：测试

## 章节控制
- 所属卷：第一卷
- 剧情单元：L1-03
- 字数目标：2500
- 字数口径：visible_chars_v1
- 视角：第三人称
- 章节目标：下渠
- 目标情绪：困境到希望
- 章尾停笔点：钉尖将触石

## 〖人物状态〗
许渡身在渠口。

## 〖前情〗
护山阵即将碎裂。

## 〖事件骨架〗
1. 谢寒川准备封渠。
2. 许渡听见残脉。
3. 许渡下渠。

## 〖写作要求〗
只写到钉尖将触石。

## 长篇追踪约束
禁止提前破境。
`
function run(text){
 const project=path.join(root,'book');const dir=path.join(project,'大纲')
 fs.mkdirSync(dir,{recursive:true})
 fs.writeFileSync(path.join(dir,'细纲_第021章.md'),text)
 return spawnSync(process.execPath,[verifier,'--json','--project',project,'--chapter','21'],{encoding:'utf8'})
}
try{
 let g=run(good);assert.strictEqual(g.status,0,g.stdout+g.stderr);assert.strictEqual(JSON.parse(g.stdout).status,'ready')
 for(const name of ['章节控制','〖人物状态〗','〖前情〗','〖事件骨架〗','〖写作要求〗','长篇追踪约束']){
  const x=run(good.replace('## '+name,'## 已删除'+name))
  assert.strictEqual(x.status,1,name);assert.match(x.stdout,/缺标题/)
 }
 assert.strictEqual(run(good.replace('visible_chars_v1','other_chars')).status,1)
 assert.strictEqual(run(good.replace('1. 谢寒川准备封渠。','谢寒川准备封渠。').replace('2. 许渡听见残脉。','许渡听见残脉。').replace('3. 许渡下渠。','许渡下渠。')).status,1)
 const old=run('### 第21章：旧格式\n- 核心事件：旧\n- 字数目标：2500')
 assert.strictEqual(old.status,1)
 process.stdout.write('outline-contract: DPO-only fixtures passed\n')
}finally{fs.rmSync(root,{recursive:true,force:true})}
