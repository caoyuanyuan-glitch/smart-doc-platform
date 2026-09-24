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
  - `注意`、`提示` 段落即使标签词被加粗包裹，也必须转成 `note` 标签；未指定类型时默认 `type="tip"`

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
  - 步骤之间穿插的 note 必须挂到所属步骤项内，不能把整个 `ol` 吞进 note；只有标签的 note（如单独一行 `注意：`）继续包裹其后的列表作为正文
  - `注意` 输出为 `type="caution"`，`提示` 等默认 `type="tip"`
  - 提示、警告、小心等内容只保留 `note` 文本，不输出图标图片
  - 出现在正文句子中的小按钮图标（如“点击界面右上角的 [按钮] 按键”）必须以内联 `<image>` 保留；孤立小图标及 note 段落内的小图标仍丢弃
  - 图片输出不需要 `alt` 标签
  - 表格标题只保留名称内容，去掉 `表 13`、`Table 13` 这类编号前缀，IME 样式会自动补序号
  - 图片标题也只保留名称内容，`图4-2 Oligo文库结构` 与 `Figure 7 ...` 都去掉编号前缀，编号由 IME 样式自动生成
  - 章节、小节与附录标题同样不带手工编号（`第一章`、`2.1`、`3.1.1`、`附录A`、`B-1`），编号由 IME 样式自动生成；`3'RNA`、`1.13×` 这类以数字开头的内容不算编号
  - 带编号的短段落只有文本本身像标题时才作为章节；`cDNA产物扩增循环数参考` 这类编号列表项保持为列表内容，不能升级为独立章节
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
  - `git push` 报 500 的两种成因：`credential helper: server returned status 500` 表示 `/app/agent/bin/agent git-credential-helper` 不可用，改用 `gh auth login --hostname github.com --git-protocol https --web` 授权后 `gh auth setup-git` 再 push；`send-pack: unexpected disconnect` 表示 push 参数不被支持，GitHub 不认 GitLab 的 `-o merge_request.*` 语法，去掉 `-o` 重推
  - `gh` 默认未登录，可从 git 凭据助手取 bot token：`TOKEN=$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null | sed -n 's/^password=//p')`，再用 `GH_TOKEN="$TOKEN" gh pr create ...`。token 只经环境变量传递，不落盘、不输出
  - PR 相关查询：`gh pr list --state open --json number,title,url,headRefName` 取链接；`gh pr view <n> --json state,mergedAt,mergeCommit` 看是否合并；`git merge-base --is-ancestor <commit> origin/main` 核验提交是否真进了主干

前后端自验命令
- Date: 2026-08-25
- Context: Agent 在执行竞品分析模块前端校验与预览时校正当前仓库路径
- Category: 构建方法
- Instructions:
  - 当前仓库根目录为 `/workspace`
  - 当前工作区前端构建校验使用 `cd /workspace/frontend && npm run build`
  - 当前工作区前端预览启动使用 `cd /workspace/frontend && npm run dev -- --host 0.0.0.0 --port 5173`
  - 当前工作区后端语法校验使用 `cd /workspace/backend && python3 -m compileall app`
  - 后台终端（`background_terminal_create`）的 shell 里没有 `python`，需使用 `python3`；前端 `npm run build` 必须先跑过一次 `npm ci`，否则报 `vite: not found`

产品型号与编号空格规则
- Date: 2026-06-24
- Context: 用户 уточ明智能润色中的字母数字空格保留规则
- Category: 行为指令
- Instructions:
  - 产品型号内部连续字母数字保持连写，例如 `DNBelab-D4RS`
  - 编号与标题或术语之间保留空格，例如 `表1 DNBelab-D4RS`、`2.1 RNA`

大模型调用顺序
- Date: 2026-07-07
- Context: Agent 在执行审核模块 AI 调用排障时发现；2026-09-22 补充提示词分层与输出截断排查
- Category: 环境配置
- Instructions:
  - runtime.env 已提交到 Git 仓库，不再依赖外部备份文件恢复
  - 添加新的 API Key 后直接编辑 backend/runtime.env 并 commit 即可
  - 审核模块 LLM provider 优先级: Qwen > Kimi > DeepSeek > ArkClaw > MCAI Proxy > Proxy
  - 排查 AI 审核结果异常时，先确认后端启动日志中的 provider 预热状态和审核日志中的 `AI客户端可用`、`providers=`、规范文件长度
  - 提示词分层：`app/utils/prompt_builder.py` 不在本仓库中，`ai_client` 恒走其 fallback 分支；但中文审核仍会经 fallback 的 `ReviewPromptBuilder.build_audit_system_prompt()` 调用 `review_rules.build_system_prompt()`（含 P3 语义规则），英文则使用内置英文 system prompt。看到 `prompt_builder 模块缺失` 告警不等于 P3 语义提示词未生效
  - AI 审核输出截断排查：`AI_AUDIT_MAX_TOKENS` 是自适应基准（默认 4096，封顶 base×2）；模型对长中文块偶发"输出饱和"导致 JSON 截断，日志出现 `[AI] <provider> 审核响应 JSON 截断解析失败` 即该块产出为空。单纯调大上限往往无效（模型会把预算写满），优先减小单块内容

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
  - 真实文档端到端审核测试：`cd /workspace/backend && PYTHONPATH=/workspace/backend uvicorn app.main:app --host 127.0.0.1 --port 8000`；启动时会自动建表、种子默认/外部评审规则与预置误报记忆
  - 开发环境启动后自动创建引导管理员 `admin` / `admin123`（`APP_ENV` 非生产时密码会被强制校正为该值）
  - 登录接口走 OAuth2 表单而非 JSON：`curl -s -X POST http://127.0.0.1:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' -d 'username=admin&password=admin123'`，取响应里的 `access_token` 作为 `Authorization: Bearer` 头做接口级端到端验证
  - 人工批注提取：`python3 backend/scripts/extract_pdf_annotations.py <带批注PDF> <输出.md>`，同编号带 `Tina` 后缀的 PDF 即人工意见来源
  - 起草流程：`POST /api/documents/upload/` 上传 → `POST /api/review/{document_id}?mode=hybrid` 建任务 → 轮询 `GET /api/review/{id}/progress` 直到 `completed`
  - 与人工意见对比：`PYTHONPATH=/workspace/backend python3 backend/scripts/evaluate_review.py --review-id <id> --human-baseline <人工意见.md>`，脚本会按文件名自动剥离 ` Tina` 后缀做归属
  - AI provider 可用性先查 `GET /api/review/provider-status`；全部不可用时审核会降级为纯规则，`layers.ai_assisted` 仍可能非 0，不能据此判断 AI 已生效
  - AI provider 配置写在 `当前工作区/backend/runtime.env`（`DEFAULT_MODEL_PROVIDER` 与各家 `*_API_KEY/_BASE_URL/_MODEL`），`bootstrap_runtime_env` 只在进程导入时加载一次，改完必须重启后端才生效；`apply_ai_secret_aliases` 会把 kimi/qwen 的别名统一，deepseek 需显式配 `DEEPSEEK_API_KEY`
  - `evaluate_review.py` 的指标仅供趋势参考：匹配判据已收窄为「包含命中或最长公共子串占比 ≥0.5」，中文碎片单独保留，仍会受 PDF 文本层碎片影响；审核验收必须以人工逐条复核为准
  - `layers` 与 `source` 是两个口径：`layers` 按检查机制归类（命中结构完整性模式即记 `structural_consistency`，即使来源是 AI），`source` 按产出子系统归类；统计 AI 贡献时直接数 `/api/review/{id}/issues` 的 `source` 字段
  - PDF 版式复核依赖视觉 provider 链（`REVIEW_VISUAL_PROVIDERS`，默认 `kimi,qwen`），纯文本模型（deepseek）不在链中；视觉 provider 不可用时 `pdf_visual_verification` 的候选全部 failed 且无页级结果
  - 外部评审规则库（29 条）只在能确定性表达成模式匹配时才生成正则，语义/版式类规则落为 `(?!)`；规则正则与 `language` 在种子阶段写入 rules 表，改完 `app/crud/rule.py` 的转换逻辑必须重启后端重新种子才生效
  - 排查英文文档漏报时先确认规则挂在哪个语言分支：中文人工基线规则不参与纯英文文档，英文文档只走 `_run_english_heuristic_audit` 与 `_run_manual_engineering_audit`，语言无关的判据需要单独接到英文分支
  - 拼写检查页面（`frontend/src/views/SpellCheck.vue`）的口径：拼写类问题来自 `backend/app/utils/spell_checker.py`，其余「规则」类来自 `backend/app/api/spell_check.py` 的确定性规则（`legacy_grammar_rule` 主谓一致、`low_level_rule`、`languagetool`）
  - 英文语法能力扩展走 `backend/app/utils/grammar_engine.py`（LanguageTool），不要再扩 `backend/app/api/spell_check.py` 里的正则语法规则；历史遗留的 `run_grammar` 只保留结构上可确证主语的句式判定，无法确证时跳过
  - 拼写检查页准确率/检出率实测方法：把文件名带 `Tina` 后缀的 PDF 当作人工批注来源，用 `backend/scripts/extract_pdf_annotations.py` 或 PyMuPDF 直接读 annot；待检文件用 `app.utils.document_parser.parse_pdf` 取全文后调 `app.api.spell_check.process_text(text, file_type='pdf')`；issue 的 `start` 字符位置按 `full_text.split('\f')` 的页边界映射回页号，再与批注的 `selected_text`/`context` 归一化后按页对齐
  - `_collect_low_level_rule_issues` 会用 `re.IGNORECASE` 编译规则，凡是依赖大写形式的正则必须在该规则上置 `case_sensitive: True`，否则 `[A-Z]` 会被重新解释为任意大小写
  - PyEnchant 把部分真实错词当作合法英文词（如 `twp`），`spell.unknown()` 不会返回它们；这类词只能靠 `FORCED_MISSPELLINGS` + `COMMON_MISSPELLINGS` 硬编码命中，而这两处按既有边界锁定指令属禁止触碰，需用户明确放开才能做
  - 拼写检查页指标口径：必须分域报告，把「全部批注」与「文本层缺陷批注」当作两个分母；视觉版式（间距/挤压）、内容取舍（按修订历史删除、核对货号）、引号改写、措辞建议不属于文本规则可判范围，计入会系统性压低检出率。准确率也有两套口径，批注对齐口径（分子=与批注对齐条数）会把真实但未批注的检出算成误报，作为下界；结论以人工核验口径（分子=确认的真实缺陷数）为准
  - `spell_checker.py` 的检出上限由硬编码词表决定：`_PDF_FIXED_PHRASE_MISSPELLINGS`、`FORCED_MISSPELLINGS`、`COMMON_MISSPELLINGS`、`TERM_VARIANT_CORRECTIONS` 全为硬编码，唯一 Disk I/O 入口 `WHITELIST_FILE` 只能抑制误报；要提升拼写检出率只能改这个被锁定的文件
  - 2026-09-24 用户明确放开一处边界：允许改动 `_is_protected_technical_token`（可新增 `_singular_candidates`），在精确匹配失败后做三档后缀单复数还原（`ies→y`、`*es→*`、`*s→*`，`-ss` 结尾不还原），使只以单数收录于白名单的术语其规则复数不再误报；`_TECH_TERMS_EXACT` 的构建方式仍禁止改动，还原只在查询侧进行
  - `document_parser.extract_pdf` 按 PyMuPDF 文本块 `"\n\n".join` 拼页，MGI 的 IFU（InDesign 导出）每个视觉行即一个文本块，故解析文本行间全是空行，直接渲染会得到碎句 + 右侧大片留白。拼写检查页用 `spell_check.py` 的 `_merge_soft_wrapped_lines`（仅 pdf）回流解决，不动 `document_parser` 以免影响审核/翻译/比对模块；预览文本被改写后，评测脚本不能再按 offset 映射页码，改写只涉及空白，可对「合并文本/原文」按非空白字符线性对齐得到索引映射

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
