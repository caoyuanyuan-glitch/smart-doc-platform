from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import json
import re
from app.database import get_db
from app.crud.document import get_document
from app.crud.review import create_review, get_review, get_reviews, update_review_status, create_issue, get_issues, update_issue
from app.crud.rule import get_rules
from app.crud.term import get_terms
from app.crud.audit_basis import get_audit_basis
from app.schemas.review import Review, Issue, IssueUpdate
from app.utils.ai_client import ai_client

router = APIRouter()

def extract_chapter(content, position):
    lines = content[:position].split('\n')
    chapter = ""
    for i in range(len(lines)-1, max(0, len(lines)-20), -1):
        line = lines[i].strip()
        if line.startswith('#') or line.startswith('##') or line.startswith('###'):
            chapter = line.lstrip('#').strip()
            break
    return chapter

def get_context(content, start, end, context_length=200):
    start_idx = max(0, start - context_length)
    end_idx = min(len(content), end + context_length)
    context = content[start_idx:end_idx]
    if start_idx > 0:
        context = "..." + context
    if end_idx < len(content):
        context = context + "..."
    return context

@router.get("/", response_model=list[Review])
async def list_reviews(db: Session = Depends(get_db)):
    reviews = get_reviews(db)
    result = []
    for review in reviews:
        doc = get_document(db, document_id=review.document_id)
        review_dict = review.__dict__.copy()
        review_dict['document_name'] = doc.filename if doc else ''
        result.append(review_dict)
    return result

def detect_language(content):
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', content)
    english_chars = re.findall(r'[a-zA-Z]', content)
    
    if len(chinese_chars) > len(english_chars) * 2:
        return "cn"
    elif len(english_chars) > len(chinese_chars) * 2:
        return "en"
    return "both"

def run_rule_audit(content, rules):
    issues = []
    document_language = detect_language(content)
    seen_issues = set()
    
    for rule in rules:
        try:
            if rule.language == "cn" and document_language == "en":
                continue
            if rule.language == "en" and document_language == "cn":
                continue
            
            matches = re.finditer(rule.regex, content)
            for match in matches:
                chapter = extract_chapter(content, match.start())
                context = get_context(content, match.start(), match.end(), 200)
                
                issue_key = f"{rule.rule_no}-{match.start()}"
                if issue_key in seen_issues:
                    continue
                seen_issues.add(issue_key)
                
                issues.append({
                    "severity": "general",
                    "category": rule.category,
                    "rule": rule.rule_no,
                    "chapter": chapter,
                    "original_text": match.group(),
                    "context": context,
                    "suggestion": rule.suggestion if rule.suggestion else "",
                    "description": rule.description,
                    "audit_basis": rule.audit_basis if rule.audit_basis else "技术文档写作规范",
                    "confidence": 100,
                    "source": rule.audit_basis if rule.audit_basis else "技术文档写作规范",
                    "position": f"{match.start()}-{match.end()}"
                })
        except Exception as e:
            continue
    return issues

def run_term_check(content, terms):
    issues = []
    for term in terms:
        occurrences = [m.start() for m in re.finditer(re.escape(term.non_standard), content)]
        for pos in occurrences:
            chapter = extract_chapter(content, pos)
            context = get_context(content, pos, pos + len(term.non_standard), 200)
            issues.append({
                "severity": "suggestion",
                "category": "术语规范",
                "rule": "TERM",
                "chapter": chapter,
                "original_text": term.non_standard,
                "context": context,
                "suggestion": f"建议使用标准术语: {term.standard}",
                "description": f"发现非标准术语: {term.non_standard}",
                "audit_basis": "MGI中文技术文档写作风格指南 - 缩略语",
                "confidence": 95,
                "source": "MGI中文技术文档写作风格指南 - 缩略语",
                "position": f"{pos}-{pos + len(term.non_standard)}"
            })
    return issues

@router.post("/{document_id}")
async def create_review_task(document_id: int, mode: str = "hybrid", db: Session = Depends(get_db)):
    document = get_document(db, document_id=document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    from app.schemas.review import ReviewCreate, IssueCreate
    review = create_review(db=db, review=ReviewCreate(document_id=document_id, mode=mode))
    
    try:
        issues = []
        
        if mode in ["rule", "hybrid"]:
            rules = get_rules(db)
            rule_issues = run_rule_audit(document.content, rules)
            issues.extend(rule_issues)
            
            terms = get_terms(db)
            term_issues = run_term_check(document.content, terms)
            issues.extend(term_issues)
        
        if mode in ["ai", "hybrid"]:
            ai_result = ai_client.audit_document(document.content)
            ai_issues = ai_result.get("issues", [])
            for issue in ai_issues:
                issue["source"] = "ai"
            issues.extend(ai_issues)
        
        for issue in issues:
            create_issue(db=db, issue=IssueCreate(
                review_id=review.id,
                severity=issue["severity"],
                category=issue["category"],
                rule=issue["rule"],
                chapter=issue["chapter"],
                original_text=issue["original_text"],
                context=issue.get("context", ""),
                suggestion=issue.get("suggestion", ""),
                description=issue.get("description", ""),
                audit_basis=issue.get("audit_basis", ""),
                confidence=issue.get("confidence", 0),
                source=issue.get("source", "rule"),
                position=issue.get("position", "")
            ))
        
        summary = json.dumps({
            "total": len(issues),
            "fatal": len([i for i in issues if i["severity"] == "fatal"]),
            "serious": len([i for i in issues if i["severity"] == "serious"]),
            "general": len([i for i in issues if i["severity"] == "general"]),
            "suggestion": len([i for i in issues if i["severity"] == "suggestion"])
        })
        
        update_review_status(db, review.id, "completed", len(issues), summary)
        
        return {"review_id": review.id, "total_issues": len(issues)}
    
    except Exception as e:
        update_review_status(db, review.id, "failed", 0, str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{review_id}", response_model=Review)
async def read_review(review_id: int, db: Session = Depends(get_db)):
    review = get_review(db, review_id=review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    doc = get_document(db, document_id=review.document_id)
    review_dict = review.__dict__.copy()
    review_dict['document_name'] = doc.filename if doc else ''
    return review_dict

@router.get("/{review_id}/issues", response_model=list[Issue])
async def read_review_issues(review_id: int, db: Session = Depends(get_db)):
    issues = get_issues(db, review_id=review_id)
    return issues

@router.put("/issues/{issue_id}", response_model=Issue)
async def update_issue_status(issue_id: int, issue_update: IssueUpdate, db: Session = Depends(get_db)):
    issue = update_issue(db, issue_id=issue_id, issue_update=issue_update)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue

@router.get("/{review_id}/report")
async def generate_report(review_id: int, db: Session = Depends(get_db)):
    review = get_review(db, review_id=review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    issues = get_issues(db, review_id=review_id)
    confirmed_issues = [i for i in issues if i.status in ["confirmed", "converted_to_rule"]]
    
    summary = json.loads(review.summary) if review.summary else {}
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>审核报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .summary {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        .summary td {{ border: 1px solid #ddd; padding: 8px; }}
        .issue {{ border: 1px solid #ddd; padding: 15px; margin-bottom: 10px; }}
        .fatal {{ border-left: 5px solid #dc3545; }}
        .serious {{ border-left: 5px solid #fd7e14; }}
        .general {{ border-left: 5px solid #ffc107; }}
        .suggestion {{ border-left: 5px solid #17a2b8; }}
    </style>
</head>
<body>
    <div class="header"><h1>智能技术文档审核报告</h1></div>
    <h2>审核概览</h2>
    <table class="summary">
        <tr><td>审核总数</td><td>{summary.get('total', 0)}</td></tr>
        <tr><td>致命问题</td><td>{summary.get('fatal', 0)}</td></tr>
        <tr><td>严重问题</td><td>{summary.get('serious', 0)}</td></tr>
        <tr><td>一般问题</td><td>{summary.get('general', 0)}</td></tr>
        <tr><td>建议</td><td>{summary.get('suggestion', 0)}</td></tr>
    </table>
    <h2>问题详情</h2>
"""
    
    for issue in confirmed_issues:
        html_content += f"""
    <div class="issue {issue.severity}">
        <h3>问题 #{issue.id}</h3>
        <p><strong>严重级别:</strong> {issue.severity}</p>
        <p><strong>分类:</strong> {issue.category}</p>
        <p><strong>规则:</strong> {issue.rule}</p>
        <p><strong>章节:</strong> {issue.chapter}</p>
        <p><strong>原文:</strong> {issue.original_text}</p>
        <p><strong>修改建议:</strong> {issue.suggestion}</p>
        <p><strong>问题描述:</strong> {issue.description}</p>
        <p><strong>审核依据:</strong> {issue.audit_basis}</p>
        <p><strong>置信度:</strong> {issue.confidence}%</p>
        <p><strong>来源:</strong> {issue.source}</p>
    </div>
"""
    
    html_content += "</body></html>"
    
    return {"content": html_content, "format": "html"}
