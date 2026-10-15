# DPO-only narrative-writer 执行协议

## 唯一正文写手
调用入口是 `claudeqwen` 中的 `/story-long-write 写第N章`；子 Agent `narrative-writer` 配置 `model: inherit`，继承主会话已连接的 Qwen 27B 玄幻 DPO 模型。禁止原版 solo/direct（主会话代写）的正文回退；子 Agent 不存在或路由未验证时须停止报告。

## 写作输入
主会话运行 `build_dpo_prompt.py --project {书目录} --chapter N --out`，产出 `.story/work/第NNN章/dpo_prompt.json`，包含 `system`、`user`、`source_outline`、`writer_mode`。仅向写手交付四段式 user；System 基线：`你是一名中文长篇小说写作助手，只输出小说正文。`。

**注意 Claude Code 子 Agent 自带宿主系统指令**：`model: inherit` 与「写手消息遵循模型卡」不是完全相同的 system/user wire-format。本机验收需要检查子 Agent 真实请求模型/LoRA、工具调用和正文质量。

## 默认整章一次成文
只调用一次写作子 Agent 生成整章；不使用原版前组/后组 checkpoint。严重截断或未完成时落临时文件，停止提交，按作者确认/受控重写处理，禁止默默改成别的模型。

写手只操作指定临时正文文件；不得修改 `大纲/`、`设定/`、`追踪/`。主会话负责最终正文文件、质量门禁与追踪提交。
关闭 Thinking（如果本地代理允许），采样参数以模型卡给出的示例作为首轮调试参考，实际参数以本地推理服务支持为准。
