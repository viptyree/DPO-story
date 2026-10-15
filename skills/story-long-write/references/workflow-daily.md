# DPO-only 日更续写流程

此模式由本地 `claudeqwen` 执行，Codex 负责前置规划与旧书资料补齐；正文唯一写手为继承本地 LoRA 的 `narrative-writer`。
作者明确要求多章时，每批最多三章；裸调用不能默认日更。

1. `tracking_commit.py check --project {书目录}`，以 `last_committed_chapter+1` 为待写首章。读取 `追踪/上下文.md`，不是从聊天猜进度。
2. 检查要求的章数、每章对应 DPO 细纲、卷纲单元、境界/伏笔与信息释放边界。任何一章缺纲或旧九字段格式均停止，交回 Codex 按 `workflow-outline.md` 规划；不得临时口头编出新剧情。
3. **必须顺序逐章**执行 `workflow-chapter.md`：DPO 四段式编译 → narrative-writer **整章一次生成** → `storyctl.py chapter check` → `tracking_commit.py draft` → `storyctl.py chapter commit`。
4. 只有本章 `tracking_committed: true` 后才能读取新追踪并进入下一章。禁止一次启动多个 narrative-writer 并发提交。
5. 已完成指定章节或最多三章即停；报告完成数、未完成原因、下章现有细纲是否就绪。不自动追加下一批。

**质量检查与模型路由异常**：按 `workflow-chapter.md` 停止，保留当前临时草稿。不允许主会话或其他非 DPO 模型代写。

## 向作者汇报
<!-- author-report -->
```md
本批完成第{A}-{B}章，共{已完成章节数}章，均已单章检查并顺序提交追踪。
本批剧情推进：{摘要}。未完成事项：{无或具体阻塞项}。
```
