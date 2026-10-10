# 独立仓库发布手册

**注意：** 当前 GitHub 连接器没有创建仓库的 API 操作，新仓库必须先由仓库所有者在 https://github.com/new 建立。不要初始化 README、LICENSE 或 .gitignore（避免首次推送冲突）。

建议新仓库：`viptyree/oh-story-xuanhuan`，先设为 Private，测试通过后再公开。

## 从原 Fork 导出子目录的独立历史（Windows PowerShell）
```powershell
git clone https://github.com/viptyree/oh-story-claudecode.git
cd oh-story-claudecode
git fetch origin feature/fanqie-xuanhuan
git switch -c feature/fanqie-xuanhuan origin/feature/fanqie-xuanhuan
git subtree split --prefix=experimental/oh-story-xuanhuan -b xuanhuan-standalone
git remote add standalone https://github.com/viptyree/oh-story-xuanhuan.git
git push standalone xuanhuan-standalone:main
```

完成后，独立仓库根目录就是 `skills/`、`tests/`、`docs/`。如有已有同名本地仓库，需先核对目录、remote 和本地修改，不能直接覆盖。

## 测试
```powershell
git clone https://github.com/viptyree/oh-story-xuanhuan.git
cd oh-story-xuanhuan
py -3 -m unittest discover -s tests -v
```

## 发布状态
- **0.1.0-alpha**：两份独立的 Skill 入口与玄幻提示规则，静态契约测试；不等于独立可用的完整运行时。
- 尚未封装原版 `storyctl.py` / `tracking_commit.py` 的依赖，也尚未验证两个宿主和旧书互操作。
- 不建议作为生产版取代原版 Oh Story 的追踪提交流程。
- 通过完整项目测试之后再考虑使用正式版本号及公开 Release。
