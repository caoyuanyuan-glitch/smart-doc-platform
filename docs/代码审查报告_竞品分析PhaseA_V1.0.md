# 代码审查报告 — 竞品分析模块 Phase A（洞察引擎 + 多文档对比）

| 项 | 内容 |
| --- | --- |
| 审查对象 | 分支 `optimize-competitor-analysis`，commit `f479c1c`（13 文件，+1900/-20） |
| 审查方式 | 编码自审 + 独立交叉审查（reviewer 代理复查）+ 修复后回归 |
| 审查工具 | WorkBuddy（AI 代码审查） |
| 日期 | 2026-08-24 |

## 一、问题清单（已全部修复）

| 级别 | 位置 | 问题 → 修复 |
| --- | --- | --- |
| P0 | frontend/CompetitorCompare.vue | `taskTable` 模板 ref 未在 script 声明，超选取消勾选逻辑必然抛 ReferenceError → 补 `const taskTable = ref(null)` |
| P0 | backend/api/competitor.py | 洞察生成在请求线程同步执行且未捕获异常，AI 调用可阻塞数十秒、异常会拖垮整个分析任务 → try/except 降级为空洞察；AI 层 `fallback=False, timeout=20` |
| P1 | frontend/CompetitorCompare.vue | 维度缺测（null）文档雷达图画成 0 分误导 → 缺测文档不入图，提示条说明 |
| P1 | backend/api/competitor.py | 损坏 JSON 任务被"任务数不足"400 误导排障 → 先剔除损坏再校验数量，明确 422 文案 |
| P1 | backend/utils/competitor_insight.py | 文档衍生文本直拼 prompt 存在提示词注入面 → system prompt 增加数据边界声明；输出经转义+截断+白名单化 |
| P1 | tests | 盲区：重复 ID/非整数/损坏 JSON/并列最优/缺测维度/404 未覆盖 → 补 8 个用例 |
| P2 | backend/utils/competitor_comparison.py | 并列最高分只标一个 ▲；无基线时阈值文案错（8 vs 15）；先转义后截断可产生孤立反斜杠 → 并列均标；按有无基线输出阈值；先截断后转义 |
| P2 | backend/utils/competitor_insight.py | 规则层为空时 AI 层不触发（与"AI 增强"语义不符）→ AI 层始终尝试，失败自动降级 |
| P2 | backend/schemas/competitor.py | `task_ids: list` 无元素约束 → `List[int] = Field(min_length=2, max_length=5)`，API 保留 bool/重复兜底校验 |
| P2 | backend/api/competitor.py | 报告用完整标题、落库截断 120，两处不一致 → 渲染前统一截断 |

未修（可接受项）：雷达图勾选顺序按表格序保留（el-table 无选择时序）；`overall_score` 缺失按 0 排名垫底（历史数据均有该字段）；AI 返回多段方括号文本时正则可能匹配错跨度（解析失败安全降级，无功能影响）。

## 二、通过项（单行列举）

路由顺序（/compare 均在 /{task_id} 前，测试验证）、越权双向 404、JSON 序列化往返一致、_md_escape 覆盖（标题/文档名/洞察/差距对）、删除返回体对齐平台约定、AI 降级链路（env 开关→无 key→调用失败→解析失败四级降级）、测试 45/45 + 集成 24/24 + vite build 通过。

审核工具：WorkBuddy（AI 代码审查）
