# DPO-only narrative-writer 执行协议

## 唯一正文写手
沿用 oh-story：主控准备与验收，`narrative-writer` 生产正文。调用入口是 `claudeqwen` 中的 `/story-long-write 写第N章`；写手配置 `model: inherit`，主会话使用 Qwen3.8 27B UD Q4_K_M + DPO LoRA、128K、vision off。启动器显式注册项目写手；主会话不代写。

## 写作输入
主会话运行 `chapter_pipeline.py --project "{书目录}" --chapter N --prepare-only`，产出 `.story/work/第NNN章/dpo_prompt.json` 和准备指纹。输入含 `system`、`user`、`source_outline`、`writer_mode`；主控照 oh-story 做上下文筛选与事实审阅。`generate_dpo_draft.py` 只将严格的 System/User 两条消息发给本地服务；System 基线：`你是一名中文长篇小说写作助手，只输出小说正文。`。

Claude Code 子 Agent 仍继承本地模型，但它只负责执行生成脚本；实际正文请求由脚本直接发送模型卡的 System/User wire-format。本机验收仍需检查服务实际加载了 DPO LoRA 和正文质量。

## 逐场生成与交接
主控按 `scene-handoff.md` 准备计划。写手运行 `chapter_pipeline.py --project "{书目录}" --chapter N --generate-prepared`，每次最多一场。awaiting_scene_review 返回主控核验，不能由写手自批；审阅通过后再调用同一命令。局部错误按 `scene-repair.md` 交回本地模型，修订后重审。所有场景通过才拼章，检查全章字数及原版正文规则。其他 blocked 保留失败稿，不盲重试。无计划整章模式仅保留兼容实验，自动均分停用。

写手只运行指定生成脚本；不得修改 `大纲/`、`设定/`、`追踪/`。主会话负责原样复制最终正文文件、质量门禁与追踪提交；不得自己补正文。
显式发送 `chat_template_kwargs.enable_thinking=false`；采样采用模型卡示例 temperature=0.85、top_p=0.90、top_k=40、repeat_penalty=1.05，并设 min_p=0，避免继承推理服务默认的额外截断。整章输出预算 6500 tokens 是本管线工程设置，不能说成模型卡推荐值。
