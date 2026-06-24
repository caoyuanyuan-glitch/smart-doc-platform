# 用户指令记忆

本文件记录了用户的指令、偏好和教导，用于在未来的交互中提供参考。

## 格式

### 用户指令条目
用户指令条目应遵循以下格式：

[用户指令摘要]
- Date: [YYYY-MM-DD]
- Context: [提及的场景或时间]
- Instructions:
  - [用户教导或指示的内容，逐行描述]

### 项目知识条目
Agent 在任务执行过程中发现的条目应遵循以下格式：

[项目知识摘要]
- Date: [YYYY-MM-DD]
- Context: Agent 在执行 [具体任务描述] 时发现
- Category: [运维部署|构建方法|测试方法|排错调试|工作流协作|环境配置]
- Instructions:
  - [具体的知识点，逐行描述]

## 去重策略
- 添加新条目前，检查是否存在相似或相同的指令
- 若发现重复，跳过新条目或与已有条目合并
- 合并时，更新上下文或日期信息
- 这有助于避免冗余条目，保持记忆文件整洁

## 条目

每日启动前拉取最新代码并创建分支
- Date: 2026-06-17
- Context: 用户要求每天早上开始跑代码前提醒拉取最新 main 并创建新分支
- Category: 工作流协作
- Instructions:
  - 每日开始开发任务前，必须先执行 `git checkout main && git pull origin main`
  - 然后根据当天日期创建新分支，命名规范: `YYMMDD-(feat|fix|chore|refactor)-xxxxx-xxxx-xxxx`
  - 例如: `git checkout -b 260618-feat-polish-module`
   - 创建后 `git push -u origin <branch-name>` 推送到远端

每日17:50 推送所有修改
- Date: 2026-06-18
- Context: 用户要求在每天下午 17:50（北京时间 UTC+8）统一推送当天所有分支上的修改
- Category: 工作流协作
- Instructions:
  - 所有时间以北京时间为准 (TZ='Asia/Shanghai')
  - 白天可以随时 commit，但 push 全部等到 17:50
  - 17:50 时检查所有有本地 commit 的分支，逐分支 push
  - 格式: `git push origin <branch>`

前后端自验命令
- Date: 2026-06-24
- Context: Agent 在执行登录页、历史记录与问答优化任务时发现
- Category: 构建方法
- Instructions:
  - 前端构建校验使用 `cd /workspace/frontend && npm run build`
  - 后端语法校验使用 `cd /workspace/backend && python3 -m compileall app`
