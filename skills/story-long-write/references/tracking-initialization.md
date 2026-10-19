# 追踪初始化事务

## 初始化事务

新书从第 0 章初始化：把下面的 JSON 写到 `{书目录}/.story/work/init.json`，先按本书设定补足当前核心角色状态，再跑 `{PYTHON} {skill 根}/scripts/tracking_commit.py init --project "{书目录}" --input "{书目录}/.story/work/init.json"`；成功后删除临时文件。不要在嵌套的 `pwsh -Command "..."` 中写 `$dir`：外层可能提前展开它。`story-import` 导入已有小说时把最后完整章写入 `last_chapter=N`；第 1..N 章不伪造日更记录，常规续写从 N+1 章开始。

```json
{
  "schema_version": 1,
  "book_title": "让你管账号，你高燃混剪炸全网",
  "last_chapter": 0,
  "context": {
    "position": {
      "volume": "第一卷·军宣整顿",
      "volume_start_chapter": 1,
      "story_time": "江晨到火箭军文工团报到前",
      "scene": "火箭军文工团"
    },
    "long_term_constraints": ["军宣爽点要用作品效果和围观反应链兑现，不能只靠系统播报"],
    "active_character_names": ["江晨"],
    "continuity_risks": [],
    "recent_chapters": [],
    "next_chapter_commitments": ["让江晨报到，并落下五天百万粉的新手任务"]
  },
  "character_snapshots": {
    "江晨": {
      "identity": "新到任的文工团创作者",
      "location": "火箭军文工团报到处",
      "goal": "完成报到并确认新手任务",
      "state": "尚未正式报到",
      "abilities_resources": ["会制作混剪视频"],
      "relationships": [],
      "knowledge": ["知道自己即将入职"],
      "open_threads": ["五天百万粉任务尚未开始"]
    }
  },
  "foreshadow": [],
  "timeline_events": []
}
```

导入初始化时直接传入当前核心角色快照、伏笔当前行、时间线事件和固定 7 栏状态输入。阶段/卷级回看按需查询正文，不作为每章强一致追踪产物。

`character_snapshots` 的键必须是人物名；`identity`、`location`、`goal`、`state` 为非空文字；`abilities_resources`、`relationships`、`knowledge`、`open_threads` 为文字列表，可为空数组。`active_character_names` 中每个人物都必须有快照。不要使用“身份、能力、境界”等中文字段名，也不要为省事删掉真实在场的核心角色。第 0 章的 `foreshadow` 和 `timeline_events` 留空；本章发生后再正式登记。
