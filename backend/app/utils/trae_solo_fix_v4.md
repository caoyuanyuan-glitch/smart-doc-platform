# Trae Solo 优化指令 V4 — 基于最新对比报告（compare_report_27）

## 一、已修复的问题（无需再改）

| 问题 | 状态 |
|:----|:----|
| 汇总卡片数据异常 | ✅ 已修复（完全一致16/高度相似6/部分相似7/差异较大27） |
| 培训建议不具备普适性 | ✅ 已删除，改为复核建议 |
| 差异说明模板化 | ✅ 已改为具体标注 |
| 严重程度标记 | ✅ 已添加 🔴🟠🟢🔵 标签 |
| 措辞调整过度拆分 | ✅ 已改善（Site requirements 从12条降到6条） |

## 二、仍需修复的问题

### 问题：差异行重复（🟡 一般）

**现象：** 仍有 **5组** 完全相同的 diff 行被重复列出：

```
×2: 🔴 A → B "Otherwise, it may cause altered experimental results..."
×2: 🟢 措辞调整 "Follow the safety standards of your laboratory..."
×2: 🔴 A → B "If the requirements above are not met, the device must..."
×4: 🔵 A 独有 "Let the device air-dry."
×2: 🔵 B 独有 "Let the parts air-dry."
```

**根因：** 同一个 diff 内容被多次匹配到不同的句段对中，去重逻辑不彻底。

**修复：** 在生成 diff 行之前进行内容去重，完全相同的内容只保留一条。

```python
def deduplicate_diff_rows(diff_rows):
    """对 diff 行进行去重"""
    seen = set()
    unique_rows = []
    for row in diff_rows:
        # 提取纯文本内容作为去重键
        text = re.sub(r'<[^>]+>', '', row).strip()
        key = text[:200]  # 取前200字符作为键
        if key not in seen:
            seen.add(key)
            unique_rows.append(row)
    return unique_rows
```

## 三、修改清单

| 优先级 | 问题 | 修复内容 |
|:----:|:----|:--------|
| 🟡 P1 | **差异行重复** | 完全相同的内容去重，只保留一条 |
