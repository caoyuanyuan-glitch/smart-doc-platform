# Gold Set 标注补全清单

> 由 `scripts/audit_goldset_quality.py` 生成。数字可复算，勿手工改统计。

## 汇总

- 批注总数：**88**
- 需补全：**33**

| 文档 | 强制 | 批注数 | 需补全 | FN占位 |
|---|---|---|---|---|
| gospatial_v2_24_en | 是 | 10 | 10 | 是 |
| e25rs_cn | 是 | 9 | 9 | 是 |
| e25rs_en | 是 | 17 | 0 | 是 |
| e25rs_v8_cn_observed | 否 | 9 | 5 | 是 |
| e25rs_v8_en_observed | 否 | 10 | 5 | 是 |
| g99_v9_observed | 否 | 33 | 4 | 是 |

问题分布：上下文为空 16 条、选中文本为空 14 条、缺页码 10 条、作者占位 10 条、选中文本是概念描述 4 条

---

## gospatial_v2_24_en

基线：`goldset\human_baseline_gospatial_v2_24.md` · 强制评测：是

> ⚠ FN（漏检项）区仍是 `【待补】` 占位 —— 必须填真实漏检项。

| # | 期望规则 | 选中文本 | 作者 | 问题 | 待补页码 | 待补上下文 |
|---|---|---|---|---|---|---|
| 1 | AI-TM-001 | 商标相关表述 | 待补 | 缺页码、作者占位、选中文本是概念描述、上下文为空 | ____ | ____ |
| 2 | DOC-DUP-001 | 跨页重复句 | 待补 | 缺页码、作者占位、选中文本是概念描述、上下文为空 | ____ | ____ |
| 3 | DET-TERM-SPELL-001 | Cassetter | 待补 | 缺页码、作者占位 | ____ | ____ |
| 4 | DOC-DUP-007 | the the | 待补 | 缺页码、作者占位、上下文为空 | ____ | ____ |
| 5 | DOC-CATNO-001 | Catalog number | 待补 | 缺页码、作者占位、上下文为空 | ____ | ____ |
| 6 | DOC-PROC-002 | 步骤引导语 | 待补 | 缺页码、作者占位、选中文本是概念描述、上下文为空 | ____ | ____ |
| 7 | DOC-FILE-001 | 文件名 | 待补 | 缺页码、作者占位、选中文本是概念描述、上下文为空 | ____ | ____ |
| 8 | DOC-GRAM-002 | before clean | 待补 | 缺页码、作者占位 | ____ | ____ |
| 9 | DOC-GRAM-002 | during clean | 待补 | 缺页码、作者占位 | ____ | ____ |
| 10 | DOC-TERM-002 | Monthly cleaning | 待补 | 缺页码、作者占位 | ____ | ____ |

## e25rs_cn

基线：`goldset\human_baseline_e25rs_cn.json` · 强制评测：是

> ⚠ 未找到 FN（漏检项）区 —— recall 分母不可知，必须补一节漏检项。

| # | 期望规则 | 选中文本 | 作者 | 问题 | 待补页码 | 待补上下文 |
|---|---|---|---|---|---|---|
| 1 | CYY-CN-LAYOUT-006 | 装基本信息 货号 名 | Tina | 上下文为空 | ____ | ____ |
| 2 | CYY-CN-CONSIST-031 | CL App-D FCU S | Tina | 上下文为空 | ____ | ____ |
| 3 | CYY-CN-PRODUCT-004 | 号：940-005203-00 | Tina | 上下文为空 | ____ | ____ |
| 4 | CYY-CN-DUP-001 | 本试剂盒适用于本试剂盒适用于M 文库插入片段长度为200 bp~50 | Tina | 上下文为空 | ____ | ____ |
| 5 | CYY-CN-SCOPE-002 | 于MGI 接头 于App-C 测 | Tina | 上下文为空 | ____ | ____ |
| 6 | CYY-CN-TERM-006 | 选测试方 | Tina | 上下文为空 | ____ | ____ |
| 7 | CYY-CN-GRAMMAR-012 | 书 4. 如 如 品 5. 如 B | Tina | 上下文为空 | ____ | ____ |
| 8 | CYY-CN-SCOPE-003 | 型是FCL， | Tina | 上下文为空 | ____ | ____ |
| 9 | CYY-CN-CONSIST-032 | 头镊子 其它胶 | Tina | 上下文为空 | ____ | ____ |

## e25rs_en

基线：`goldset\human_baseline_e25rs_en.json` · 强制评测：是

> ⚠ 未找到 FN（漏检项）区 —— recall 分母不可知，必须补一节漏检项。

本文档全部批注质量合格。

## e25rs_v8_cn_observed

基线：`goldset\human_baseline_高通量测序试剂套装使用说明书_中文_RUO_QD_V8.0_R01Tina.json` · 强制评测：否

> ⚠ 未找到 FN（漏检项）区 —— recall 分母不可知，必须补一节漏检项。

| # | 期望规则 | 选中文本 | 作者 | 问题 | 待补页码 | 待补上下文 |
|---|---|---|---|---|---|---|
| 1 | STRUCT-LAYOUT-001 |  | Tina | 选中文本为空、上下文为空 | ____ | ____ |
| 3 | STRUCT-DUP-001 |  | Tina | 选中文本为空 | ____ | ____ |
| 5 | AI-STYLE-001 |  | Tina | 选中文本为空 | ____ | ____ |
| 8 | AI-STYLE-001 |  | Tina | 选中文本为空 | ____ | ____ |
| 9 | AI-STYLE-001 |  | Tina | 选中文本为空 | ____ | ____ |

## e25rs_v8_en_observed

基线：`goldset\human_baseline_High-throughputSequencingSetInstructionsforUse_English_RUO_QD_V8.0_R01Tina.json` · 强制评测：否

> ⚠ 未找到 FN（漏检项）区 —— recall 分母不可知，必须补一节漏检项。

| # | 期望规则 | 选中文本 | 作者 | 问题 | 待补页码 | 待补上下文 |
|---|---|---|---|---|---|---|
| 1 | DET-SPACE-001 |  | Tina | 选中文本为空 | ____ | ____ |
| 2 | DET-PUNCT-001 |  | Tina | 选中文本为空 | ____ | ____ |
| 8 | DET-SPACE-001 |  | Tina | 选中文本为空 | ____ | ____ |
| 9 | AI-STYLE-001 |  | Tina | 选中文本为空 | ____ | ____ |
| 10 | AI-STYLE-001 |  | Tina | 选中文本为空 | ____ | ____ |

## g99_v9_observed

基线：`goldset\human_baseline_DNBSEQ-G99RS&DNBSEQ-G99ARSSystemGuide(StandardMPS2.0)_V9.0_R01Lijuan.json` · 强制评测：否

> ⚠ 未找到 FN（漏检项）区 —— recall 分母不可知，必须补一节漏检项。

| # | 期望规则 | 选中文本 | 作者 | 问题 | 待补页码 | 待补上下文 |
|---|---|---|---|---|---|---|
| 11 | STRUCT-LAYOUT-001 |  | shaolijuan | 选中文本为空 | ____ | ____ |
| 13 | STRUCT-LAYOUT-001 |  | shaolijuan | 选中文本为空 | ____ | ____ |
| 26 | STRUCT-LAYOUT-001 |  | shaolijuan | 选中文本为空 | ____ | ____ |
| 33 | STRUCT-LAYOUT-001 |  | shaolijuan | 选中文本为空 | ____ | ____ |
