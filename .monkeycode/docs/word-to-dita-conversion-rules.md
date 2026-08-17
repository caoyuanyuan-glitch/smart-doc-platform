# Word to DITA Conversion Rules

适用范围：当前项目的 Word/WPS 转 DITA 批量转换。

## 目标

- 输出结构以源 Word 为准。
- 文本内容保持原文语义与顺序。
- 仅在 IME/DITA 平台需要的地方做结构适配。

## 模板复用规则

- `Cover` topic 直接复用参考 DITA zip 包中的原始 topic。
- `booklists/toc` 继续复用参考 DITA zip 包。
- `Manufacturer information` 按源 Word 生成，不复用模板 appendix 内容。
- `Cover` 下挂 3 个固定前部 topic：
  - `About the user manual`
  - `Manufacturer information`
  - `Revision history`

## Word 预处理规则

- `.wps` 如本质为 OOXML 压缩包，可按 `.docx` 链路直接处理。
- Word 自带目录块不进入 DITA 正文。
- 纯页码段落不进入 DITA 正文。
- Word 里因排版产生的句内断行需要自动合并，避免一句话被切成多段。

## 标题与结构规则

- DITA 层级按源 Word 标题层级建树，章节结构需要与 Word 层级 100% 一致。
- `Revision history` 视为真实章节。
- `Contents` 视为目录，不视为正文章节。
- `Formula N ...` 和包含等式的公式行保留在正文中，不拆成 topic。
- `Cover` 正文里的产品编号、版本号等短行优先留在封面正文，不单独生成 topic。

## 列表规则

- 有序步骤列表转换为 `ol` 时保持连续。
- 步骤下的图片、表格、note 挂到对应步骤项下。
- 图片、表格、note 不打断同一个 `ol`。
- Word 操作步骤中的加粗强调文本需要保留并转换为 `b` 标签。

## Note 规则

- 中文 note 识别标签词：`注意事项`、`其他注意事项`、`注意`、`提示`、`警告`、`小心`。
- 英文 note 识别标签词：`Warning`、`Caution`、`Tips`、`Danger`、`StopPoint`、`Stop point`。
- 英文普通 `Do not ...` 句子保持正文段落。
- 当正文句后紧邻 warning 图标时，按 warning 处理。
- 默认普通 note 输出为 `type="tip"`。
- note 图标图片不输出到最终 DITA。

## 图片规则

- 图片保留到输出包中。
- 图片不输出 `alt` 标签。
- 紧邻 note 文本的小图标图片视为 note 图标，跳过输出。
- 英文图片标题去掉 `Figure N` 编号前缀。
- 中文图片标题保留 `图 N`。

## 表格规则

- 表格标题去掉 `Table N` 或 `表 N` 编号前缀。
- 仅有表题没有表体时，保留为普通段落，不伪造空表。
- DOCX 合并单元格按共享 `_tc` 保留真实内容，避免内容被误清空。
- Word 表格跨页后重复出现的表头行，需要在转换后自动删除。
- 若同一 Markdown 表中出现嵌入式 `Table N ...` 行，视为下一张表的标题并拆分为独立表格。
- 被合并单元格拆碎的英文表题片段需自动拼回完整标题。

## 验收口径

- 标题数量与结构和源 Word 对齐。
- 图片按有效内容去重后不丢失。
- note 图标图片不计入图片丢失。
- 表格标题、图片标题、列表、note 转换结果都应通过自动校验。

## 当前批量转换基线

- 当前稳定基线输出包：`当前工作区/backend/static/uploads/outputs/output_20260813_061625.zip`
- 当前核心实现文件：`当前工作区/backend/app/api/convert.py`
- 当前包级验收脚本：`当前工作区/backend/tools/verify_word_to_dita_package.py`
