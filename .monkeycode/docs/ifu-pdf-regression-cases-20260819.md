# IFU PDF OCR 回归样例

日期：2026-08-19

对比对象：
- 基线文本：`当前工作区/H-020-001371-00 DNBelab C Series High-throughput Single-cell 5'RNA&V(D)J Library Preparation Set V2.0 Instructions for Use_English_RUO_QD_R01.pdf`
- 待测文本：`当前工作区/H-020-001371-00 DNBelab C Series High-throughput Single-cell 5'RNA&V(D)J Library Preparation Set V2 Tina..pdf`

结论：
- 两份 PDF 的主体内容一致。
- 第二份更像 OCR 结果，适合作为回归缺陷样例来源。
- 第一份可作为这组样例的基线文本。

## 样例清单

| ID | 类别 | 优先级 | 参考信号 | 缺陷信号 | 建议断言 |
| --- | --- | --- | --- | --- | --- |
| PDF-SPACE-001 | 单位/空格 | high | `Cytoactivity < 5%` 一类数值与符号间距稳定 | `Cytoactivity<5%`、`Cytoactivity <5%`、`Cytoactivity < 5 %` | 对 `<`、`>`、`=`、数字、百分号的组合做规范化比对，要求候选文本与基线文本一致 |
| PDF-TABLE-001 | 表格/版式 | high | 基线表格存在合并单元格语义 | OCR 结果把 `rowspan` 语义摊平成重复行，或行数异常膨胀 | 比较表格结构时统计 `rowspan` 或等价分组信号，候选结果不能把分组标题重复灌入每一行 |
| PDF-FIGURE-001 | 图片/对象缺失 | high | 基线文本保留图片占位或图号锚点 | OCR 结果缺少图片占位、图号或相邻说明文字 | 在图号附近检查占位符、图题或对象锚点是否存在，缺任一项即失败 |
| PDF-TYPO-001 | 断词噪声 | medium | 基线句子连续，如 `vortex mixer to mix thoroughly` | OCR 结果出现 `vortex mixer it o mix thoroughly` 这类断词或插字噪声 | 对高风险短语做短窗口 fuzzy compare，允许轻微 OCR 噪声计数，超过阈值即失败 |
| PDF-DROP-001 | 丢行/漏句 | high | 基线章节内句子连续完整 | OCR 结果在同一段或同一章节内漏掉一整行或半句 | 对段落做句级对齐，若候选文本在同一锚点附近缺少完整句子，标记为内容遗漏 |

## 建议的自动化落地方式

1. 先做文本级回归：覆盖 `PDF-SPACE-001`、`PDF-TYPO-001`、`PDF-DROP-001`。
2. 再做结构级回归：覆盖 `PDF-TABLE-001`、`PDF-FIGURE-001`。
3. 报告输出按 `类别 + 锚点 + 参考片段 + 候选片段 + 断言结果` 展示，便于人工复核。

## 最小执行口径

- 文本级：按句对齐后比较规范化字符串。
- 表格级：按表格块比较行数、列数、分组标题复用情况。
- 图片级：按图号或图题锚点比较对象占位是否存在。

## 后续扩展

- 这 5 条适合作为种子样例先接入回归集。
- 后续可以继续补充具体页码、章节标题和原文片段，升级为稳定的金标集。
