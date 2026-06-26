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

产品型号与编号空格规则
- Date: 2026-06-24
- Context: 用户 уточ明智能润色中的字母数字空格保留规则
- Category: 行为指令
- Instructions:
  - 产品型号内部连续字母数字保持连写，例如 `DNBelab-D4RS`
  - 编号与标题或术语之间保留空格，例如 `表1 DNBelab-D4RS`、`2.1 RNA`

大模型调用顺序
- Date: 2026-06-24
- Context: 用户指定项目内大模型优先级顺序
- Category: 行为指令
- Instructions:
  - 大模型调用顺序固定为 `Kimi > DeepSeek > ArkClaw`
  - 项目中移除 `Qwen` 及其 API Key 配置

审核模块改动范围约束
- Date: 2026-06-25
- Context: 用户要求本次优化仅处理审核模块稳定性
- Category: 行为指令
- Instructions:
  - 本次任务仅修改审核模块相关实现
  - 其他业务模块保持现状，除非用户明确要求联动修改

推送前需用户确认
- Date: 2026-06-25
- Context: 用户指出不要擅自推送代码到 GitHub
- Category: 工作流协作
- Instructions:
  - 未收到用户明确推送指令（如"推送"、"push"、"提交到GitHub"等），不得擅自执行 git push
  - 代码 commit 后等待用户下一步指示

当天更新提交推送规则
- Date: 2026-06-25
- Context: 用户要求今天所有更新内容均需提交并推送到 GitHub
- Category: 工作流协作
- Instructions:
  - 2026-06-25 当天，用户要求的所有代码或配置更新完成后，都需要提交并推送到 GitHub
  - 若推送因凭据或平台服务异常失败，需要保留本地提交并向用户说明阻塞原因
