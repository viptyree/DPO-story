# DPO-only 子 Agent 调用协议

## narrative-writer：单章正文
1. 主会话运行 `chapter_pipeline.py --project "{书目录}" --chapter N --prepare-only`，统一完成服务、追踪和细纲校验；按 oh-story 读取必要卷纲、追踪和设定。
2. 核对 `dpo_prompt.json` 的事实、四段式与信息边界。写手不重建或覆盖主控已审核的 Prompt。
3. 仅当当前 Claude Code 已通过 `model: inherit` 的本地 DPO 路由验证时，调用 `narrative-writer` 子 Agent，任务如下：
```text
任务：执行本章已审核计划的下一步本地正文生成，不做规划与审稿。
项目目录：{书目录}
DPO Prompt 文件：{书目录}/.story/work/第NNN章/dpo_prompt.json
唯一命令：python "{story-long-write skill 根}/scripts/chapter_pipeline.py" --project "{书目录}" --chapter N --generate-prepared
脚本直接读取 Prompt 的 System/User 四段式，调用本地 DPO 服务并写 dpo_draft.md 和 `dpo_report.json`。不要由 Agent 在工具参数里输出正文。
完成仅返回：脚本 status、草稿路径、是否出现截断。
```
4. awaiting_scene_review 时主控按 `scene-handoff.md` 审阅并填写交接文件，再调用写手；不要求作者逐场批准。只有最终 ready 且内容通过，才原样复制草稿并运行原版检查和 Tracking Draft/Commit；blocked 停止。不得只因机器初筛通过就确认情节点完成。
5. 子 Agent 不可用时核对本次启动器的 `--agents` 注册和项目 agent 文件；模型、LoRA 或工具失败则报告具体原因。正文始终由本地 DPO 服务生成，不由主控代写。

## 其他 agents
`story-architect`、`character-designer`、`story-explorer`、`consistency-checker`、`chapter-extractor`、`story-researcher` 继续执行原版非正文职责；其任务包需要同步消费 DPO 新细纲而非九字段。不得允许非 DPO 写手写正式正文。

### 对标资料缺失处理
story-explorer 返回 `profile_missing` 且 `custom_style` 为真时继续按本书 `设定/文风.md` 写作，不把缺失误判成 benchmark_book_missing；否则按原版停下修复流程处理。
