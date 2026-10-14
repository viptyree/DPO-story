# DPO-only 子 Agent 调用协议

## narrative-writer：单章正文
1. 主会话完成 `tracking_commit.py check`、DPO 细纲校验及必要卷纲/追踪读取。
2. 运行 `build_dpo_prompt.py --project {书目录} --chapter N --out` 并核对四段式完整性，不能手工把原版九槽 prompt 直接交给 DPO。
3. 仅当当前 Claude Code 已通过 `model: inherit` 的本地 DPO 路由验证时，调用 `narrative-writer` 子 Agent，任务如下：
```text
任务：为本章生成唯一一份完整玄幻小说正文，不做规划与审稿。
项目目录：{书目录}
DPO Prompt 文件：{书目录}/.story/work/第NNN章/dpo_prompt.json
只允许写入：{书目录}/.story/work/第NNN章/dpo_draft.md
使用 Prompt 中四段式 User 内容。不要自行增加新事件，不提前释放底牌。
默认整章一次生成，不能自动改成前后两组。
完成仅返回：输出路径、是否完成全部情节点、是否出现截断。
```
4. 主会话核对输出，写入正式正文并运行原版 `storyctl.py chapter check` 与 Tracking Draft/Commit；未验收则不提交。
5. 反复截断、子 Agent 不可用、模型不对或工具失败：停下报告，不得由 Codex 或其他通用模型代写。

## 其他 agents
`story-architect`、`character-designer`、`story-explorer`、`consistency-checker`、`chapter-extractor`、`story-researcher` 继续执行原版非正文职责；其任务包需要同步消费 DPO 新细纲而非九字段。不得允许非 DPO 写手写正式正文。
