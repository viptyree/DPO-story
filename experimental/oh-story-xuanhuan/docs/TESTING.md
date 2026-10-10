# 开发与验证

## 1. 本地获取当前开发分支
```powershell
git clone -b feature/fanqie-xuanhuan https://github.com/viptyree/oh-story-claudecode.git
cd oh-story-claudecode
py -3 -m unittest discover -s experimental/oh-story-xuanhuan/tests -v
```

此命令仅运行新技能的**静态契约测试**，不能证明生成的细纲被真实项目接受，也不能证明正文工作流可用。

## 2. 用 Oh Story 原版检查器测试细纲
完成真实书的细纲之后运行（把书目录与章节号替换为实际值）：
```powershell
node skills/story-long-write/scripts/check-outline-contract.js --json --project "D:\\novel\\我的小说" --chapter 1
```

这条验证需要书目录有完整细纲，某些检查还需要原版卷纲。严禁用测试工具直接修改追踪 JSON。

## 3. 正文阶段
正文 Skill 当前只提供独立的指令/风格层，不保证其本身已被 Codex/Claude 发现或拥有独立运行时。先在隔离测试小说工程内验证以下内容：
- 指定一章，不越界写下一章；
- 同一个细纲经过原版检查器；
- 质量检测通过；
- 使用原版事务工具进行 tracking draft/commit；
- 使用原版进行下一章续写，验证人物状态、伏笔、作者真相与读者已知没有漂移。

## 4. 交付门禁
发布为独立安装包前必须完成：真实 Codex/Claude 入口适配；复制所需 Python/Node 工具链及其依赖；跨 Windows 路径测试；旧版 Oh Story 数据互通测试；恢复/回滚演练；至少 3 章连续生成与追踪提交。
