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
