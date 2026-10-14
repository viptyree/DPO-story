# DPO-only 单章正文 SOP

仅供本地 claudeqwen 进入 `/story-long-write 写第N章` 使用。原版写手前后两组机制停用；新细纲以 `dpo-outline-contract.md` 为准。

1. 项目预检：`tracking_commit.py check --project {书目录}`。无状态的新书按原版 `tracking-initialization.md` 初始化；有正文却丢状态按 `stop-and-fix.md` 停下。
2. 完整读取 `大纲/细纲_第NNN章.md`，运行 `check-outline-contract.js --json --project {书目录} --chapter N`。没有新版 DPO 四区域或校验失败就停止，不调用写手。
3. 读取 `追踪/上下文.md`、相关角色/力量体系/伏笔、上一章末尾；用 `outline_view.py --unit` 取卷纲当前单元；比对细纲中的人物状态是否过时，冲突停下交给作者或 Codex 修纲。
4. 运行 `build_dpo_prompt.py --project {书目录} --chapter N --out`。仔细核对本章所有 `〖事件骨架〗`、章尾停笔点、禁止提前释放和正文目标字数，不能遗漏。
5. 当前会话必须为已验证连接本地玄幻 DPO LoRA 的 `claudeqwen`；`narrative-writer` 必须可用且成功继承该模型。调用规范见 `agent-calls.md` 与 `dpo-writer.md`。**不允许当前主会话 solo 代写或其他模型代写。**
6. 子 Agent 默认一次成文，输出临时文件 `.story/work/第NNN章/dpo_draft.md`。正文不完整、模型截断、违反细纲信息边界时保留草稿且停止提交；按具体问题定点重写需要新的完整 DPO 任务。
7. 主会话验收临时文本后整理为 `正文/第NNN章_章名.md`，调用 `storyctl.py chapter check --project {书目录} --chapter N --fix-punctuation`。blocking 修复、advisory 人工判断，`tool_unavailable` 禁止提交，字数范围问题按原版作者选择流程。
8. `tracking_commit.py draft --project {书目录} --chapter N`；填写本章实际发生的角色、伏笔、地点与时间线状态，`storyctl.py chapter commit --project {书目录} --chapter N --input {工作目录}/tracking.json`；返回 `tracking_committed: true` 才算完成。
9. 汇报章节、字数、检查结果和状态提交情况；只写作者明确要求的章节。

本流程不废除原版追踪状态格式及事务安全规则。若原版验证器或其他工具因旧细纲字段出错，属于兼容缺陷，必须修复，**不得临时绕过**。
