# DPO-only 单章正文 SOP

版本：2.1.0-dpo。沿用 oh-story 的主控、专用写手、审查和追踪闭环。适用于 Claude Code / claudeqwen 的 `/story-long-write 开始写第一章`、`写第N章`。`narrative-writer` 内部通过脚本请求本地 DPO LoRA；新细纲以 `dpo-outline-contract.md` 为准。

1. 从 `.active-book` 识别书目录与章号。执行 `python "{skill 根}/scripts/chapter_pipeline.py" --project "{书目录}" --chapter N --prepare-only`，展示版本 `2.1.0-dpo` 和脚本路径。该命令统一检查服务实际模型、唯一启用的 DPO LoRA、追踪及细纲，并构建 Prompt；避免主会话手拼校验和初始化命令。
2. 若返回 `stage=tracking_init`，按报告中的模板及 `tracking-initialization.md` 填完整核心角色快照，然后加 `--init-input "{init.json}" --prepare-only` 再运行。脚本一次报告快照错误；不允许删掉核心人物绕过校验。已有正文却丢状态时按 `stop-and-fix.md` 恢复，不能新建第 0 章状态。
3. 若其他校验失败，按明确错误修复后再准备，不绕过。Windows PowerShell 直接调用 `python` 并逐项传参，路径用引号；不要在 `pwsh -Command "...$dir..."` 内嵌另一层 PowerShell。
4. 完整读取细纲、`追踪/上下文.md`、必要角色/力量体系/伏笔、上一章末尾；用 `outline_view.py --unit` 取当前卷纲单元。按 oh-story 的必读设定槽筛出时代、制度和资源事实：若准备报告为 `context_prepare`，按模板写工作目录 `dpo_context.json`，字段为 `schema_version:1` 和 `setting_excerpts` 列表，每项只含 `source`（本书设定相对路径）与 `text`（原文摘句），再运行准备命令。每条最多600字、合计最多2000字；不转交未来真名、幕后秘密和未发生进展。核对四段式里实际收到的事实、情节点、章尾、禁释信息和字数。
5. 发现事实冲突先修规划；不把长篇秘密整段塞进正文 Prompt，也不向主会话索取正文。核对人物关系、物件归属、开场与结束状态、既往经历和行动动机；角色卡与细纲不同不能静默删掉作者新增设定，先确认版本依据。已在中段揭示的信息，章尾应推进选择或后果，避免重新“发现”。
6. 按 `agent-calls.md` 把已审核的 Prompt 交给 `narrative-writer`。写手只运行 `chapter_pipeline.py --project "{书目录}" --chapter N --generate-prepared`，脚本保留主控审过的输入且核对准备后细纲与追踪未变。写手注册由 `claudeqwen` 显式注入保障；运行时仍缺失则报告注册错误，不让主会话代写。
7. 按 `scene-handoff.md` 审核分场计划，每次调用只生成一场。awaiting_scene_review 时主控通读正文，按情节点、事实、连续性与结束状态填写有原句依据的审阅，再交写手继续；不需要作者逐场批准。局部错误按 `scene-repair.md` 提交事实要求，由同一本地模型修订后重审。其他 blocked 报告“细纲要求→实际原句→问题”并停止。不得自动认定完成、擅改字数、主控拼补或盲重试。

   视角或物件持有状态难以判定时，可运行 `python "{skill 根}/scripts/base_scene_critic.py" --project "{书目录}" --chapter N`。仅此审稿请求关闭同一LoRA，正文和局部替换仍用非零DPO，不改全局配置或另加载模型。读取 dpo_scene_critic.json，确认原稿指纹一致并核对原句；它可能漏报或误报，只辅助审阅，不自动放行，不代写或提交Tracking，也不能推翻字数和剧情门禁。
8. `dpo_report.json` 的 `ready` 只是机器初筛。主会话还须逐场阅读 dpo_draft.md，核对每个情节点有没有提前发生、重演或缺失，并核对人物、衣物、伤口、地点、物件、时间和章尾是否前后一致；发现冲突即报告并结束本轮，不复制到正式正文。内容通过后才能**原样复制**至 `正文/第NNN章_章名.md`，不得用主会话补写章尾、扩写或创建自己的草稿；执行 `storyctl.py chapter check --project {书目录} --chapter N`，不要加 `--fix-punctuation`。检查器逐字核对正式正文与本地 DPO 草稿，核对报告及 Prompt 指纹。blocking、字数不达标或章尾缺失时停止提交；`tool_unavailable` 禁止提交。
9. 沿用 oh-story 写后核对：章尾钩子、爽点与契约四问（主角是否靠选择挣到结果、收益归属是否合理、是否提前动用底牌、旧期待是否有兑现）；扫描工程词；审查新增物三级和检测建议。需要正文修改时只能交回本地 DPO 修订，主控不代写。通过后运行 `tracking_commit.py draft --project {书目录} --chapter N`，按脚本预填格式登记本章实际角色、伏笔、地点与时间线；`storyctl.py chapter commit --project {书目录} --chapter N --input {工作目录}/tracking.json` 返回 `tracking_committed: true` 才算完成。
10. 汇报章节、字数、检查结果和状态提交情况；只写作者明确要求的章节。

DPO提交前脚本自动验证并复制本章工作证据到 `.story/dpo-evidence/第NNN章/`，提交成功后发布 current.json，再清理原临时目录。归档失败不提交；提交后发布失败则保留工作目录并报告。后续检查使用归档核对正文，不因工作目录已清理而当作旧格式。归档证明来源，不能代替内容审阅。

本流程不废除原版追踪状态格式及事务安全规则。若原版验证器或其他工具因旧细纲字段出错，属于兼容缺陷，必须修复，**不得临时绕过**。

## 向作者汇报（按实际情况选一种）
已经收到模型正文但检查失败时使用“草稿已生成，但未通过”的模板；“写作未开始”仅用于模型调用前的服务或输入错误。
<!-- author-report -->
```md
第{N}章《{标题}》已经完成，约{实际字数}字。
本章完成了：{主要事件及结尾}。已检查细纲与连续性，追踪提交成功。
```
<!-- author-report -->
```md
第{N}章草稿已生成，但质量门禁没有通过：{阻塞项}。
草稿已保留，没有提交追踪。请先修复上述问题。
```
<!-- author-report -->
```md
第{N}章写作未开始：本地 DPO 服务或输入校验未通过，原因：{实际错误}。
当前管线：{版本}，脚本：{路径}。
```
<!-- author-report -->
```md
第{N}章正文约{实际字数}字，目标为{字数范围}，不在接受范围内。
你要保留当前长度、调整细纲/目标后重写，还是放弃本章？未选择之前不提交追踪。
```
