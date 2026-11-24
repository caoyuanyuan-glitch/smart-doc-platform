# 审核依据汇总

本目录汇总当前审核模块实际使用或直接依赖的审核依据，便于团队离线查看、同步和补齐。

## 当前实际生效

- `../写作风格指南/中文技术文档写作风格指南.md`
  - 用途：中文文档写作风格约束
  - 代码入口：`backend/app/api/review.py::_build_ai_review_basis_sections`
- `../说明书自检checklist/中文说明书写作Checklist.xlsx`
  - 用途：中文说明书发布前自检
  - 代码入口：`backend/app/api/review.py::_build_ai_review_basis_sections`
- `../说明书自检checklist/英文说明书写作Checklist.xlsx`
  - 用途：英文说明书发布前自检
  - 代码入口：`backend/app/api/review.py::_build_ai_review_basis_sections`
- `cyy-human-review-baseline.json`
  - 用途：CYY 人工审核经验基线，当前 AI 深审和部分高置信规则补强的重要来源
  - 代码入口：`backend/app/api/review.py::_load_cyy_human_review_basis`
- `cyy-human-review-baseline-summary.md`
  - 用途：人工批注基线摘要，方便人工理解基线覆盖范围
- `release-checklist.md`
  - 用途：发布前清单说明，明确 checklist 的使用基准

## 相关补充材料

- `../技术文档审核规则库/说明书审核能力补强方案.md`
  - 用途：审核能力建设方案与缺陷归类参考
- `../句式清单/建库试剂/句式表达参考手册_建库试剂说明书.md`
- `../句式清单/来自平台反馈/平台反馈的句式清单.md`
- `../句式清单/自动化/句式表达参考手册_自动化说明书.docx`

## 已补齐并纳入装载

- `../写作风格指南/MGI英文技术文档写作风格指南.md`
  - 用途：英文文档语态、时态、冠词、缩写、大小写和单位规范
  - 代码入口：`backend/app/api/review.py::_build_ai_review_basis_sections`
- `../常见错误清单/技术文档常见错误清单与规范.md`
  - 用途：中文和中英混排高频错误、单位错误、固定表述错误识别
  - 代码入口：`backend/app/api/review.py::_build_ai_review_basis_sections`

## 仍需注意

- 数据库表 `audit_bases`：当前为空，尚未作为有效审核依据来源

## 当前检出率瓶颈

- 审核依据缺口已经缩小，后续重点转向解析文本缺口和专项一致性问题
- 当前更大的瓶颈是标准答案中有一部分项无法在平台解析文本中直接命中，`missing_in_parsed_text_count=18`
- 当前规则侧已经覆盖了大量高置信中文问题，进一步提升召回需要同时补依据和改善解析/比对口径
