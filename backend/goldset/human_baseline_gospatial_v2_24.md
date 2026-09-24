# 人工批注 Gold Set — GoSpatial V2-24 英文说明书（任务 3）

> 用途：作为准确率评测的标准答案集，配合
> `python scripts/evaluate_review.py --review-id <ID> --human-baseline <本文件>` 使用。
>
> **状态：初版，需人工复核补全。** 已填入的条目来自审核报告 #3 的 12 条问题中经确认的
> 9 条真实问题（另 3 条为平台误报，已剔除，见文末「不作为 gold 的项」）。
> `page` / `context` 空缺项请审阅人补齐——缺失会降低匹配命中率，从而低估 recall。

---

## 批注 1

- file: H-020-001010-00GoSpatial-V2-24AutomatedSamplePreparationSystemUserManual_English_RUO_WH.pdf
- page:
- annotation_type: 批注
- author: 待补
- comment: 商标使用需法务确认，正文商标标注与声明页不一致
- selected_text: 商标相关表述
- context:
- category: 商标法务
- layer: ai_assisted
- expected_rule: AI-TM-001

## 批注 2

- file: H-020-001010-00GoSpatial-V2-24AutomatedSamplePreparationSystemUserManual_English_RUO_WH.pdf
- page:
- annotation_type: 批注
- author: 待补
- comment: 同一句话跨页重复出现，需删减一处
- selected_text: 跨页重复句
- context:
- category: 重复内容
- layer: structural_consistency
- expected_rule: DOC-DUP-001

## 批注 3

- file: H-020-001010-00GoSpatial-V2-24AutomatedSamplePreparationSystemUserManual_English_RUO_WH.pdf
- page:
- annotation_type: 批注
- author: 待补
- comment: Cassetter 拼写错误，应为 Cassette
- selected_text: Cassetter
- context: Select the Cassetter module and load the samples.
- category: 术语拼写
- layer: deterministic
- expected_rule: DET-TERM-SPELL-001

## 批注 4

- file: H-020-001010-00GoSpatial-V2-24AutomatedSamplePreparationSystemUserManual_English_RUO_WH.pdf
- page:
- annotation_type: 批注
- author: 待补
- comment: 冠词 the 重复
- selected_text: the the
- context:
- category: 语法与表达
- layer: deterministic
- expected_rule: DOC-GRAM-001

## 批注 5

- file: H-020-001010-00GoSpatial-V2-24AutomatedSamplePreparationSystemUserManual_English_RUO_WH.pdf
- page:
- annotation_type: 批注
- author: 待补
- comment: Catalog number 应统一写为 Cat. No.
- selected_text: Catalog number
- context:
- category: 术语一致性
- layer: structural_consistency
- expected_rule: DOC-CATNO-001

## 批注 6

- file: H-020-001010-00GoSpatial-V2-24AutomatedSamplePreparationSystemUserManual_English_RUO_WH.pdf
- page:
- annotation_type: 批注
- author: 待补
- comment: 操作步骤引导语重复
- selected_text: 步骤引导语
- context:
- category: 操作步骤
- layer: structural_consistency
- expected_rule: DOC-PROC-002

## 批注 7

- file: H-020-001010-00GoSpatial-V2-24AutomatedSamplePreparationSystemUserManual_English_RUO_WH.pdf
- page:
- annotation_type: 批注
- author: 待补
- comment: 文件名与正文引用不一致
- selected_text: 文件名
- context:
- category: 信息完整
- layer: structural_consistency
- expected_rule: DOC-FILE-001

## 批注 8

- file: H-020-001010-00GoSpatial-V2-24AutomatedSamplePreparationSystemUserManual_English_RUO_WH.pdf
- page:
- annotation_type: 批注
- author: 待补
- comment: before clean 应改为 before cleaning
- selected_text: before clean
- context: Before clean the instrument, power it down completely.
- category: 语法与表达
- layer: deterministic
- expected_rule: DOC-GRAM-002

## 批注 9

- file: H-020-001010-00GoSpatial-V2-24AutomatedSamplePreparationSystemUserManual_English_RUO_WH.pdf
- page:
- annotation_type: 批注
- author: 待补
- comment: during clean 应改为 during cleaning
- selected_text: during clean
- context: during clean the surface
- category: 语法与表达
- layer: deterministic
- expected_rule: DOC-GRAM-002

## 批注 10

- file: H-020-001010-00GoSpatial-V2-24AutomatedSamplePreparationSystemUserManual_English_RUO_WH.pdf
- page:
- annotation_type: 批注
- author: 待补
- comment: 维护周期中 cleaning 与 disinfection 术语混用，需统一
- selected_text: Monthly cleaning
- context: Monthly cleaning and disinfection schedule
- category: 术语一致性
- layer: structural_consistency
- expected_rule: DOC-TERM-002

---

## 待人工补充的漏检项（FN）

以下内容为 PR #145 之前平台未召回、人工认为应报的项。
**gold set 必须包含漏检项，否则 recall 恒不可知**（见 `dashboard_metrics.py` 说明）。
请审阅人继续补充：

- 【待补】
- 【待补】

---

## 不作为 gold 的项（已确认的平台误报，勿计入）

以下 3 条来自审核报告 #3，经核实为平台误报，**不得**写入 gold set，
否则会把误报算成真阳性，虚高 recall：

| 报告编号 | 内容 | 为何是误报 |
|---|---|---|
| #0007 | `a HOME` → 建议 `an HOME` | HOME 为可读词，/h/ 辅音开头，`a HOME` 正确 |
| #0008 | `a UPS` → 建议 `an UPS` | UPS 按字母名读 /juː/ 辅音开头，`a UPS` 正确 |
| #0010 | `omics` → 建议 `Omics` | spatial omics 为标准专业术语，小写正确 |
