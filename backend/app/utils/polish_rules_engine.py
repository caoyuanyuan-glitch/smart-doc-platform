"""文档润色核心规则引擎 —— 5 条机器检测规则

规则按优先级依次应用：
  1. 术语替换（保守匹配）
  2. 祈使句规范
  3. 数字单位空格
  4. 中英文空格
  5. 标点规范
"""

import re

# ═══════════════════════════════════════════════
# 规则 1：术语替换（保守匹配）
# ═══════════════════════════════════════════════

def apply_term_replace(line: str, term_dict: dict, context_text: str = "") -> str:
    """
    保守术语替换：只替换完整词匹配的非标准术语。
    term_dict: {非标准词: 标准词}
    """
    if not term_dict:
        return line
    result = line
    for old_term, new_term in term_dict.items():
        if not old_term or not new_term:
            continue
        # 使用完整词边界匹配，避免误伤通用名词
        pattern = re.compile(r'(?<!\w)' + re.escape(old_term) + r'(?!\w)')
        if pattern.search(result):
            result = pattern.sub(new_term, result)
    return result


# ═══════════════════════════════════════════════
# 规则 2：祈使句规范
# ═══════════════════════════════════════════════

# 操作类动词：不加"请"
ACTION_VERBS = [
    '点击', '选择', '输入', '将', '打开', '关闭', '放置',
    '按下', '单击', '双击', '拖动', '滑动', '选中', '勾选',
    '填写', '复制', '粘贴', '删除', '保存', '发送', '提交',
]

# 建议类动词：加"请"
SUGGESTION_VERBS = [
    '检查', '确认', '确保', '避免', '防止', '联系',
    '注意', '查看', '核对', '验证', '参考', '咨询',
    '留意', '关注', '查阅', '了解',
]

# 警告类动词：保持原样（已含否定祈使）
WARNING_VERBS = [
    '严禁', '禁止', '请勿', '不得', '切勿', '切莫',
]

# 已有"请"字的动词（跳过检测）
_VERBS_PREFIXED_WITH_QING = re.compile(
    r'请\s*(' + '|'.join(ACTION_VERBS + SUGGESTION_VERBS) + r')'
)


def detect_imperative_issues(line: str) -> list:
    """
    检测祈使句规范问题。
    返回: [{original, replacement, reason, rule_name}, ...]
    """
    issues = []
    # 跳过警告类动词（已有否定祈使，保持原样）
    for verb in WARNING_VERBS:
        if verb in line:
            return []

    # 检测建议类动词是否缺少"请"
    for verb in SUGGESTION_VERBS:
        if verb in line:
            # 检查前面是否已有"请"
            idx = line.find(verb)
            if idx > 0:
                before = line[max(0, idx - 3):idx].strip()
                if before.endswith('请'):
                    continue
            elif idx == 0:
                # 句首：补充"请"
                pass
            new_line = line[:idx] + '请' + line[idx:]
            if new_line != line:
                issues.append({
                    'original': verb,
                    'replacement': '请' + verb,
                    'reason': '建议类动词应加"请"',
                    'rule_name': '祈使句规范',
                    'type': 'imperative',
                })
                return issues  # 每行最多一个祈使句修改

    # 检测操作类动词前面是否误加了"请"
    for verb in ACTION_VERBS:
        idx = line.find(f'请{verb}')
        if idx >= 0:
            new_line = line[:idx] + verb + line[idx + 1 + len(verb):]
            if new_line != line:
                issues.append({
                    'original': f'请{verb}',
                    'replacement': verb,
                    'reason': '操作类动词不加"请"',
                    'rule_name': '祈使句规范',
                    'type': 'imperative',
                })
                return issues

    return issues


def fix_imperative(line: str, issues: list) -> str:
    """根据检测结果修复祈使句"""
    if not issues:
        return line
    for issue in issues:
        if issue['original'] in line:
            line = line.replace(issue['original'], issue['replacement'], 1)
    return line


# ═══════════════════════════════════════════════
# 规则 3：数字单位空格
# ═══════════════════════════════════════════════

# 常见单位（正则模式）
_UNIT_TOKENS = r'μL|mL|L|mg|g|kg|mm|cm|m|℃|rpm|r/min|V|kV|A|mA|W|kW|MW|Hz|kHz|MHz|GHz|Pa|kPa|MPa|N|kN|s|min|h|bp|M|mM|μM|nM'

_NUMBER_UNIT_NO_SPACE = re.compile(
    r'(\d+\.?\d*)\s*(' + _UNIT_TOKENS + r')'
)


def detect_number_unit_spacing(line: str) -> list:
    """
    检测数字与单位之间缺少空格的问题。
    """
    issues = []
    for m in _NUMBER_UNIT_NO_SPACE.finditer(line):
        full = m.group(0)
        number_part = m.group(1)
        unit_part = m.group(2)
        # 检验是否已有空格
        if ' ' in full or '\u00A0' in full:
            continue
        replacement = f'{number_part} {unit_part}'
        if full != replacement:
            issues.append({
                'original': full,
                'replacement': replacement,
                'reason': '数字与单位间需空格',
                'rule_name': '数字单位空格',
                'type': 'format',
            })
    return issues


def fix_number_unit_spacing(line: str, issues: list) -> str:
    for issue in issues:
        line = line.replace(issue['original'], issue['replacement'], 1)
    return line


# ═══════════════════════════════════════════════
# 规则 4：中英文空格
# ═══════════════════════════════════════════════

# 中文字符后紧跟英文单词/缩写
_CN_FOLLOWED_BY_EN = re.compile(
    r'([\u4e00-\u9fff\u3000-\u303f\uff00-\uffef])([A-Za-z][A-Za-z0-9]*)'
)

# 英文单词后紧跟中文字符
_EN_FOLLOWED_BY_CN = re.compile(
    r'([A-Za-z0-9]+)([\u4e00-\u9fff\u3000-\u303f\uff00-\uffef])'
)

# 例外：英文缩写后紧跟数字（如 V1.0, v2.3）
_EN_THEN_NUMBER = re.compile(r'([A-Za-z]+)(\d+\.?\d*)')


def detect_cn_en_spacing(line: str) -> list:
    """
    检测中文与英文之间缺少空格的问题。
    例外：英文缩写 + 数字（如 V1.0）不处理。
    """
    issues = []

    # 记录"英文+数字"组合的位置，作为例外跳过
    skip_ranges = []
    for m in _EN_THEN_NUMBER.finditer(line):
        skip_ranges.append((m.start(), m.end()))

    def _is_skipped(pos):
        for s, e in skip_ranges:
            if s <= pos < e:
                return True
        return False

    # 中文后紧跟英文
    for m in _CN_FOLLOWED_BY_EN.finditer(line):
        if _is_skipped(m.end() - 1):
            continue
        full = m.group(0)
        cn = m.group(1)
        en = m.group(2)
        replacement = f'{cn} {en}'
        issues.append({
            'original': full,
            'replacement': replacement,
            'reason': '中文与英文缩写间需空格',
            'rule_name': '中英文空格',
            'type': 'format',
        })

    # 英文后紧跟中文
    for m in _EN_FOLLOWED_BY_CN.finditer(line):
        if _is_skipped(m.start()):
            continue
        full = m.group(0)
        en = m.group(1)
        cn = m.group(2)
        replacement = f'{en} {cn}'
        issues.append({
            'original': full,
            'replacement': replacement,
            'reason': '英文与中文间需空格',
            'rule_name': '中英文空格',
            'type': 'format',
        })

    return issues


def fix_cn_en_spacing(line: str, issues: list) -> str:
    # 按位置排序，从后往前替换避免索引偏移
    sorted_issues = sorted(
        issues,
        key=lambda x: line.find(x['original']) if x['original'] in line else 9999,
        reverse=True
    )
    for issue in sorted_issues:
        line = line.replace(issue['original'], issue['replacement'], 1)
    return line


# ═══════════════════════════════════════════════
# 规则 5：标点规范
# ═══════════════════════════════════════════════

# 句尾标点（中文）
_SENTENCE_END_PUNCTUATION = set('。！？！？')

# 句子级标点检查：中文句子应以中文字符结尾，并带标点
_CN_SENTENCE_NO_PUNCT = re.compile(
    r'([\u4e00-\u9fff)]）]}」』】])(?:\s*)$'
)

# 条件从句后缺少逗号
_CONDITIONAL_WITHOUT_COMMA = re.compile(
    r'(如|如果|若|如需|若要|如需|若需|假如|倘若|一旦|万一|要是)'
    r'([\u4e00-\u9fff\w]+?)(可|请|应|须|将|会|则|就|即|便)'
)

# 条件从句"如...可"→"如...，可"的精确匹配
_CONDITIONAL_FIX = re.compile(
    r'(如[\u4e00-\u9fff]+)(可[\u4e00-\u9fff]*)'
)


def detect_punctuation_issues(line: str) -> list:
    """
    检测标点问题：
    1. 句尾缺少标点
    2. 条件句缺逗号
    """
    issues = []

    # 1. 句尾缺标点
    stripped = line.rstrip()
    if stripped and stripped[-1] not in _SENTENCE_END_PUNCTUATION:
        # 不以标点结尾的中文句子
        issues.append({
            'original': stripped[-1:],
            'replacement': stripped[-1:] + '。',
            'reason': '句尾缺少标点',
            'rule_name': '标点规范',
            'type': 'punctuation',
            'context_original': stripped[-20:],
            'context_replacement': stripped[-20:] + '。',
        })

    # 2. 条件句缺逗号
    for m in _CONDITIONAL_FIX.finditer(line):
        prefix = m.group(1)  # "如..."
        suffix = m.group(2)  # "可..."
        original = m.group(0)
        replacement = f'{prefix}，{suffix}'
        if '，' not in original and ',' not in original:
            issues.append({
                'original': original,
                'replacement': replacement,
                'reason': '条件从句后应加逗号',
                'rule_name': '标点规范',
                'type': 'punctuation',
            })

    return issues


def fix_punctuation(line: str, issues: list) -> str:
    for issue in issues:
        if issue.get('type') == 'punctuation' and issue.get('reason') == '句尾缺少标点':
            stripped = line.rstrip()
            line = stripped + '。'
        elif issue['original'] in line:
            line = line.replace(issue['original'], issue['replacement'], 1)
    return line


# ═══════════════════════════════════════════════
# 统一入口：应用所有规则
# ═══════════════════════════════════════════════

def apply_all_rules(
    line: str,
    term_dict: dict = None,
    enabled_rules: list = None,
    context_text: str = "",
) -> tuple:
    """
    对单行文本应用所有启用的规则。

    参数:
        line: 输入文本行
        term_dict: 术语字典 {非标准: 标准}
        enabled_rules: 启用的规则列表，默认全部启用
                      ['termReplace', 'imperativePlease', 'numberSpace', 'cnEnSpace', 'punctuation']
        context_text: 上下文文本（用于术语替换的上下文判断）

    返回:
        (polished_line, issues_list)
        issues_list: [{original, replacement, reason, rule_name, type}, ...]
    """
    if enabled_rules is None:
        enabled_rules = ['termReplace', 'imperativePlease', 'numberSpace', 'cnEnSpace', 'punctuation']

    issues = []
    result = line

    # 规则 1：术语替换
    if 'termReplace' in enabled_rules and term_dict:
        before = result
        result = apply_term_replace(result, term_dict, context_text)
        if result != before:
            for old, new in term_dict.items():
                if old in before and new in result:
                    issues.append({
                        'original': old,
                        'replacement': new,
                        'reason': f'术语对照表',
                        'rule_name': '术语替换',
                        'type': 'term',
                        'engine_key': 'termReplace',
                    })

    # 规则 2：祈使句规范
    if 'imperativePlease' in enabled_rules:
        imp_issues = detect_imperative_issues(result)
        if imp_issues:
            for issue in imp_issues:
                issue['engine_key'] = 'imperativePlease'
            issues.extend(imp_issues)
            result = fix_imperative(result, imp_issues)

    # 规则 3：数字单位空格
    if 'numberSpace' in enabled_rules:
        num_issues = detect_number_unit_spacing(result)
        if num_issues:
            for issue in num_issues:
                issue['engine_key'] = 'numberSpace'
            issues.extend(num_issues)
            result = fix_number_unit_spacing(result, num_issues)

    # 规则 4：中英文空格
    if 'cnEnSpace' in enabled_rules:
        cn_issues = detect_cn_en_spacing(result)
        if cn_issues:
            for issue in cn_issues:
                issue['engine_key'] = 'cnEnSpace'
            issues.extend(cn_issues)
            result = fix_cn_en_spacing(result, cn_issues)

    # 规则 5：标点规范
    if 'punctuation' in enabled_rules:
        punct_issues = detect_punctuation_issues(result)
        if punct_issues:
            for issue in punct_issues:
                issue['engine_key'] = 'punctuation'
            issues.extend(punct_issues)
            result = fix_punctuation(result, punct_issues)

    return result, issues


def apply_custom_rules(line: str, rules: list = None) -> tuple:
    """执行规则管理中配置的非系统规则。"""
    if not rules:
        return line, []

    type_map = {
        'replacement_rule': 'terminology',
        'forbidden_rule': 'forbidden',
        'sentence_applicability_rule': 'style',
        'imperative_rule': 'style',
        'format_rule': 'format',
    }
    replacement_types = {'replacement_rule', 'forbidden_rule', 'sentence_applicability_rule'}
    result = line
    issues = []

    for rule in rules:
        pattern = (rule.match_pattern or '').strip()
        if not pattern:
            continue
        replacement = rule.replacement_text or ''
        before = result
        matched = False
        matched_text = ''

        try:
            search_match = re.search(pattern, result)
            if search_match:
                matched_text = search_match.group(0)
            if rule.rule_type in replacement_types:
                result, count = re.subn(pattern, replacement, result)
            else:
                count = 1 if search_match else 0
            matched = count > 0
        except re.error:
            if pattern in result:
                matched_text = pattern
                if rule.rule_type in replacement_types:
                    result = result.replace(pattern, replacement)
                matched = True

        if matched:
            issues.append({
                'original': matched_text or pattern,
                'replacement': replacement,
                'reason': rule.description or rule.rule_name or '自定义规则',
                'rule_name': rule.rule_name or '自定义规则',
                'type': type_map.get(rule.rule_type, 'custom'),
                'rule_id': rule.id,
                'before': before,
                'after': result,
            })

    return result, issues
