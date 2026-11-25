"""已裁定误报过滤器（跨多次实测复现，用户已逐项裁定不算问题）。

本模块只做一件事：把"人工反复裁定为误报"的类型写进过滤层，减少误报。
**不新增任何问题类型，不改变正常问题**——只返回 True 表示"这条应丢弃"。

纳入的 6 类（均有实测证据 + 用户裁定）：
  1. 标准警示模板句「如操作不当或不避免，则…伤害/生物风险」（中文，多次实测 4 条/文档）
  2. UI 图标提取伪影「tap/点击 后无控件名、按钮缺失」（✓/✗ 在渲染页可见，文本层缺失）
  3. 表格文本层拼接伪影（版本记录/故障表等表头被连成一句）
  4. 中文单位与中文连接（24 h内/24 h后）——单位与中文之间不加空格符合惯例
  5. UI 图注/界面标签当句子判语法（"Display the flow cell type" 等）
  6. AI 输出伪影原文（nonTips 等从未出现在文档中的字符串，AI 生成时截断产生）

设计约束：
- 匹配必须精确（整句模板 / 特定上下文），不得泛化到真实问题。
- 不碰用户明确要报的类型（确定性拼写、单位空格缺失、内容缺失等）。
"""

from __future__ import annotations

import re
from typing import Any


def _val(issue: Any, key: str) -> str:
    if isinstance(issue, dict):
        return str(issue.get(key, "") or "")
    return str(getattr(issue, key, "") or "")


_RULE_NO_RE = re.compile(r"^[A-Z][A-Z0-9_-]*\d+$|^[A-Z]+(?:-[A-Z0-9]+)+$")


def _is_rule_sourced(issue: Any) -> bool:
    """是否为确定性规则产出（规则号形态 + 规则来源）。

    注意：不能只看 rule 是否非空。AI 问题的 rule 字段在 canonicalize 之前
    常被污染成中文描述（如「信息不完整」），此时 rule 非空但仍是 AI 问题，
    若一律跳过会让过滤在持久化关口完全失效（实测 4 条图标伪影全部漏过）。
    """
    rule = _val(issue, "rule").strip()
    if not rule or not _RULE_NO_RE.match(rule.upper()):
        return False
    source = _val(issue, "source").strip().lower()
    return source in {"", "rule", "term", "spellcheck"}


# ── 1. 标准警示模板句 ──────────────────────────────────────────────
# 中文说明书危险/警告/注意/生物风险四档警示的统一句式，风格指南规定用法。
# 不用 ^ 锚定：AI 有时会把整行（含"提示操作者按照说明进行操作，"前缀）当原文截出，
# 锚定开头会让这类同源条目漏过（v5 实测 1 条）。
_WARNING_TEMPLATE = re.compile(
    r"如操作不当或不避免[，,]?\s*则(?:将会|可能)(?:导致|存在)"
    r"(?:死亡|严重伤害|轻微或中度伤害|潜在生物风险)"
)


def is_ruled_warning_template(issue: Any) -> bool:
    original = _val(issue, "original_text").strip()
    return bool(_WARNING_TEMPLATE.search(original))


# ── 2. UI 图标提取伪影 ─────────────────────────────────────────────
# 渲染页有 ✓/✗ 内嵌图标，文本层丢失；AI 报"未指明按钮/控件名"。
# 仅在 original/context 出现"tap . / 点击 后空位"等空位特征时丢弃；
# 若原文明确写了按钮名（如 "tap OK"）则不丢弃，避免掩盖真问题。
_UI_EMPTY_SLOT = re.compile(
    r"\b(?:tap|click|press|select)\s+(?:on\s+)?[\.。、,，;；]|\b(?:tap|click)\s*$|"
    r"点击\s*[\.。、，]|(?:按钮|图标|控件)(?:名称)?(?:缺失|未显示|未指明)"
)
# 点击动词后若紧跟这些词，说明后面是目的/位置状语而非控件名（"tap to return"）。
_UI_STOPWORDS = frozenset({
    "to", "on", "again", "it", "here", "the", "a", "an", "this", "that", "these", "those",
    "and", "or", "until", "then", "once", "when", "if", "for", "in", "at", "into",
    "back", "now", "twice", "below", "above", "directly",
})
_UI_ACTION_WORD = re.compile(r"\b(?:tap|click|press|select)\b", re.IGNORECASE)
_UI_AFTER_ACTION = re.compile(
    r"\s+(?:the\s+)?([\"\[【]?)([A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff _-]*)"
)


def _has_named_control(original: str) -> bool:
    """原文是否在点击动作后明确写了控件名（"tap OK" / 点击【查看】）。

    不能用一个宽松正则一把梭：早期写法把 "tap to return" 里的 to 当成控件名，
    导致 4 条 ✓/✗ 图标伪影在持久化关口全部漏过（v4 实测）。
    """
    for match in _UI_ACTION_WORD.finditer(original):
        tail = original[match.end():]
        after = _UI_AFTER_ACTION.match(tail)
        if not after:
            continue
        wrapped, word = after.group(1), after.group(2).strip()
        if wrapped:  # 引号/方括号包裹 → 明确命名
            return True
        first = re.split(r"\s+", word)[0]
        if not first:
            continue
        # "tap the Finish button" 里的 the 是冠词，控件名在后面
        if first.lower() == "the":
            rest = re.split(r"\s+", word, maxsplit=1)
            if len(rest) < 2:
                continue
            first = rest[1]
        if first.lower() in _UI_STOPWORDS:
            continue
        return True
    return False


def is_ruled_icon_artifact(issue: Any) -> bool:
    if _is_rule_sourced(issue):
        return False  # 确定性规则问题不动
    original = _val(issue, "original_text")
    blob = " ".join([original, _val(issue, "context")])
    suggestion = _val(issue, "suggestion")
    # 强信号：AI 明确要求"指明/命名要点击的控件"，而原文里点击动作没有命名对象。
    # 渲染页里 ✓/✗ 图标存在但未进文本层（用户已裁定这类提取伪影不算文档问题）。
    # 只认 suggestion 里的"指明控件"诉求，不用 description 里的泛化措辞——
    # description 的 "UI object missing" 在真缺控件名的场合也会出现，放宽会误删真问题。
    asks_name_control = bool(re.search(
        r"name\s+(?:the\s+)?(?:\w+[\s/]+){0,2}(?:control|button|icon)"
        r"|specify\s+(?:the\s+)?(?:\w+\s+){0,3}(?:control|button|icon)"
        r"|(?:control|button|icon)\s+(?:is\s+)?(?:not\s+named|unnamed)"
        r"|指明(?:按钮|控件|图标)|未指明(?:按钮|控件|图标)"
        r"|按钮对象缺失|操作对象缺失|控件对象缺失",
        suggestion, re.IGNORECASE,
    ))
    # AI 自己把原文的 tap 处标为占位符（如 "instead of the placeholder 'tap to return to...'"
    # —— p32 各分支的 ✓/✗ 图标在文本层缺失，实测同页 5 条同一根因）
    placeholder_tap = bool(
        re.search(r"placeholder", suggestion, re.IGNORECASE)
        and re.search(r"\b(?:tap|click)\b", original, re.IGNORECASE)
    )
    if placeholder_tap:
        asks_name_control = True
    ui_action = bool(re.search(r"\b(?:tap|click|press|select)\b|点击|轻触|长按", blob, re.IGNORECASE))
    if not (asks_name_control and ui_action):
        return False
    # 原文里已有命名控件（如 "tap OK" / "点击【查看】"）→ 可能是真问题，不丢
    if _has_named_control(original):
        return False
    if re.search(r"[【\[][^】\]]{1,12}[】\]]", original):
        return False
    return True


# ── 3. 表格文本层拼接伪影 ──────────────────────────────────────────
# "版本日期版本" = 版本记录表头 [版本][日期][版本] 拼接；
# "故障现象原因分析处理方法" = 故障处理表三列表头拼接。
#
# 同一串拼接文本，AI 可能报两种完全不同的问题，必须区分：
#   a) 伪影型：AI 把"表头被连成一句"本身当缺陷（"三列内容粘连，无法区分列归属"）——
#      渲染页三列表头本来分开，属提取伪影，丢。
#   b) 真缺陷型：AI 借这个拼接串指出表格结构问题（"表头列名重复且缺列"）——
#      渲染核实（MGIDL 中文 p3）：首列表头文字为白色字 + 白色底，视觉上不可见，
#      表头确实缺列名。这是真问题，**不能当伪影丢**。
# 早期版本只按字符串精确匹配，把 (b) 类真问题一并丢弃（中文首轮 12 条里的
# "版本日期版本" 就是被误删的真缺陷），本版按 AI 的描述语区分。
_TABLE_HEADER_CONCAT = {
    "版本日期版本",
    "故障现象原因分析处理方法",
}
# AI 描述指向"表格结构缺陷"→ 真问题
_TABLE_STRUCT_DEFECT = re.compile(
    r"缺列|列名缺失|缺少.{0,4}列|缺(?:少)?表头|表头缺失|结构不完整|列不完整"
)
# AI 描述只指向"文本粘连"本身 → 提取伪影
_TABLE_CONCAT_ONLY = re.compile(
    r"粘连|连成|拼接|无法区分列|无法判断列|合并成|连在一起|缺少分隔|缺失分隔|缺分隔"
    r"|无分隔|未分隔|应可区分|列名应可区分"
)
# AI 描述指向"单元格内容缺失/表格结构缺陷" → 真问题，必须保留
_TABLE_CONTENT_MISSING = re.compile(
    r"无任何数据|未提供|缺少.{0,24}(?:数据|数值|内容|列名|列内容)|仅有表头|只有表头"
)
# 疑似多列表头被拼成一句：无中文句读标点的中英文长串（渲染页本应是分列）
_HEADER_JOIN_PUNCT = re.compile(r"[，。、；：,.;:!？?]")
# 描述明确指向"表格中两列内容之间缺少分隔"（不要求原文形态）
_TABLE_COLUMN_SEP_HINT = re.compile(r"表格列|列与列|标题.{0,6}说明|符号.{0,6}标题")
# 术语条目名与解释之间缺分隔符：用户确认是真缺陷（GB 术语表要求），不得当表头伪影丢
_TERM_ENTRY_HINT = re.compile(r"术语条目|词条|条目名|条目与解释|术语表")
# 图注/示意图"编号 + 名称 + 说明"被文本层拼成一句（渲染页同一行，实为并列要素）
_CAPTION_HINT = re.compile(r"名称与说明.*(?:连写|分隔)|(?:连写|分隔).*名称与说明")
_CAPTION_SHAPE = re.compile(r"^\d{1,2}\s*[\u4e00-\u9fff]")
# 明确指出文件名/文件夹名与截图不一致、疑似漏字母 → 拼写真问题，不能当拼接伪影丢
# （Tina R02 p117：【Workpace】应为 Workspace）
_FILE_NAME_HINT = re.compile(r"文件夹名|文件名|少.{0,3}字母|漏字|拼写|截图为|截图写")


def _looks_like_joined_headers(text: str) -> bool:
    t = text.strip()
    if not (6 <= len(t) <= 40):
        return False
    if _HEADER_JOIN_PUNCT.search(t):
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", t))


def is_ruled_table_header_concat(issue: Any) -> bool:
    original = _val(issue, "original_text").strip()
    # rule 字段可能携带规则/判定文本（description 为空时由 canonicalize 回填）
    blob = " ".join(_val(issue, k) for k in ("description", "suggestion", "rule"))
    if _FILE_NAME_HINT.search(blob):
        return False  # 文件名拼写错误是真问题
    if _TERM_ENTRY_HINT.search(blob):
        return False  # 术语条目分隔符缺失是真问题
    # "缺少列分隔/缺少列间分隔"仍属粘连伪影，不能算结构缺陷
    struct_defect = bool(_TABLE_STRUCT_DEFECT.search(blob)) and not re.search(
        r"列(?:间)?的?分隔|列分隔", blob
    )
    # 原文是表头串、描述开头就指出粘连：后续"完整性受影响"属顺带表述，仍丢
    if _looks_like_joined_headers(original) and _TABLE_CONCAT_ONLY.search(blob[:24]):
        return True
    if struct_defect or _TABLE_CONTENT_MISSING.search(blob):
        return False  # 指出表格内容/结构缺陷 → 真问题，保留
    if not _TABLE_CONCAT_ONLY.search(blob):
        return False
    if original in _TABLE_HEADER_CONCAT or _looks_like_joined_headers(original):
        return True
    if _CAPTION_HINT.search(blob) and _CAPTION_SHAPE.match(original):
        return True
    return bool(_TABLE_COLUMN_SEP_HINT.search(blob))


# ── 4. 中文单位与中文连接 ──────────────────────────────────────────
# "24 h内"/"24 h后"：数字与单位间已有空格，单位与中文连接不加空格是惯例。
# 两种形态都要覆盖：
#   a) 切片带数字：`24 h后`
#   b) 切片只有单位+中文：`h后`（R025 命中时原文往往只截到这一段）
_UNIT = r"(?:h|min|s|mL|μL|ul|mg|ng|bp|kb|℃|°C|V|A|W|rpm)"
_ZH_CONNECT = r"(?:内|后|前|时|以上|以下|之间|左右)"
_UNIT_ZH_CONNECT_FULL = re.compile(
    rf"^\d+(?:\.\d+)?\s+{_UNIT}\s*{_ZH_CONNECT}$", re.IGNORECASE
)
_UNIT_ZH_CONNECT_BARE = re.compile(rf"^{_UNIT}\s*{_ZH_CONNECT}$", re.IGNORECASE)
# 上下文里"数字 + 空格 + 单位 + 中文"的完整写法，用于给裸切片（h后）做佐证
_NUM_UNIT_ZH_IN_CTX = re.compile(
    rf"\d+(?:\.\d+)?\s+{_UNIT}\s*{_ZH_CONNECT}", re.IGNORECASE
)


def is_ruled_unit_zh_connect(issue: Any) -> bool:
    original = _val(issue, "original_text").strip()
    hint = _val(issue, "suggestion") + _val(issue, "description")
    if "空格" not in hint:
        return False
    # a) 自带数字：只认"数字与单位间已有空格"的写法（无空格才是真问题，不能丢）
    if _UNIT_ZH_CONNECT_FULL.match(original):
        return True
    # b) 裸切片：必须能在上下文里找到"数字 + 空格 + 单位 + 中文"的完整写法
    if _UNIT_ZH_CONNECT_BARE.match(original):
        return bool(_NUM_UNIT_ZH_IN_CTX.search(_val(issue, "context")))
    return False


# ── 5. UI 图注/界面标签当句子判语法 ────────────────────────────────
# "Display the flow cell type." 是界面文字/标签，非描述句，用动词原形正确。
# 仅当建议是改成第三人称单数、且原文是短标签（≤6 词、无主语）时丢弃。
_UI_LABEL_CANDIDATE = re.compile(
    r"^(?:Display|Show|Select|Set|Enable|Disable|Reset|Enter|Exit|View|Open|Close|"
    r"Start|Stop|Confirm|Cancel|Clear|Load|Unload|Save|Delete|Add|Remove)\s+[A-Za-z][A-Za-z0-9 _-]{2,40}\.?$"
)


def is_ruled_ui_label_grammar(issue: Any) -> bool:
    original = _val(issue, "original_text").strip()
    if not _UI_LABEL_CANDIDATE.match(original):
        return False
    blob = (_val(issue, "suggestion") + " " + _val(issue, "description")).lower()
    return bool(re.search(r"third.person|subject.verb|displays|shows|selects|主谓", blob))


# ── 5b. 跨文档套用学习补丁（过拟合） ──────────────────────────────
# 学到的替换对绑定来源文档，套到别的文档就是把一篇的用词习惯当另一篇的错误。
# 这 3 对来自实测确认：Close→cover（动词误判）、power supply→mains supply（同义改写）。
_OVERFIT_LEARNED_PAIRS = (
    ("close", "cover"),
    ("power supply", "mains supply"),
    ("main power supply socket", "mains supply"),
)


def is_ruled_learned_patch_overfit(issue: Any) -> bool:
    if _val(issue, "rule").upper() != "LEARN-PATCH-001":
        return False
    desc = _val(issue, "description").lower()
    suggestion = _val(issue, "suggestion").lower()
    blob = desc + " " + suggestion
    return any(a in blob and b in blob for a, b in _OVERFIT_LEARNED_PAIRS)


# ── 6. AI 输出伪影原文 ─────────────────────────────────────────────
# AI 把两个词截断黏成新词（nonTips = non- + Tips），从未出现在文档中。
# 这里只识别"某个词被插入另一个完整英文词"的明显伪影，避免误伤真拼写错误。
_GLUED_WORD_ARTIFACT = re.compile(
    r"\b(?:non[A-Z][a-z]+|[A-Z][a-z]+[A-Z][a-z]{2,})\b"
)


def is_ruled_ai_glued_word(issue: Any, content: str = "") -> bool:
    if _val(issue, "source").lower() != "ai" or not content:
        return False
    original = _val(issue, "original_text").strip()
    match = _GLUED_WORD_ARTIFACT.search(original)
    if not match:
        return False
    token = match.group(0)
    # 文档里真实出现过 → 不是伪影
    if token.lower() in content.lower():
        return False
    # 拆分后两半都在文档里 → 确认是黏连伪影
    split = re.findall(r"[A-Z]?[a-z]+", token)
    if len(split) < 2:
        return False
    content_lower = content.lower()
    return all(part.lower() in content_lower for part in split if len(part) >= 2)


# ── 7. 操作步骤「请」等敬语 ────────────────────────────────────────
# 用户裁定：「请」「请勿」在中文说明书里是标准写法（「请勿」还表达禁止，
# 删掉会改语义），一律不报。旧规则「操作步骤不得添加请等敬语」已从提示词移除，
# 这里兜底拦截历史版本或模型自行产出的同类问题。
_POLITENESS_HINT = re.compile(
    r"敬语|不得添加[“\"'‘]?请|删除[“\"'‘]?请|不加[“\"'‘]?请|避免使用敬语"
)


def is_ruled_politeness(issue: Any) -> bool:
    if "请" not in _val(issue, "original_text"):
        return False
    hint = " ".join(
        _val(issue, key) for key in ("description", "suggestion", "rule")
    )
    return bool(_POLITENESS_HINT.search(hint))


# ── 8. 纯排版空格/分隔体例（AI 自产出） ────────────────────────────
# 中文技术文档里「中文与英文缩写之间是否加空格」「乘号/等号前后空格」
# 「表格内同类条目的分隔体例」属排版风格。AI 常凭"正文别处有空格"反推
# 全文不一致，价值极低且易误判（T7+RS 中文实测 24 条）。
# 规则引擎（rule/term/spellcheck 来源）的显式单位规则保留，不进此过滤器。
_SPACING_HINT = re.compile(r"空格|间距|分隔符|标点符号")
# 出现这些词说明背后有实质缺陷，必须保留
_SPACING_SUBSTANCE = re.compile(
    r"错别字|拼写|错字|用词|语序|歧义|成分残缺|缺(?:少)?(?:主语|宾语|对象)"
    r"|无法确定|重复|冗余|赘余|含义"
)
# 人工审核明确要求上报的格式问题，按原文形态判定，避免误伤"原文已合规"的 AI 误报
# （Tina R02 批注：单位前面缺空格 / 括号前有多余空格）
_NUM_UNIT_TIGHT = re.compile(r"\d(?:GB|TB|MB|min|bp|mm|cm|kg|mg|mL|μL|℃|°C|rpm|VDC)")
_PAREN_SPACE_TIGHT = re.compile(r"[A-Za-z\u4e00-\u9fff]\s+（[^）]{1,8}）")
_SPACING_EDGE = re.compile(
    r"[\u4e00-\u9fff][A-Za-z0-9]|[A-Za-z0-9][\u4e00-\u9fff]|[=+×*/]\s*\d|\d\s*[=+×*/]"
)


def is_ruled_spacing_style(issue: Any) -> bool:
    if _is_rule_sourced(issue):
        return False
    # 关键：AI 问题的 rule 字段常是判定文本，description 可能为空
    # （canonicalize_issue_rule 会在落库前把 rule 文本回填进 description）。
    blob = " ".join(_val(issue, key) for key in ("description", "suggestion", "rule"))
    if not _SPACING_HINT.search(blob):
        return False
    if _SPACING_SUBSTANCE.search(blob):
        return False
    original = _val(issue, "original_text")
    if _NUM_UNIT_TIGHT.search(original) or _PAREN_SPACE_TIGHT.search(original):
        return False  # 数字与单位空格、括号前空格：人工要求上报
    # 中英文/数字边界、描述指向括号空格、或原文本身含空格
    return (
        bool(_SPACING_EDGE.search(original))
        or "括号" in blob
        or " " in original
    )


# ── 9. 无依据的"术语不统一"指控 ────────────────────────────────────
# AI 常在没有指出具体两种写法的情况下报"同一概念全文统一""术语混用"，
# 建议栏只重复原文（T7+RS 实测 5~7 条）。人工审核要求给出具体对照才算问题。
_TERM_CLAIM = re.compile(
    r"同一(?:概念|术语|对象|动作|缩写)"
    r"|术语(?:不统一|混用|不一致)"
    r"|名称(?:不统一|不一致)"
    r"|用词(?:混用|不统一)"
)
_TERM_CONCRETE = re.compile(r"→|->|应改为|应为|统一为|写成|改成")
_ASCII_TERM_PAIR = re.compile(
    r"([A-Za-z][A-Za-z0-9 ._+-]{1,30}?)\s*(?:与|和|/)\s*([A-Za-z][A-Za-z0-9 ._+-]{1,30})"
)
# 中文写法对照："振荡混匀与涡旋混匀""存储与储存"，两侧都是 ≥3 字实词才算
_CJK_TERM_PAIR = re.compile(
    r"([\u4e00-\u9fff]{3,8})\s*(?:与|和)\s*([\u4e00-\u9fff]{3,8})"
)
_QUOTED_TERM = re.compile(r"[“\"「『]([^”\"」』]{1,30})[”\"」』]")


def _norm_term(text: str) -> str:
    return re.sub(r"[\s_]+", "", text).lower()


def is_ruled_vague_term_claim(issue: Any) -> bool:
    if _is_rule_sourced(issue):
        return False
    blob = " ".join(_val(issue, key) for key in ("description", "suggestion", "rule"))
    if not _TERM_CLAIM.search(blob):
        return False
    if re.search(r"重复|冗余|赘余|精简|啰嗦", blob):
        return False  # 语言重复类缺陷是真问题
    if _TERM_CONCRETE.search(blob):
        return False
    quoted = _QUOTED_TERM.findall(blob)
    if len(quoted) >= 2:
        return False  # 引用了两种写法
    if any(re.search(r"[→/]|与|和", term) for term in quoted):
        return False  # 引号内直接给出对照
    for left, right in _ASCII_TERM_PAIR.findall(blob):
        # "DualBarcode 与 Dual Barcode" 是同一写法的大小写/空格差异，不算具体对照
        if _norm_term(left) != _norm_term(right):
            return False  # 指出了两种不同写法，是真问题
    for left, right in _CJK_TERM_PAIR.findall(blob):
        if left != right:
            return False  # 中文写法对照（"振荡混匀与涡旋混匀"）
    return True


# ── 10. AI 自认"没问题"却仍生成的结论 ─────────────────────────────
# 实测 "X 轴 Cycle 数：图表与正文描述一致" 被当成问题上报。
# 只认"X 与 Y 一致/相符"这种成对结论，避免把"术语一致性"这类分类标签当结论。
_POSITIVE_VERDICT = re.compile(
    r"(?:与|和)[^。；，,;]{0,14}?(?:一致|相符|吻合|无误|无问题)"
)
_POSITIVE_NEGATION = re.compile(
    r"不(?:一致|相符|吻合|正确|符合)|未发现问题|缺失|缺少|错误|重复|冗余"
    r"|建议|应(?:改|为|统一|补|核|与)|需(?:改|要|补|核|与|确)"
    r"|须(?:与|核)|必须|务必|无法|不清|待(?:确认|核)|混用|不统一"
    r"|[应需须]"
)


def is_ruled_positive_verdict(issue: Any) -> bool:
    if _is_rule_sourced(issue):
        return False
    # 只处理"短结论句"（如"图表与正文描述一致"）；长描述多半在讲具体缺陷。
    # 长度只按判定文本算，suggestion 常附带改写建议（"X 轴 Barcode ID"），
    # 不能让它把短结论句挤出阈值。
    text = " ".join(_val(issue, key) for key in ("description", "rule")).strip()
    if len(text) > 24:
        return False
    blob = f"{text} {_val(issue, 'suggestion')}"
    return bool(_POSITIVE_VERDICT.search(text)) and not _POSITIVE_NEGATION.search(blob)


# ── 总入口 ─────────────────────────────────────────────────────────
def should_drop_ruled_fp(issue: Any, content: str = "") -> bool:
    return (
        is_ruled_warning_template(issue)
        or is_ruled_icon_artifact(issue)
        or is_ruled_table_header_concat(issue)
        or is_ruled_unit_zh_connect(issue)
        or is_ruled_ui_label_grammar(issue)
        or is_ruled_learned_patch_overfit(issue)
        or is_ruled_politeness(issue)
        or is_ruled_spacing_style(issue)
        or is_ruled_vague_term_claim(issue)
        or is_ruled_positive_verdict(issue)
        or is_ruled_ai_glued_word(issue, content)
    )
