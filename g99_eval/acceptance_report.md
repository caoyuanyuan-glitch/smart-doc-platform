# G99 审核召回验收报告

- Date: 2026-10-21
- PDF: 当前工作区 `/g99_eval/g99_noannot.pdf`（244 页，批注已删除）
- Goldset: 当前工作区 `/backend/goldset/human_baseline_DNBSEQ-G99RS&DNBSEQ-G99ARSSystemGuide(StandardMPS2.0)_V9.0_R01Lijuan.json`（33 条）
- 评测函数: `_match_annotations_injectively()` 单射 strict

## Provider 声明

默认视觉链 kimi,qwen 凭据不可用（Kimi 401 / Qwen 欠费 400）。本轮视觉与完整主流程使用 DeepSeek。规则通道数字不含视觉能力。视觉通道数字来自 DeepSeek 页级复核，不把不可用 provider 包装成算法提升。

`app/utils/prompt_builder.py` 仍不在本仓库，AI 走 fallback 提示词，这是既有状态。

## 通道结果

| 口径 | strict 命中 | strict 检出率 | strict 准确率 | 宽松检出率 | issue 数 |
|---|---|---|---|---|---|
| 规则通道（隔离，含页码回填） | 17/33 | 51.52% | 5.20% | 75.76% | 327 |
| 规则通道（完整主流程拆分） | 14/33 | 42.42% | 6.33% | 75.76% | 221 |
| PDF 视觉通道（完整主流程拆分） | 2/33 | 6.06% | 3.17% | 45.45% | 63 |
| AI 深度通道（完整主流程拆分） | 5/33 | 15.15% | 11.90% | 36.36% | 42 |
| 规则 + 视觉（完整主流程） | 16/33 | 48.48% | 5.63% | 96.97% | 284 |
| 完整主流程 `_run_review_background` | 19/33 | 57.58% | 5.83% | 96.97% | 326 |

规则通道相对上一轮 14/33 新增 3 条，来源是 `DOC-SPACE-006` 经页码回填命中 ℃ 批注。

去重修复前完整主流程是 14/33。页码回填挪到去重之前后，℃ 的 p82/p88 进入生产结果，完整主流程升到 19/33。

本轮完整流程视觉命中 p79、p90（均为 `visual_uncertain`，confidence 72）。p213 本轮为 reject，没有落 issue。隔离 168 页复核里 DeepSeek 对 p69 做过 confirm。

当前生产口径 19/33；S3 目标 22/33。剩余 14 条：LAYOUT p69×2 / p70 / p76 / p158 / p159 / p213，COMPONENT p32 / p72，IMAGE p114，AI-STYLE p43 / p121 / p175，以及 p43 两条被单射占掉的术语/小写。几何信号只用于选页。

## 回归

- P0/P1 单测 T1–T23: 23 passed
- 全量 pytest: 1158 passed, 6 failed, 1 skipped
- 6 个失败均为改动前环境性预置：4 个 `DocxHeadingDetectionTest` 缺样例、`test_polish_match_score`、`test_document_ocr_keeps_numbered_paragraphs`（缺 tesseract）
- 旧 goldset（e25rs / GoSpatial）本环境无对应 PDF、无历史 review 行，未能重跑

## 视觉选页

生产默认限额仍为 48。评测将 `REVIEW_PDF_VISUAL_VERIFY_LAYOUT_LIMIT` 设为 168，覆盖全部疑点页。本轮已确认 8 个版式 gold 页全部进入复核集：69, 70, 76, 79, 90, 158, 159, 213。

## 未做能力

- STRUCT-COMPONENT-001（p32 / p72）
- AI-STYLE-001（p43 / p69 / p121 / p175）
- STRUCT-IMAGE-001 图片颜色（p114）
- 改动未 commit
