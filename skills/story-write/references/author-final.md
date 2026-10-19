# 作者终审（流水线一级）+ diff 留痕

作者改稿不是事后补丁，而是流水线内的一级步骤：模型原稿冻结，作者终稿成为 provenance
基线，每章自动导出「模型原稿 vs 作者终稿」diff 供后续统计（常改什么 → 反哺细纲与 DPO 偏好）。

## 前提
- `write_draft.py` 已跑出 `ready`，`dpo_draft.md` 存在（模型原稿）。
- 作者已在 `正文/第NNN章_章名.md` 完成严控审阅与手动改稿（与模型原稿不同）。

## 执行
```
python "{story-write 根}/scripts/author_final.py" --project "{书目录}" --chapter N
```

它做四件事：
1. **冻结模型原稿** `dpo_draft.md`，读取作者终稿 `正文/第NNN章_章名.md`。两者必须不同（逐字一致返回 `unchanged`）。
2. **导出 diff**：unified diff 写到 `.story/dpo-evidence/第NNN章/author_diff.md`；改动统计（删/增行数、按标点修正/短删/改写的分类、原/终字数）写到 `author_stats.json`。这是后续 DPO 偏好统计的原始数据。
3. **登记 provenance 基线**：`work/author_final.json` 含 `model_original_sha256`、`author_final_sha256`、`diff_sha256`、stats。
4. **复检**：对作者终稿跑确定性标点归一化 + `check_blocking_quality` + 全章字数 ±15%，结果写 `author_final_report.json`。

## 之后
- 走 `story-long-write` 的 commit 路径：`storyctl.py chapter check` → Tracking Draft/Commit。
  - provenance 门（`storyctl._check_dpo_provenance`）检测到 `author_final.json` 时，比对正文 = 作者终稿（而非模型原稿）；模型原稿仍按生成报告校验并归档。
  - 证据归档（`dpo_evidence.archive_work`）同时保留冻结的 `dpo_draft.md` 与 `author_final.json`，`author_diff.md`/`author_stats.json` 在 `.story/dpo-evidence/第NNN章/` 下随章留存。
- 报告作者：终稿字数、quality、diff 路径、基线已登记；可继续下一章或提交。

## 改动边界（建议，供作者审阅时把握）
- **自由改**：表达、句式、节奏、标点、对话措辞、细节描写。
- **少改**：剧情事实（谁做了什么、谁在场、境界/物资/地点状态）。若确需改剧情事实，在追踪事务（delta/timeline）里登记该裁定，避免下一章按旧事实承接。
- 每章 diff 会自动记录实际改动，长期统计可识别作者系统性偏好（如常删某类过渡句、常改某类对话），反哺细纲写法与 DPO 训练偏好。
