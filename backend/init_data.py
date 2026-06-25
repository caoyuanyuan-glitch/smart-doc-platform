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
    
    db.query(Rule).delete()
    db.query(Term).delete()
    db.query(AuditBasis).delete()
    
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
            "audit_basis": "中文技术文档写作风格指南 - 中文标点符号",
            "language": "cn"
        },
        {
            "rule_no": "R002",
            "category": "标点符号",
            "description": "英文标点后应加空格",
            "regex": r"([.,?!;:])([a-zA-Z])",
            "example": "word.word 应改为 word. word",
            "suggestion": "英文标点后请添加空格",
            "audit_basis": "MGI英文技术文档写作风格指南 - Punctuation",
            "language": "en"
        },
        {
            "rule_no": "R003",
            "category": "标点符号",
            "description": "禁止标点符号重复",
            "regex": r"([.,?!;:]){2,}",
            "example": "Hello.. 应改为 Hello.",
            "suggestion": "请删除重复的标点符号",
            "audit_basis": "技术文档常见错误清单与规范 - 标点符号",
            "language": "both"
        },
        {
            "rule_no": "R004",
            "category": "标点符号",
            "description": "引号应成对出现",
            "regex": r"[\"“]([^\"”]*)$",
            "example": "\"Hello 应改为 \"Hello\"",
            "suggestion": "请补全缺失的右引号",
            "audit_basis": "中文技术文档写作风格指南 - 中文标点符号",
            "language": "both"
        },
        {
            "rule_no": "R005",
            "category": "标点符号",
            "description": "括号应成对出现",
            "regex": r"[\(\（]([^\)\）]*)$",
            "example": "(Hello 应改为 (Hello)",
            "suggestion": "请补全缺失的右括号",
            "audit_basis": "中文技术文档写作风格指南 - 中文标点符号",
            "language": "both"
        },
        {
            "rule_no": "R006",
            "category": "标点符号",
            "description": "禁止使用全角括号内的英文内容",
            "regex": r"（[a-zA-Z]+）",
            "example": "（DNA）应改为 (DNA)",
            "suggestion": "英文内容请使用半角括号",
            "audit_basis": "中文技术文档写作风格指南 - 中文标点符号",
            "language": "cn"
        },
        {
            "rule_no": "R007",
            "category": "标点符号",
            "description": "引号方向正确",
            "regex": r"(\")([^\"]*)(\"|$)",
            "example": "\"ON\" 不应为 \"ON\"",
            "suggestion": "请使用正确方向的引号",
            "audit_basis": "技术文档常见错误清单与规范 - 标点符号",
            "language": "both"
        },
        {
            "rule_no": "R008",
            "category": "标点符号",
            "description": "上角标格式正确",
            "regex": r"(\w+)[®™]",
            "example": "Qubit® 应改为 Qubit^®^",
            "suggestion": "商标符号应使用上角标格式",
            "audit_basis": "技术文档常见错误清单与规范 - 标点符号",
            "language": "en"
        },
        
        # ========== 单位规则 ==========
        {
            "rule_no": "R009",
            "category": "单位格式",
            "description": "微升单位应为μL",
            "regex": r"\bul\b",
            "example": "10ul 应改为 10 μL",
            "suggestion": "请将ul改为μL",
            "audit_basis": "技术文档常见错误清单与规范 - 单位",
            "language": "both"
        },
        {
            "rule_no": "R010",
            "category": "单位格式",
            "description": "毫升单位应为mL",
            "regex": r"\bml\b",
            "example": "100ml 应改为 100 mL",
            "suggestion": "请将ml改为mL",
            "audit_basis": "技术文档常见错误清单与规范 - 单位",
            "language": "both"
        },
        {
            "rule_no": "R011",
            "category": "单位格式",
            "description": "单位不应使用复数形式",
            "regex": r"\b(mins?|hs?|secs?)\b",
            "example": "5mins 应改为 5 min",
            "suggestion": "单位不应加s",
            "audit_basis": "技术文档常见错误清单与规范 - 单位",
            "language": "en"
        },
        {
            "rule_no": "R012",
            "category": "单位格式",
            "description": "千克单位应为kg",
            "regex": r"\bKg\b",
            "example": "10Kg 应改为 10 kg",
            "suggestion": "请将Kg改为kg",
            "audit_basis": "技术文档常见错误清单与规范 - 单位",
            "language": "both"
        },
        {
            "rule_no": "R013",
            "category": "单位格式",
            "description": "数字与单位之间应有空格",
            "regex": r"(\d+)([a-zA-Zμ℃℉%]+)",
            "example": "10mm 应改为 10 mm",
            "suggestion": "数字与单位之间请添加空格",
            "audit_basis": "MGI英文技术文档写作风格指南 - Numbers and measurements",
            "language": "en"
        },
        {
            "rule_no": "R014",
            "category": "单位格式",
            "description": "范围表示应使用~连接",
            "regex": r"(\d+\s*[a-zA-Zμ℃℉%]*)\s*[-–—]\s*(\d+\s*[a-zA-Zμ℃℉%]*)",
            "example": "10-20℃ 应改为 10 ~ 20 ℃",
            "suggestion": "范围表示请使用~连接",
            "audit_basis": "中文技术文档写作风格指南 - 数及数量",
            "language": "cn"
        },
        {
            "rule_no": "R015",
            "category": "单位格式",
            "description": "百分比数字与符号之间不应有空格",
            "regex": r"(\d+)\s+%",
            "example": "50 % 应改为 50%",
            "suggestion": "百分比符号前不应有空格",
            "audit_basis": "MGI英文技术文档写作风格指南 - Numbers and measurements",
            "language": "en"
        },
        
        # ========== 数字规则 ==========
        {
            "rule_no": "R016",
            "category": "数字格式",
            "description": "日期格式应统一为YYYY-MM-DD",
            "regex": r"\d{1,2}[-/]\d{1,2}[-/](\d{2}|\d{4})(?!\d)",
            "example": "2024/01/15 应改为 2024-01-15",
            "suggestion": "日期格式请统一为YYYY-MM-DD",
            "audit_basis": "中文技术文档写作风格指南 - 数及数量",
            "language": "both"
        },
        {
            "rule_no": "R017",
            "category": "数字格式",
            "description": "大数字应使用逗号分隔",
            "regex": r"\b(\d{4,})\b",
            "example": "10000 应改为 10,000",
            "suggestion": "大数字请使用逗号分隔",
            "audit_basis": "MGI英文技术文档写作风格指南 - Numbers and measurements",
            "language": "en"
        },
        {
            "rule_no": "R018",
            "category": "数字格式",
            "description": "中文文档中小于10的数字应使用文字",
            "regex": r"(?<!\d)\b([1-9])\b(?!\d)",
            "example": "5 应改为 五",
            "suggestion": "小于10的数字请使用中文数字",
            "audit_basis": "中文技术文档写作风格指南 - 数及数量",
            "language": "cn"
        },
        {
            "rule_no": "R019",
            "category": "数字格式",
            "description": "时间格式应统一为HH:MM:SS",
            "regex": r"\d{1,2}:\d{2}(?!:\d{2})",
            "example": "14:30 应改为 14:30:00",
            "suggestion": "时间格式请统一为HH:MM:SS",
            "audit_basis": "中文技术文档写作风格指南 - 数及数量",
            "language": "both"
        },
        
        # ========== 英文规则 ==========
        {
            "rule_no": "R020",
            "category": "英文规范",
            "description": "英文单词拼写检查",
            "regex": r"\b(teh|adn|wtih|hvae|tihs|taht|whta)\b",
            "example": "teh 应改为 the",
            "suggestion": "请检查单词拼写",
            "audit_basis": "MGI英文技术文档写作风格指南 - Spelling",
            "language": "en"
        },
        {
            "rule_no": "R021",
            "category": "英文规范",
            "description": "英文首字母大写",
            "regex": r"\b([a-z][a-z]+)\b(?=\s*\.)",
            "example": "hello. 应改为 Hello.",
            "suggestion": "句首单词首字母请大写",
            "audit_basis": "MGI英文技术文档写作风格指南 - Capitalization",
            "language": "en"
        },
        {
            "rule_no": "R022",
            "category": "英文规范",
            "description": "标题首字母大写",
            "regex": r"^([a-z])",
            "example": "hello world 应改为 Hello World",
            "suggestion": "标题首字母请大写",
            "audit_basis": "MGI英文技术文档写作风格指南 - Capitalization",
            "language": "en"
        },
        {
            "rule_no": "R023",
            "category": "英文规范",
            "description": "冠词使用检查",
            "regex": r"\b(a|an)\s+([aeiouAEIOU])",
            "example": "a apple 应改为 an apple",
            "suggestion": "元音开头单词前请使用an",
            "audit_basis": "MGI英文技术文档写作风格指南 - Articles",
            "language": "en"
        },
        {
            "rule_no": "R024",
            "category": "英文规范",
            "description": "英文单词连续重复",
            "regex": r"\b(\w+)\s+\1\b",
            "example": "the the 应改为 the",
            "suggestion": "请删除重复的单词",
            "audit_basis": "技术文档常见错误清单与规范 - 英文",
            "language": "en"
        },
        
        # ========== 中文规则 ==========
        {
            "rule_no": "R025",
            "category": "中文规范",
            "description": "禁止中英文混排无空格",
            "regex": r"([\u4e00-\u9fff])([a-zA-Z])|([a-zA-Z])([\u4e00-\u9fff])",
            "example": "中文English 应改为 中文 English",
            "suggestion": "中英文之间请添加空格",
            "audit_basis": "中文技术文档写作风格指南 - 中英文混排",
            "language": "cn"
        },
        {
            "rule_no": "R026",
            "category": "中文规范",
            "description": "禁止使用多余空格",
            "regex": r" {2,}",
            "example": "多 余 空格",
            "suggestion": "请删除多余空格",
            "audit_basis": "中文技术文档写作风格指南 - 排版规范",
            "language": "cn"
        },
        {
            "rule_no": "R027",
            "category": "中文规范",
            "description": "禁止使用全角空格",
            "regex": r"　",
            "example": "全角空格",
            "suggestion": "请使用半角空格",
            "audit_basis": "中文技术文档写作风格指南 - 排版规范",
            "language": "cn"
        },
        {
            "rule_no": "R028",
            "category": "中文规范",
            "description": "括号前不应有空格",
            "regex": r"(\S)\s+([\(\（])",
            "example": "内容 (括号) 应改为 内容(括号)",
            "suggestion": "括号前不应有空格",
            "audit_basis": "中文技术文档写作风格指南 - 中文标点符号",
            "language": "cn"
        },
        {
            "rule_no": "R029",
            "category": "中文规范",
            "description": "括号后应有空格",
            "regex": r"([\)\）])(\S)",
            "example": "(括号)内容 应改为 (括号) 内容",
            "suggestion": "括号后请添加空格",
            "audit_basis": "中文技术文档写作风格指南 - 中文标点符号",
            "language": "cn"
        },
        
        # ========== 格式规则 ==========
        {
            "rule_no": "R030",
            "category": "格式规范",
            "description": "标题格式统一",
            "regex": r"^(#+)\s*([^#].*)$",
            "example": "##标题 应改为 ## 标题",
            "suggestion": "标题符号后请添加空格",
            "audit_basis": "技术文档常见错误清单与规范 - Markdown",
            "language": "both"
        },
        {
            "rule_no": "R031",
            "category": "格式规范",
            "description": "列表格式检查",
            "regex": r"^\s*[-*+]\s*$",
            "example": "- 空列表项",
            "suggestion": "列表项请添加内容",
            "audit_basis": "技术文档常见错误清单与规范 - Markdown",
            "language": "both"
        },
        {
            "rule_no": "R032",
            "category": "格式规范",
            "description": "代码块格式检查",
            "regex": r"```(\w*)\s*$",
            "example": "```python 后应添加代码",
            "suggestion": "代码块请添加内容",
            "audit_basis": "技术文档常见错误清单与规范 - Markdown",
            "language": "both"
        },
        {
            "rule_no": "R033",
            "category": "格式规范",
            "description": "链接格式检查",
            "regex": r"\[([^\]]+)\]\(\)",
            "example": "[链接]() 应改为 [链接](url)",
            "suggestion": "链接请添加URL",
            "audit_basis": "技术文档常见错误清单与规范 - Markdown",
            "language": "both"
        },
        {
            "rule_no": "R034",
            "category": "格式规范",
            "description": "图片格式检查",
            "regex": r"!\[([^\]]*)\]\(\)",
            "example": "![图片]() 应改为 ![图片](url)",
            "suggestion": "图片请添加URL",
            "audit_basis": "技术文档常见错误清单与规范 - Markdown",
            "language": "both"
        },
        
        # ========== 语法规则 ==========
        {
            "rule_no": "R035",
            "category": "语法检查",
            "description": "中文句子过长",
            "regex": r"([^。！？\n]{50,})",
            "example": "超长句子",
            "suggestion": "建议拆分为多个短句",
            "audit_basis": "中文技术文档写作风格指南 - 句子",
            "language": "cn"
        },
        {
            "rule_no": "R036",
            "category": "语法检查",
            "description": "英文句子过长",
            "regex": r"([^.!?\n]{60,})",
            "example": "Very long sentence without punctuation",
            "suggestion": "建议拆分为多个短句",
            "audit_basis": "MGI英文技术文档写作风格指南 - Sentences",
            "language": "en"
        },
        {
            "rule_no": "R037",
            "category": "语法检查",
            "description": "被动语态检查",
            "regex": r"\b(was|were|is|are)\s+[a-z]+ed\b",
            "example": "was done 应改为 did",
            "suggestion": "建议使用主动语态",
            "audit_basis": "MGI英文技术文档写作风格指南 - Voice",
            "language": "en"
        },
        {
            "rule_no": "R038",
            "category": "语法检查",
            "description": "冗余修饰",
            "regex": r"\b(非常|十分|特别)\s+(重要|关键|核心)",
            "example": "非常重要 应改为 重要",
            "suggestion": "请简化修饰词",
            "audit_basis": "中文技术文档写作风格指南 - 词汇",
            "language": "cn"
        },
        
        # ========== 命名规则 ==========
        {
            "rule_no": "R039",
            "category": "命名规范",
            "description": "变量命名应使用驼峰式",
            "regex": r"\b(_[a-zA-Z]|[a-z][A-Z][a-z])\b",
            "example": "my_variable 应改为 myVariable",
            "suggestion": "变量命名请使用驼峰式",
            "audit_basis": "技术文档常见错误清单与规范 - 命名",
            "language": "en"
        },
        {
            "rule_no": "R040",
            "category": "命名规范",
            "description": "类名应使用 PascalCase",
            "regex": r"\bclass\s+[a-z]",
            "example": "class myClass 应改为 class MyClass",
            "suggestion": "类名首字母请大写",
            "audit_basis": "技术文档常见错误清单与规范 - 命名",
            "language": "en"
        },
        
        # ========== 专业术语 ==========
        {
            "rule_no": "R041",
            "category": "专业术语",
            "description": "技术术语拼写检查",
            "regex": r"\b(tecnology|tecnical|devlop|implementaion)\b",
            "example": "tecnology 应改为 technology",
            "suggestion": "请检查技术术语拼写",
            "audit_basis": "技术文档常见错误清单与规范 - 术语",
            "language": "en"
        },
        {
            "rule_no": "R042",
            "category": "专业术语",
            "description": "医学术语规范",
            "regex": r"\b(mg|mg\.|ml|ml\.)\b",
            "example": "mg 应改为 mg",
            "suggestion": "医学单位请使用标准缩写",
            "audit_basis": "医疗器械说明书和标签管理规定",
            "language": "both"
        },
        
        # ========== 一致性规则 ==========
        {
            "rule_no": "R043",
            "category": "一致性",
            "description": "术语前后不一致",
            "regex": r"\b(API|api|Api)\b",
            "example": "API和api混用",
            "suggestion": "请保持术语一致性",
            "audit_basis": "技术文档常见错误清单与规范 - 一致性",
            "language": "both"
        },
        {
            "rule_no": "R044",
            "category": "一致性",
            "description": "数字格式不一致",
            "regex": r"\b(\d{1,3})(\d{3})\b",
            "example": "100000 应改为 100,000",
            "suggestion": "大数字请使用千位分隔符",
            "audit_basis": "技术文档常见错误清单与规范 - 一致性",
            "language": "en"
        },
        
        # ========== 其他规则 ==========
        {
            "rule_no": "R045",
            "category": "其他",
            "description": "文件编码应为UTF-8",
            "regex": r"[\x80-\xFF]",
            "example": "非UTF-8字符",
            "suggestion": "请确保文件编码为UTF-8",
            "audit_basis": "技术文档常见错误清单与规范 - 编码",
            "language": "both"
        },
        {
            "rule_no": "R046",
            "category": "其他",
            "description": "禁止使用Tab缩进",
            "regex": r"\t",
            "example": "Tab缩进",
            "suggestion": "请使用空格缩进",
            "audit_basis": "技术文档常见错误清单与规范 - 缩进",
            "language": "both"
        },
        {
            "rule_no": "R047",
            "category": "其他",
            "description": "行尾不应有空格",
            "regex": r" +$",
            "example": "行尾空格",
            "suggestion": "请删除行尾空格",
            "audit_basis": "技术文档常见错误清单与规范 - 格式",
            "language": "both"
        },
        {
            "rule_no": "R048",
            "category": "其他",
            "description": "文件应以空行结尾",
            "regex": r"[^\n]$",
            "example": "文件末尾无空行",
            "suggestion": "文件末尾请添加空行",
            "audit_basis": "技术文档常见错误清单与规范 - 格式",
            "language": "both"
        },
        {
            "rule_no": "R049",
            "category": "其他",
            "description": "禁止使用BOM头",
            "regex": r"^\xef\xbb\xbf",
            "example": "UTF-8 BOM",
            "suggestion": "请移除BOM头",
            "audit_basis": "技术文档常见错误清单与规范 - 编码",
            "language": "both"
        },
        {
            "rule_no": "R050",
            "category": "其他",
            "description": "URL格式检查",
            "regex": r"https?://[^\s]+",
            "example": "http://example.com",
            "suggestion": "URL格式请正确",
            "audit_basis": "技术文档常见错误清单与规范 - 链接",
            "language": "both"
        }
    ]
    
    for rule_data in rules:
        rule = Rule(**rule_data)
        db.add(rule)
    
    db.commit()
    print("规则初始化完成")
    
    db.close()

if __name__ == "__main__":
    init_data()