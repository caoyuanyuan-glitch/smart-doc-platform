# Requirements Document

## Introduction

拼写检查结果页加入白名单时，系统需要保存文档原文命中的词形，保留原始大小写。

## Glossary

- **原文词形**: 检查结果中由 `start` 和 `end` 定位的文档片段。
- **拼写建议**: 拼写引擎为原文词形提供的候选替换词。
- **白名单词条**: 用户确认后保存并用于后续检查过滤的词。

## Requirements

### Requirement 1: 原文词形入白名单

**User Story:** AS 拼写检查用户, I want 将原文命中的专用词加入白名单, so that 白名单保留文档中的实际大小写。

#### Acceptance Criteria

1. WHEN 用户在拼写结果页点击“加入白名单”, 系统 SHALL 使用当前问题的原文词形创建白名单词条。
2. WHEN 原文词形包含大写或混合大小写, 系统 SHALL 将相同大小写保存到白名单词条。
3. WHEN 拼写问题包含修订建议, 系统 SHALL 将修订建议保留为修订操作的输入。
4. WHEN 拼写引擎聚合大小写不同的同形词, 系统 SHALL 为每个问题返回对应位置的原文词形。
