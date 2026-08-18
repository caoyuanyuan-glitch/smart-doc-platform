# 拼写检查原文词形白名单

Feature Name: spellcheck-original-case-whitelist
Updated: 2026-08-17

## Description

白名单添加动作使用检查结果位置对应的原文片段。拼写建议继续用于替换，不参与白名单入词。

## Components and Interfaces

- `spell_checker.check_spelling`: 每个出现位置使用正则匹配的原始文本填充 `original_text`。
- `spell_check._build_response`: 将 `original_text` 传递为前端错误对象的 `word`。
- `SpellCheck.vue`: 从当前结果正文按错误位置截取原文词形，提交至白名单接口。

## Correctness Properties

- 白名单请求参数与当前正文 `text[start:end]` 相同。
- `Oligo`、`oligo` 与 `OLIGO` 保持为三个独立词形。
- 修订建议只影响“应用”和“编辑”操作。

## Error Handling

当位置无效时，前端使用后端返回的 `word` 作为回退值，并保持其字符串内容。

## Test Strategy

- 验证拼写检查对混合大小写原文返回相同的 `original_text`。
- 验证响应对象的 `word` 与原文片段一致。
