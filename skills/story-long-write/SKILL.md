---
name: story-long-write
version: 2.0.0-dpo
description: "玄幻 DPO 长篇小说规划与正文：Codex 负责开书、设定、卷纲、DPO细纲；claudeqwen 负责通过 narrative-writer 调用本地 DPO LoRA 写指定章节。"
metadata: {"openclaw":{"source":"https://github.com/viptyree/oh-story-claudecode"}}
---
# story-long-write｜DPO-only 玄幻长篇

## 唯一职责分工
- **Codex（GPT-6）**：开书、定设定、卷纲、DPO 细纲、规划校验；**禁止直接代写正式正文**。
- **claudeqwen**：在小说根目录启动，接受 `/story-long-write 写第N章`；主会话检查状态、编译 Prompt、调用本地 DPO 写手、验收并提交。
- **narrative-writer**：`model: inherit`，只负责按 DPO 模型卡形式写正文。继承是否指向加载 LoRA 的本地服务必须在用户本机验证。无写手或路由不明则停下，**不启用 solo/direct 正文回退**。
- 其他原版 Skills、Agents、Hooks 维持其非正文职责，不因为本 Skill 改版而删除。

## 路由与先读资料
| 作者意图 | 完整读取的权威流程 | 停止条件 |
| --- | --- | --- |
| 讨论结构、选题 | 按当前任务定点读 `references/workflow-setup.md` | 仅讨论不自动落盘 |
| 开书、定设定 | `references/workflow-setup.md` | 每个作者确认点后停 |
| 出卷纲 | `references/workflow-volume.md` | 只交付卷纲，不转正文 |
| 出细纲、补纲 | `references/workflow-outline.md` + `references/dpo-outline-contract.md` | 新版校验通过才交付 |
| 写第N章 | `references/workflow-chapter.md` + `references/dpo-writer.md` + `references/agent-calls.md` | 指定一章成功提交后停 |
| 日更、续写 | `references/workflow-daily.md`，每章再走新版 chapter 流程 | 每轮最多三章，逐章提交 |
| 修稿、重写 | `references/workflow-revision.md`，复用 DPO 正文交接协议 | 不更改作者未授权的剧情 |

裸调用没有具体意图时仅诊断当前书与可做的操作，不默认启动写作。

## DPO 细纲为唯一正式协议
**不再使用原版九字段、五段式、前后两组写手分配。**
权威模板：`references/dpo-outline-contract.md`。章节存 `大纲/细纲_第NNN章.md`，内容需含 `章节控制`、`〖人物状态〗`、`〖前情〗`、`〖事件骨架〗`、`〖写作要求〗`、`长篇追踪约束`。细纲生成后跑 `scripts/check-outline-contract.js`。旧细纲不能静默当作已迁移。
卷纲、设定、时间线、角色档案与追踪状态仍保留原版磁盘协议。卷纲使用 `outline_view.py --unit` 定点读取。

## DPO 正文闭环
1. `tracking_commit.py check` 与 DPO 细纲校验；缺输入停止并修复，不绕过。
2. 从实际追踪、上一章结尾、当前卷纲单元和必要设定准备本章上下文；若细纲状态与权威追踪冲突，先修纲。
3. `scripts/build_dpo_prompt.py --project {书目录} --chapter N --out`，主会话审核并补齐必要相关事实，确保四段式输入不丢失边界。
4. `narrative-writer` **默认整章一次生成**，写入本章书内工作目录的临时草稿文件（文件名 dpo_draft.md），不得直接改追踪或正文权威。
5. 主会话保存正式正文，执行 `storyctl.py chapter check`，修复 blocking、人工判断 advisory；`tracking_commit.py draft` 和 `storyctl.py chapter commit` 成功才完成。
6. 报告正文字数、已兑现剧情和追踪结果；无作者授权不写下一章。

> **新增物三级**（规划和写作共用）：
> - **直接写**：微动作、过场、一次性路人、短对话和环境细节，不改变承诺与设定；无需记录。
> - **写了要报**：具名角色、复用的地点属性、势力、能力形态、关系变化、伏笔与跨章承诺，向主控申报并登记。
> - **先问作者**：新主线或反转、金手指规则、境界上限、真相与伏笔结算、收益归属、卷级底牌与已定决策冲突；未确认不得写。
>
## 原版系统保留的价值
- `story-setup` 部署 Agents/Hooks，`story-long-analyze` 做对标拆解。
- `storyctl.py` 质量检查、`tracking_commit.py` 权威事务、`追踪/上下文.md` 长篇续接状态继续有效。
- 新的 DPO 细纲必须同步适配原版各检查工具、跨 Skills 引用与自动部署；遇到旧协议不兼容视为待修缺陷，禁止跳过门禁。

## 模型卡
https://huggingface.co/JiangLing-js/Qwen3.8-27B-Chinese-Xuanhuan-Novel-Writer-DPO
模型卡示例的 System Prompt 为「你是一名中文长篇小说写作助手，只输出小说正文。」；User 使用四段式 `〖人物状态〗`、`〖前情〗`、`〖事件骨架〗`、`〖写作要求〗`。本 Skill 是 Claude Code 宿主交接，模型实际 wire-format 不能仅凭文字配置假定等同模型卡；必须实测。
