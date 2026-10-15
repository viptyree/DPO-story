# DPO-story

**基于 [Oh Story](https://github.com/zenstory-ai/oh-story-claudecode) 的玄幻长篇小说 DPO 专用改造版。**

> **当前阶段：本地试运行 / 待完整验收。** 核心 DPO 细纲与 Prompt 编译专项测试已通过，但不能据此保证所有原版 Skills、Hooks 和 Windows 本地推理链路都能正常工作。请先在测试书目验证，不要直接覆盖已有正式作品。

## 项目定位

DPO-story 保留 Oh Story 的文件式长篇管理思路（设定、大纲、正文、追踪、质量检查），调整**玄幻长篇正文**的生产链路：

| 工作 | 执行者 | 主要职责 |
| --- | --- | --- |
| 对标拆解、世界观、人物、力量体系、全书/卷纲、细纲 | **Codex（GPT-6）** | 决定剧情逻辑与章节事件，不负责正式正文 |
| 写作流程编排与质量/状态门禁 | **Claude Code 主会话（本地命令 `claudeqwen`）** | 读文件、校验细纲、准备写作材料、调用子 Agent、验收与追踪提交 |
| 唯一正式正文写手 | **`narrative-writer` 子 Agent** | `model: inherit`，预期继承 `claudeqwen` 连接的本地玄幻 DPO LoRA；默认一次生成完整一章 |

设计针对 **Qwen3.8-27B + 玄幻写作 DPO LoRA** 的本地推理环境。**本仓库不包含模型权重、LoRA 权重、推理服务器、Claude Code 或 Codex；安装本项目不会自动部署模型。** 用户必须自行配置可用的本地模型 API 和 `claudeqwen` 命令。

### 与原版 Oh Story 的主要差异

- 长篇细纲：用内嵌的 DPO 四段式结构**替代原版九字段和五段式**，不维护双标准或单独的 DPO 场景卡。
- 正文：默认**整章一次生成**，不再把前组/后组分段写作作为默认做法。
- 模型职责：Codex 规划，`narrative-writer` 写正文；若无法确认使用本地 DPO LoRA，禁止自动由其他模型代写。
- 工程状态：尽可能继续使用原版的 `storyctl.py`、`tracking_commit.py`、追踪文件与质量门禁。

**重要限制：** Claude Code 的 `model: inherit` 不等于直接对模型 API 发出完全纯净的 System/User 两条消息；是否真的继承本地模型及加载的 LoRA 必须检查本地推理服务日志并实际运行验证。

## Windows 安装与试运行

### 1. 克隆本仓库

使用 PowerShell：

```powershell
cd D:\novel
git clone https://github.com/viptyree/DPO-story.git
cd .\DPO-story
git branch --show-current
```

正常应显示 `main`。建议电脑已安装 `git`、Python 3 和 Node.js，以运行检查脚本。另需自行安装、配置 Codex CLI、Claude Code CLI 及本地 DPO 模型服务。

### 2. 先运行无需模型的基础测试

从本仓库根目录执行：

```powershell
python -m unittest discover -s tests -p test_dpo_only_smoke.py -v
node --check skills/story-long-write/scripts/check-outline-contract.js
python -m py_compile skills/story-long-write/scripts/build_dpo_prompt.py
```

这些是**核心代码烟雾测试**，不是完整小说生产流程测试。即使通过，也仍需验证模型继承、正文落盘、Tracking Commit 与连续章节。

### 3. 安装 Skill 并部署写作项目

本仓库代码与用户小说工程应分开。推荐通过 Skills CLI 安装**这个 Fork**（不要误装上游版本）：

```powershell
npx skills add viptyree/DPO-story -y -g
```

进入**小说项目根目录**后启动对应的 Claude Code / Codex 会话，使用 `/story-setup`（Codex 环境通常为 `$story-setup`）部署项目所需的 Agent、Hooks 和参考文件。部署完成后**关闭并重新启动 Claude Code 会话**，否则新的子 Agent 可能尚未注册。

如果部署器提示引用旧上游路径、模板不存在、已有配置冲突或权限不符，请保留错误输出并停止，不要手工覆盖现有 `.claude` 配置。安装与部署细节参见 [story-setup](skills/story-setup/SKILL.md) 和 [Claude Code 部署说明](skills/story-setup/references/deploy-claude-code.md)。

### 4. Codex 负责生成 DPO 细纲

在你的小说工程目录：

```powershell
cd "D:\novel\你的测试小说"
codex
```

示例任务：

```text
按照本书设定与卷纲，使用 DPO-story 的 story-long-write 细纲协议，
为第一卷生成第1章的 DPO 专用细纲。
只生成细纲，不写小说正文；生成后运行细纲结构校验。
```

新细纲保存于 `大纲/细纲_第001章.md`。其标准章节结构如下：

```md
# 第1章：示例章名

## 章节控制
- 所属卷：第一卷
- 剧情单元：L1-01
- 字数目标：2500
- 字数口径：visible_chars_v1
- 视角：第三人称紧贴主角
- 章节目标：...
- 目标情绪：...
- 章尾停笔点：...

## 〖人物状态〗
当前境界、位置、行动目的、人物关系与信息差。

## 〖前情〗
已发生的事实、当前困境、必须衔接的情节。

## 〖事件骨架〗
1. 谁做出什么具体行动。
2. 对手怎样反应。
3. 主角作出什么取舍、付出什么代价。
4. 本章推进到哪个明确结果。

## 〖写作要求〗
叙述视角、重点画面、节奏要求、禁止提前透露的设定与停笔位置。

## 长篇追踪约束
本章允许改变的状态、必须继承的事实、伏笔边界和下一章承诺。
```

准确的权威格式见 [DPO 细纲协议](skills/story-long-write/references/dpo-outline-contract.md)。

可以先在 PowerShell 中校验细纲：

```powershell
node "D:\novel\DPO-story\skills\story-long-write\scripts\check-outline-contract.js" --json --project "D:\novel\你的测试小说" --chapter 1
```

### 5. claudeqwen 负责写小说正文

先确保本地推理服务器已加载基础模型和 DPO LoRA，且 `claudeqwen` 指向该服务；**仓库不会创建 `claudeqwen` 命令**。

```powershell
cd "D:\novel\你的测试小说"
claudeqwen
```

在 Claude Code 中输入：

```text
/story-long-write 写第1章
```

预期流程：

1. 检查追踪状态和第 1 章 DPO 细纲。
2. 运行 `build_dpo_prompt.py`，编译四段式写作材料并核对前情。
3. 调用 `narrative-writer`，尝试使用**当前本地模型**生成整章正文。
4. 输出临时草稿，检查文本完整性及质量。
5. 通过后写入 `正文/`，执行追踪事务并确认提交成功；失败则保留草稿，不伪报成功。

**注意：** 对没有追踪状态的新书，应先运行 `story-setup` / 正规开书初始化流程。直接运行 Prompt 编译器并不会自动补建完整追踪状态。

## 主要目录与工具

| 路径 | 作用 |
| --- | --- |
| [`skills/story-long-write/SKILL.md`](skills/story-long-write/SKILL.md) | DPO 专用长篇工作流入口 |
| [`references/dpo-outline-contract.md`](skills/story-long-write/references/dpo-outline-contract.md) | 唯一 DPO 细纲格式 |
| [`scripts/check-outline-contract.js`](skills/story-long-write/scripts/check-outline-contract.js) | 细纲结构校验 |
| [`scripts/build_dpo_prompt.py`](skills/story-long-write/scripts/build_dpo_prompt.py) | 四段式 Prompt 编译、追踪读取及上一章结尾衔接 |
| [`narrative-writer.md`](skills/story-setup/references/templates/agents/narrative-writer.md) | Claude Code 专用正文子 Agent 模板 |
| [`scripts/migrate_legacy_outline.py`](skills/story-long-write/scripts/migrate_legacy_outline.py) | 原版细纲迁移辅助 |
| [`tests/test_dpo_only_smoke.py`](tests/test_dpo_only_smoke.py) | DPO 专项烟雾测试 |
| [`docs/DPO-ONLY-MIGRATION.md`](docs/DPO-ONLY-MIGRATION.md) | 改造记录与未完成的兼容性事项 |

旧细纲迁移默认**仅预览，不修改文件**：

```powershell
python "D:\novel\DPO-story\skills\story-long-write\scripts\migrate_legacy_outline.py" "D:\novel\你的测试小说\大纲\细纲_第001章.md"
```

人工检查预览无误后，才可以选择 `--write`。工具会创建 `.before-dpo.bak` 备份，并保留需要作者判断的占位内容；**转换后仍需人工审核，不保证自动可写**。

## 当前已知限制与测试状态

- ✅ DPO 专项结构与 Prompt 烟雾测试已有通过记录。
- ✅ Claude Code / OpenCode 等部分 Agent 模板兼容测试已有通过记录。
- ⚠️ 原版部分跨平台回归、发布检查仍有未通过项；不能宣称整套 Oh Story 已完全兼容新版细纲。
- ⚠️ 写作前的人物、伏笔、境界、卷纲事实一致性仍需主控核验，不是全自动语义判定。
- ⚠️ `model: inherit` 是否确实到达本地 DPO LoRA，需要在 Windows 上观察本地推理日志。
- ⚠️ 全章生成、字数门禁、正式追踪提交、三章连续写作、重开会话续写尚需真实环境完整验收。
- ⚠️ 旧版九字段细纲与新 DPO 格式**不互相兼容**。

建议先用一部**全新测试书**跑通第 1 章，再测试第 2–3 章和断点续写。出现错误时附上命令、终端输出、相关章节细纲以及不含密钥的本地推理服务日志。

## 致谢与许可证

本项目是在 [zenstory-ai/oh-story-claudecode](https://github.com/zenstory-ai/oh-story-claudecode) 基础上的个人 DPO 写作工作流改造，并非 Oh Story 官方版本。感谢原项目作者和社区的工作。

代码许可沿用仓库的 [MIT License](LICENSE)。有关原版的其他能力和使用说明请参考上游项目；本 README 优先描述 **DPO-story 当前实际的玄幻长篇写作流程**。
