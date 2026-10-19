---
name: story-write
version: 1.0.0
description: "纯正文生成（机器门控）+ 作者终审一级留痕：复用 story-long-write 的 DPO 管线与场景拆分/合并，去掉逐场人工审阅 JSON，生成后交付合并整章草稿与机检报告给作者；作者直接在正文改稿，author_final 步骤把模型原稿 vs 作者终稿的 diff 落盘并登记为 provenance 基线。"
metadata: {"openclaw":{"source":"story-long-write 拆分出的纯生成 + 作者终审阶段"}}
---
# story-write｜纯正文生成 + 作者终审留痕

## 职责边界
- **只做正文生成与作者终审留痕**，不规划、不出细纲、不提交追踪（Tracking Commit 仍由 `story-long-write` 的 commit 路径完成）。
- 复用 `story-long-write` 的全部脚本（`chapter_pipeline.py` 准备、`scene_handoff.py` 场景拆分/合并、`scene_repair.py` 局部修订、`storyctl.py` 质量门、`dpo_evidence.py` 证据归档），不复制、不改写场景拆分与合并逻辑，保证与旧管线逐字一致。
- **交付物必须落在 `正文/` 目录**：草稿生成通过后，立即把 `dpo_draft.md` 复制为 `正文/第NNN章_章名.md`（与既有章节文件同一目录、同一命名口径），再向作者报告。作者终审改稿直接在 `正文/` 文件上做；`.story/work/第NNN章/dpo_draft.md` 只是工作稿，不能作为交付物路径。
- 与 `story-long-write` 的关键差异：**逐场只跑机器门控**（模型名、finish_reason、字数区间、重复段、结尾三词匹配），事实自动提取，**不再要求逐场人工审阅 JSON**；作者改为在合并后的整章草稿上做严控审阅与手动改稿。
- **作者终审是流水线一级**：作者改稿后跑 `author_final.py`，它冻结模型原稿 `dpo_draft.md`、导出「模型原稿 vs 作者终稿」diff 到 `.story/dpo-evidence/第NNN章/`、把作者终稿登记为 provenance 基线。此后 `story-long-write` 的 commit 以作者终稿为比对基准，模型原稿归档留痕。

## 路由
| 作者意图 | 执行 | 停止条件 |
| --- | --- | --- |
| 写第N章（纯生成） | `references/write-flow.md` 全流程 | 交付合并整章草稿 + 机检报告后停，交给作者审阅 |
| 作者改稿完成 | 跑 `scripts/author_final.py`（见 `references/author-final.md`） | 登记基线 + 导出 diff 后停，提示走 story-long-write commit |

裸调用无具体意图时只诊断当前书状态，不启动生成。

## 与 story-long-write 的分工
1. `story-write`：prepare（复用 `chapter_pipeline.py --prepare-only`）→ 场景计划 → **机器门控逐场生成 + 自动修订** → 合并 + 确定性标点 + 全章机检 → **交付草稿 + 机检报告，停**。
2. 作者：读整章草稿，严控审阅，直接在 `正文/第NNN章_章名.md` 手动改稿。
3. `story-write`：`author_final.py` 冻结原稿、导出 diff、登记作者终稿为基线。
4. `story-long-write`：`storyctl.py chapter check`（此时 provenance 门比对作者终稿基线）→ Tracking Draft/Commit → 证据归档（含 `author_diff.md` 与冻结的 `dpo_draft.md`）。

## 新增物三级（与 story-long-write 共用）
- **直接写**：微动作、过场、一次性路人、短对话与环境细节；无需记录。
- **写了要报**：具名角色、复用地点属性、势力、能力形态、关系变化、伏笔与跨章承诺；向主控申报并登记。
- **先问作者**：新主线/反转、金手指规则、境界上限、真相与伏笔结算、收益归属、卷级底牌冲突；未确认不得写。

## 模型卡
https://huggingface.co/JiangLing-js/Qwen3.8-27B-Chinese-Xuanhuan-Novel-Writer-DPO
System 基线「你是一名中文长篇小说写作助手，只输出小说正文。」；User 四段式 `〖人物状态〗`、`〖前情〗`、`〖事件骨架〗`、`〖写作要求〗`。采样 temperature 0.85 / top_p 0.90 / top_k 40 / min_p 0 / repeat_penalty 1.05 / enable_thinking=false；单场输出预算 min(6500,2600) tokens（工程设置，非模型卡值）。

## 部署与兼容
- 依赖 `story-long-write` 已部署（脚本以相对路径 `../story-long-write/scripts` 导入）。
- 每本书管线有进程锁，禁止并发覆盖 Prompt 和草稿。
- PowerShell 直接执行 `python "脚本路径" --project "书目录" --chapter N`，不要套 `pwsh -Command`。
- 本 Skill 不注册额外 Agent；生成由脚本直接调用本地 DPO 服务，主会话不代写正文。
