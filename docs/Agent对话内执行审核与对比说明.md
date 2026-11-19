# Agent 对话内执行审核 / 对比 / 转换 · 实现说明

日期：2026-11-19　审核工具：WorkBuddy

## 一、需求与结论

用户提出：在聊天框说"帮我审核一个文件"并附文件，Agent 就应执行；对比同理，弹出 A/B 上传按钮后执行。

核查后确认用户判断正确——**之前"A 方案只能跳转"是实现取舍，不是技术限制**。改为在对话内真正执行。

## 二、交互设计

| 意图 | 交互 | 执行方式 | 历史留痕 |
|---|---|---|---|
| 审核 | 识别到 review → 对话内显示"选择待审核文件"按钮 → 上传后自动触发 | **异步**：上传→触发→进度卡片（1.5s 轮询）→完成推 issue 摘要 | →「审核任务」`/review/tasks` |
| 对比 | 识别到 compare → 显示"选择两个文件对比"按钮 → 选两个文件后自动对比 | **同步**：直接调同步对比接口，等结果回来显示差异摘要 | →「对比任务」`/compare/tasks` |
| 转换 | 识别到 convert → 选目标格式（Markdown/DITA/CSV）+ 选文件 → 触发 | **异步**：上传→触发→进度卡片（1.5s 轮询）→完成提示 | →「转换历史」`/convert/history` |

进度卡片展示：状态、百分比进度条、当前步骤、完成摘要、"查看完整报告/历史"跳转。失败可重试。

## 二·补 三类任务的历史留痕（用户追加需求）

用户要求：Agent 触发的审核/对比/转换必须出现在各自历史页面。核查结论：

- **审核**：`POST /review/{id}` 创建 Review，归属靠关联 `Document.user_id`；历史页 `GET /review/` 按同一 `Document.user_id` 过滤 → **天然可见**，无需改代码。
- **对比**：`POST /compare/` 经 `_do_single_compare` 落 `CompareTask.user_id`；历史页 `GET /compare/` 按 `user_id` 过滤 → **天然可见**，无需改代码。
- **转换**：原本 Agent 对 convert 只做"跳转落地页"，对话内不产生任务 → 历史页查不到（断点在"没落库"，非过滤）。本次把转换也做成对话内执行：调 `convertAPI.convert` → `POST /convert/` 落 `ConvertTask.user_id` → 历史页 `GET /convert/` 按 `user_id` 过滤可见。

三类任务都用各自**正常创建端点**，归属用户与页面手动触发完全一致，因此历史页自动可见，无来源过滤差异。完成后对话卡片摘要会明确提示"任务已保存到 XX 历史"，并提供跳转入口。

## 三、为什么后端零改动

核查发现所需能力全是现成 REST API，且鉴权一致（同一 Bearer token / current_user）：

- 上传 `POST /api/documents/upload/` → `documentAPI.upload`（拿 document_id）
- 触发审核 `POST /api/review/{document_id}`（真异步，BackgroundTasks）→ `reviewAPI.create`（拿 review_id）
- 进度 `GET /api/review/{review_id}/progress` → `reviewAPI.getProgress`（返回 status/step/progress，字段名已核实）
- 结果 `GET /api/review/{review_id}/issues` → `reviewAPI.getIssues`
- 对比 `POST /api/compare/`（同步，秒级~几十秒）→ `compareAPI.create`
- 转换 `POST /api/convert/`（异步，落 ConvertTask）→ `convertAPI.convert`；进度 `convertAPI.getProgress`（status=processing/completed/failed、progress、current_step、error_message）

因此三类任务全部只改前端 `AgentDock.vue`，复用现有 API 封装，不新增后端端点、不碰任何引擎。

## 四、改动文件

仅 `frontend/src/components/AgentDock.vue`：
- 消息对象扩展 `upload`（上传入口配置）与 `task`（任务状态）字段
- 新增 `onFileSelected` / `startReview` / `startCompare` / `startConvert` / `finishReview` / `retryTask` / 轮询管理
- review/compare/convert 意图不再显示"前往"按钮，改显示内联上传入口；convert 额外带目标格式下拉
- 完成后卡片摘要提示"任务已保存到 XX 历史"，跳转指向对应历史页（`/review/tasks`、`/compare/tasks`、`/convert/history`）
- 新增上传入口、格式下拉与进度卡片样式
- 组件卸载时清理所有轮询定时器

## 五、边界与已知限制（如实说明）

1. **对比是同步阻塞**：`POST /api/compare/` 无异步中间态，聊天框会等待（默认 axios timeout 10 分钟；小文档秒级，大文档几十秒）。若实测卡顿，需给后端 compare 补 BackgroundTasks + 进度端点（用户选做，本次未做）。
2. **审核后台任务是进程内 BackgroundTasks**：进程重启/多实例会丢进度，靠 DB 兜底——这是平台现状，非本次引入。
3. **对比需一次选两个文件**：file input 用 Ctrl/Shift 多选，不支持分两次选。UI 文案已注明。
4. **进度字段**：审核用 `status`（running/completed/failed/cancelled）+ `step`；转换用 `status`（processing/completed/failed）+ `current_step` + `error_message`。两者终态枚举不同，代码分别处理。
5. **转换历史可见的前提**：`POST /convert/` 落 `ConvertTask.user_id`，历史页 `GET /convert/` 按 user_id 过滤——与页面手动转换同源，天然可见。若落库失败（进程内 `_task_store` 兜底），重启会丢，属平台现状。
6. **构建验证**：`vite build` 成功（22s），组件正常编译。
6. **未做端到端 UI 实测**：本环境无法启动完整前端+后端+登录态联调；逻辑基于现成 API 签名与字段核实。建议在有登录态的部署环境走一遍真实上传→审核→进度→结果。

审核工具：WorkBuddy（AI 文档审核）
