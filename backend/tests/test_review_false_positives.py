from app.review_engine import pipeline as review_pipeline
from app.review_engine.false_positives import is_rulebook_false_positive, rulebook_false_positive_reason


def test_nested_list_numbering_is_false_positive():
    issue = {
        "source": "ai",
        "rule": "AI-STYLE-001",
        "category": "格式规范",
        "severity": "general",
        "original_text": "1)",
        "context": "1. Prepare the sample\n  1) Mix the buffer\n  2) Incubate",
        "suggestion": "外层与内层编号格式不统一，请统一为 1. 2. 3.",
        "description": "嵌套有序列表编号差异",
        "audit_basis": "格式规范",
        "confidence": 88,
    }

    assert rulebook_false_positive_reason(issue) == "nested_ordered_list_numbering"
    assert review_pipeline.select_review_issues([issue]) == []


def test_official_global_site_is_false_positive():
    issue = {
        "source": "ai",
        "rule": "DET-URL-001",
        "category": "官网地址",
        "severity": "serious",
        "original_text": "https://global-mgitech.com/",
        "context": "Visit https://global-mgitech.com/ for support.",
        "suggestion": "官网地址错误，应改为 en.mgi-tech.com",
        "description": "术语一致性：官网地址不正确",
        "audit_basis": "官网规范",
        "confidence": 90,
    }

    assert is_rulebook_false_positive(issue) is True
    assert review_pipeline.select_review_issues([issue]) == []


def test_english_email_only_contact_is_false_positive():
    issue = {
        "source": "ai",
        "rule": "AI-CHECK-001",
        "category": "信息完整性",
        "severity": "general",
        "original_text": "MGI-service@mgi-tech.com",
        "context": "Technical support: MGI-service@mgi-tech.com",
        "suggestion": "The manufacturer contact is missing a telephone number.",
        "description": "English manual lacks a phone number",
        "audit_basis": "contact completeness",
        "confidence": 86,
    }

    assert rulebook_false_positive_reason(issue) == "english_manual_email_only_contact"


def test_english_email_chinese_complaint_is_false_positive():
    issue = {
        "source": "ai",
        "rule": "AI-CHECK-001",
        "category": "信息完整性",
        "severity": "general",
        "original_text": "MGI-service@mgi-tech.com",
        "context": "Technical support: MGI-service@mgi-tech.com",
        "suggestion": "制造商联系方式缺少联系电话",
        "description": "海外英文手册仅提供邮箱",
        "audit_basis": "信息完整性",
        "confidence": 86,
    }

    assert rulebook_false_positive_reason(issue) == "english_manual_email_only_contact"


def test_real_legacy_url_is_kept():
    issue = {
        "source": "rule",
        "rule": "DET-URL-001",
        "category": "官网地址",
        "severity": "serious",
        "original_text": "https://en.mgi-tech.com/",
        "context": "Visit https://en.mgi-tech.com/ for support.",
        "suggestion": "英文手册应使用 https://global-mgitech.com/",
        "description": "官网地址错误",
        "audit_basis": "官网规范",
        "confidence": 95,
    }

    assert is_rulebook_false_positive(issue) is False


def test_following_status_phrase_is_false_positive():
    issue = {
        "source": "ai",
        "rule": "AI-STYLE-001",
        "category": "Grammar",
        "severity": "general",
        "original_text": "following status",
        "context": "Check the following status on the screen.",
        "suggestion": "Change to following statuses",
        "description": "grammar",
        "audit_basis": "style",
        "confidence": 88,
    }

    assert rulebook_false_positive_reason(issue) == "accepted_pdf_phrase_following_status"
    assert review_pipeline.select_review_issues([issue]) == []


def test_product_output_filename_is_false_positive():
    issue = {
        "source": "ai",
        "rule": "AI-STYLE-001",
        "category": "格式规范",
        "severity": "general",
        "original_text": "ROINAMEquantification.csv",
        "context": "Export ROINAMEquantification.csv from the software.",
        "suggestion": "文件名连写不规范，应拆开",
        "description": "filename concatenation",
        "audit_basis": "style",
        "confidence": 88,
    }

    assert rulebook_false_positive_reason(issue) == "product_output_filename"


def test_rule_layer_figure_placeholder_is_false_positive():
    issue = {
        "source": "rule",
        "rule": "CYY-CN-PLACEHOLDER-001",
        "category": "占位符残留",
        "severity": "serious",
        "original_text": "XX/XX/XXXX",
        "suggestion": "请替换为正式内容或删除该占位符",
        "description": "文档中仍存在明显占位符残留，发布前需要替换为正式文本。",
        "audit_basis": "CYY人工审核经验基线 - 占位符残留",
        "confidence": 97,
    }

    assert rulebook_false_positive_reason(issue) == "figure_placeholder_mask"
    assert review_pipeline.select_review_issues([issue]) == []


def test_material_code_placeholder_is_kept():
    issue = {
        "source": "rule",
        "rule": "CYY-CN-MATERIAL-001",
        "category": "物料编码",
        "severity": "serious",
        "original_text": "00XXXX-00",
        "suggestion": "请申请并替换为正式物料编码",
        "description": "文档中仍存在 00XXXX 类物料编码占位符，发布前需要替换为正式编号。",
        "audit_basis": "CYY人工审核经验基线 - 物料编码占位",
        "confidence": 96,
    }

    assert rulebook_false_positive_reason(issue) is None


def test_pdf_trademark_text_layer_is_false_positive():
    issues = [
        {
            "source": "rule",
            "rule": "DOC-TM-001",
            "category": "商标格式",
            "severity": "general",
            "original_text": "DNBSEQTM",
            "suggestion": "DNBSEQ™",
            "description": "DNBSEQ 商标标识应使用 ™ 符号并保持格式一致，避免写成普通 TM 文本。",
            "audit_basis": "说明书发布前自检 Checklist - 商标标识一致性",
            "confidence": 93,
        },
        {
            "source": "ai",
            "rule": "商标需列明且为上标格式，商标归属对应正确",
            "category": "法规合规",
            "severity": "serious",
            "original_text": "® 是微软公司在美国和/ 或其他国家（地区）的商标或注册商标。",
            "suggestion": "商标声明应完整、正确对应各商标持有者，且上标格式正确",
            "description": "",
            "audit_basis": "说明书发布前自检Checklist第5条：文中出现的商标需列明，且为上标格式",
            "confidence": 90,
        },
    ]

    assert rulebook_false_positive_reason(issues[0]) == "pdf_trademark_text_layer"
    assert rulebook_false_positive_reason(issues[1]) == "pdf_trademark_text_layer"
    assert review_pipeline.select_review_issues(issues) == []
