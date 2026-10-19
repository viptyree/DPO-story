# story-write 纯生成流程（机器门控）

目标：把「写正文」从 `story-long-write` 里拆出来独立跑，逐场只用确定性机器信号推进，
不要求逐场人工审阅 JSON；生成完交付合并整章草稿 + 机检报告，交作者审阅。

## 前置
- 细纲已就绪：`大纲/细纲_第NNN章.md` 含 `章节控制`、`〖人物状态〗`、`〖前情〗`、`〖事件骨架〗`、`〖写作要求〗`、`长篇追踪约束`。
- 追踪状态已初始化（`追踪/上下文.md` 各栏目齐全）。
- 本地 DPO 服务在线（默认 `http://127.0.0.1:8088`），已加载 `qwen3.8-27b-udq4-xuanhuan-dpo` LoRA。
- Node.js 可用（确定性标点/质量检查需要）。

## 步骤
1. **准备**（复用 story-long-write 的 chapter_pipeline）：
   ```
   python "{story-long-write 根}/scripts/chapter_pipeline.py" --project "{书目录}" --chapter N --prepare-only
   ```
   产出 `.story/work/第NNN章/dpo_prompt.json` 与准备指纹。返回 `tracking_init` 时按模板填完角色状态再 `--init-input` 重跑；返回 `context_prepare` 时把本章必需设定原文摘句写入工作目录 `dpo_context.json`（schema_version:1，setting_excerpts 每项仅 source 相对路径 + text 原文）后重跑。审核 `dpo_prompt.json`，冲突先修规划。

2. **场景计划**（2..6 场，拆分/合并逻辑与旧管线完全一致）：
   生成 `.story/work/第NNN章/dpo_scene_plan.json`，字段同 story-long-write `scene-handoff.md`：
   `schema_version:1`、`prompt_sha256`（= dpo_prompt.json 的 sha256）、`scenes` 数组。
   每场含 `start_state`、`end_state`、`target_chars`（250..1600，合计=全章目标）、`beats`（按序覆盖全部细纲情节点 id+action）；可选 `character_states`/`context_quotes`/`requirements`/`sampling`/`lora_scale`。
   `load_plan` 会严格校验（情节点按序全覆盖、字数合计相等、采样参数范围）。

3. **机器门控逐场生成 + 自动修订 + 合并**：
   ```
   python "{story-write 根}/scripts/write_draft.py" --project "{书目录}" --chapter N
   ```
   - 每场一次 LLM 往返；推进只看机器信号：模型名匹配、finish_reason=stop、本场字数在目标 65%..150%、无重复段（80 字窗口/24 字句）、末场结尾三词匹配 ≥0.3。
   - 事实自动提取（end_state 回显 + beat 回显 + 末 300 字实质句）并注入下一场 prompt，保留旧管线的逐场事实承接，但不再需要人工写 established_facts。
   - 机械性错误（篇幅偏离/重复段）自动触发局部修订（复用 `scene_repair.requested_repair`），每场最多 2 轮；修订仍走本地模型，不手补正文。
   - 硬错误（模型/finish 不符）保留失败稿并 blocked 停止，不盲重试。
   - 全部场景通过后合并为 `dpo_draft.md`，跑确定性标点归一化 + `check_blocking_quality`（AI 句式、退化、标点、细纲照搬）+ 全章字数 ±15%。
   - 报告 `dpo_report.json`：status ready/blocked、各场 chars/repair_rounds/errors/facts、quality、draft_sha256。

4. **交付，停**：
   - **先把 `dpo_draft.md` 复制为 `正文/第NNN章_章名.md`**（与既有章节文件同一目录、同一命名口径），交付物必须在 `正文/` 目录里，不能只留在 `.story/work/`。
   - 向作者报告：章节、`visible_chars_v1` 字数、各场机检与修订情况、quality 结果、`正文/` 文件路径。
   - 提示作者：在 `正文/第NNN章_章名.md` 做严控审阅与手动改稿；改完跑 `author_final.py`（见 `author-final.md`）。
   - **不提交追踪**；无作者授权不写下一章。

## 与旧管线的差异（仅此处不同，其余逐字一致）
- 旧：逐场生成 → 主控近读 → 手写证据 JSON（completed_beats/canon/continuity/ending/established_facts，逐句 verbatim）→ 机器校验 → 通过才承接下一场。
- 新：逐场生成 → **机器门控**（上列 5 项信号）→ 自动修订 ≤2 轮 → 自动承接；事实自动提取。
- 审阅责任后移到作者的整章严控审阅 + 手动改稿；`author_final.py` 的 diff 留痕记录作者实际改动。

## 失败处理
- `blocked`（机械性）：保留 `scene_gate/{plan_hash}/scene_NN*` 各场稿与 `dpo_report.json`，按报告 errors 修计划或重跑；不覆盖已生成稿。
- `blocked`（硬错误）：检查本地服务模型/LoRA/finish_reason，修正后重跑。
- 全章字数越界：作者可在终审时接受当前长度（commit 时 `--force` / accept-current-length）。
