# Requirements Document

## Introduction

在开始审核页增加「文本片段审核」子页签，用户粘贴句子或段落后，系统只检查语法、拼写和术语。

## Glossary

- **文本片段**: 用户粘贴的一句或多段正文，不含完整文档结构
- **片段审核范围**: 语法、拼写、术语三类问题

## Requirements

### Requirement 1

**User Story:** AS 审核人员, I want 粘贴句子或段落并立即审核, so that 不必上传整份文档也能检查用词

#### Acceptance Criteria

1. WHEN 用户打开开始审核页, THE 系统 SHALL 展示名为「文本片段审核」的子页签
2. WHEN 用户在该页签粘贴文本并点击开始审核, THE 系统 SHALL 创建一次片段审核任务
3. IF 粘贴文本为空, THE 系统 SHALL 提示用户输入文本后再启动审核

### Requirement 2

**User Story:** AS 审核人员, I want 结果只覆盖语法、拼写和术语, so that 不会混入结构或版式问题

#### Acceptance Criteria

1. WHEN 片段审核完成, THE 系统 SHALL 只保留语法、拼写、术语相关问题
2. WHILE 片段审核运行, THE 系统 SHALL 复用现有快速审核和完整审核模式选择
3. WHEN 片段审核完成, THE 系统 SHALL 允许用户查看问题并进入历史任务处理
