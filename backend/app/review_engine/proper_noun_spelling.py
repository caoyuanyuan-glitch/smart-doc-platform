"""专有名词拼写校验（SPELL-PROP）。

## 要解决的问题

普通拼写检查对**专有名词**几乎无效：

- `Intergra`（应为 `Integra`，某电子移液器品牌）——`Integra` 不在英文词典中，
  拼写库给出的候选是 `integral / intergrade / interwar`，全部是错的；
- 文档内也找不到 `Integra`（全文只有那 1 处 `Intergra`），
  所以「文档内词表」这条兜底路径同样失效。

这类问题的唯一可靠依据是**外部专有名词库**（本项目的白名单
`app/data/whitelist.json`）。有了它，「`Intergra` 应当写作 `Integra`」
就不再是猜测，而是可确证的事实。

## 判定依据（三重约束，缺一不可）

1. **白名单里存在该专有名词**（产品名/品牌名/专业术语等）；
2. **错拼词与规范名的编辑距离 ≤ 1**（多一个字母、少一个字母、
   换位一个字母、错一个字母）；
3. **该错拼词本身不是白名单词，也不是英文词典词**——
   否则说明它是另一个合法专有名词或普通词，不能判为错拼。

第 3 条是关键防线：`Integra` 这类词若自身已在白名单里，
就不该被当成 `Intergra` 的纠正目标去误伤真正的其他品牌。

## 为什么不用「模糊匹配」

早期直觉是「把文档里的词和白名单词做模糊匹配」——但这会产生大量
噪声：白名单里的 `MGI` 会匹配到 `MGI-100`、`MGISP`；`DNA` 会匹配到
`DNase`。本模块因此只认**编辑距离 ≤ 1 的单 token 近似**，
并且要求该 token 在文档中**不以白名单形态出现**。
"""

from __future__ import annotations

import json
import re
from functools import lru_cache


# 白名单中属于「专有名词」的分类。只有这些分类参与拼写纠错——
# 「科学术语」（E. coli / in vitro）本身不会拼错，
# 「文档编号」「货号」「版本号」也不适用编辑距离纠错。
_PROPER_CATEGORIES = {
    "产品名",
    "品牌名",
    "专业术语",
    "设备型号",
    "生化术语",
    "科学术语",
    "术语",
}

# 白名单里不参与拼写纠错的分类。
_IGNORED_CATEGORIES = {
    "文档编号",
    "版本号",
    "货号",
    "域名",
    "邮箱",
}

# 参与纠错的最小长度：短于 4 个字符的专有名词做编辑距离 1 匹配
# 误报率过高（`MGI` / `ID` / `CPU` 等），且这些词大多已在
# SPELLCHECK_WHITELIST 的精确表里被豁免。
_MIN_TOKEN_LENGTH = 4

# 单词边界：专有名词可能含连字符、斜杠、空格。
# 本模块只处理**单个 token**（不含空格），多词专有名词交给
# 文档内术语基线模块处理。
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def _whitelist_path() -> "object":
    """延迟导入路径解析，避免模块级循环依赖。"""
    from app.paths import WHITELIST_FILE

    return WHITELIST_FILE


@lru_cache(maxsize=1)
def _load_proper_nouns() -> tuple[frozenset[str], frozenset[str]]:
    """加载白名单中的专有名词。

    返回 (专有名词集合, 白名单全词集合)：
    - 专有名词集合用于「应该改成什么」；
    - 白名单全词集合用于「这个词本身是不是合法的」。

    结果做缓存：白名单是运行期可编辑的数据文件，但拼写检查
    是逐段调用的，不能每次都读盘。
    """
    try:
        path = _whitelist_path()
        if not path.exists():
            return frozenset(), frozenset()
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return frozenset(), frozenset()

    proper: set[str] = set()
    all_words: set[str] = set()

    for items in (data or {}).values():
        for item in items or []:
            word = str(item.get("word") or "").strip()
            if not word:
                continue
            all_words.add(word)
            category = str(item.get("category") or "").strip()
            if category in _IGNORED_CATEGORIES:
                continue
            if category and category not in _PROPER_CATEGORIES:
                continue
            # 只取单 token 的专有名词；多词短语（含空格）不参与
            # 编辑距离纠错——那是「术语写法不统一」的范畴。
            if " " in word or not _TOKEN_RE.fullmatch(word):
                continue
            if len(word) < _MIN_TOKEN_LENGTH:
                continue
            proper.add(word)

    return frozenset(proper), frozenset(all_words)


def reload_proper_nouns() -> None:
    """清空缓存，用于白名单热更新后立即生效。"""
    _load_proper_nouns.cache_clear()


def _edit_distance_at_most_one(a: str, b: str) -> bool:
    """判断两个等长相近的词之间编辑距离是否 ≤ 1。

    只处理长度差 ≤ 1 的情况——编辑距离 ≥ 2 的相似度不足以
    支撑「确证」，容易把不同专有名词判成同一个。
    """
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if a == b:
        return False

    # 等长：只能是一次替换，或相邻两位换位
    if la == lb:
        diffs = [i for i in range(la) if a[i] != b[i]]
        if len(diffs) == 1:
            return True
        if len(diffs) == 2 and diffs[1] == diffs[0] + 1:
            i = diffs[0]
            return a[i] == b[i + 1] and a[i + 1] == b[i]
        return False

    # 长度差 1：短的一方删掉一个字符后必须完全相等
    if la > lb:
        a, b = b, a
        la, lb = lb, la
    i = j = 0
    skipped = False
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        if skipped:
            return False
        skipped = True
        j += 1
    return True


def _is_dictionary_word(token: str) -> bool:
    """安全地查询英文词典（词典对象可能不支持成员判定）。"""
    try:
        from app.utils.spell_checker import _is_dictionary_word as _impl

        return bool(_impl(token))
    except Exception:
        return False


def _singular_candidates(token: str) -> list[str]:
    """生成 token 的单数候选形式。

    专有名词常以复数形式被收录（RNA -> RNAs），若错拼词的**单数形式**
    已在白名单里，说明这个 token 本身是合法的复数用法，不是错拼。
    """
    lower = (token or "").lower()
    candidates = []
    if lower.endswith("ies") and len(lower) > 3:
        candidates.append(lower[:-3] + "y")
    if lower.endswith(("ses", "xes", "zes", "ches", "shes")):
        candidates.append(lower[:-2])
    if lower.endswith("s") and not lower.endswith("ss") and len(lower) > 1:
        candidates.append(lower[:-1])
    return candidates


def _is_legal_plural_form(token: str, whitelist_lower: set[str]) -> bool:
    """判断 token 是否是白名单词的合法复数/大小写变体。

    `DNAs` 的单数 `DNA` 在白名单里 -> `DNAs` 合法，不能判成 `RNAs` 的错拼。
    """
    for candidate in _singular_candidates(token):
        if candidate in whitelist_lower:
            return True
    return False


def _is_line_wrap_artifact(token: str, correct: str, content: str) -> bool:
    """判断错拼词是否为 PDF 折行造成的片段。

    PDF 文本层常把 `DNBSEQ-G99RS` 折成 `NBSEQ-G99RS`（首字母 D 被甩到上一行）。
    这类"错拼词"其实是正确写法的真子串，且正确写法在文档别处完整出现过。

    与真正的拼写错误区分开：`Intergra` 不是 `Integra` 的子串，
    因此不受此规则影响。
    """
    correct_lower = correct.lower()
    token_lower = token.lower()
    if len(token_lower) >= len(correct_lower):
        return False
    if token_lower not in correct_lower:
        return False
    # 正确写法在文档中确实完整出现过（说明它是真实内容，不是我们臆造的）
    return bool(re.search(re.escape(correct_lower), content.lower()))


def _is_derived_form(token: str, proper_nouns: frozenset[str]) -> bool:
    """判断 token 是否是某个白名单专有名词的**派生形态**。

    白名单术语加上额外字符构成的词（`Oligo` -> `OligoX`）是另一个
    产品/试剂名，不是 `Oligo` 的错拼。判据是**词首延伸**：
    token 以白名单词开头且多出字符。

    这个判据不会伤到真正的错拼：
    - `Intergra` 不是 `Integra` 的前缀延伸（首字符就不同）；
    - `Integra` -> `Integrate` 虽成立，但 `Integrate` 是英文词典词，
      早已被词典防线拦下。
    """
    lowered = token.lower()
    for proper in proper_nouns:
        p = proper.lower()
        if len(lowered) > len(p) and lowered.startswith(p):
            # 多出的部分必须是字母/数字后缀（`OligoX`），
            # 若是完整单词（`Oligo seq`）则不是派生形态。
            tail = lowered[len(p):]
            if tail.isalnum():
                return True
    return False


def _dictionary_can_correct(token: str, correct: str) -> bool:
    """判断普通拼写库的候选里是否已经包含**完全正确**的写法。

    拼写库对 `intergra` 给出的候选正是 `integra`——但这是**大小写错误**
    的建议（正确写法是 `Integra`），因此不能算"已能纠正"。

    而 `oligox` 的候选是 `oligo`（`OligoX` 是独立产品名，并非 `Oligo`
    的错拼），候选中不含正确写法，同样需要本规则接手。

    判据取严：**候选必须与规范名完全一致（区分大小写）**。这样：
    - `intergra` -> 候选 `integra` != `Integra` -> 本规则接管，
      给出带正确大小写的建议；
    - `oligox` -> 候选 `oligo` != `Oligo` -> 本规则接管，但白名单里
      `Oligo` 会被 `oligox` 距离 1 命中——由下面的派生词防线处理。

    拼写库不可用时（未安装 / 桩实现）返回 False，交给本规则处理，
    宁可多报一条也不漏掉真实错误。
    """
    try:
        from app.utils.spell_checker import spell
    except Exception:
        return False

    try:
        candidates = spell.candidates(token)
    except Exception:
        return False

    if not candidates:
        return False

    return any(str(c) == correct for c in candidates)


def find_proper_noun_spelling_issues(
    content: str,
    *,
    file_type: str | None = None,
    min_word_length: int = 3,
) -> list[dict]:
    """检出「专有名词错拼」（SPELL-PROP）。

    例：`Intergra` → `Integra`。
    """
    if not content:
        return []

    proper_nouns, whitelist_words = _load_proper_nouns()
    if not proper_nouns:
        return []

    # 白名单词（含多词短语）的小写形式，用于判断「这个词本身合法吗」
    whitelist_lower = {w.lower() for w in whitelist_words}

    issues: list[dict] = []
    seen: set[tuple[str, int]] = set()

    for match in _TOKEN_RE.finditer(content):
        token = match.group(0)
        if len(token) < max(min_word_length, _MIN_TOKEN_LENGTH):
            continue

        lowered = token.lower()

        # 已经是白名单词（含其大小写变体）→ 合法，不报
        if lowered in whitelist_lower:
            continue
        # 白名单词的合法复数形式（DNAs / RNAs）→ 合法，不报
        if _is_legal_plural_form(token, whitelist_lower):
            continue
        # 已在白名单精确表里的技术术语/缩写 → 合法
        try:
            from app.utils.spell_checker import is_whitelisted

            if is_whitelisted(token):
                continue
        except Exception:
            pass
        # 英文词典里的普通词 → 合法
        if _is_dictionary_word(lowered):
            continue

        # 找编辑距离 ≤ 1 的规范专有名词
        candidates = [
            proper for proper in proper_nouns
            if _edit_distance_at_most_one(lowered, proper.lower())
        ]
        if not candidates:
            continue

        # 多个候选时无法确定正确写法，不报（宁可漏报也不误报）
        if len(candidates) > 1:
            continue

        correct = candidates[0]
        # 纠正目标本身必须与原词大小写形态相容：
        # `Integra` 与 `integra` 只差大小写时不算拼写错误。
        if correct.lower() == lowered:
            continue
        # **普通拼写库已能纠正的词，不在本规则重复上报**。
        #
        # 拼写库对 `intergra` 给出的候选正是 `integra`（正确），
        # 对 `oligox` 给出的候选是 `oligo`（错误——`OligoX` 是独立产品名）。
        # 判据：候选里含正确写法 -> 普通 SPELL 规则已能处理，重复报会
        # 让同一处出现两条问题；候选里不含正确写法 -> 只有专有名词库
        # 才能确证，此时才由本规则出手。
        if _dictionary_can_correct(lowered, correct):
            continue
        # **派生形态不属于专有名词错拼**：白名单术语加上后缀构成的词
        # （`Oligo` -> `OligoX`）是另一个产品/试剂名，不是 `Oligo` 的
        # 错拼。这类词交由普通 SPELL 规则处理。
        if _is_derived_form(token, proper_nouns):
            continue
        # PDF 折行伪影：错拼词是正确写法的真子串 → 不是拼写错误
        if _is_line_wrap_artifact(token, correct, content):
            continue

        dedupe_key = (lowered, match.start())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        try:
            from app.utils.spell_checker import (
                _build_spelling_context,
                _extract_chapter,
                _format_spelling_suggestion,
            )

            context = _build_spelling_context(content, match.start(), match.end())
            chapter = _extract_chapter(content, match.start())
            suggestion = _format_spelling_suggestion(token, context, [correct], "确定")
        except Exception:
            context = content[max(0, match.start() - 90):match.end() + 90]
            chapter = ""
            suggestion = correct

        issues.append({
            "severity": "serious",
            "category": "拼写/用词错误",
            "rule": "SPELL-PROP",
            "chapter": chapter,
            "original_text": token,
            "context": context,
            "suggestion": suggestion,
            "description": (
                f"原文片段：'{context}'；[{token}] 与专有名词库中的"
                f"[{correct}] 仅相差一个字符，且 [{token}] 既不在专有名词库中，"
                f"也不在英文词典中，判定为专有名词拼写错误；"
                f"建议修改为：[{correct}]。"
            ),
            "audit_basis": "专有名词拼写规范",
            "confidence": 96,
            "source": "spellcheck",
            "position": f"{match.start()}-{match.end()}",
        })

    return issues
