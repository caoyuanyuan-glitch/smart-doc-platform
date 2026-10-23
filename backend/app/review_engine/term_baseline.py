"""文档内术语基线比对（DET-TERM-BASELINE-001）。

## 要解决的问题

人工审核里最常见的一类文字问题不是"拼错字母"，而是**同一个概念在
文档里出现了两种写法**：

- 目录写 `Sequencing Reagent Set`，正文写 `sequencing set`；
- 缩写表写 `PE | Pair-end sequencing`，正文写 `pair-end`。

这类问题靠外部词典查不出来（两处都"合法"），只能靠**文档自身
建立起来的基线**来判定。

## 判定依据

本模块只上报**有确定文档内证据**的三类事实，不做任何主观推断：

1. **产品目录建立的「型号 → 规范产品名」映射**。
   文档的产品目录里通常有一张表，形如
   `Sequencing Reagent Set | SR-xxxx`，
   于是"型号"就与"规范产品名"绑定。若正文出现
   `sequencing set`（缺少 `Reagent`），而全文的
   `Sequencing Reagent Set` 出现 N 次且"sequencing set"只出现 M 次
   （M ≪ N），则可确定正文用的是简写而非规范名。

2. **同一术语的「大小写变体」基线**。
   统计同一词的各书写形态，若某形态是少数派（且全文不存在其小写形态），
   则该少数派写法偏离了文档自身基线。

3. **同一术语的「单复数/词形」基线**。
   只在无歧义时上报（见 `_is_legal_morphology`）。

## 明确不做的事

- 不比较"哪个更规范"——本模块只报告"存在两种写法"这一客观事实，
  建议统一为文档内多数写法。
- 不跨标准体系比较（不同体系的标准名本来就不同）。
- 不因"全文未出现某写法"就判定为错误——那需要外部知识库。
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict


# 规范产品名 → 常见简写候选的构造规则。
# 只匹配"规范名去掉中间词"这类**确定性的缩写**，
# 不做模糊匹配，避免把不同概念合并。
_ABBREVIATION_DROP_WORDS = ("Reagent", "Flow Cell", "Kit", "Cartridge", "Package")

# 同一种偏离写法的上报上限：既要让正文里的每一处都能被标出，
# 又不能让同一问题在全篇刷屏。
_MAX_REPORTS_PER_PATTERN = 6


def _encode_position(start: int, end: int, **meta) -> str:
    payload = {"start": start, "end": end, "area": meta.pop("area", "正文")}
    payload.update({key: value for key, value in meta.items() if value not in (None, "", [], {})})
    return json.dumps(payload, ensure_ascii=False)


def _page_at(text: str, offset: int) -> int:
    return text[: max(0, offset)].count("\f") + 1


def _context(text: str, start: int, end: int, radius: int = 70) -> str:
    return re.sub(r"\s+", " ", text[max(0, start - radius):min(len(text), end + radius)]).strip()


def _issue(rule, text, start, end, original, description, suggestion,
           *, category="术语一致性", severity="general", confidence=86,
           audit_basis="文档内术语基线", chapter=""):
    return {
        "severity": severity,
        "category": category,
        "rule": rule,
        "chapter": chapter,
        "original_text": original,
        "context": _context(text, start, end),
        "suggestion": suggestion,
        "description": description,
        "audit_basis": audit_basis,
        "confidence": confidence,
        "source": "rule",
        "status": "pending",
        "position": _encode_position(start, end, page=_page_at(text, start), area="正文"),
    }


# ----------------------------------------------------------------------
# 术语形态统计
# ----------------------------------------------------------------------

# 大小写形态归一：把词统一成小写序列，用于判断"是不是同一个词"。
_CASELESS_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9]+")

# 普通英文功能词：它们的大小写由句首语法决定，不是术语写法问题。
_NON_TERM_CASELESS = frozenset("""
the and but for nor yet so if then else when while what which who whom whose that this
these those there here all any both each few more most other some such only own same
data information detail details item items text number value time date day year
""".split())


def _caseless_key(term: str) -> str:
    """把术语折叠为"忽略大小写与词边界"的比较键。

    `Sequencing Reagent Set` 与 `sequencing set` 的键分别是
    `sequencingreagentset` 与 `sequencingset`——不同，说明它们是
    两种不同写法而不是大小写差异。

    `Pair-end` 与 `pair-end` 的键相同 `pairend`——说明只是大小写差异。
    """
    return "".join(part.lower() for part in _CASELESS_RE.findall(term or ""))


def _collect_canonical_names(text: str) -> dict[str, int]:
    """收集文档内作为"规范产品名"使用的大写多词术语及其出现次数。

    判据：3 个及以上单词、每个词首字母大写、且在文档中重复出现。
    这类术语是文档自己建立的基线（如 `Sequencing Reagent Set`）。

    **只在同一行内匹配**：PDF 文本层会把相邻行用空行拼在一起，
    若允许跨行，`Sequencing Reagent Set` 会与下一行的
    `V2.0 8.0` 之类粘成一个假术语，计数被稀释到阈值以下，
    反而把真实的规范名挤出基线。
    """
    counter: Counter[str] = Counter()
    pattern = re.compile(
        r"\b(?:[A-Z][a-z]+)(?:[^\S\n]+(?:[A-Z][a-z]+)){2,}\b"
    )
    for match in pattern.finditer(text or ""):
        counter[match.group(0)] += 1
    return dict(counter)


# 界面字段标签的判定：候选写法后紧跟这些词时，它是界面上的字段名
# （`Sequencing Cartridge ID`、`Cartridge type`），指的是界面元素，
# 与产品目录里的产品名不是同一个对象，不能报"写法不统一"。
_UI_FIELD_SUFFIX_RE = re.compile(
    r"^\s*(?:ID|Ids|Type|type|Type\s*:|No\.?)\b"
)

# 产品目录表的标题行：出现这些表名说明该页是"产品/组件清单"，
# 目录里列出的名称就是文档确立的规范名。
#
# 大小写不敏感：真实文档里的标题是 `Table 1 Available sequencing sets`
# （小写 s），若要求大写 `Set`，目录页会整页漏判，
# 规范名就永远拿不到"在目录页出现"的资格。
_CATALOG_TABLE_RE = re.compile(
    r"Table\s+\d+\s+(?:Available\s+)?[A-Za-z][^\n]{0,80}?"
    r"(?:Set|Cartridge|Cell|Pack|Product|Reagent|Kit)s?\b",
    re.IGNORECASE,
)


def _collect_catalog_pages(text: str) -> set[int]:
    """找出所有「产品目录表」所在的物理页。

    只有在产品目录里列出的名称，才具备"规范名"资格。
    这是排除误报的关键：界面字段标签（如 `Sequencing Cartridge ID`、
    `Cartridge type`）也会被简写成 `sequencing cartridge`，但它
    根本不是产品名，两者是不同对象。
    """
    pages = set()
    offset = 0
    for page_text in (text or "").split("\f"):
        if _CATALOG_TABLE_RE.search(page_text or ""):
            pages.add(offset)
        offset += 1
    return pages


def _in_catalog_page(text: str, position: int) -> bool:
    """判断某个字符偏移是否落在产品目录页内。"""
    page_index = text[: max(0, position)].count("\f")
    return page_index in _collect_catalog_pages(text)


def _abbreviation_candidates(canonical: str) -> list[str]:
    """由规范产品名构造其"去中间词"简写候选。

    `Sequencing Reagent Set` -> [`Sequencing Set`, `Sequencing`]
    只保留去词后仍有 2 个词以上的候选，避免退化成过泛的单���。
    """
    words = canonical.split()
    candidates = []
    for drop in _ABBREVIATION_DROP_WORDS:
        if drop not in words:
            continue
        rest = [w for w in words if w != drop]
        if len(rest) >= 2:
            candidates.append(" ".join(rest))
    return candidates


def _is_legal_morphology(short: str, full: str) -> bool:
    """判断短写法与全写法之间是否存在合法的英语形态关系。

    复数（set/sets）、进行时、过去式都属于合法差异，
    不能当成"简写不统一"报出去。
    """
    s, f = short.casefold(), full.casefold()
    if s == f:
        return True
    short_w, full_w = s.split(), f.split()
    if len(short_w) != len(full_w):
        return False
    for a, b in zip(short_w, full_w):
        if a == b:
            continue
        if b == a + "s" or b == a + "es":
            continue
        if b == a + "d" and a.endswith("e"):
            continue
        if a == b + "s":
            continue
        return False
    return True


def _is_ui_field_label(text: str, end: int) -> bool:
    """判断该处写法是否是界面字段标签而非产品名引用。

    `Sequencing Cartridge ID`、`Cartridge type` 这类写法指的是
    软件界面上的字段/选项，与产品目录里的 `Sequencing Reagent Cartridge`
    是不同对象，不能按"写法不统一"上报。
    """
    tail = text[end:end + 24]
    if _UI_FIELD_SUFFIX_RE.match(tail):
        return True
    # 界面提示语（`selected Sequencing cartridge!`、`Cartridge in place`）
    line_start = text.rfind("\n", 0, end) + 1
    line = text[line_start:text.find("\n", end) if text.find("\n", end) > 0 else len(text)]
    if re.search(r"(?i)\bselected\b|\bin\s+place\b|\btype\s*:", line):
        return True
    return False


# 型号串：含数字或斜杠的全大写 token 组，
# 如 `G99`、`FCL`、`SE100/PE50`、`FCS/FCU/FCX SE100`。
_MODEL_TOKEN_RE = re.compile(
    r"\b(?:[A-Z]{2,}[A-Z0-9]*|[A-Z]{2,}\d+[A-Z0-9]*)"
    r"(?:\s*/?\s*(?:[A-Z]{2,}[A-Z0-9]*|[A-Z]{2,}\d+[A-Z0-9]*))*"
)


def _has_model_prefix(text: str, start: int) -> bool:
    """判断该处写法前面是否紧邻产品型号串。

    只有「型号 + 简写」才是对产品的**具体引用**（`G99 FCL SE100/PE50
    sequencing set`），而泛指用法（`the sequencing set`、
    `sequencing sets overview`）不是——后者指的是"这套试剂"这个泛概念，
    用简写并不构成错误。

    这个判据是"同一文档内两种写法"与"简写是正常用法"的分界线。
    """
    prefix = text[max(0, start - 60):start]
    for model in _MODEL_TOKEN_RE.findall(prefix):
        # 型号必须含数字或斜杠，否则 `The`/`Available` 之类也会被算进去
        if re.search(r"\d", model) or "/" in model:
            return True
    return False


def _find_terminology_baseline_issues(text: str, *, parsed: bool = True) -> list[dict]:
    """比对文档内同一概念的不同写法（DET-TERM-BASELINE-001）。"""
    source = str(text or "")
    if not parsed or not source.strip():
        return []

    canonical_counts = _collect_canonical_names(source)
    if not canonical_counts:
        return []

    issues: list[dict] = []
    reported_positions: set[int] = set()
    catalog_pages = _collect_catalog_pages(source)

    # 按出现次数降序，优先以出现最多的规范名为基线
    ordered = sorted(
        ((name, cnt) for name, cnt in canonical_counts.items() if cnt >= 3),
        key=lambda item: -item[1],
    )

    for canonical, canonical_count in ordered:
        # 规范名必须在产品目录中出现过，否则它只是"文中一处大写词"，
        # 不具备基线资格（例如界面标签 `Sequencing Cartridge ID`）。
        canonical_pattern = re.compile(
            re.escape(canonical).replace(r"\ ", r"\s+"))
        canonical_hits = list(canonical_pattern.finditer(source))
        if not any(
            source[:m.start()].count("\f") in catalog_pages
            for m in canonical_hits
        ):
            continue

        for candidate in _abbreviation_candidates(canonical):
            key_canonical = _caseless_key(canonical)
            if _caseless_key(candidate) == key_canonical:
                continue

            # 统计候选写法在全文的出现次数与形态
            pattern = re.compile(re.escape(candidate).replace(r"\ ", r"\s+"), re.IGNORECASE)
            hits = list(pattern.finditer(source))
            if not hits:
                continue

            # 候选写法的词数必须少于规范名，否则不是"简写"关系
            if len(candidate.split()) >= len(canonical.split()):
                continue

            # 合法形态关系（复数等）不报
            if _is_legal_morphology(candidate, canonical):
                continue

            # 少数派才报：候选出现次数应显著少于规范名。
            #
            # 比较口径必须与上报口径一致——都用"**带型号前缀的产品引用**"，
            # 不能用全文总次数。泛指用法（`A sequencing set includes a
            # Sequencing Flow Cell`）不是对产品的具体引用，若计入总数，
            # 候选的全文计数会超过规范名，导致真正该报的三处
            # （`G99 FCL SE100/PE50 sequencing set can perform ...`）
            # 反而被少数派门槛挡掉。
            canonical_refs = sum(
                1 for m in canonical_hits if _has_model_prefix(source, m.start())
            )
            candidate_refs = sum(
                1 for m in hits if _has_model_prefix(source, m.start())
            )
            if candidate_refs >= canonical_refs:
                continue

            # 逐处上报偏离基线的写法。只报首处会让正文里的实际错误
            # 全部漏掉（首处往往在目录页，而人工批注标在正文）。
            # 上限用于防止同一问题刷屏。
            reported_for_candidate = 0
            for match in hits:
                if reported_for_candidate >= _MAX_REPORTS_PER_PATTERN:
                    break
                surface = match.group(0)
                surface_key = _caseless_key(surface)
                if surface_key == key_canonical:
                    continue
                if match.start() in reported_positions:
                    continue
                # 界面字段标签（`Sequencing Cartridge ID`）指的是界面元素，
                # 与产品目录里的产品名不是同一个对象，不属于写法不统一。
                if _is_ui_field_label(source, match.end()):
                    continue
                # 泛指用法（`the sequencing set`、`sequencing sets overview`）
                # 不是对产品的具体引用，不报。
                if not _has_model_prefix(source, match.start()):
                    continue
                reported_positions.add(match.start())
                reported_for_candidate += 1
                issues.append(_issue(
                    "DET-TERM-BASELINE-001", source, match.start(), match.end(), surface,
                    f"本文档产品目录中的规范名称为 `{canonical}`"
                    f"（全文出现 {canonical_count} 次），"
                    f"但此处写作 `{surface}`（该写法全文出现 {len(hits)} 次）。"
                    f"同一产品/概念存在两种写法，会影响检索与跨文档比对。",
                    f"建议统一为 `{canonical}`。",
                    severity="general",
                    confidence=88,
                ))

    return issues


def _find_case_variant_issues(text: str, *, parsed: bool = True) -> list[dict]:
    """同一术语的少数派大小写写法（DET-TERM-CASE-001）。

    只有当少数派形态**在全文找不到其小写形式**时才有确定证据：
    说明文档自身已确立了"该术语应大写"的基线。

    以下情形不报：
    - 普通英文功能词（the/data/when/…）——它们的大小写由句首语法决定，
      不是术语写法问题；
    - 全大写的安全警示标记（WARNING/CAUTION/NOTICE）——那是**有意的
      视觉强调**，不是写法不一致；
    - 两种形态频次接近——无法确定哪个是基线。
    """
    source = str(text or "")
    if not parsed or not source.strip():
        return []

    # 统计每个「忽略大小写键」的形态分布
    by_key: dict[str, Counter[str]] = defaultdict(Counter)
    for match in re.finditer(r"\b[A-Z][A-Za-z]{2,}(?:[-–—][A-Za-z]+)?\b", source):
        surface = match.group(0)
        by_key[_caseless_key(surface)][surface] += 1

    issues = []
    for key, counter in by_key.items():
        if len(counter) < 2:
            continue
        # 普通功能词不是术语
        if key in _NON_TERM_CASELESS:
            continue
        majority_surface, majority_count = counter.most_common(1)[0]
        # 全大写形态是有意的视觉强调，不作为基线
        if majority_surface.isupper():
            continue
        for surface, count in counter.most_common()[1:]:
            # 少数派必须显著少于多数派
            if count >= majority_count:
                continue
            # 少数派必须没有小写形态（即全文无小写变体）
            lowered = surface.lower()
            if any(s != s.lower() and s.lower() == lowered for s in counter):
                continue
            # 少数派本身是全大写强调标记，不报
            if surface.isupper():
                continue
            # 差异必须只体现在大小写
            if surface.casefold() != lowered:
                continue
            match = re.search(re.escape(surface), source)
            if not match:
                continue
            issues.append(_issue(
                "DET-TERM-CASE-001", source, match.start(), match.end(), surface,
                f"本文档中该术语以 `{majority_surface}` 为主（{majority_count} 次），"
                f"此处写作 `{surface}`（全文 {count} 次），且全文没有其小写形式。"
                f"同一术语的大小写不统一。",
                f"建议与全文多数写法保持一致：`{majority_surface}`。",
                category="术语大小写一致性",
                confidence=84,
            ))
            break

    return issues


def check_term_baseline(text: str, *, parsed: bool = True) -> list[dict]:
    """文档内术语基线比对入口。"""
    issues = _find_terminology_baseline_issues(text, parsed=parsed)
    issues.extend(_find_case_variant_issues(text, parsed=parsed))
    return issues
