# DPO-only 正文修订与重写

规划修订与正文修订分离：Codex 修订 `大纲/细纲_第NNN章.md` 的 DPO 细纲；claudeqwen 调 `narrative-writer` 完成正式正文修订。

1. 确认作者指定的章节、局部段落或整章范围；有多解时让作者确定，不自动扩展改稿范围。
2. 必须备份当前正式正文，完整读取 DPO 细纲、相邻章首尾、实际追踪和有关角色状态。验证新细纲通过 `check-outline-contract.js`。
3. **整章重写**：将既定事件骨架、前情、状态、停笔点与作者修订要求合并为四段式 DPO Prompt，`narrative-writer` 默认一次重写整章，写临时路径。
4. **局部修改**：由 claudeqwen 编制具体的段落替换范围，在 DPO 的 `〖前情〗` 放目标片段与必要衔接，在 `〖写作要求〗` 指明仅重写该局部；主会话用确定性文件操作替换，其他段落原样保留。
5. 无可用的 DPO `narrative-writer` 或模型不符时停止，禁止退回主会话代写。
6. 运行 `storyctl.py chapter check`，按原版合法 revision 模式更新追踪事务，验证成功后才报告完成；不得手改 `_tracking-state.json`。
7. 不得借修稿新增未经作者批准的主线、法则、境界或伏笔结算。
