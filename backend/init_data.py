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
    
    # 添加规则
    rules = [
        {
            "rule_no": "R001",
            "category": "术语",
            "description": "禁止使用非标准术语",
            "regex": r"(账套|用户名)",
            "example": "账套应改为租户"
        },
        {
            "rule_no": "R002",
            "category": "格式",
            "description": "日期格式应统一为YYYY-MM-DD",
            "regex": r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}",
            "example": "2024/01/15 应改为 2024-01-15"
        },
        {
            "rule_no": "R003",
            "category": "标点",
            "description": "中文文档应使用中文标点",
            "regex": r"([a-zA-Z]+)[.?!]",
            "example": "Hello. 应改为 Hello。"
        },
        {
            "rule_no": "R004",
            "category": "数字",
            "description": "数字与单位之间应有空格",
            "regex": r"(\d+)([a-zA-Zμ]+)",
            "example": "10mm 应改为 10 mm"
        },
        {
            "rule_no": "R005",
            "category": "术语",
            "description": "产品名称应使用标准名称",
            "regex": r"(体外诊断试剂|检测试剂盒)",
            "example": "使用标准产品名称"
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
        {"standard": "接口", "non_standard": "API"}
    ]
    
    for term_data in terms:
        if not db.query(Term).filter(Term.non_standard == term_data["non_standard"]).first():
            db.add(Term(**term_data))
    
    # 添加审核依据
    basis_data = {
        "name": "医疗器械说明书编写规范",
        "file_type": "pdf",
        "content": "医疗器械说明书应当符合国家标准和行业规范，内容应当真实、准确、完整。"
    }
    
    if not db.query(AuditBasis).filter(AuditBasis.name == basis_data["name"]).first():
        db.add(AuditBasis(**basis_data))
    
    db.commit()
    db.close()
    print("初始化数据成功！")

if __name__ == "__main__":
    init_data()