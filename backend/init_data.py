from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models.rule import Rule
from app.models.term import Term
from app.models.audit_basis import AuditBasis

DATABASE_URL = "sqlite:///./app.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_data():
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    # 添加50条审核规则（基于MGI中英文写作风格指南和常见错误清单）
    rules = [
        # ========== 标点符号规则 ==========
        {
            "rule_no": "R001",
            "category": "标点符号",
            "description": "中文文档应使用全角标点",
            "regex": r"(?<![a-zA-Z])[.,?!;](?![a-zA-Z])",
            "example": "Hello. 应改为 Hello。",
            "suggestion": "请将半角标点替换为全角标点",
            "audit_basis": "中文技术文档写作风格指南 - 中文标点符号"
        },
        {
            "rule_no": "R002",
            "category": "标点符号",
            "description": "英文标点后应加空格",
            "regex": r"([.,?!;:])([a-zA-Z])",
            "example": "word.word 应改为 word. word",
            "suggestion": "英文标点后请添加空格",
            "audit_basis": "MGI英文技术文档写作风格指南 - Punctuation"
        },
        {
            "rule_no": "R003",
            "category": "标点符号",
            "description": "禁止标点符号重复",
            "regex": r"([.,?!;:]){2,}",
            "example": "Hello.. 应改为 Hello.",
            "suggestion": "请删除重复的标点符号",
            "audit_basis": "技术文档常见错误清单与规范 - 标点符号"
        },
        {
            "rule_no": "R004",
            "category": "标点符号",
            "description": "引号应成对出现",
            "regex": r"[\"“]([^\"”]*)$",
            "example": "“Hello 应改为 “Hello”",
            "suggestion": "请补全缺失的右引号",
            "audit_basis": "中文技术文档写作风格指南 - 中文标点符号"
        },
        {
            "rule_no": "R005",
            "category": "标点符号",
            "description": "括号应成对出现",
            "regex": r"[\(\（]([^\)\）]*)$",
            "example": "(Hello 应改为 (Hello)",
            "suggestion": "请补全缺失的右括号",
            "audit_basis": "中文技术文档写作风格指南 - 中文标点符号"
        },
        {
            "rule_no": "R006",
            "category": "标点符号",
            "description": "禁止使用全角括号内的英文内容",
            "regex": r"（[a-zA-Z]+）",
            "example": "（DNA）应改为 (DNA)",
            "suggestion": "英文内容请使用半角括号",
            "audit_basis": "中文技术文档写作风格指南 - 中文标点符号"
        },
        {
            "rule_no": "R007",
            "category": "标点符号",
            "description": "引号方向正确",
            "regex": r"(\")([^\"]*)(\"|$)",
            "example": "\"ON\" 不应为 ”ON\"",
            "suggestion": "请使用正确方向的引号",
            "audit_basis": "技术文档常见错误清单与规范 - 标点符号"
        },
        {
            "rule_no": "R008",
            "category": "标点符号",
            "description": "上角标格式正确",
            "regex": r"(\w+)[®™]",
            "example": "Qubit® 应改为 Qubit^®^",
            "suggestion": "商标符号应使用上角标格式",
            "audit_basis": "技术文档常见错误清单与规范 - 标点符号"
        },
        
        # ========== 单位规则 ==========
        {
            "rule_no": "R009",
            "category": "单位格式",
            "description": "微升单位应为μL",
            "regex": r"\bul\b",
            "example": "10ul 应改为 10 μL",
            "suggestion": "请将ul改为μL",
            "audit_basis": "技术文档常见错误清单与规范 - 单位"
        },
        {
            "rule_no": "R010",
            "category": "单位格式",
            "description": "毫升单位应为mL",
            "regex": r"\bml\b",
            "example": "100ml 应改为 100 mL",
            "suggestion": "请将ml改为mL",
            "audit_basis": "技术文档常见错误清单与规范 - 单位"
        },
        {
            "rule_no": "R011",
            "category": "单位格式",
            "description": "单位不应使用复数形式",
            "regex": r"\b(mins?|hs?|secs?)\b",
            "example": "5mins 应改为 5 min",
            "suggestion": "单位不应加s",
            "audit_basis": "技术文档常见错误清单与规范 - 单位"
        },
        {
            "rule_no": "R012",
            "category": "单位格式",
            "description": "千克单位应为kg",
            "regex": r"\bKg\b",
            "example": "10Kg 应改为 10 kg",
            "suggestion": "请将Kg改为kg",
            "audit_basis": "技术文档常见错误清单与规范 - 单位"
        },
        {
            "rule_no": "R013",
            "category": "单位格式",
            "description": "数字与单位之间应有空格",
            "regex": r"(\d+)([a-zA-Zμ℃℉%]+)",
            "example": "10mm 应改为 10 mm",
            "suggestion": "数字与单位之间请添加空格",
            "audit_basis": "MGI英文技术文档写作风格指南 - Numbers and measurements"
        },
        {
            "rule_no": "R014",
            "category": "单位格式",
            "description": "范围表示应使用~连接",
            "regex": r"(\d+\s*[a-zA-Zμ℃℉%]*)\s*[-–—]\s*(\d+\s*[a-zA-Zμ℃℉%]*)",
            "example": "10-20℃ 应改为 10 ~ 20 ℃",
            "suggestion": "范围表示请使用~连接",
            "audit_basis": "中文技术文档写作风格指南 - 数及数量"
        },
        {
            "rule_no": "R015",
            "category": "单位格式",
            "description": "百分比数字与符号之间不应有空格",
            "regex": r"(\d+)\s+%",
            "example": "50 % 应改为 50%",
            "suggestion": "百分比符号前不应有空格",
            "audit_basis": "MGI英文技术文档写作风格指南 - Numbers and measurements"
        },
        
        # ========== 数字规则 ==========
        {
            "rule_no": "R016",
            "category": "数字格式",
            "description": "日期格式应统一为YYYY-MM-DD",
            "regex": r"\d{1,2}[-/]\d{1,2}[-/](\d{2}|\d{4})(?!\d)",
            "example": "2024/01/15 应改为 2024-01-15",
            "suggestion": "日期格式请统一为YYYY-MM-DD",
            "audit_basis": "中文技术文档写作风格指南 - 数及数量"
        },
        {
            "rule_no": "R017",
            "category": "数字格式",
            "description": "大数字应使用逗号分隔",
            "regex": r"\b(\d{4,})\b",
            "example": "10000 应改为 10,000",
            "suggestion": "大数字请使用逗号分隔",
            "audit_basis": "MGI英文技术文档写作风格指南 - Numbers and measurements"
        },
        {
            "rule_no": "R018",
            "category": "数字格式",
            "description": "小于10的数字应使用文字",
            "regex": r"\b([1-9])\b(?!\d)",
            "example": "5 应改为 五",
            "suggestion": "小于10的数字请使用中文数字",
            "audit_basis": "MGI英文技术文档写作风格指南 - Numbers and measurements"
        },
        {
            "rule_no": "R019",
            "category": "数字格式",
            "description": "时间格式应统一为HH:MM:SS",
            "regex": r"\d{1,2}:\d{2}(?!:\d{2})",
            "example": "14:30 应改为 14:30:00",
            "suggestion": "时间格式请统一为HH:MM:SS",
            "audit_basis": "中文技术文档写作风格指南 - 数及数量"
        },
        
        # ========== 术语规则 ==========
        {
            "rule_no": "R020",
            "category": "术语规范",
            "description": "禁止使用非标准术语",
            "regex": r"(账套|用户名|平台)",
            "example": "账套应改为租户",
            "suggestion": "请使用标准术语",
            "audit_basis": "中文技术文档写作风格指南 - 缩略语"
        },
        {
            "rule_no": "R021",
            "category": "术语规范",
            "description": "试剂与硬件用词正确",
            "regex": r"配[置制]",
            "example": "配置溶液应改为配制溶液",
            "suggestion": "试剂相关请使用'配制'，硬件相关请使用'配置'",
            "audit_basis": "技术文档常见错误清单与规范 - 错别字"
        },
        {
            "rule_no": "R022",
            "category": "术语规范",
            "description": "振荡与震荡用词正确",
            "regex": r"\b震[荡动]\b",
            "example": "震荡混匀应改为振荡混匀",
            "suggestion": "请使用'振荡'而非'震荡'",
            "audit_basis": "技术文档常见错误清单与规范 - 错别字"
        },
        {
            "rule_no": "R023",
            "category": "术语规范",
            "description": "仓与舱用词正确",
            "regex": r"试剂[舱仓]",
            "example": "试剂舱应改为试剂仓",
            "suggestion": "请使用'仓'表示存储空间",
            "audit_basis": "技术文档常见错误清单与规范 - 错别字"
        },
        {
            "rule_no": "R024",
            "category": "术语规范",
            "description": "储存与存储用词统一",
            "regex": r"\b存[\u50a8储]\b",
            "example": "存储应改为储存",
            "suggestion": "请统一使用'储存'",
            "audit_basis": "技术文档常见错误清单与规范 - 错别字"
        },
        {
            "rule_no": "R025",
            "category": "术语规范",
            "description": "移液器写法正确",
            "regex": r"\bPipet[s]?\b",
            "example": "Pipets 应改为 Pipettes",
            "suggestion": "请使用正确拼写Pipettes",
            "audit_basis": "技术文档常见错误清单与规范 - 错别字"
        },
        {
            "rule_no": "R026",
            "category": "术语规范",
            "description": "中英文夹杂处理",
            "regex": r"(Cat\.\s*No\.|Item\s*No\.)",
            "example": "Cat. No. 应改为 货号",
            "suggestion": "请使用中文表述",
            "audit_basis": "技术文档常见错误清单与规范 - 共性问题"
        },
        {
            "rule_no": "R027",
            "category": "术语规范",
            "description": "欧代标识正确",
            "regex": r"\bEC\s+REP\b",
            "example": "EC REP 应改为 EU REP",
            "suggestion": "请使用正确标识EU REP",
            "audit_basis": "技术文档常见错误清单与规范 - 共性问题"
        },
        {
            "rule_no": "R028",
            "category": "术语规范",
            "description": "缩略语首次出现应注明全称",
            "regex": r"\b(DNA|RNA|PCR|IVD|RUO)\b",
            "example": "DNA应注明(deoxyribonucleic acid)",
            "suggestion": "首次出现请注明全称",
            "audit_basis": "MGI英文技术文档写作风格指南 - Abbreviations and acronyms"
        },
        
        # ========== 时态语态规则 ==========
        {
            "rule_no": "R029",
            "category": "时态语态",
            "description": "应使用主动语态",
            "regex": r"[被被]动语态结构",
            "example": "被执行应改为执行",
            "suggestion": "请使用主动语态",
            "audit_basis": "MGI英文技术文档写作风格指南 - Voice"
        },
        {
            "rule_no": "R030",
            "category": "时态语态",
            "description": "应使用现在时态",
            "regex": r"(将|将会|将要|已)\s+[执行处理]",
            "example": "将执行应改为执行",
            "suggestion": "请使用现在时态",
            "audit_basis": "MGI英文技术文档写作风格指南 - Tense"
        },
        {
            "rule_no": "R031",
            "category": "时态语态",
            "description": "避免使用shall/will",
            "regex": r"\b(shall|will)\b",
            "example": "will begin 应改为 begins",
            "suggestion": "避免使用shall/will",
            "audit_basis": "MGI英文技术文档写作风格指南 - Tense"
        },
        
        # ========== 标题规则 ==========
        {
            "rule_no": "R032",
            "category": "标题格式",
            "description": "标题应使用正确样式",
            "regex": r"^#{1,6}\s+.+",
            "example": "一级标题使用#",
            "suggestion": "标题格式请遵循规范",
            "audit_basis": "中文技术文档写作风格指南 - 标题"
        },
        {
            "rule_no": "R033",
            "category": "标题格式",
            "description": "标题层级应正确嵌套",
            "regex": r"#{3,}\s+.+",
            "example": "三级标题应在二级标题之后",
            "suggestion": "请检查标题层级",
            "audit_basis": "中文技术文档写作风格指南 - 标题"
        },
        
        # ========== 句子规则 ==========
        {
            "rule_no": "R034",
            "category": "句子结构",
            "description": "句子应简洁",
            "regex": r"[^。！？]{100,}",
            "example": "句子超过100字",
            "suggestion": "请拆分长句",
            "audit_basis": "中文技术文档写作风格指南 - 句子"
        },
        {
            "rule_no": "R035",
            "category": "句子结构",
            "description": "避免使用双重否定",
            "regex": r"不.*不.*",
            "example": "不得不执行应改为必须执行",
            "suggestion": "请避免双重否定",
            "audit_basis": "中文技术文档写作风格指南 - 句子"
        },
        {
            "rule_no": "R036",
            "category": "句子结构",
            "description": "避免使用被动语态",
            "regex": r"[被被]\+动词",
            "example": "被处理应改为处理",
            "suggestion": "请使用主动语态",
            "audit_basis": "MGI英文技术文档写作风格指南 - Voice"
        },
        {
            "rule_no": "R037",
            "category": "句子结构",
            "description": "正确使用的/地/得",
            "regex": r"(的\s+动词|地\s+名词|得\s+名词)",
            "example": "开心的笑了应改为开心地笑了",
            "suggestion": "请正确使用的/地/得",
            "audit_basis": "中文技术文档写作风格指南 - 句子"
        },
        
        # ========== 英文规则 ==========
        {
            "rule_no": "R038",
            "category": "英文规范",
            "description": "英文单词拼写正确",
            "regex": r"\b(teh|adn|wtih|hvae|tihs)\b",
            "example": "teh 应改为 the",
            "suggestion": "请检查英文拼写",
            "audit_basis": "MGI英文技术文档写作风格指南 - Grammar"
        },
        {
            "rule_no": "R039",
            "category": "英文规范",
            "description": "英文大小写正确",
            "regex": r"\b(mysql|html|dna|rna)\b",
            "example": "mysql 应改为 MySQL",
            "suggestion": "专有名词首字母请大写",
            "audit_basis": "MGI英文技术文档写作风格指南 - Capitalization"
        },
        {
            "rule_no": "R040",
            "category": "英文规范",
            "description": "冠词使用正确",
            "regex": r"\b([aeiouAEIOU][a-zA-Z]+)\b",
            "example": "university 前应使用a",
            "suggestion": "请正确使用冠词",
            "audit_basis": "MGI英文技术文档写作风格指南 - Articles"
        },
        {
            "rule_no": "R041",
            "category": "英文规范",
            "description": "使用美式英语",
            "regex": r"\b(colour|centre|analyse)\b",
            "example": "colour 应改为 color",
            "suggestion": "请使用美式英语拼写",
            "audit_basis": "MGI英文技术文档写作风格指南 - Version of English"
        },
        
        # ========== 界面元素规则 ==========
        {
            "rule_no": "R042",
            "category": "界面元素",
            "description": "界面元素应加粗",
            "regex": r"(Click|Select|Tap)\s+(\w+)",
            "example": "Click Continue 应改为 Click **Continue**",
            "suggestion": "界面元素名称请加粗",
            "audit_basis": "MGI英文技术文档写作风格指南 - User interface"
        },
        {
            "rule_no": "R043",
            "category": "界面元素",
            "description": "菜单路径格式正确",
            "regex": r"(Menu|菜单)\s*[-→]\s*(\w+)",
            "example": "File -> Save 应使用 >",
            "suggestion": "菜单路径请使用 > 连接",
            "audit_basis": "中文技术文档写作风格指南 - 界面和控件"
        },
        
        # ========== 表格规则 ==========
        {
            "rule_no": "R044",
            "category": "表格规范",
            "description": "表格应有表头",
            "regex": r"\|.+\|",
            "example": "表格缺少表头",
            "suggestion": "请添加表头",
            "audit_basis": "中文技术文档写作风格指南 - 表格"
        },
        {
            "rule_no": "R045",
            "category": "表格规范",
            "description": "表格单元格不应为空",
            "regex": r"\|\s*\|",
            "example": "表格有空单元格",
            "suggestion": "空单元格请填写'无'或'-'",
            "audit_basis": "中文技术文档写作风格指南 - 表格"
        },
        
        # ========== 列表规则 ==========
        {
            "rule_no": "R046",
            "category": "列表规范",
            "description": "列表项应格式统一",
            "regex": r"^(\*|-|\d+\.)\s+",
            "example": "列表项格式不一致",
            "suggestion": "请使用统一的列表格式",
            "audit_basis": "中文技术文档写作风格指南 - 项目列表"
        },
        {
            "rule_no": "R047",
            "category": "列表规范",
            "description": "列表应至少包含两项",
            "regex": r"^(\*|-)\s+.+$",
            "example": "列表只有一项",
            "suggestion": "列表应至少包含两项",
            "audit_basis": "中文技术文档写作风格指南 - 项目列表"
        },
        
        # ========== 共性问题规则 ==========
        {
            "rule_no": "R048",
            "category": "共性问题",
            "description": "禁止使用推销性质词汇",
            "regex": r"(最佳|最好|最著名|最新技术|最高水平|最先进)",
            "example": "最佳产品应改为产品",
            "suggestion": "请避免使用推销性质词汇",
            "audit_basis": "中文技术文档写作风格指南 - 写作要求"
        },
        {
            "rule_no": "R049",
            "category": "共性问题",
            "description": "注意与切忌用词正确",
            "regex": r"(切忌|切记)",
            "example": "切忌远离应改为切记远离",
            "suggestion": "请正确区分注意与切忌",
            "audit_basis": "技术文档常见错误清单与规范 - 错别字"
        },
        {
            "rule_no": "R050",
            "category": "共性问题",
            "description": "以与已用词正确",
            "regex": r"\b以\b",
            "example": "设备以停止应改为设备已停止",
            "suggestion": "请正确区分以与已",
            "audit_basis": "技术文档常见错误清单与规范 - 错别字"
        }
    ]
    
    for rule_data in rules:
        if not db.query(Rule).filter(Rule.rule_no == rule_data["rule_no"]).first():
            db.add(Rule(**rule_data))
    
    # 添加术语
    terms = [
        {"standard": "租户", "non_standard": "账套"},
        {"standard": "用户", "non_standard": "用户名"},
        {"standard": "系统", "non_standard": "平台"},
        {"standard": "配置", "non_standard": "设定"},
        {"standard": "接口", "non_standard": "API"},
        {"standard": "执行", "non_standard": "运行"},
        {"standard": "完成", "non_standard": "结束"},
        {"standard": "开始", "non_standard": "启动"},
        {"standard": "使用", "non_standard": "采用"},
        {"standard": "包含", "non_standard": "包括"},
        {"standard": "进行", "non_standard": "执行"},
        {"standard": "检查", "non_standard": "查看"},
        {"standard": "设置", "non_standard": "配置"},
        {"standard": "选择", "non_standard": "挑选"},
        {"standard": "创建", "non_standard": "建立"}
    ]
    
    for term_data in terms:
        if not db.query(Term).filter(Term.non_standard == term_data["non_standard"]).first():
            db.add(Term(**term_data))
    
    # 添加审核依据
    basis_list = [
        {
            "name": "MGI中文技术文档写作风格指南",
            "file_type": "md",
            "content": "规定产品说明书/操作指南的中文写作风格，适用于产品说明书、操作指南、快速操作指南、软件操作指南等。"
        },
        {
            "name": "MGI英文技术文档写作风格指南",
            "file_type": "md",
            "content": "Provides writing rules for MGI technical writers, editors, reviewers, and UI designers. Covers language, grammar, punctuation, structure, numbers, user interface, etc."
        },
        {
            "name": "技术文档常见错误清单与规范",
            "file_type": "md",
            "content": "用于确保技术文档的准确性、一致性和专业性，涵盖标点符号、错别字、共性问题、单位等常见错误。"
        },
        {
            "name": "医疗器械说明书和标签管理规定（6号令）",
            "file_type": "pdf",
            "content": "医疗器械说明书应当符合国家标准和行业规范，内容应当真实、准确、完整。"
        },
        {
            "name": "GB/T 18268.1 电磁兼容性要求",
            "file_type": "pdf",
            "content": "测量、控制和实验室用的电设备电磁兼容性要求。"
        },
        {
            "name": "GB 4793.1 安全要求",
            "file_type": "pdf",
            "content": "测量、控制和实验室用电气设备的安全要求。"
        }
    ]
    
    for basis_data in basis_list:
        if not db.query(AuditBasis).filter(AuditBasis.name == basis_data["name"]).first():
            db.add(AuditBasis(**basis_data))
    
    db.commit()
    db.close()
    print("初始化数据成功！")

if __name__ == "__main__":
    init_data()
