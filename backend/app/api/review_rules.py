"""
技术文档审核规则库
包含中文错别字、标点符号、语法、术语、单位、合规、英文拼写等规则
"""

# ============================================
# 4.1 中文错别字规则
# ============================================
CHINESE_SPELLING_RULES = [
    {"original": "现成情况", "expected": "现场情况", "severity": "serious", "rule": "词语误用"},
    {"original": "切忌", "expected": "切记", "severity": "serious", "rule": "词语误用（切忌意为务必，切记意为牢记）"},
    {"original": "配置溶液", "expected": "配制溶液", "severity": "serious", "rule": "词语误用（配制指调配制作）"},
    {"original": "震荡混匀", "expected": "振荡混匀", "severity": "serious", "rule": "词语误用（振荡指往复运动）"},
    {"original": "试剂艙", "expected": "试剂仓", "severity": "serious", "rule": "错别字"},
    {"original": "以（表示已完成时）", "expected": "已", "severity": "serious", "rule": "词语误用"},
    {"original": "交户", "expected": "交互", "severity": "serious", "rule": "错别字"},
    {"original": "手工冰箱", "expected": "冰箱", "severity": "serious", "rule": "不规范表述"},
    {"original": "拍摄模组", "expected": "识别模组", "severity": "general", "rule": "术语错误（拍摄模组不含扫码器）"},
]

# ============================================
# 4.2 中文标点符号规则
# ============================================
CHINESE_PUNCTUATION_RULES = [
    {"pattern": r"（[A-Za-z0-9\)）", "expected": "（A-Za-z0-9）", "severity": "serious", "rule": "全角括号必须配对"},
    {"pattern": r"[A-Za-z0-9]\*[\*A-Za-z]", "expected": "×", "severity": "general", "rule": "尺寸标注用×不用*"},
    {"pattern": r"\d+\s+号", "expected": "", "severity": "general", "rule": "中文文字间不能有多余空格"},
]

# ============================================
# 4.3 中文语法规则
# ============================================
CHINESE_GRAMMAR_RULES = [
    {"pattern": r"不避免", "expected": "不按照说明操作", "severity": "serious", "rule": "避免不避免类语法错误"},
    {"pattern": r"限期", "expected": "期限或使用寿命", "severity": "suggestion", "rule": "限期改为期限或使用寿命"},
]

# ============================================
# 4.4 中文术语规则
# ============================================
CHINESE_TERMINOLOGY_RULES = [
    {"pattern": r"手工冰箱", "original": "手工冰箱", "expected": "冰箱", "severity": "serious",
     "rule": "不规范表述"},
    {"pattern": r"拍摄模组", "original": "拍摄模组", "expected": "识别模组", "severity": "general",
     "rule": "术语错误（拍摄模组不含扫码器）"},
]

# ============================================
# 4.5 单位规则
# ============================================
UNIT_RULES = [
    {"pattern": r"\bKg\b", "expected": "kg", "severity": "general", "rule": "单位大小写"},
    {"pattern": r"(?<=\d)ml\b", "expected": "mL", "severity": "general", "rule": "毫升单位"},
    {"pattern": r"(?<=\d)ul\b", "expected": "μL", "severity": "general", "rule": "微升单位"},
    {"pattern": r"(?<=\d)mins\b", "expected": "min", "severity": "general", "rule": "时间单位"},
    {"pattern": r"(?<=\d)hs\b", "expected": "h", "severity": "general", "rule": "时间单位"},
    {"pattern": r"(?<=\d)sec\b", "expected": "s", "severity": "general", "rule": "时间单位"},
    {"pattern": r"\b10x[A-Z]", "expected": "×", "severity": "general", "rule": "乘号表示"},
]

# ============================================
# 4.6 合规规则
# ============================================
COMPLIANCE_RULES = [
    {"pattern": r"EC\s*REP", "expected": "EU REP", "severity": "serious", "rule": "欧代标识错误"},
    {"pattern": r"en\.mgi-tech\.com", "expected": "https://global-mgitech.com", "severity": "serious", "rule": "英文手册应使用国际官网"},
]

# ============================================
# 4.7 英文拼写规则（领域词典）
# ============================================
ENGLISH_CORRECT_SPELLINGS = [
    "manual", "system", "developed", "operating", "instruction", "guide", "preparation",
    "process", "determination", "automated", "rigorously", "repeated", "stability",
    "accuracy", "quantification", "application", "version", "table", "hardware",
    "customized", "configuration", "applicable", "equipment", "customer", "through",
    "released", "components", "cartridge", "enzyme", "centrifuge", "until", "using",
    "reagents", "recommended", "technical", "making", "workflow", "divided", "concentration",
    "analysis", "mixture", "suitable", "fungi", "species", "genome", "blue", "circular",
    "uncyclized", "according", "running", "corresponding", "information", "follows",
    "desktop", "selection", "appear", "interface", "button", "respectively", "calculation",
    "following", "thoroughly", "chapter", "section", "introduction", "preface",
    "specimen", "sensitivity", "specificity", "pipette", "dispense", "aspirate",
    "incubate", "centrifuge", "homogenize", "dilute", "aliquot", "vortex", "resuspend"
]

# 英式/美式拼写对照
BRITISH_AMERICAN_SPELLINGS = {
    "customised": "customized",
    "normalised": "normalized",
    "analysed": "analyzed",
    "recognised": "recognized",
    "labelled": "labeled",
    "cancelled": "canceled",
    " programme ": "program",
    "colour": "color",
}

# ============================================
# 4.8 英文语法规则
# ============================================
ENGLISH_GRAMMAR_RULES = [
    {"pattern": r"\bPlease\b", "expected": "", "severity": "suggestion", "rule": "正文中避免使用Please"},
    {"pattern": r"\bfor\s+run\s+\w+", "expected": "for running", "severity": "suggestion", "rule": "for + 动词"},
    {"pattern": r"\bdesk\s+top\b", "expected": "desktop", "severity": "general", "rule": "单词拆分"},
    {"pattern": r"\bat\s+your\s+own\s+risk\b", "expected": "proceed with caution", "severity": "suggestion", "rule": "避免口语化表述"},
]


# ============================================
# v2 对齐：P0 规则库 10 大分类视图
# 中文 5 维：字词 / 句子 / 标点 / 段落 / 逻辑
# 英文 5 维：拼写 / 句式 / 标点 / 语法 / 逻辑
# ============================================

# --- 中文·段落（v2 新增维度；初期可为空，由 T3 人工意见回流填充）---
CHINESE_PARAGRAPH_RULES = []

# --- 中文·逻辑（v2 新增维度；确定性部分已由 review.py _run_logic_integrity_audit 覆盖，此处不重复）---
CHINESE_LOGIC_RULES = []

# --- 英文·句式（v2 新增维度）---
ENGLISH_SENTENCE_RULES = [
    {"pattern": r"\bturn\s+on\s+it\b", "expected": "turn it on", "severity": "suggestion",
     "rule": "短语动词词序（PDF 伪影优先走视觉复核）"},
]

# --- 英文·标点（v2 新增维度）---
ENGLISH_PUNCTUATION_RULES = [
    {"pattern": r"[a-zA-Z]、(?=[a-zA-Z])", "expected": ",", "severity": "serious",
     "rule": "中文顿号混入英文"},
]

# --- 英文·逻辑（v2 新增维度；初期可为空）---
ENGLISH_LOGIC_RULES = []

# --- 10 大分类聚合视图（v2 第 2 节 P0 口径）---
def _dedupe_rules(rules):
    """同一维度内按 (原文, 期望) 去重，避免同一规则双跑重复上报。"""
    seen, unique = set(), []
    for rule in rules:
        key = (rule.get("original") or rule.get("pattern"), rule.get("expected"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(rule)
    return unique


V2_RULE_CATEGORIES = {
    "中文_字词": _dedupe_rules(list(CHINESE_TERMINOLOGY_RULES) + list(CHINESE_SPELLING_RULES)),
    "中文_句子": list(CHINESE_GRAMMAR_RULES),
    "中文_标点": list(CHINESE_PUNCTUATION_RULES),
    "中文_段落": list(CHINESE_PARAGRAPH_RULES),
    "中文_逻辑": list(CHINESE_LOGIC_RULES),
    "英文_拼写": list(ENGLISH_CORRECT_SPELLINGS),
    "英文_句式": list(ENGLISH_SENTENCE_RULES),
    "英文_标点": list(ENGLISH_PUNCTUATION_RULES),
    "英文_语法": list(ENGLISH_GRAMMAR_RULES),
    "英文_逻辑": list(ENGLISH_LOGIC_RULES),
}


# ============================================
# System Prompt 模板
# ============================================
SYSTEM_PROMPT_TEMPLATE = """你是一个专业的技术文档审核工程师，专精于医疗器械/IVD/科研试剂领域。
请严格按照以下规则对文档进行审核。

【审核规则】

一、中文错别字规则（严重）
1. 现成情况 → 现场情况
2. 切忌（意为务必时）→ 切记
3. 配置溶液 → 配制溶液
4. 震荡混匀 → 振荡混匀
5. 试剂舱 → 试剂仓
6. 以（表示已完成时）→ 已

二、中文标点符号规则
1. 全角括号必须配对：功率（W) → 功率（W）
2. 尺寸标注用×不用*：W*D*H → W×D×H
3. 中文文字间不能有多余空格：146 号 → 146号
4. UI交互元素可使用【】标注：点击【确定】、选择【下一步】
5. 单引号仅在明确影响语义或格式规范时报告

三、中文语法规则
1. 避免"不避免"类语法错误：如操作不当或不避免 → 如不按照说明操作
2. 避免使用成语：周而复始 → 如此循环
3. 避免文言化表述：未尽事宜 → 未覆盖的信息
4. 使用限期 → 使用期限或使用寿命

四、中文术语规则
1. 手工冰箱不是专业术语：传统手工冰箱 → 传统冰箱
2. 拍摄模组不含扫码器，应为识别模组
3. 仅按钮、菜单、输入框、选项等可交互UI元素使用【】标注；界面名称和标题保持原文写法
4. 同一概念全文统一，不混用

五、单位规则
1. Kg → kg
2. ml → mL
3. ul → μL
4. mins → min, hs → h, sec → s
5. 数字与单位、倍数符号、缓冲液缩写之间必须保留空格：200μL → 200 μL；20xTE → 20 × TE

六、合规规则（严重）
1. ROHS表名应为"产品中有害物质的名称及含有信息表"
2. 欧代标识：EU REP（不是 EC REP）
3. 英文手册官网：https://global-mgitech.com
4. 中文手册官网：www.mgi-tech.com

七、英文拼写规则（领域词典）
以下为正确拼写：{english_words}

美式/英式拼写对照：
- customised → customized
- normalised → normalized
- analysed → analyzed
- recognised → recognized

八、英文语法规则
1. 主谓一致：单数主语用单数动词
2. 冠词：可数名词单数前必须有冠词（a/an/the）
3. 时态：使用一般现在时
4. 语态：优先使用主动语态
5. Please：除UI提示外，正文中避免使用
6. for + 动词：for running（不是 for run）
7. 乘号：使用 ×，且前后保留空格（如 20 × TE）
8. 单词拆分：desktop（不是 desk top）

九、中文顿号混入英文（严重）
英文文档中不得出现中文顿号"，"。

十、语义质量检查（中文文档重点，逐句执行）

【冗余与多余】
1. 删除无信息量的套话/引导语：如封面"关于本指南"、"以下将介绍"等可整体删除或压缩
2. 删除句中冗余虚词：如"请点击"→"点击"、"将"字赘余（"将鼠标移至"→"鼠标移至"）
3. 同一信息在前后章节重复描述时，后文应指出"与 xx 章重复"，不重复报告

【表述准确性】
4. 用词与界面/行为实际不符时报告，如"发出提示"应核实是否实为"播放提示音"
5. 描述更像其他对象时报告，如把"进度条"描述成"状态显示"等近似但不准确的说法

【信息完整性】
6. 操作步骤缺后续动作时报告，如"点击关闭当前界面"应补充"并返回主界面"
7. 步骤结果缺收尾动作时报告，如屏幕锁定类操作应补"并锁定屏幕"

【一致性】
8. 同一对象/动作在不同章节描述不一致时报告，指出两处写法，给出统一写法
9. 同一术语/缩写的大小写全文必须一致，如 barcode/Barcode 混用、DNA/duallabel 混用
10. 同类结构标点必须一致，如同一列表项有的用顿号有的用逗号

【语气与方向】
11. 操作步骤中不得添加"请"等敬语（除 UI 界面本身显示的提示外）；发现原句含"请"且非 UI 提示时报告
12. 判断修改方向：AI 只建议删除/修正，不得把原文没有的错误反向添加

【图表衔接】
13. 表格/图与正文衔接处标点检查：表格后接正文时用句号，图题后接下文用句号

【句子成分】
14. 检查句子是否缺字/多字：如"系统设置界面吗"缺"点击关闭当前界面并返回主界面"；"重新修饰"缺"的"（"重新修饰的词"）

【输出格式】
请按以下JSON格式输出审核结果，不要输出其他内容：
{{
  "issues": [
    {{
      "type": "拼写|语法|标点|术语|单位|合规|格式|冗余|表述不准确|信息不完整|一致性|语气|图表衔接|句子成分",
      "severity": "serious|general|suggestion",
      "location": "问题所在位置",
      "original": "原文内容",
      "expected": "正确写法",
      "rule": "违反的具体规则描述"
    }}
  ],
  "summary": {{
    "total": 数量,
    "serious": 严重数量,
    "general": 一般数量,
    "suggestion": 建议数量
  }}
}}

【去重规则】
同一错误在同一文档中只报告第一次出现的位置，不要重复报告。

【误报抑制规则】
1. PDF 文本层中的半词、碎词、双层重复、引号映射异常、图标缺失、按钮缺失，优先按提取伪影处理
2. 嵌套有序列表中外层 `1.`、内层 `1)` 属于正常层级表达，不报告为格式不统一
3. 商标声明页已经覆盖时，正文中的 `®`、`TM`、`™` 不要求重复补标
4. 海外英文手册仅提供 Email、未提供电话，默认视为可接受
5. 英文句号位于闭引号外、弯引号与直引号混用，默认按 PDF 提取或风格差异处理
6. 产品实际输出文件名中的占位符连写形式，例如 `ROINAMEquantification.csv`，默认视为可接受
7. `following status`、`turn on it` 这类已被人工接受的 PDF 表达，优先走视觉复核，不直接上报

【语义类误报抑制规则】
1. 语义类问题必须引用原文完整句子，不得仅凭单字/单词判断（"的"类缺字除外，须说明所在句子成分）
2. "冗余/多余"类必须给出删后仍通顺的句子，否则不上报
3. 方向相反类：仅当原文明显含该词时报告删除，不得建议添加原文没有的词
4. 表格衔接类：仅当表格后紧跟正文且确实无句号时报告"""


SEMANTIC_FEWSHOT_EXAMPLES = """
【语义检查示例】（"原句 → 审核结论"形式）

示例1（冗余）：
原句：关于本指南，本手册介绍了 G99 系统的操作方法。
结论：{"type":"冗余","severity":"suggestion","location":"封面","original":"关于本指南，","expected":"删除","rule":"无信息量引导语，可整体删除"}

示例2（冗余虚词）：
原句：请将样品放入离心机中。
结论：{"type":"冗余","severity":"suggestion","original":"请","expected":"删除","rule":"操作步骤不加敬语'请'"}

示例3（表述不准确）：
原句：系统会发出提示声音。
结论：{"type":"表述不准确","severity":"general","original":"发出提示声音","expected":"播放提示音","rule":"用词与实际不符，应为播放提示音"}

示例4（信息不完整）：
原句：点击关闭当前界面。
结论：{"type":"信息不完整","severity":"general","original":"点击关闭当前界面","expected":"点击关闭当前界面并返回主界面","rule":"缺后续动作，应返回主界面"}

示例5（一致性-大小写）：
原句：barcode 扫描完成后，系统显示 Barcode 编号。
结论：{"type":"一致性","severity":"general","original":"barcode...Barcode","expected":"统一为 Barcode","rule":"同一术语大小写不一致"}

示例6（方向相反）：
原句：请点击【开始】按钮。
结论：{"type":"语气","severity":"suggestion","original":"请","expected":"删除","rule":"操作步骤中不加'请'（UI 提示除外）"}
"""


def build_system_prompt() -> str:
    """构建完整的System Prompt"""
    english_words = ", ".join(ENGLISH_CORRECT_SPELLINGS)
    return SYSTEM_PROMPT_TEMPLATE.format(english_words=english_words) + SEMANTIC_FEWSHOT_EXAMPLES


def get_all_rules() -> dict:
    """获取所有规则"""
    return {
        "chinese_spelling": CHINESE_SPELLING_RULES,
        "chinese_punctuation": CHINESE_PUNCTUATION_RULES,
        "chinese_grammar": CHINESE_GRAMMAR_RULES,
        "chinese_terminology": CHINESE_TERMINOLOGY_RULES,
        "unit": UNIT_RULES,
        "compliance": COMPLIANCE_RULES,
        "english_spelling": ENGLISH_CORRECT_SPELLINGS,
        "english_grammar": ENGLISH_GRAMMAR_RULES,
        "british_american": BRITISH_AMERICAN_SPELLINGS,
        "v2_categories": V2_RULE_CATEGORIES,
    }
