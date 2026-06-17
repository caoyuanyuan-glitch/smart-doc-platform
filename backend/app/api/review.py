from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import json
import re
import asyncio
import os
from app.database import get_db
from app.crud.document import get_document
from app.crud.review import create_review, get_review, get_reviews, update_review_status, create_issue, get_issues, update_issue
from app.crud.rule import get_rules
from app.crud.term import get_terms
from app.crud.audit_basis import get_audit_basis
from app.crud.knowledge import get_folder_tree, get_folder, get_folder_files
from app.schemas.review import Review, Issue, IssueUpdate, ReviewCreate, IssueCreate
from app.utils.ai_client import ai_client
from app.utils.spell_checker import run_spelling_and_grammar_check

router = APIRouter()


def get_knowledge_basis(db: Session):
    basis_list = []
    try:
        tree = get_folder_tree(db, None)
        for folder in tree:
            folder_obj = get_folder(db, folder.id)
            if folder_obj:
                files = get_folder_files(db, folder.id)
                for file in files:
                    basis_list.append({
                        "title": file.name,
                        "folder": folder.name,
                        "path": f"{folder.name}/{file.name}"
                    })
    except Exception as e:
        print(f"获取知识库审核依据失败: {e}")
    return basis_list


def extract_chapter(content, position):
    lines = content[:position].split('\n')
    chapter = ""
    for i in range(len(lines) - 1, max(0, len(lines) - 20), -1):
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


# ------------------------------------------------------------------
# 误报白名单: 常见合法英文缩写 / 公司名 / 术语 (避免简单正则误报)
# ------------------------------------------------------------------
_EN_ABBREV_ALLOWED = [
    "Ltd.", "Co.", "Inc.", "LLC.", "LLP.", "Corp.",
    "Mr.", "Mrs.", "Ms.", "Dr.", "Prof.",
    "e.g.", "i.e.", "etc.", "et al.",
    "P.R.", "R.P.", "U.S.A.", "U.K.", "U.S.",
    "vs.", "etc", "sq.",
]


def _in_abbreviation_allowed(text):
    t = text.strip()
    for a in _EN_ABBREV_ALLOWED:
        if t.lower() == a.lower() or t.lower().endswith(a.lower()):
            return True
    return False


def run_rule_audit(content, rules, knowledge_basis=None):
    """规则审核: 基于正则, 加上简易白名单过滤, 按内容去重"""
    issues = []
    document_language = detect_language(content)
    seen_keys = set()

    for rule in rules:
        try:
            if rule.language == "cn" and document_language == "en":
                continue
            if rule.language == "en" and document_language == "cn":
                continue

            matches = list(re.finditer(rule.regex, content))
            for match in matches:
                original_text = match.group()

                if document_language in ("en", "both") and _in_abbreviation_allowed(original_text):
                    continue

                chapter = extract_chapter(content, match.start())
                norm_text = re.sub(r"\s+", "", original_text).lower()
                dedup_key = f"{rule.rule_no}|{norm_text}|{chapter}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                context = get_context(content, match.start(), match.end(), 200)

                basis = rule.audit_basis if rule.audit_basis else ""
                if not basis and knowledge_basis:
                    for kb in knowledge_basis:
                        if any(kw.lower() in rule.description.lower() for kw in ["标点", "格式", "术语", "写作"]):
                            if any(name in kb["title"] for name in ["风格指南", "写作规范", "手册", "指南"]):
                                basis = kb["path"]
                                break

                issues.append({
                    "severity": "general",
                    "category": rule.category or "其他",
                    "rule": rule.rule_no,
                    "chapter": chapter,
                    "original_text": original_text,
                    "context": context,
                    "suggestion": rule.suggestion if rule.suggestion else "",
                    "description": rule.description or "",
                    "audit_basis": basis if basis else "技术文档写作规范",
                    "confidence": 100,
                    "source": "rule",
                    "position": f"{match.start()}-{match.end()}"
                })
        except Exception as e:
            print(f"规则 {getattr(rule,'rule_no','?')} 匹配出错: {e}")
            continue
    return issues


def run_term_check(content, terms):
    """术语检查: 按归一化原文去重"""
    issues = []
    if not terms:
        return issues

    seen_keys = set()
    for term in terms:
        try:
            if not term.non_standard:
                continue
            occurrences = list(re.finditer(re.escape(term.non_standard), content))
            for match in occurrences:
                chapter = extract_chapter(content, match.start())
                norm_text = re.sub(r"\s+", "", term.non_standard).lower()
                dedup_key = f"TERM|{norm_text}|{chapter}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                context = get_context(content, match.start(), match.end(), 200)
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
                    "source": "term",
                    "position": f"{match.start()}-{match.end()}"
                })
        except Exception as e:
            print(f"术语 {getattr(term, 'non_standard', '?')} 匹配出错: {e}")
            continue
    return issues


def dedupe_issues_by_original(issues):
    """按 '分类 + 归一化原文' 合并, 并保留出现次数最多的项"""
    if not issues:
        return []
    seen = {}
    for issue in issues:
        norm = re.sub(r"\s+", "", str(issue.get("original_text", ""))).lower()
        key = f"{issue.get('category','')}|{norm}"
        if not key.strip():
            continue
        if key in seen:
            # 保留 confidence 更高 / 章节更明确的项
            old = seen[key]
            new_conf = issue.get("confidence", 0) or 0
            old_conf = old.get("confidence", 0) or 0
            if new_conf > old_conf:
                seen[key] = issue
        else:
            seen[key] = issue
    return list(seen.values())


@router.post("/{document_id}")
async def create_review_task(document_id: int, mode: str = "hybrid", db: Session = Depends(get_db)):
    document = get_document(db, document_id=document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    review = create_review(db=db, review=ReviewCreate(document_id=document_id, mode=mode))

    try:
        issues = []
        content = document.content or ""
        content = content[:20000]
        document_language = detect_language(content)
        print(f"[审核] 文档ID={document_id}, 语言检测={document_language}, 内容长度={len(content)}字符")

        knowledge_basis = get_knowledge_basis(db)

        has_ai_client = ai_client.has_any_client
        print(f"[审核] AI客户端可用: {has_ai_client}, 模式={mode}")

        if mode in ["rule", "hybrid"]:
            rules = get_rules(db)
            print(f"[审核] 加载规则数量: {len(rules)}")
            rule_issues = run_rule_audit(content, rules, knowledge_basis)
            print(f"[审核] 规则匹配到问题: {len(rule_issues)}个")
            terms = get_terms(db)
            print(f"[审核] 加载术语数量: {len(terms)}")
            term_issues = run_term_check(content, terms)
            print(f"[审核] 术语匹配到问题: {len(term_issues)}个")

            # 英文文档进行拼写和语法检查
            if document_language in ("en", "both"):
                print(f"[审核] 开始拼写和语法检查...")
                try:
                    spelling_issues = run_spelling_and_grammar_check(content)
                    print(f"[审核] 拼写/语法检查发现问题: {len(spelling_issues)}个")
                    rule_issues.extend(spelling_issues)
                except Exception as e:
                    print(f"[审核] 拼写/语法检查失败: {e}")

            candidate_rule_issues = rule_issues + term_issues

            if has_ai_client and len(candidate_rule_issues) > 0:
                print(f"[审核] 开始AI二次验证，候选问题数={len(candidate_rule_issues)}")
                try:
                    filtered = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(None, ai_client.filter_rule_false_positives, candidate_rule_issues, document_language),
                        timeout=90.0
                    )
                    candidate_rule_issues = filtered
                    print(f"[审核] AI二次验证后保留问题数={len(candidate_rule_issues)}")
                except asyncio.TimeoutError:
                    print(f"[审核] AI 二次验证超时(90s), 使用原始规则结果({len(candidate_rule_issues)}个)")
                except Exception as e:
                    print(f"[审核] AI 二次验证失败, 使用原始规则结果: {e}")

            issues.extend(candidate_rule_issues)
            print(f"[审核] 规则审核阶段共产出问题数={len(candidate_rule_issues)}")

        if mode in ["ai", "hybrid"] and has_ai_client:
            print(f"[审核] 开始AI智能审核，模式={mode}")
            try:
                ai_result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, ai_client.audit_document, content, document_language),
                    timeout=180.0
                )
                ai_issues = ai_result.get("issues", [])
                print(f"[审核] AI审核返回问题数={len(ai_issues)}")
                for issue in ai_issues:
                    issue["source"] = "ai"
                    issue.setdefault("severity", "general")
                    issue.setdefault("category", "其他")
                    issue.setdefault("original_text", "")
                    issue.setdefault("context", "")
                    issue.setdefault("chapter", "")
                    issue.setdefault("rule", "AI")
                    issue.setdefault("suggestion", "")
                    issue.setdefault("description", "")
                    issue.setdefault("audit_basis", "AI 审核")
                    issue.setdefault("confidence", 80)
                    issue.setdefault("position", "")
                    if issue["severity"] not in ("fatal", "serious", "general", "suggestion"):
                        issue["severity"] = "general"

                issues.extend(ai_issues)
            except asyncio.TimeoutError:
                print(f"[审核] AI 审核超时(180s), 跳过 AI 审核")
            except Exception as e:
                print(f"[审核] AI 审核失败, 跳过 AI 审核: {e}")

        issues = dedupe_issues_by_original(issues)
        print(f"[审核] 去重后最终问题数={len(issues)}")
        if len(issues) > 0:
            categories = {}
            for issue in issues:
                cat = issue.get("category", "未分类")
                categories[cat] = categories.get(cat, 0) + 1
            print(f"[审核] 问题分类统计: {categories}")

        for issue in issues:
            create_issue(db=db, issue=IssueCreate(
                review_id=review.id,
                severity=issue["severity"],
                category=issue.get("category", ""),
                rule=issue.get("rule", ""),
                chapter=issue.get("chapter", ""),
                original_text=issue.get("original_text", ""),
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
            "fatal": len([i for i in issues if i.get("severity") == "fatal"]),
            "serious": len([i for i in issues if i.get("severity") == "serious"]),
            "general": len([i for i in issues if i.get("severity") == "general"]),
            "suggestion": len([i for i in issues if i.get("severity") == "suggestion"]),
            "language": document_language,
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
        <p><strong>上下文:</strong> {issue.context}</p>
        <p><strong>修改建议:</strong> {issue.suggestion}</p>
        <p><strong>问题描述:</strong> {issue.description}</p>
        <p><strong>审核依据:</strong> {issue.audit_basis}</p>
        <p><strong>置信度:</strong> {issue.confidence}%</p>
        <p><strong>来源:</strong> {issue.source}</p>
    </div>
"""

    html_content += "</body></html>"

    return {"content": html_content, "format": "html"}
