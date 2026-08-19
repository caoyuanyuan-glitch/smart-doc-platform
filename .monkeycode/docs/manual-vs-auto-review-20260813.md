# 人工调整包与自动转换包对比记录

日期：2026-08-13

对比对象：
- 人工调整包：`/workspace/.monkeycode-tmp-files/ad660c8c-PM038997_H-940-001530-00-01 MGIEasy Whole Genome Methylation Sequencing Library Prep Kit User Manual-1.7z`
- 自动转换包基线：`/workspace/backend/static/uploads/outputs/output_20260813_063716.zip`
- 原始 Word：`/workspace/H-940-001530-00-01 MGIEasy Whole Genome Methylation Sequencing Library Prep Kit User Manual 3.0-2503.docx`

说明：人工包文件扩展名是 `.7z`，实际容器格式是 `zip`。

## 总体结论

- 两份包通过 ditamap 标题映射后，均为 102 个 topic，章节框架一致。
- 人工包对正文做了大量结构性修正，差异最大的章节包括：
  - `Barcode using guide (96 RXN)`
  - `Shearing condition`
  - `Components`
  - `Workflow`
  - `Adapter ligation`
  - `Cleanup of adapter-ligated product`
- 自动包当前最主要的问题集中在：
  - 表格跨页或复杂表头重复展开
  - 表格列名前缀误混入单元格文本
  - Cover 内容明显不完整
  - 少数提示块与图片/列表的组合结构需要继续核对

## 已确认的人工修正优于自动结果的点

### 1. `Components`

自动结果文件：`/tmp/opencode/manual_compare/auto/DTC041009.dita`

人工结果文件：`/tmp/opencode/manual_compare/manual/DTC047196.dita`

现象：
- 自动结果把模块标题 `MGIEasy Whole Genome Methylation Sequencing Library Prep Module Cat. No.: 940-001529-00` 重复灌入了每一行物料内容。
- 人工结果保持为正常表格语义，模块名只作为分组标题出现一次。

判断：
- 人工结果更接近原始 Word。
- 自动结果属于表格合并格/跨行分组信息误下沉到数据行的问题。

### 2. `Workflow`

自动结果文件：`/tmp/opencode/manual_compare/auto/DTC041022.dita`

人工结果文件：`/tmp/opencode/manual_compare/manual/DTC047209.dita`

现象：
- 自动结果中间出现了一次重复表头：`Section Workflow Hands-on time (1 RXN) Total time (1 RXN)`。
- 人工结果将整个 workflow 表整理为连续表格，没有重复表头残留。
- 自动结果结尾少了 `Stop point.`。
- 根据原始 Word markdown，`Stop point.` 和图标确实存在。

判断：
- 自动结果这里存在遗漏。
- 人工结果对这个章节的处理更完整。

### 3. `Cleanup of adapter-ligated product`

自动结果文件：`/tmp/opencode/manual_compare/auto/DTC041047.dita`

人工结果文件：`/tmp/opencode/manual_compare/manual/DTC047234.dita`

现象：
- 自动结果在段首保留了两条提示内容：
  - `Do not disturb or pipette the beads when adding reagents or transferring supernatant...`
  - `The elution buffer in this cleanup step is NF Water.`
- 人工结果中这两条提示确实不存在。
- 人工结果把后面的 `Transfer all liquid to a new 1.5 mL centrifuge tube...` 改成了一个独立 `tip`。
- 原始 Word 和用户截图都确认这两条提示存在，且属于 `Tips + ul` 结构。

判断：
- 这两条提示以原始 Word 为准，应保留。
- 自动结果在内容存在性上更完整。
- 人工结果这里属于真实遗漏，并且把普通正文误改成了 `tip`。

### 4. `Barcode using guide (96 RXN)`

自动结果文件：`/tmp/opencode/manual_compare/auto/DTC041102.dita`

人工结果文件：`/tmp/opencode/manual_compare/manual/DTC047289.dita`

现象：
- 自动结果保留了 `refer to Appendix on page 51`。
- 人工结果改成了 `refer to Appendix`，去掉了页码。
- 按你之前的转换规则，页码不需要转换，IME 会自动生成。

判断：
- 人工结果更符合当前规则。
- 自动结果这里属于保留了不应带入 DITA 的页码信息。

### 5. `Shearing condition`

自动结果文件：`/tmp/opencode/manual_compare/auto/DTC041098.dita`

人工结果文件：`/tmp/opencode/manual_compare/manual/DTC047285.dita`

现象：
- 自动结果中出现了列名前缀污染，例如：
  - `S220 Vessel S220`
  - `S220 Sample Volume 55 μL`
  - `E220 Vessel E220`
  - `E220 Racks ...`
- 人工结果将这些内容还原成正常的表头与表格内容。

判断：
- 自动结果这里存在明显表格列标题串行污染问题。
- 人工结果更接近原始 Word。

### 6. `Cover`

自动结果文件：`/tmp/opencode/manual_compare/auto/CTT041001.dita`

人工结果文件：`/tmp/opencode/manual_compare/manual/CTT047290.dita`

现象：
- 自动结果 `Cover` 文件很短，和当前规则一致，主要复用模板 cover。
- 人工结果 `Cover` 长很多，说明人工包对封面 topic 本体填了更多内容。

判断：
- 这项需要按你的最终交付标准决定。
- 如果坚持当前规则“Cover 直接复用参考 zip 包原始 topic”，自动结果符合规则。
- 如果最终平台导入效果要求封面本体带更多源 Word 内容，则需要重新评估 cover 策略。

## 已确认自动结果优于人工结果的点

### `Cleanup of adapter-ligated product` 中的 `Tips + ul`

原始 Word 和截图确认存在：
- `Do not disturb or pipette the beads when adding reagents or transferring supernatant...`
- `The elution buffer in this cleanup step is NF Water.`

当前自动链路已经修复为 `note` 包裹 `ul` 的输出逻辑。

人工结果 XML 已确认未包含这两条内容。

最终判断：
- 自动结果内容更完整。
- 人工结果这一节存在遗漏。

## 当前已确认的自动结果错误/遗漏

1. `Workflow` 丢了 `Stop point.`。
2. `Workflow` 有重复表头残留。
3. `Components` 存在模块名重复注入每一行的问题。
4. `Shearing condition` 存在列头混入数据行的问题。
5. `Barcode using guide (96 RXN)` 仍保留页码 `page 51`。

## 本轮代码侧已完成的修复

1. 已在 `convert.py` 的表格输出阶段增加重复表头行过滤，目标覆盖 `Workflow` 中间重复表头问题。
2. 已在 `convert.py` 的表格输出阶段增加首列重复分组值压缩，目标覆盖 `Components` 和 `Shearing condition` 中由合并格下沉造成的首列污染问题。
3. 已在 `convert.py` 的正文与有序/无序列表输出路径增加 `on page N` 页码引用清洗，目标覆盖 `Barcode using guide (96 RXN)` 的 `page 51` 残留问题。
4. 已收窄 `Workflow <- Table 10 Workflow` 的同名表题内容回收规则，避免影响其他真实章节的 topic 数量与标题映射。
5. 已补充针对性单测并通过：`python3 -m unittest tests.test_convert_dita_generation`。

## 最新真实包验证结果

- 最新真实包：`/workspace/backend/static/uploads/outputs/output_20260813_132839.zip`
- 包级验收结果：`passed: true`
- 关键子项：
  - `titles_match.passed: true`
  - `images_not_lost.passed: true`
  - `table_titles_converted.passed: true`
  - `figure_titles_converted.passed: true`
  - `notes_converted.passed: true`
  - `ordered_lists_converted.passed: true`
  - `unordered_lists_converted.passed: true`

## 最新章节级结论

1. `Workflow`：自动结果已恢复到正确章节，重复表头已去除，章节本体不再为空。
2. `Components`：模块名重复灌入问题已明显改善，当前每个模块分组只在首行保留一次编号信息。
3. `Barcode using guide (96 RXN)`：`page 51` 已成功移除，文本变为 `refer to Appendix to select barcodes.`。
4. `Shearing condition`：首列污染已部分改善，但首个数据行仍保留一次 `S220 / Vessel`，属于剩余的表格细节问题。

## 仍待真实包复核的点

1. `Workflow` 的 `Stop point.` 目前仍需回到真实导出链路确认其最佳落点，当前没有做强行结构改写。
2. `Cleanup of adapter-ligated product` 的 `Tips + ul + note` 结构虽然内容完整性更高，结构细节仍有继续优化空间。
3. `Shearing condition` 首个数据行与表头重复的问题仍可继续细修。

## 当前已确认的人工结果风险点

1. `Cleanup of adapter-ligated product` 里的 `Tips + ul` 已确认被删掉。
2. `Cleanup of adapter-ligated product` 中 `Transfer all liquid...` 被误改成 `tip`。
3. `Cover` 是否超出既定规则，需要按最终交付口径确认。

## 建议的下一步核对顺序

1. 先复核 `Cleanup of adapter-ligated product` 的人工包 XML，确认 `Tips` 是否真的缺失。
2. 再以人工结果为目标，修自动链路中的三个表格类问题：
   - `Components`
   - `Workflow`
   - `Shearing condition`
3. 同步去掉所有章节中的页码残留，例如 `page 51`。
