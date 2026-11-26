# Requirements Document

## Introduction

对比审核在上传一份中文和一份英文文件时，自动做中英对照一致性检查。

## Glossary

- **对比审核**: 开始审核页中的「对比审核」子页签
- **中英对照**: 按目录标题或章节序号、货号/型号、带单位数值和主干步骤数对齐中英文说明书

## Requirements

### Requirement 1

**User Story:** AS 审核人员, I want 上传中英各一份说明书后自动对照, so that 不必另开入口也能检查译稿一致性

#### Acceptance Criteria

1. WHEN 用户在对比审核中上传主文档和参考文件, THE 系统 SHALL 自动检测两侧语言
2. IF 两侧同时存在中文和英文, THE 系统 SHALL 进入中英对照模式
3. IF 两侧为同一语言, THE 系统 SHALL 保持原有核心参数与主干流程比对

### Requirement 2

**User Story:** AS 审核人员, I want 系统先核对编号、货号和数值, so that 漏译和写错能被稳定检出

#### Acceptance Criteria

1. WHEN 中英编号章节无法按序号对齐, THE 系统 SHALL 报告 P1 章节缺失
2. WHEN 说明书含目录标题, THE 系统 SHALL 按中英目录标题对齐章节，并报告一侧缺失的目录项
3. WHEN 对齐章节中的货号或型号不一致, THE 系统 SHALL 报告 P0
4. WHEN 带单位数值不一致, THE 系统 SHALL 报告 P1
5. WHEN 仅有译名不同且无货号或数值可对齐, THE 系统 SHALL 报告 P2 待确认

### Requirement 3

**User Story:** AS 审核人员, I want 结果里单独看到中英对照明细, so that 能和原有参数表分开处理

#### Acceptance Criteria

1. WHEN 中英对照完成, THE 系统 SHALL 在结果区展示「中英对照」标记
2. WHEN 存在中英对照行, THE 系统 SHALL 展示「中英对照明细表」
3. WHEN 用户导出 HTML 报告, THE 系统 SHALL 说明本次包含中英对照
