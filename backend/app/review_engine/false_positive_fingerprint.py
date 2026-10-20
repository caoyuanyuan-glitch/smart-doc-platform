"""结构化误报指纹：让人工裁定的预置误报记忆真正可命中引擎产出。

## 为什么需要这个模块

历史实现把误报记忆存成精确签名 `rule|category|original_text`，
预置条目（`FP-V1-001` 等）里 `rule` 字段填的是**记忆条目 ID**，
`original_text` 填的是**规则说明文字**；而真实 issue 的 `rule` 是引擎规则号
（如 `R011`、`DOC-GRAM-001`），`original_text` 是**问题片段原文**。

两侧第 1 段与第 3 段结构根本不同，签名永不相交 —— 实测 7 条预置条目命中 0 条。
也就是说 `误报过滤规则库_v1` 里那 12 条人工经验，在预置层面从未生效过。

真正在起作用的是 `false_positives.py` 里的结构化匹配器，与本模块无关。

## 本模块做什么

不改任何规则逻辑、不整类删除 rule，只做一件事：
给预置误报条目补上**可被引擎 issue 匹配的结构化指纹**（rule_family +
归一化问题片段特征 + 上下文特征 + 文档类型/语言），
让"人工裁定过一次 → 后续同类问题自动标记疑似误报"这条链路真正闭合。

命中判定全部走**结构化证据**，不使用"整类删除规则"这种激进手段。
"""

from __future__ import annotations

import re
from typing import Any


# ----------------------------------------------------------------------
# 归一化
# ----------------------------------------------------------------------

# 归一化时需要抹平的差异：全角/半角、引号种类、连字符种类、
# 以及 PDF 文本层常见的重复空格。这些差异会让同一个问题在两次审核里
# 产生完全不同的字符串，是精确签名失效的直接原因。
_QUOTE_MAP = {
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "「": '"', "」": '"', "『": '"', "』": '"',
}
_DASH_MAP = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": "-", "―": "-", "−": "-",
}


def normalize_fragment(text: Any) -> str:
    """把问题片段归一到稳定形式，抹平纯排版差异但保留语义。"""
    value = str(text or "")
    for src, dst in _QUOTE_MAP.items():
        value = value.replace(src, dst)
    for src, dst in _DASH_MAP.items():
        value = value.replace(src, dst)
    value = re.sub(r"\s+", " ", value)
    return value.strip().casefold()


# 词干化时必须保留的后缀：这些词去掉尾字母后词义会变
# （ss -> class/glass，us -> status/focus，is -> this/analysis）。
_NO_STRIP_SUFFIX = ("ss", "us", "is", "os", "as")


def _stem_token(token: str) -> str:
    """极简英文词干化，只抹平词形变化，不做语义分析。

    人工重述同一个问题时最常见的改动就是换词形（min/mins、
    wash/washes、load/loaded），不做归一的话覆盖相似度会直接掉到阈值以下。
    刻意不用 Porter 这类完整词干算法——它会把 min 砍成 mi 这种无意义残片，
    反而制造假相似。
    """
    if not token.isascii():
        return token
    value = token
    # 只在剥离后仍至少剩 3 个字符时才做，避免 using -> us、aged -> ag 这类残片。
    if len(value) > 4 and value.endswith("ies"):
        return value[:-3] + "y"
    if len(value) > 5 and value.endswith("ing"):
        return value[:-3]
    if len(value) > 5 and value.endswith("ed"):
        return value[:-2]
    if len(value) > 4 and value.endswith("es") and not value.endswith(_NO_STRIP_SUFFIX):
        return value[:-2]
    if len(value) > 3 and value.endswith("s") and not value.endswith(_NO_STRIP_SUFFIX):
        return value[:-1]
    return value


def _tokens(text: Any) -> list[str]:
    """中英文混合分词：英文按词并轻量词干化，中文按字。

    中文没有空格边界，若整体作为一个 token 则"改一个字"就会让指纹失效；
    按字切分可以让"同段落出现同样的字"成为较稳定的匹配依据。
    """
    value = normalize_fragment(text)
    return [
        _stem_token(tok)
        for tok in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", value)
        if tok
    ]


def _content_tokens(text: Any) -> set[str]:
    """只保留信息量较高的 token（英文词长>=3、单个汉字不计入）。"""
    return {tok for tok in _tokens(text) if (tok.isascii() and len(tok) >= 3) or len(tok) >= 2}


# 高频功能词/英文停用词：这些词几乎出现在任何问题里，
# 拿它们做指纹会让"换个措辞"退化成"任意问题都命中"。
_STOPWORDS = frozenset("""
the a an and or of to in for on at by with from is are was were be been being this that these those
it its as not no but if then than so such use used using add adds adding new please should would
can could may might must shall will do does did done get gets got set sets setting
into onto upon about above below between within without more most less least other others
""".split())


def _salient_tokens(text: Any) -> set[str]:
    """信息 token = 内容 token 去掉高频功能词。"""
    return {tok for tok in _content_tokens(text) if tok not in _STOPWORDS}


# ----------------------------------------------------------------------
# 规则族归一
# ----------------------------------------------------------------------

# 引擎规则号 -> 稳定的规则族标签。
# 用族而不是精确 rule ID 做匹配，是因为同一条人工经验通��对应一整族规则
# （例如"单复数/单位类"覆盖 R011、R023 等多条），逐条维护成本高且易漏。
RULE_FAMILY_RULES: dict[str, tuple[str, ...]] = {
    "pdf_text_layer_artifact": (
        "R024", "DOC-PDF-DUP", "DOC-ARROW", "DOC-LIGATURE",
        "R046", "DOC-QUOTE-MAP", "DOC-HYPHEN",
    ),
    "spacing_format": (
        "DOC-GRAM-001", "DOC-SPACE", "DOC-FORMAT", "R025", "R027", "R046",
        "DOC-INDENT", "DOC-ALIGN",
    ),
    "unit_plural": ("R011", "R023", "DOC-UNIT"),
    "list_numbering": ("DOC-NUM-001", "DOC-LIST", "DOC-ORDER"),
    "reference_numbering": ("REF-001", "REF-002", "REF-003", "DOC-REF"),
    "terminology_consistency": (
        "CYY-CN-CONSIST-001", "CYY-CN-CONSIST-002", "CYY-TERM-001",
        "DOC-TERM-001", "DOC-TERM", "DOC-SPELL-001", "DOC-PROPER",
    ),
    "trademark_symbol": ("DOC-TM", "R033", "DOC-TRADEMARK"),
    "contact_info": ("DOC-CONTACT", "DOC-MAIL", "DOC-PHONE"),
    "blank_separator_page": ("DOC-PAGE-001", "DOC-BLANK", "DOC-PAGE"),
    "layout_visual": ("DOC-LAYOUT", "DOC-TABLE-LAYOUT", "DOC-FIGURE-SIZE"),
}


def rule_family(rule: Any) -> str:
    """把引擎规则号归一到规则族；未知规则返回规范化后的规则号本身。"""
    value = str(rule or "").strip().upper()
    if not value:
        return ""
    for family, rules in RULE_FAMILY_RULES.items():
        if value in rules:
            return family
    return f"raw:{value}"


# ----------------------------------------------------------------------
# 预置条目 -> 结构化模式
# ----------------------------------------------------------------------

# 每条预置误报记忆 = 一组可匹配的结构化条件。
# 全部条件为 AND 关系；任何一条不满足就不命中，避免把真问题误杀。
#
# 字段说明：
#   families      —— 允许的规则族
#   require_blob  —— 问题文本/上下文里必须出现的特征词（正则）
#   forbid_blob   —— 出现即视为真问题的排除特征（正则）
#   language      —— 限定文档语言（None 表示不限）
#   require_category —— 限定问题类别关键字（正则）
PresetPattern = dict[str, Any]


PRESET_PATTERNS: dict[str, PresetPattern] = {
    # FP-V1-001 嵌套有序列表编号差异
    "FP-V1-001": {
        "families": {"list_numbering", "spacing_format"},
        "require_blob": r"编号|格式不统一|numbering|list\s+style|嵌套",
        "forbid_blob": r"缺失|漏写|跳号|断号|重复编号",
        "language": None,
    },
    # FP-V1-002 正文商标 ® 不要求重复标注
    "FP-V1-002": {
        "families": {"trademark_symbol"},
        "require_blob": r"商标|®|\btrademark\b|\btm\b|注册商标",
        "forbid_blob": r"首次出现|声明页缺失|完全未出现",
        "language": None,
    },
    # FP-V1-003 软件生成文件名连写
    "FP-V1-003": {
        "families": {"spacing_format"},
        "require_blob": r"文件名|filename|文件名连写|\.csv|\.xlsx|\.txt|拼接",
        "forbid_blob": r"文档正文中的标题|章节标题",
        "language": None,
    },
    # FP-V1-004 内嵌图标不进文本层（PDF 伪影）
    "FP-V1-004": {
        "families": {"pdf_text_layer_artifact", "layout_visual"},
        "require_blob": r"图标|icon|按钮|button|图片缺失|未显示图标|插入图标",
        "forbid_blob": r"正文明确说明无此图标|文档注明",
        "language": None,
    },
    # FP-V1-005 引号映射伪影
    "FP-V1-005": {
        "families": {"pdf_text_layer_artifact"},
        "require_blob": r"引号|quote|直引号|弯引号|映射|字形",
        "forbid_blob": r"同一段内混用导致语义歧义",
        "language": None,
    },
    # FP-V1-006 英文句号在闭引号外
    "FP-V1-006": {
        "families": {"spacing_format", "pdf_text_layer_artifact"},
        "require_blob": r"句号|period|标点|punctuation|\.\s*$",
        "forbid_blob": r"句子结构混乱|导致断句错误",
        "language": "en",
    },
    # FP-V1-007 文本层单复数/短语动词词序
    "FP-V1-007": {
        "families": {"pdf_text_layer_artifact", "unit_plural"},
        "require_blob": r"单复数|复数|词序|following\s+status|turn\s+on\s+it|语法",
        "forbid_blob": r"可渲染页显示|正文多处一致使用",
        "language": None,
    },
    # FP-V1-008 双层文本层重复
    "FP-V1-008": {
        "families": {"pdf_text_layer_artifact"},
        "require_blob": r"重复文本层|双层文本层|text\s+layer\s+repeat|duplicate",
        "forbid_blob": r"正文内容本身重复|章节重复",
        "language": None,
    },
    # FP-V1-009 海外英文手册仅提供 Email
    "FP-V1-009": {
        "families": {"contact_info"},
        "require_blob": r"电话|phone|tel|联系方式|联系电话|缺电话",
        "forbid_blob": r"中文版|国内|法规要求电话",
        "language": "en",
    },
    # FP-V1-010 同探头不同频率表标题相同
    "FP-V1-010": {
        "families": {"terminology_consistency"},
        "require_blob": r"表\s*1[78]|table\s*1[78]|凸阵式探头|声输出|频率",
        "forbid_blob": r"同一表格|同一探头同一频率",
        "language": None,
    },
    # FP-V1-011 章节隔页/留白页缺页码
    "FP-V1-011": {
        "families": {"blank_separator_page"},
        "require_blob": r"页码|page\s+number|隔页|留白|blank",
        "forbid_blob": r"正文页面缺页码|目录页码与正文不符",
        "language": None,
    },
    # FP-V1-012 官网地址 global-mgitech.com
    "FP-V1-012": {
        "families": {"terminology_consistency", "contact_info"},
        "require_blob": r"global-mgitech\.com|官网|网址|url",
        "forbid_blob": r"拼写错误|应为.*mgitech",
        "language": None,
    },
}


# ----------------------------------------------------------------------
# 匹配
# ----------------------------------------------------------------------

def match_preset_pattern(issue: Any, *, language: str | None = None) -> str | None:
    """判断 issue 是否命中某条预置误报记忆，返回记忆条目 ID。

    只在**结构化证据全部满足**时命中：
      1. 规则族在允许列表内；
      2. 问题文本/上下文命中必需特征词；
      3. 未命中排除特征（即没有出现"这是真问题"的反证）；
      4. 语言限制满足（若配置）。
    """
    if not PRESET_PATTERNS:
        return None

    rule = _issue_field(issue, "rule")
    original = _issue_field(issue, "original_text")
    context = _issue_field(issue, "context")
    suggestion = _issue_field(issue, "suggestion")
    description = _issue_field(issue, "description")
    category = _issue_field(issue, "category")

    blob = " ".join([original, context, suggestion, description, category, rule])
    blob_low = blob.casefold()
    family = rule_family(rule)

    for entry_id, pattern in PRESET_PATTERNS.items():
        families = pattern.get("families") or set()
        if families and family not in families:
            continue
        if pattern.get("language") and language and pattern["language"] != language:
            continue
        require = pattern.get("require_blob")
        if require and not re.search(require, blob_low, re.IGNORECASE):
            continue
        forbid = pattern.get("forbid_blob")
        if forbid and re.search(forbid, blob_low, re.IGNORECASE):
            continue
        return entry_id
    return None


def _issue_field(issue: Any, key: str) -> str:
    if isinstance(issue, dict):
        return str(issue.get(key, "") or "")
    return str(getattr(issue, key, "") or "")


def salient_tokens_of(issue: Any) -> set[str]:
    """取 issue 的信息 token 集合（已剔除停用词）。"""
    return _salient_tokens(_issue_field(issue, "original_text"))


def family_of(issue: Any) -> str:
    return rule_family(_issue_field(issue, "rule"))


# 相似度阈值：低于此值不认为是"同一个问题的不同措辞"。
# 0.62 的取值来自实测——`Add 5 min` / `Add 5 mins` 这类单位单复数改动
# 相似度约 0.8+，而语义不同的同类族问题通常低于 0.45。
SIMILARITY_THRESHOLD = 0.62


def similarity(a: set[str], b: set[str]) -> float:
    """两个信息 token 集合的覆盖相似度（0~1）。

    用 `|A∩B| / min(|A|,|B|)` 而非 Jaccard：
    人工重述一个问题时长度常变短（例如把 "Add 5 mins to the buffer"
    写成 "5 mins"），Jaccard 会被长句子的无关词稀释，
    覆盖相似度则只惩罚"改动了多少词"。
    """
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / min(len(a), len(b))


def matches_memory(issue: Any, memory_rule: str, memory_text: str) -> bool:
    """判断 issue 是否与一条已存误报记忆"是同一个问题"。

    优先走精确签名（人工标注意图完全一致的场景）；
    精确不中时退化到「同规则族 + token 覆盖相似度达标」。
    同族 + 相似度双条件可以避免把同族的其他真问题一起误杀。
    """
    issue_text = normalize_fragment(_issue_field(issue, "original_text"))
    memory_norm = normalize_fragment(memory_text)
    if not issue_text or not memory_norm:
        return False

    if issue_text == memory_norm:
        return True

    # 精确签名路径：保留历史行为
    issue_category = normalize_fragment(_issue_field(issue, "category"))
    memory_family = rule_family(memory_rule)
    issue_family = family_of(issue)
    if memory_family and memory_family == issue_family:
        if issue_category and issue_category in memory_norm:
            return True

    if memory_family != issue_family:
        return False
    if not (memory_family or issue_family):
        return False

    return similarity(salient_tokens_of(issue), _salient_tokens(memory_norm)) >= SIMILARITY_THRESHOLD


