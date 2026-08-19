# WorkBuddy Review

- Branch: 260803-feat-smart-polish
- Commit: 2fed158

## Findings

### P0

1. `frontend/src/views/Polish.vue`
- 问题：CAT 结果列表使用 `paragraphIndex` 作为 `v-for` key。同一段落拆成多句时 key 会重复，页面会丢卡片。
- 建议：改用 `sentenceIndex`，候选下拉项 key 也同步改为基于 `sentenceIndex`。

2. `backend/app/api/polish.py`
- 问题：AI 评分调用固定 `max_tokens=2000`，大文档候选多时 JSON 会被截断。
- 建议：按候选数量动态计算 `max_tokens`，并限制上限。

3. `backend/app/api/polish.py`
- 问题：`paragraph_texts` 缓存的是预处理后的文本，和 DOCX 原文段落可能不一致，影响 apply 段落定位。
- 建议：缓存原始段落文本用于写回映射，预处理文本单独保留。

### P1

4. `backend/app/api/polish.py`
- 问题：`_simple_match` 只用主模板文本，未展开候选变体。
- 建议：把 `_template_entry_candidates(...)` 也展开进入 CAT 召回，并做去重与总量限制。

5. `backend/app/api/polish.py`
- 问题：`jieba` 不可用时退化为逐字切分，词级匹配质量下降明显。
- 建议：fallback 改成中文 2-gram + 英文数字 token。

6. `backend/app/api/polish.py`
- 问题：无标点短句过滤阈值过高，表格或项目符号类短句会被跳过。
- 建议：把阈值从 18 放宽到 12。

7. `backend/app/api/polish.py`
- 问题：AI 评分一次性拼全部候选，长文档会超上下文窗口。
- 建议：按句子批次分批评分，单批失败不影响其他批次。

8. `backend/app/api/polish.py`
- 问题：同一段落多句替换时，后续替换可能基于已修改文本找不到原句。
- 建议：先按段落收集句子替换列表，再统一合并。

### P2

9. `backend/app/api/polish.py`
- 问题：`_cat_download_cache` 无清理机制。
- 建议：下载后即删除 token。

10. `backend/app/api/polish.py`
- 问题：无候选时 `_batch_ai_semantic_score` 返回 `None`。
- 建议：统一返回带 `status/error/scored_count` 的 dict。
