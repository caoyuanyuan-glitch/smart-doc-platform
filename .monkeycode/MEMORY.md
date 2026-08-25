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

Word 转 DITA 的 note 图标处理规则
- Date: 2026-08-12
- Context: 用户补充 IME 平台 note 标签自带提示/警告/小心类图标的验收口径
- Category: 行为指令
- Instructions:
  - 在 Word 转 DITA 的图片完整性校验中，提示、警告、小心等 note 类说明内容配套的小图标不计入“图片不丢失”范围
  - 若内容已经成功转换为 DITA `note` 标签，可不再输出这类 note 图标图片

Word 转 DITA 的目录处理规则
- Date: 2026-08-12
- Context: 用户补充 IME 平台已提供 Booklists/toc 结构
- Category: 行为指令
- Instructions:
  - Word 源文件中的目录内容不需要转换到 DITA 正文中
  - 验收时不将 Word 目录计入标题结构和内容完整性比对范围

Word 转 DITA 的步骤与图片输出规则
- Date: 2026-08-12
- Context: 用户补充 IME 导入测试时对步骤连续性、note 和图片标签的要求
- Category: 行为指令
- Instructions:
  - 有序步骤列表转换到 DITA 时，需要保持 `ol` 连续，不因图片、表格或 note 中断
  - 步骤下方的图片、表格、note 内容应放在对应步骤项下，而不是拆成多个独立 `ol`
  - 提示、警告、小心等内容只保留 `note` 文本，不输出图标图片
  - 图片输出不需要 `alt` 标签
  - 表格标题只保留名称内容，去掉 `表 13`、`Table 13` 这类编号前缀，IME 样式会自动补序号
  - Word 中因排版产生的多余回车，需要在转换时自动识别并合并，避免把同一句内容截断成两句

Git 与自检工作流
- Date: 2026-08-17
- Context: 合并 2026-06-17、2026-06-18、2026-06-25、2026-06-29 的协作约束，便于后续执行
- Category: 工作流协作
- Instructions:
  - 每日开始开发任务前，先执行 `git checkout main && git pull origin main`
  - 然后按日期创建分支，命名规范为 `YYMMDD-(feat|fix|chore|refactor)-xxxxx-xxxx-xxxx`
  - 所有时间按北京时间 `TZ='Asia/Shanghai'` 处理
  - 白天可以随时 commit，17:50 统一检查并逐分支执行 `git push origin <branch>`
  - 未收到用户明确推送指令前，不主动执行 `git push`
  - 每次完成代码修改后先做本地自检，再通知用户进行平台侧验证

前后端自验命令
- Date: 2026-07-01
- Context: Agent 在执行智能润色规则管理任务时校正路径
- Category: 构建方法
- Instructions:
  - 智能润色项目实际路径为 `/workspace/smart-doc-platform`
  - 当前工作区前端构建校验使用 `cd /workspace/smart-doc-platform/frontend && npm run build`
  - 当前工作区后端语法校验使用 `cd /workspace/smart-doc-platform/backend && python3 -m compileall app`

产品型号与编号空格规则
- Date: 2026-06-24
- Context: 用户 уточ明智能润色中的字母数字空格保留规则
- Category: 行为指令
- Instructions:
  - 产品型号内部连续字母数字保持连写，例如 `DNBelab-D4RS`
  - 编号与标题或术语之间保留空格，例如 `表1 DNBelab-D4RS`、`2.1 RNA`

大模型调用顺序
- Date: 2026-07-07
- Context: Agent 在执行审核模块 AI 调用排障时发现
- Category: 环境配置
- Instructions:
  - runtime.env 已提交到 Git 仓库，不再依赖外部备份文件恢复
  - 添加新的 API Key 后直接编辑 backend/runtime.env 并 commit 即可
  - 审核模块 LLM provider 优先级: Qwen > Kimi > DeepSeek > ArkClaw > MCAI Proxy > Proxy
  - 排查 AI 审核结果异常时，先确认后端启动日志中的 provider 预热状态和审核日志中的 `AI客户端可用`、`providers=`、规范文件长度

审核模块改动范围约束
- Date: 2026-06-25
- Context: 用户要求本次优化仅处理审核模块稳定性
- Category: 行为指令
- Instructions:
  - 本次任务仅修改审核模块相关实现
  - 其他业务模块保持现状，除非用户明确要求联动修改
  - 当前阶段不投入飞书上传相关功能，优先提升审核有效性和实质问题命中率

AI 翻译引擎排查规则
- Date: 2026-06-26
- Context: 用户要求将 Kimi 调用优先级和排查方法写入调用规则
- Category: 排错调试
- Instructions:
  - AI 翻译默认优先使用 `Kimi`，再依次回退到 `DeepSeek`、`ArkClaw`、`MCAI Proxy`、`Proxy`
  - 发生 `AI翻译引擎不可用` 时，先检查 `/api/translation/providers/status` 返回的 provider 可用状态
  - 排查重点是当前服务进程是否已注入 `KIMI_API_KEY`，再检查 `DEEPSEEK_API_KEY` 和 `ARKCLAW_API_KEY`
  - 仓库内只保留 `.env.example` 模板，实际服务配置以部署环境注入为准

DITA 父子节点兼容规则
- Date: 2026-06-30
- Context: Agent 在执行 Word 转 DITA 的 IME 右键报错排查时发现
- Category: 排错调试
- Instructions:
  - DITA 生成时，顶层空父节点可以保留为结构容器
  - 带子节点的中间父节点必须输出为真实 topic，并生成自己的 `href` 和 `keys`
  - 若中间父节点被生成为信息结构组件，IME 中其子 topic 可能出现右键加载错误

Word 转 DITA 批量转换基线规则
- Date: 2026-08-13
- Context: Agent 在收敛英文 Word 转 DITA 转换规则并准备后续批量处理时发现
- Category: 工作流协作
- Instructions:
  - 后续批量 Word/WPS 转 DITA 时，统一以 `当前工作区/.monkeycode/docs/word-to-dita-conversion-rules.md` 作为转换与验收基线
  - `Cover` topic 直接复用参考 zip 包中的原始 topic
  - `booklists/toc` 继续复用参考 zip 包，正文结构以源 Word 为准
  - Word 操作步骤中的加粗强调文本必须保留并转换为 `b` 标签
  - Word 表格跨页产生的重复表头行必须自动删除，不能依赖人工清理
  - 章节结构必须按 Word 原始层级 100% 对齐，结构一致性高于局部样式调整
  - 每次批量转换完成后，都先运行单测和包级验收，再交给用户做平台侧导入验证

前端开发代理端口约定
- Date: 2026-06-30
- Context: Agent 在执行预览登录排障时发现
- Category: 环境配置
- Instructions:
  - Vite 开发代理 `/api` 目标端口使用 `http://localhost:8000`
  - 本项目 README 指定后端开发服务端口为 `8000`
  - 若前端代理指向 `8001`，登录等接口会因代理目标错误而失败

后端审核测试运行约定
- Date: 2026-08-17
- Context: Agent 在执行审核模块准确性优化并运行回归测试时发现
- Category: 构建方法
- Instructions:
  - 后端测试需显式设置 `PYTHONPATH=/workspace/backend`，否则 `app` 包无法导入
  - 审核模块相关回归命令可直接使用 `PYTHONPATH=/workspace/backend python3 -m pytest backend/tests/test_review_cache.py backend/tests/test_review_gold_compare.py`
  - 修改中文审核规则后，优先复跑 `PYTHONPATH=/workspace/backend python3 -m pytest backend/tests/test_review_cache.py -q` 做快速回归
  - 当前环境若缺少测试依赖，先安装 `backend/requirements.txt`，并补装 `pytest` 与 `httpx`

IFU PDF 回归测试约定
- Date: 2026-08-19
- Context: Agent 在把 IFU PDF OCR 回归样例接入测试并验证时发现
- Category: 测试方法
- Instructions:
  - IFU PDF OCR 回归测试入口为 `当前工作区/backend/tests/test_document_parser_pdf_regression.py`
  - 该测试依赖 `当前工作区/.monkeycode/docs/ifu-pdf-regression-cases-20260819.json` 作为参数化样例源
  - 复跑命令使用 `PYTHONPATH=/workspace/backend python3 -m pytest backend/tests/test_document_parser_pdf_regression.py`
  - 相关审核回归可同时复跑 `PYTHONPATH=/workspace/backend python3 -m pytest backend/tests/test_review_cache.py backend/tests/test_review_gold_compare.py`

审核历史任务保留规则
- Date: 2026-08-21
- Context: 用户要求历史审核任务可持续保留，Agent 在修复默认数据库持久化链路时更新
- Category: 环境配置
- Instructions:
  - 审核模块默认数据库路径使用 `~/.smart-doc-platform/app.db` 持久化保存历史审核任务
  - 若项目根目录下存在旧库 `当前工作区/backend/app.db`，启动时需自动迁移到运行时持久目录并继续复用
  - 合并代码、重启预览服务或切换分支后，历史审核任务列表需要保持可见
  - 常规启动脚本仅在数据库文件缺失时执行 `init_data.py` 初始化，已有数据库需直接复用

WorkBuddy 联动评审目录约定
- Date: 2026-08-05
- Context: 用户要求与 workbuddy 联动，由其输出按轮次带提交号的审查建议
- Category: 工作流协作
- Instructions:
  - workbuddy 审查结果统一写入 `当前工作区/smart-doc-platform/.monkeycode/reviews/`
  - 文件名使用 `round-001-<commit>.md` 这类按轮次并带提交号的格式
  - 我处理 review 时以该目录中的最新轮次文件为准

规则设计约束
- Date: 2026-08-06
- Context: 用户要求修复 CAT 候选规则时不要在规则中加入具体词
- Category: 行为指令
- Instructions:
  - 规则优先使用结构、关系、通用模式和已有抽取能力
  - 避免通过硬编码具体词语扩展匹配或拦截规则
