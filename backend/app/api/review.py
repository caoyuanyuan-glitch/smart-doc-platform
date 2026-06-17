from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
import json
import re
import asyncio
import os
from datetime import datetime
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

_review_progress = {}  # 全局进度存储: {review_id: {'status': 'running', 'step': 'xxx', 'progress': 0-100, 'message': 'xxx'}}


def get_progress(review_id: int):
    return _review_progress.get(review_id, {'status': 'unknown', 'step': '', 'progress': 0, 'message': ''})


def set_progress(review_id: int, status: str, step: str, progress: int, message: str = ''):
    _review_progress[review_id] = {
        'status': status,
        'step': step,
        'progress': progress,
        'message': message,
        'timestamp': datetime.now().isoformat()
    }

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
        if not review_dict.get('summary'):
            review_dict['summary'] = '{}'
        # 添加进度信息
        if review.status == 'running':
            progress = get_progress(review.id)
            review_dict['progress'] = progress
        result.append(review_dict)
    return result


@router.get("/{review_id}/progress")
async def get_review_progress(review_id: int):
    return get_progress(review_id)


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


_TECH_TERMS = {
    'prep', 'device', 'consumables', 'reagents', 'extraction', 'extent', 'selection',
    'mg', 'ml', 'ul', 'μg', 'μl', 'kb', 'mb', 'gb', 'nm', 'mm', 'cm',
    'dna', 'rna', 'pcr', 'elisa', 'atp', 'cdna', 'mrna', 'trna',
    'buffer', 'solution', 'kit', 'system', 'assay', 'protocol', 'procedure',
    'sample', 'specimen', 'tube', 'plate', 'well', 'tip', 'pipette',
    'centrifuge', 'incubator', 'shaker', 'homogenizer', 'lyser',
    'volume', 'concentration', 'temperature', 'time', 'rpm', 'min', 'hr',
    'mgisp', 'bgiseq', 'dnbseq', 'dnb', 'cpas', 'coolmps',
    'quality', 'control', 'standard', 'reference', 'calibration', 'validation',
    'protocol', 'method', 'technique', 'approach', 'strategy', 'step',
}


def _is_tech_term(word):
    return word.lower() in _TECH_TERMS


def _is_sentence_start(content, position):
    before = content[max(0, position - 20):position]
    return before.strip().endswith('.') or before.strip().endswith('!') or before.strip().endswith('?') or position == 0


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

                if rule.rule_no in ("R021", "R022"):
                    if _is_tech_term(original_text):
                        continue
                    if rule.rule_no == "R021" and not _is_sentence_start(content, match.start()):
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
    """按 '分类 + 归一化原文 + 位置相近' 合并, 并保留出现次数最多的项"""
    if not issues:
        return []
    
    # 误报过滤 - 已知无效的模式
    FALSE_POSITIVE_PATTERNS = [
        re.compile(r'^[×±÷∞∑∏∫°℃℉]$'),  # 纯数学符号
        re.compile(r'^[\d\.]+$'),  # 纯数字
        re.compile(r'^[A-Z]{1,3}$'),  # 1-3个大写字母（避免误报为单词错误）
        re.compile(r'^[\.,;:\?!]+$'),  # 纯标点
    ]
    
    def is_false_positive(text):
        text = str(text).strip()
        if not text or len(text) < 2:
            return True
        for pat in FALSE_POSITIVE_PATTERNS:
            if pat.match(text):
                return True
        return False
    
    # 第一步：过滤已知误报
    filtered = [i for i in issues if not is_false_positive(i.get('original_text', ''))]
    print(f"[审核] 误报过滤: 过滤 {len(issues) - len(filtered)} 个, 剩余 {len(filtered)} 个")
    
    # 第二步：去重（按分类+归一化原文+章节）
    seen = {}
    for issue in filtered:
        norm = re.sub(r"\s+", "", str(issue.get("original_text", ""))).lower()
        chapter = issue.get("chapter", "")
        key = f"{issue.get('category','')}|{norm}|{chapter}"
        if not norm.strip():
            continue
        if key in seen:
            old = seen[key]
            new_conf = issue.get("confidence", 0) or 0
            old_conf = old.get("confidence", 0) or 0
            if new_conf > old_conf:
                seen[key] = issue
        else:
            seen[key] = issue
    return list(seen.values())


def _run_review_background(review_id: int, document_id: int, mode: str):
    """后台执行审核任务（带进度更新）"""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        set_progress(review_id, 'running', '加载文档', 5, '正在读取文档内容...')
        
        document = get_document(db, document_id=document_id)
        if not document:
            set_progress(review_id, 'failed', '文档不存在', 0, f'文档ID={document_id}不存在')
            update_review_status(db, review_id, "failed", 0, "Document not found")
            return

        issues = []
        content = document.content or ""
        content = content[:20000]
        document_language = detect_language(content)
        print(f"[审核] 文档ID={document_id}, 语言检测={document_language}, 内容长度={len(content)}字符")

        knowledge_basis = get_knowledge_basis(db)
        has_ai_client = ai_client.has_any_client
        print(f"[审核] AI客户端可用: {has_ai_client}, 模式={mode}")

        if mode in ["rule", "hybrid"]:
            set_progress(review_id, 'running', '规则审核', 15, '正在加载审核规则...')
            rules = get_rules(db)
            print(f"[审核] 加载规则数量: {len(rules)}")
            
            set_progress(review_id, 'running', '规则审核', 25, '正在执行规则匹配...')
            rule_issues = run_rule_audit(content, rules, knowledge_basis)
            print(f"[审核] 规则匹配到问题: {len(rule_issues)}个")

            set_progress(review_id, 'running', '术语检查', 35, '正在执行术语检查...')
            terms = get_terms(db)
            print(f"[审核] 加载术语数量: {len(terms)}")
            term_issues = run_term_check(content, terms)
            print(f"[审核] 术语匹配到问题: {len(term_issues)}个")

            if document_language in ("en", "both"):
                set_progress(review_id, 'running', '拼写检查', 45, '正在进行拼写和语法检查...')
                try:
                    spelling_issues = run_spelling_and_grammar_check(content)
                    print(f"[审核] 拼写/语法检查发现问题: {len(spelling_issues)}个")
                    rule_issues.extend(spelling_issues)
                except Exception as e:
                    print(f"[审核] 拼写/语法检查失败: {e}")

            candidate_rule_issues = rule_issues + term_issues

            if has_ai_client and len(candidate_rule_issues) > 0:
                set_progress(review_id, 'running', 'AI二次验证', 55, f'正在AI验证 {len(candidate_rule_issues)} 个候选问题...')
                print(f"[审核] 开始AI二次验证，候选问题数={len(candidate_rule_issues)}")
                try:
                    filtered = asyncio.get_event_loop().run_in_executor(None, ai_client.filter_rule_false_positives, candidate_rule_issues, document_language)
                    filtered = asyncio.run(asyncio.wait_for(filtered, timeout=90.0))
                    candidate_rule_issues = filtered
                    print(f"[审核] AI二次验证后保留问题数={len(candidate_rule_issues)}")
                except asyncio.TimeoutError:
                    print(f"[审核] AI 二次验证超时(90s), 使用原始规则结果({len(candidate_rule_issues)}个)")
                except Exception as e:
                    print(f"[审核] AI 二次验证失败, 使用原始规则结果: {e}")

            issues.extend(candidate_rule_issues)
            print(f"[审核] 规则审核阶段共产出问题数={len(candidate_rule_issues)}")

        if mode in ["ai", "hybrid"] and has_ai_client:
            set_progress(review_id, 'running', 'AI智能审核', 65, '正在进行AI深度审核...')
            print(f"[审核] 开始AI智能审核，模式={mode}")
            try:
                ai_result = asyncio.get_event_loop().run_in_executor(None, ai_client.audit_document, content, document_language)
                ai_result = asyncio.run(asyncio.wait_for(ai_result, timeout=180.0))
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

        set_progress(review_id, 'running', '结果处理', 85, '正在去重和保存结果...')
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
                review_id=review_id,
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

        set_progress(review_id, 'completed', '完成', 100, f'审核完成，发现 {len(issues)} 个问题')
        update_review_status(db, review_id, "completed", len(issues), summary)
        print(f"[审核] 任务完成, review_id={review_id}, 问题数={len(issues)}")

    except Exception as e:
        set_progress(review_id, 'failed', '失败', 0, str(e))
        update_review_status(db, review_id, "failed", 0, str(e))
        print(f"[审核] 任务失败, review_id={review_id}, 错误={e}")
    finally:
        db.close()


@router.post("/{document_id}")
async def create_review_task(document_id: int, mode: str = "hybrid", background_tasks: BackgroundTasks = None, db: Session = Depends(get_db)):
    document = get_document(db, document_id=document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    review = create_review(db=db, review=ReviewCreate(document_id=document_id, mode=mode))
    set_progress(review.id, 'running', '初始化', 0, '审核任务已创建')
    
    # 启动后台审核任务
    if background_tasks:
        background_tasks.add_task(_run_review_background, review.id, document_id, mode)
    
    return {"review_id": review.id, "status": "running", "message": "审核任务已启动，请轮询进度"}


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


@router.post("/{review_id}/judge")
async def batch_judge_issues(review_id: int, payload: dict, db: Session = Depends(get_db)):
    """批量人工判定问题: { 'judgments': [{'issue_id': 1, 'status': 'confirmed'}, ...] }"""
    judgments = payload.get("judgments", [])
    updated = 0
    for j in judgments:
        issue_id = j.get("issue_id")
        status = j.get("status")
        if not issue_id or not status:
            continue
        # 允许的状态: pending, confirmed, false_positive, ignored
        if status not in ["pending", "confirmed", "false_positive", "ignored"]:
            continue
        from app.schemas.review import IssueUpdate
        issue = update_issue(db, issue_id=issue_id, issue_update=IssueUpdate(status=status))
        if issue:
            updated += 1
    return {"updated": updated, "total": len(judgments)}


@router.get("/{review_id}/export-html")
async def export_review_html(review_id: int, db: Session = Depends(get_db)):
    """导出 HTML 报告 (包含所有问题及人工判定状态)"""
    from fastapi.responses import HTMLResponse
    review = get_review(db, review_id=review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    issues = get_issues(db, review_id=review_id)
    summary = json.loads(review.summary) if review.summary else {}

    # 统计人工判定结果
    confirmed = [i for i in issues if i.status == "confirmed"]
    false_pos = [i for i in issues if i.status == "false_positive"]
    pending = [i for i in issues if i.status in ["pending", None]]
    ignored = [i for i in issues if i.status == "ignored"]

    # 获取文档名
    doc = get_document(db, document_id=review.document_id)
    doc_name = doc.filename if doc else f"文档{review.document_id}"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>审核报告 - {doc_name}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; margin: 0; padding: 20px; background: #f5f7fa; color: #333; }}
        .container {{ max-width: 1100px; margin: 0 auto; background: #fff; padding: 30px 40px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #409eff; padding-bottom: 10px; }}
        h2 {{ color: #409eff; margin-top: 30px; }}
        .meta {{ background: #f8f9fa; padding: 15px; border-left: 4px solid #409eff; margin: 20px 0; }}
        .meta-row {{ margin: 5px 0; }}
        .meta-label {{ font-weight: bold; color: #555; display: inline-block; width: 100px; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin: 20px 0; }}
        .summary-card {{ padding: 15px; text-align: center; border-radius: 4px; color: #fff; }}
        .summary-card .num {{ font-size: 28px; font-weight: bold; }}
        .summary-card .label {{ font-size: 12px; margin-top: 5px; }}
        .card-total {{ background: #409eff; }}
        .card-confirmed {{ background: #67c23a; }}
        .card-false {{ background: #909399; }}
        .card-pending {{ background: #e6a23c; }}
        .card-ignored {{ background: #c0c4cc; }}
        .issue {{ border: 1px solid #e4e7ed; border-radius: 4px; padding: 15px 20px; margin: 12px 0; background: #fff; }}
        .issue.confirmed {{ border-left: 5px solid #67c23a; background: #f0f9eb; }}
        .issue.false_positive {{ border-left: 5px solid #909399; background: #f4f4f5; opacity: 0.7; }}
        .issue.ignored {{ border-left: 5px solid #c0c4cc; background: #fafafa; opacity: 0.6; }}
        .issue.pending {{ border-left: 5px solid #e6a23c; }}
        .issue-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
        .issue-title {{ font-weight: bold; color: #303133; }}
        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; color: #fff; margin-left: 6px; }}
        .badge-confirmed {{ background: #67c23a; }}
        .badge-false {{ background: #909399; }}
        .badge-pending {{ background: #e6a23c; }}
        .badge-ignored {{ background: #c0c4cc; }}
        .badge-severity-fatal {{ background: #f56c6c; }}
        .badge-severity-serious {{ background: #e6a23c; }}
        .badge-severity-general {{ background: #909399; }}
        .badge-severity-suggestion {{ background: #67c23a; }}
        .issue-field {{ margin: 6px 0; font-size: 14px; }}
        .issue-label {{ font-weight: bold; color: #606266; display: inline-block; min-width: 80px; }}
        .original-text {{ background: #fef0f0; padding: 4px 8px; border-radius: 3px; color: #c45656; font-family: 'Courier New', monospace; }}
        .suggestion {{ background: #f0f9eb; padding: 4px 8px; border-radius: 3px; color: #5a8e3f; }}
        .context {{ color: #666; font-style: italic; font-size: 13px; }}
        .empty {{ text-align: center; color: #909399; padding: 40px; }}
        .footer {{ margin-top: 40px; text-align: center; color: #909399; font-size: 12px; border-top: 1px solid #ebeef5; padding-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>智能技术文档审核报告</h1>
        <div class="meta">
            <div class="meta-row"><span class="meta-label">文档名称:</span> {doc_name}</div>
            <div class="meta-row"><span class="meta-label">审核任务:</span> #{review.id}</div>
            <div class="meta-row"><span class="meta-label">审核模式:</span> {review.mode}</div>
            <div class="meta-row"><span class="meta-label">审核时间:</span> {review.created_at}</div>
            <div class="meta-row"><span class="meta-label">报告生成:</span> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>

        <h2>审核概览</h2>
        <div class="summary-grid">
            <div class="summary-card card-total"><div class="num">{len(issues)}</div><div class="label">发现问题</div></div>
            <div class="summary-card card-confirmed"><div class="num">{len(confirmed)}</div><div class="label">已确认</div></div>
            <div class="summary-card card-false"><div class="num">{len(false_pos)}</div><div class="label">误报</div></div>
            <div class="summary-card card-pending"><div class="num">{len(pending)}</div><div class="label">待确认</div></div>
            <div class="summary-card card-ignored"><div class="num">{len(ignored)}</div><div class="label">已忽略</div></div>
        </div>
"""

    if not issues:
        html += '<div class="empty">未发现任何问题</div>'
    else:
        html += '<h2>问题详情 (共 {0} 条)</h2>'.format(len(issues))
        # 按状态排序: confirmed > pending > false_positive > ignored
        order = {"confirmed": 0, "pending": 1, None: 1, "": 1, "false_positive": 2, "ignored": 3}
        sorted_issues = sorted(issues, key=lambda i: (order.get(i.status, 1), i.id))

        for issue in sorted_issues:
            sev_class = f"badge-severity-{issue.severity or 'general'}"
            status = issue.status or "pending"
            status_class = {
                "confirmed": "badge-confirmed",
                "false_positive": "badge-false",
                "ignored": "badge-ignored",
                "pending": "badge-pending"
            }.get(status, "badge-pending")
            status_text = {
                "confirmed": "已确认",
                "false_positive": "误报",
                "ignored": "已忽略",
                "pending": "待确认"
            }.get(status, "待确认")

            html += f"""
        <div class="issue {status}">
            <div class="issue-header">
                <div class="issue-title">问题 #{issue.id} - {issue.category or '未分类'}</div>
                <div>
                    <span class="badge {sev_class}">{(issue.severity or 'general').upper()}</span>
                    <span class="badge {status_class}">{status_text}</span>
                </div>
            </div>
            <div class="issue-field"><span class="issue-label">规则:</span> {issue.rule or '-'}</div>
            <div class="issue-field"><span class="issue-label">章节:</span> {issue.chapter or '-'}</div>
            <div class="issue-field"><span class="issue-label">原文:</span> <span class="original-text">{issue.original_text or ''}</span></div>
            <div class="issue-field"><span class="issue-label">上下文:</span> <span class="context">{issue.context or '-'}</span></div>
            <div class="issue-field"><span class="issue-label">建议:</span> <span class="suggestion">{issue.suggestion or '-'}</span></div>
            <div class="issue-field"><span class="issue-label">依据:</span> {issue.audit_basis or '-'}</div>
            <div class="issue-field"><span class="issue-label">置信度:</span> {issue.confidence or 0}% | <span class="issue-label">来源:</span> {issue.source or '-'}</div>
        </div>
"""

    html += f"""
        <div class="footer">由 智能技术文档审核平台 生成 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html)


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
