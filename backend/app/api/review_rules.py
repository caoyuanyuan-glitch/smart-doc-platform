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
    {"pattern": r"[\u2018\u2019]", "expected": "【】", "severity": "general", "rule": "引号统一使用双引号或方括号"},
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
    {"pattern": r"【测序界面】", "expected": "测序界面", "severity": "general", "rule": "仅可交互UI元素用【】标注"},
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
    {"pattern": r"[a-zA-Z]、(?=[a-zA-Z])", "expected": ",", "severity": "serious", "rule": "中文顿号混入英文"},
]


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
4. 引号统一使用【】：点击'确定' → 点击【确定】

三、中文语法规则
1. 避免"不避免"类语法错误：如操作不当或不避免 → 如不按照说明操作
2. 避免使用成语：周而复始 → 如此循环
3. 避免文言化表述：未尽事宜 → 未覆盖的信息
4. 使用限期 → 使用期限或使用寿命

四、中文术语规则
1. 手工冰箱不是专业术语：传统手工冰箱 → 传统冰箱
2. 拍摄模组不含扫码器，应为识别模组
3. 仅可交互UI元素用【】标注
4. 同一概念全文统一，不混用

五、单位规则
1. Kg → kg
2. ml → mL
3. ul → μL
4. mins → min, hs → h, sec → s
5. 尺寸/倍数标注：20xTE → 20×TE

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
7. 乘号：使用 ×（如 20×TE）
8. 单词拆分：desktop（不是 desk top）

九、中文顿号混入英文（严重）
英文文档中不得出现中文顿号"，"。

【输出格式】
请按以下JSON格式输出审核结果，不要输出其他内容：
{{
  "issues": [
    {{
      "type": "拼写|语法|标点|术语|单位|合规|格式",
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
同一错误在同一文档中只报告第一次出现的位置，不要重复报告。"""


def build_system_prompt() -> str:
    """构建完整的System Prompt"""
    english_words = ", ".join(ENGLISH_CORRECT_SPELLINGS)
    return SYSTEM_PROMPT_TEMPLATE.format(english_words=english_words)


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
    }
