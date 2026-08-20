# Requirements Document

## Introduction

文档翻译需要接收 PNG、JPG 和 JPEG 图片，通过 OCR 提取图片中的文字，生成保留图片格式的译文文件。

## Glossary

- **图片文档**: 扩展名为 PNG、JPG 或 JPEG 的上传文件。
- **文字块**: OCR 在图片中识别出的同一行文字及其坐标范围。
- **译图**: 覆盖文字块译文后生成的图片文件。

## Requirements

### Requirement 1: 图片上传

**User Story:** AS 文档翻译用户, I want 上传图片文档进行翻译, so that 图片中的文字可以进入现有翻译流程。

#### Acceptance Criteria

1. WHEN 用户选择 PNG、JPG 或 JPEG 图片文档, 文档翻译页面 SHALL 接受文件并提交翻译任务。
2. WHEN 文档翻译页面显示支持的文件类型, 页面 SHALL 列出图片格式。
3. WHEN 图片文档大小超过 50MB, 文档翻译页面 SHALL 显示文件大小限制提示。

### Requirement 2: 图片文字翻译

**User Story:** AS 文档翻译用户, I want 获得包含译文的图片文件, so that 可以继续使用图片形式的文档。

#### Acceptance Criteria

1. WHEN 图片文档进入翻译任务, 系统 SHALL 通过 OCR 提取图片文字块和文字块坐标。
2. WHEN OCR 提取到文字块, 系统 SHALL 按当前翻译引擎、模型、语言和记忆库配置翻译文字块。
3. WHEN 图片翻译完成, 系统 SHALL 生成与原文件相同格式的译图并提供下载。
4. IF OCR 未提取到任何文字块, 系统 SHALL 将任务标记为失败并返回可读的 OCR 提示。
5. IF 运行环境无法提供 OCR 能力, 系统 SHALL 将任务标记为失败并返回可读的依赖提示。

### Requirement 3: 译文版式适配

**User Story:** AS 文档翻译用户, I want 译文保持原文的版式比例, so that 译文可以在原有文档结构中清晰阅读。

#### Acceptance Criteria

1. WHEN 系统写入任意格式的译文, 系统 SHALL 使用原文字号减 1pt 作为目标字号，并在原字号缺失时保持可读的原区域字号。
2. IF 译文在原文字区域中无法容纳, 系统 SHALL 在字号减 1pt 的基础上继续缩小字号以适配原区域。
3. WHEN 图片译文覆盖文字区域, 系统 SHALL 保留原有按钮、边框和其他非文字图形。
