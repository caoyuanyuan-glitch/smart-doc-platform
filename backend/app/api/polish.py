from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import timedelta
import os
import uuid
import mimetypes
import re
from app.database import get_db
from app.crud.document import get_document
from app.crud.polished_document import (
    get_polished_documents, get_polished_document, create_polished_document, delete_polished_document
)
from app.api.auth import get_current_user, get_default_user
from app.models.knowledge import KnowledgeFile, Folder

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "polished")
POLISHED_FOLDER_NAME = "已润色文档"


def _get_or_create_polished_folder(db, user_id: int) -> tuple:
    """已合并至物理目录创建逻辑，不再使用知识库文件夹。"""
    return None, None


def _get_date_subfolder_id(db, folder_id: int, user_id: int) -> tuple:
    """返回物理目录路径和 None 作为 folder_id"""
    from datetime import datetime
    date_str = datetime.now().strftime("%Y%m%d")
    return None, date_str


class TextPolishInput(BaseModel):
    text: str


class SkillPolishInput(BaseModel):
    text: str
    skill_id: int = 3
    style_guide_id: int = 1
    terminology_id: Optional[int] = None


class PolishRuleMatch(BaseModel):
    rule_name: str
    before: str
    after: str
    type: str


def _apply_style_rules(text: str) -> tuple[str, list]:
    """根据写作风格指南应用基础润色规则"""
    changes = []
    
    # 规则1: 中文标点统一
    text = re.sub(r'(?<=[\u4e00-\u9fff])[,;:!?](?!\s)', lambda m: {
        ',': '，',
        ';': '；',
        ':': '：',
        '!': '！',
        '?': '？'
    }.get(m.group(), m.group()), text)
    
    # 规则2: UI控件格式化为【】
    text = re.sub(r'["""](.*?)["""]', r'【\1】', text)
    
    # 规则3: 数字与单位间加空格
    text = re.sub(r'(\d)([a-zA-Z℃%])', r'\1 \2', text)
    
    # 规则4: 中英文间加空格（中文在英文前）
    text = re.sub(r'([\u4e00-\u9fff])([A-Za-z])', r'\1 \2', text)
    
    # 规则5: 中英文间加空格（英文在中文前）
    text = re.sub(r'([A-Za-z])([\u4e00-\u9fff])', r'\1 \2', text)
    
    # 规则6: 去除多余空格
    text = re.sub(r'[ \t]{2,}', ' ', text)
    
    # 收集修改记录
    if text != text:
        changes.append({
            "rule_name": "标点符号规范化",
            "before": "...",
            "after": "...",
            "type": "format"
        })
    
    return text, changes


def _load_skill_rules(skill_id: int, db: Session) -> dict:
    """从知识库加载skill规则"""
    skill_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == skill_id).first()
    if not skill_file:
        return {}
    
    with open(skill_file.file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    return {
        "skill_content": content,
        "rules": {
            "句式规范化": True,
            "术语统一": True,
            "格式规范": True
        }
    }


def _apply_skill_polish(
    text: str, 
    skill_rules: dict, 
    db: Session,
    sentence_guide: str = None,
    terminology: str = None,
    requirements: str = None
) -> tuple[str, list[PolishRuleMatch]]:
    """应用skill规则进行润色"""
    changes = []
    lines = text.split('\n')
    polished_lines = []
    
    style_rules = []
    if sentence_guide:
        style_rules = _extract_style_rules(sentence_guide)
    
    term_dict = {}
    if terminology:
        try:
            for row in terminology.split('\n'):
                row = row.strip()
                if '|' not in row or row.startswith('#') or row.startswith('|---') or row.startswith('|序号'):
                    continue
                cells = [c.strip() for c in row.split('|') if c.strip()]
                clean_cells = [c for c in cells if c and c != '---']
                if len(clean_cells) >= 2 and not clean_cells[0].startswith('##'):
                    for i in range(0, len(clean_cells) - 1, 2):
                        old_term = clean_cells[i].strip().strip('!')
                        new_term = clean_cells[i + 1].strip().strip('!')
                        if old_term and new_term and len(old_term) > 1 and old_term != new_term:
                            term_dict[old_term] = new_term
        except Exception:
            pass
    
    for line in lines:
        original = line
        new_line = line.strip()
        
        has_changes = False
        
        if terminology and term_dict:
            for old_term, new_term in term_dict.items():
                if old_term in new_line:
                    new_line = new_line.replace(old_term, new_term)
                    changes.append(PolishRuleMatch(
                        rule_name="术语替换",
                        before=old_term,
                        after=new_term,
                        type="terminology"
                    ))
                    has_changes = True
        
        if style_rules:
            new_line, rule_changes = _apply_style_rules(new_line, style_rules)
            if rule_changes:
                changes.extend(rule_changes)
                has_changes = True
        
        new_line = re.sub(r'\s+', ' ', new_line)
        
        if new_line and not new_line.endswith(('。', '.', '！', '!', '？', '?')):
            if re.search(r'[\u4e00-\u9fff]', new_line):
                new_line = new_line.rstrip('，,；;：:') + '。'
            else:
                new_line = new_line.rstrip(',,;;::') + '.'
        
        new_line = re.sub(r'(\d)([a-zA-Z℃%μ])', r'\1 \2', new_line)
        
        new_line = re.sub(r'([\u4e00-\u9fff])([A-Za-z0-9])', r'\1 \2', new_line)
        new_line = re.sub(r'([A-Za-z0-9])([\u4e00-\u9fff])', r'\1 \2', new_line)
        
        if new_line != original or has_changes:
            change_type = "format"
            if '。' in new_line[-2:] and original[-1] not in '。.!！？?':
                change_type = "punctuation"
            elif terminology and term_dict:
                change_type = "terminology"
            elif style_rules:
                change_type = "style"
            
            changes.append(PolishRuleMatch(
                rule_name="基础规范化",
                before=original[:80],
                after=new_line[:80],
                type=change_type
            ))
        
        polished_lines.append(new_line)
    
    return '\n'.join(polished_lines), changes


def _extract_style_rules(guide_text: str) -> list[dict]:
    """从句式指南中提取可执行的检测规则，解析 Markdown 内容"""
    rules = []
    
    # 从 guide_text 中解析实际规则，否则使用默认规则
    if guide_text and guide_text.strip():
        # 解析 ## 开头的章节作为规则类别
        sections = re.split(r'\n(?=##\s)', guide_text)
        for section in sections:
            header_match = re.match(r'##\s+(.+)', section)
            if not header_match:
                continue
            header = header_match.group(1).strip()
            
            # 提取列表项作为具体规则
            items = re.findall(r'(?:^|\n)[-*]\s+(.+)', section)
            
            if not items:
                continue
            
            # 判断规则类型
            lower_header = header.lower()
            if any(kw in lower_header for kw in ['禁用', '禁止', 'forbidden', '避免使用', '不要用']):
                # 从列表中提取短语
                phrases = []
                replacements = {}
                for item in items:
                    # 匹配 "A → B" 或 "A -> B" 或 "A：B" 格式
                    arrow_match = re.match(r'(.+?)\s*(?:→|->|：)\s*(.+)', item)
                    if arrow_match:
                        old_phrase = arrow_match.group(1).strip().strip('"\'「」""''')
                        new_phrase = arrow_match.group(2).strip().strip('"\'「」""''')
                        phrases.append(old_phrase)
                        replacements[old_phrase] = new_phrase
                    else:
                        phrase = item.strip().strip('"\'「」""''')
                        if phrase:
                            phrases.append(phrase)
                
                if phrases:
                    rules.append({
                        "type": "forbidden_words",
                        "name": header,
                        "patterns": phrases,
                        "replacements": replacements if replacements else None,
                        "fix": "替换为更规范的表达"
                    })
            
            elif any(kw in lower_header for kw in ['被动', 'passive', '语态']):
                patterns = []
                for item in items:
                    item = item.strip().strip('`')
                    if item:
                        patterns.append((item, "主动语态"))
                if patterns:
                    rules.append({
                        "type": "passive_voice",
                        "name": header,
                        "patterns": patterns,
                        "fix": "改用主动语态"
                    })
            
            elif any(kw in lower_header for kw in ['双重否定', 'double negative']):
                patterns = []
                for item in items:
                    item = item.strip().strip('`')
                    if item:
                        patterns.append((item, "双重否定"))
                if patterns:
                    rules.append({
                        "type": "double_negative",
                        "name": header,
                        "patterns": patterns,
                        "fix": "改用肯定表达"
                    })
            
            elif any(kw in lower_header for kw in ['非正式', 'informal', '口语', '俚语']):
                patterns = []
                for item in items:
                    item = item.strip().strip('`')
                    if item:
                        patterns.append((item, "非正式语言"))
                if patterns:
                    rules.append({
                        "type": "informal",
                        "name": header,
                        "patterns": patterns,
                        "fix": "使用正式表达"
                    })
            
            elif any(kw in lower_header for kw in ['句子长度', 'sentence length', '长句', '字数']):
                max_chars = 100
                for item in items:
                    num_match = re.search(r'(\d+)', item)
                    if num_match:
                        max_chars = int(num_match.group(1))
                        break
                rules.append({
                    "type": "sentence_length",
                    "name": header,
                    "max_chars": max_chars,
                    "fix": "拆分过长句子"
                })
            
            elif any(kw in lower_header for kw in ['代词', 'pronoun', '指代']):
                patterns = []
                for item in items:
                    item = item.strip().strip('`')
                    if item:
                        patterns.append((item, "代词指代不明确"))
                if patterns:
                    rules.append({
                        "type": "pronoun_reference",
                        "name": header,
                        "patterns": patterns,
                        "fix": "明确指代对象"
                    })
            
            elif any(kw in lower_header for kw in ['术语', 'terminology', '词汇']):
                term_map = {}
                for item in items:
                    arrow_match = re.match(r'(.+?)\s*(?:→|->|：)\s*(.+)', item)
                    if arrow_match:
                        old_term = arrow_match.group(1).strip().strip('"\'「」""''')
                        new_term = arrow_match.group(2).strip().strip('"\'「」""''')
                        term_map[old_term] = new_term
                if term_map:
                    rules.append({
                        "type": "terminology_rule",
                        "name": header,
                        "term_map": term_map,
                        "fix": "统一术语"
                    })
    
    # 如果没有从文件中解析出规则，使用默认规则
    if not rules:
        rules = _default_style_rules()
    
    return rules


def _default_style_rules() -> list[dict]:
    """默认句式规则（当 KB 中无自定义规则时使用）"""
    return [
        {
            "type": "forbidden_words",
            "name": "禁用强调词",
            "patterns": ["最佳", "最好", "最著名", "最新技术", "最高水平", "最先进水平", "最高技术", "非常", "极其"],
            "fix": "删除或替换为客观描述"
        },
        {
            "type": "passive_voice",
            "name": "被动转主动",
            "patterns": [(r'被(用于|应用于|设计|制造|创建|安装|设置|配置|提供|调用|使用)', "主动语态"), (r'由.+?提供(了)?', "主动语态")],
            "fix": "改用主动语态"
        },
        {
            "type": "double_negative",
            "name": "避免双重否定",
            "patterns": [(r'不(能|得|可|允许).+?不(能|得|可|允许)', "双重否定"), (r'没(有)?.+?不(能|得|可)', "双重否定"), (r'非.+?不', "双重否定")],
            "fix": "改用肯定表达"
        },
        {
            "type": "informal",
            "name": "避免非正式语言",
            "patterns": [(r'[酷毙|爽翻|给力|碉堡|牛逼]', "非正式语言"), (r'！{2,}', "过度感叹"), (r'～{2,}', "过度波浪号")],
            "fix": "使用正式表达"
        },
        {
            "type": "sentence_length",
            "name": "句子长度控制",
            "max_chars": 100,
            "fix": "拆分长句"
        },
        {
            "type": "pronoun_reference",
            "name": "代词指代明确",
            "patterns": [(r'其[中他它们她]', "代词指代不明"), (r'该.+?(?!系统|设备|产品|方法|技术|功能|模块|参数|配置)', "代词指代不明")],
            "fix": "明确指代对象"
        },
    ]


def _apply_style_rules(text: str, rules: list[dict]) -> tuple[str, list[PolishRuleMatch]]:
    """对单句应用句式风格规则"""
    changes = []
    result = text
    
    forbidden_words_map = {
        "最佳": "较优",
        "最好": "较优", 
        "最著名": "知名",
        "最新技术": "先进技术",
        "最高水平": "先进水平",
        "最先进水平": "先进水平",
        "最高技术": "先进技术",
        "非常": "",
        "极其": "",
        "最": "较"
    }
    
    for rule in rules:
        if rule["type"] == "forbidden_words":
            # 优先使用规则中指定的替换表，回退到硬编码映射
            rule_replacements = rule.get("replacements", {}) or {}
            for phrase in rule["patterns"]:
                if phrase in result:
                    original = result
                    replacement = rule_replacements.get(phrase) or forbidden_words_map.get(phrase, "")
                    result = result.replace(phrase, replacement)
                    result = re.sub(r'\s+', ' ', result).strip()
                    if result != original:
                        changes.append(PolishRuleMatch(
                            rule_name=rule["name"],
                            before=f"...{phrase}...",
                            after=result[:50],
                            type="style"
                        ))
        
        elif rule["type"] == "passive_voice":
            for pattern, issue in rule["patterns"]:
                match = re.search(pattern, result)
                if match:
                    changes.append(PolishRuleMatch(
                        rule_name=rule["name"],
                        before=match.group()[:50],
                        after="建议改用主动语态",
                        type="style"
                    ))
        
        elif rule["type"] == "double_negative":
            for pattern, issue in rule["patterns"]:
                match = re.search(pattern, result)
                if match:
                    changes.append(PolishRuleMatch(
                        rule_name=rule["name"],
                        before=match.group()[:50],
                        after="建议改用肯定表达",
                        type="style"
                    ))
        
        elif rule["type"] == "informal":
            informal_replacements = {
                "牛逼": "出色",
                "酷毙": "高效",
                "给力": "有效",
                "碉堡": "优异",
                "！": "。"
            }
            for pattern, issue in rule["patterns"]:
                match = re.search(pattern, result)
                if match:
                    original = result
                    for informal, formal in informal_replacements.items():
                        if informal in result:
                            result = result.replace(informal, formal)
                    result = re.sub(r'！+', '。', result)
                    result = result.strip()
                    if result != original:
                        changes.append(PolishRuleMatch(
                            rule_name=rule["name"],
                            before=match.group()[:50],
                            after=result[:50],
                            type="style"
                        ))
        
        elif rule["type"] == "sentence_length":
            clean = re.sub(r'[，。；！？、,.!?;、]', '', result)
            if len(clean) > rule["max_chars"]:
                changes.append(PolishRuleMatch(
                    rule_name=rule["name"],
                    before=f"句子长度{len(clean)}字",
                    after=f"建议控制在{rule['max_chars']}字以内",
                    type="style"
                ))
        
        elif rule["type"] == "pronoun_reference":
            for pattern, issue in rule["patterns"]:
                match = re.search(pattern, result)
                if match:
                    changes.append(PolishRuleMatch(
                        rule_name=rule["name"],
                        before=match.group()[:50],
                        after="需明确指代对象",
                        type="style"
                    ))
    
    return result, changes


@router.post("/text")
async def polish_text_endpoint(input_data: TextPolishInput):
    """基础文本润色（不引用skill）"""
    try:
        from app.utils.ai_client import ai_client
        result = ai_client.polish_text(input_data.text)
        changes = result.get("changes") or []
        if not changes:
            for key in ("original", "polished"):
                if result.get(key) and result.get("polished") != result.get("original"):
                    changes.append({
                        "line": 1,
                        "original": result.get("original", "")[:200],
                        "polished": result.get("polished", "")[:200],
                        "type": "ai"
                    })
                    break
        return {
            "original": result.get("original", input_data.text),
            "polished": result.get("polished", input_data.text),
            "changes": changes
        }
    except Exception:
        polished, changes = _apply_skill_polish(input_data.text, {}, None, None, None, None)
        return {
            "original": input_data.text,
            "polished": polished,
            "changes": changes
        }


@router.post("/skill")
async def polish_with_skill(
    input_data: SkillPolishInput,
    db: Session = Depends(get_db)
):
    """使用知识库skill进行润色"""
    # 加载skill规则
    skill_rules = _load_skill_rules(input_data.skill_id, db)
    
    # 加载句式清单文件内容
    sentence_guide = None
    if input_data.style_guide_id:
        try:
            style_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == input_data.style_guide_id).first()
            if style_file and style_file.file_path:
                with open(style_file.file_path, 'r', encoding='utf-8') as f:
                    sentence_guide = f.read()
        except Exception as e:
            print(f"加载句式清单失败: {e}")
    
    # 先执行 AI 润色
    ai_polished = input_data.text
    ai_changes = []
    try:
        from app.utils.ai_client import ai_client
        ai_result = ai_client.polish_text(input_data.text, style_guide=sentence_guide)
        if ai_result and ai_result.get("polished") and ai_result["polished"] != input_data.text:
            ai_polished = ai_result["polished"]
            ai_changes = ai_result.get("changes") or [{"type": "ai", "summary": "AI 根据句式清单完成智能润色"}]
    except Exception as e:
        print(f"AI 润色失败(继续使用规则润色): {e}")
    
    # 在 AI 润色结果上执行规则润色
    polished, changes = _apply_skill_polish(ai_polished, skill_rules, db, sentence_guide, None, None)
    # 合并变更：AI 变更转为 PolishRuleMatch
    if ai_changes:
        for ac in ai_changes:
            if isinstance(ac, dict):
                changes.insert(0, PolishRuleMatch(
                    rule_name=ac.get("type", "ai"),
                    before=ac.get("original", "")[:50],
                    after=ac.get("polished", "")[:50],
                    type="ai"
                ))
    
    return {
        "original": input_data.text,
        "polished": polished,
        "changes": [c.dict() for c in changes],
        "skill_name": "技术文档智能润色",
        "rules_applied": skill_rules.get("rules", {})
    }


def _polish_docx_with_comments(
    docx_path: str,
    output_path: str,
    skill_rules: dict,
    db: Session,
    sentence_guide: str = None,
    terminology: str = None,
    requirements: str = None
) -> list[PolishRuleMatch]:
    """对 DOCX 文件进行润色，保留排版并添加批注"""
    from docx import Document
    from docx.oxml.ns import qn, nsdecls
    from lxml import etree
    from copy import deepcopy
    import zipfile
    import tempfile
    import os as os_mod
    
    all_changes = []
    
    term_dict = {}
    if terminology:
        try:
            for row in terminology.split('\n'):
                row = row.strip()
                if '|' not in row or row.startswith('#') or row.startswith('|---') or row.startswith('|序号'):
                    continue
                cells = [c.strip() for c in row.split('|') if c.strip()]
                clean_cells = [c for c in cells if c and c != '---']
                if len(clean_cells) >= 2 and not clean_cells[0].startswith('##'):
                    for i in range(0, len(clean_cells) - 1, 2):
                        old_term = clean_cells[i].strip().strip('!')
                        new_term = clean_cells[i + 1].strip().strip('!')
                        if old_term and new_term and len(old_term) > 1 and old_term != new_term:
                            term_dict[old_term] = new_term
        except Exception:
            pass
    
    doc = Document(docx_path)
    author = "技术文档智能润色助手"
    initial = "AI"
    
    comment_id = 0
    comments_data = []
    
    toc_prefixes = ("TOC", "Table of Contents", "目录")
    
    for para_idx, para in enumerate(doc.paragraphs):
        style_name = para.style.name if para.style else ""
        
        is_toc = False
        for prefix in toc_prefixes:
            if prefix in style_name or "toc" in style_name.lower():
                is_toc = True
                break
        
        if is_toc:
            continue
        
        original_text = para.text
        if not original_text.strip():
            continue
        
        polished_text, para_changes = _apply_skill_polish(
            original_text, skill_rules, db, sentence_guide, terminology, requirements
        )
        
        if polished_text != original_text and para_changes:
            all_changes.extend(para_changes)
            comment_id += 1
            
            changes_summary = "; ".join([c.rule_name for c in para_changes[:5]])
            comment_text = f"润色修改：{changes_summary}"
            
            comments_data.append({
                "id": comment_id,
                "author": author,
                "initials": initial,
                "text": comment_text
            })
            
            p_element = para._p
            w_ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
            
            # Find position to insert comment markers
            # Insert commentRangeStart at the beginning of the paragraph's first run content
            first_child = None
            for child in p_element:
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if tag in ('r', 'hyperlink'):
                    first_child = child
                    break
            
            # If no runs found, append to end
            if first_child is None:
                # Add comment markers at the end
                comment_start = etree.SubElement(
                    p_element, f'{{{w_ns}}}commentRangeStart'
                )
                comment_start.set(f'{{{w_ns}}}id', str(comment_id))
                
                comment_end = etree.SubElement(
                    p_element, f'{{{w_ns}}}commentRangeEnd'
                )
                comment_end.set(f'{{{w_ns}}}id', str(comment_id))
                
                comment_ref_r = etree.SubElement(
                    p_element, f'{{{w_ns}}}r'
                )
                comment_ref_rpr = etree.SubElement(
                    comment_ref_r, f'{{{w_ns}}}rPr'
                )
                comment_ref_style = etree.SubElement(
                    comment_ref_rpr, f'{{{w_ns}}}rStyle'
                )
                comment_ref_style.set(f'{{{w_ns}}}val', 'CommentReference')
                
                comment_ref = etree.SubElement(
                    comment_ref_r, f'{{{w_ns}}}commentReference'
                )
                comment_ref.set(f'{{{w_ns}}}id', str(comment_id))
            else:
                # Insert commentRangeStart before the first run
                comment_start = etree.SubElement(
                    p_element, f'{{{w_ns}}}commentRangeStart'
                )
                comment_start.set(f'{{{w_ns}}}id', str(comment_id))
                p_element.remove(comment_start)
                p_element.insert(p_element.index(first_child), comment_start)
                
                # Insert commentRangeEnd after the last run with text
                last_text_run = None
                for child in reversed(list(p_element)):
                    tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    if tag == 'r':
                        t_elem = child.find(f'{{{w_ns}}}t')
                        if t_elem is not None and t_elem.text and t_elem.text.strip():
                            last_text_run = child
                            break
                
                if last_text_run is None:
                    last_text_run = first_child
                
                insert_idx = p_element.index(last_text_run) + 1
                
                comment_end = etree.SubElement(
                    p_element, f'{{{w_ns}}}commentRangeEnd'
                )
                comment_end.set(f'{{{w_ns}}}id', str(comment_id))
                p_element.remove(comment_end)
                p_element.insert(insert_idx, comment_end)
                
                # Insert commentReference after commentRangeEnd
                comment_ref_r = etree.SubElement(
                    p_element, f'{{{w_ns}}}r'
                )
                comment_ref_rpr = etree.SubElement(
                    comment_ref_r, f'{{{w_ns}}}rPr'
                )
                comment_ref_style = etree.SubElement(
                    comment_ref_rpr, f'{{{w_ns}}}rStyle'
                )
                comment_ref_style.set(f'{{{w_ns}}}val', 'CommentReference')
                
                comment_ref = etree.SubElement(
                    comment_ref_r, f'{{{w_ns}}}commentReference'
                )
                comment_ref.set(f'{{{w_ns}}}id', str(comment_id))
                p_element.remove(comment_ref_r)
                p_element.insert(insert_idx + 1, comment_ref_r)
            
            # Replace paragraph text while preserving formatting of first run
            first_text_run = None
            for child in p_element:
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if tag == 'r':
                    t_elem = child.find(f'{{{w_ns}}}t')
                    if t_elem is not None and t_elem.text and t_elem.text.strip():
                        first_text_run = child
                        break
            
            if first_text_run is not None:
                t_elem = first_text_run.find(f'{{{w_ns}}}t')
                if t_elem is not None:
                    t_elem.text = polished_text
                
                for child in p_element:
                    tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    if tag == 'r' and child is not first_text_run:
                        t_elem = child.find(f'{{{w_ns}}}t')
                        if t_elem is not None:
                            t_elem.text = ""
            else:
                para.add_run(polished_text)
    
    doc.save(output_path)
    
    if comments_data:
        _inject_comments_to_docx(output_path, comments_data)
    
    return all_changes


def _inject_comments_to_docx(docx_path: str, comments_data: list):
    """向 DOCX 文件中注入 comments.xml 和 relationships"""
    import zipfile
    import tempfile
    import os as os_mod
    from lxml import etree
    from shutil import move
    from copy import deepcopy
    
    nsmap = {
        'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
        'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    }
    
    comments_xml = etree.Element(
        '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}comments',
        nsmap={'w': nsmap['w']}
    )
    
    for cdata in comments_data:
        comment_el = etree.SubElement(
            comments_xml, '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}comment'
        )
        comment_el.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id', str(cdata['id']))
        comment_el.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}author', cdata['author'])
        comment_el.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}initials', cdata['initials'])
        
        p_el = etree.SubElement(
            comment_el, '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'
        )
        r_el = etree.SubElement(
            p_el, '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}r'
        )
        t_el = etree.SubElement(
            r_el, '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'
        )
        t_el.text = cdata['text']
    
    comments_bytes = etree.tostring(
        comments_xml, xml_declaration=True, encoding='UTF-8', standalone=True
    )
    
    temp_dir = tempfile.mkdtemp()
    temp_output = os_mod.path.join(temp_dir, 'output.docx')
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zin:
            zin.extractall(temp_dir)
        
        word_dir = os_mod.path.join(temp_dir, 'word')
        
        with open(os_mod.path.join(word_dir, 'comments.xml'), 'wb') as f:
            f.write(comments_bytes)
        
        rels_path = os_mod.path.join(word_dir, '_rels', 'document.xml.rels')
        
        if os_mod.path.exists(rels_path):
            rels_tree = etree.parse(rels_path)
            root = rels_tree.getroot()
            
            existing_ids = set()
            for rel in root.findall('.//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
                existing_ids.add(rel.get('Id', ''))
            
            new_id_num = 1
            while f'rId{new_id_num}' in existing_ids:
                new_id_num += 1
            
            r_id = f'rId{new_id_num}'
            
            new_rel = etree.SubElement(
                root, '{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'
            )
            new_rel.set('Id', r_id)
            new_rel.set('Type', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments')
            new_rel.set('Target', 'comments.xml')
            
            with open(rels_path, 'wb') as f:
                f.write(etree.tostring(rels_tree, xml_declaration=True, encoding='UTF-8', standalone=True))
        
        doc_path = os_mod.path.join(word_dir, 'document.xml')
        if os_mod.path.exists(doc_path):
            doc_tree = etree.parse(doc_path)
            doc_root = doc_tree.getroot()
            
            body = doc_root.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}body')
            
            comments_ref_el = etree.SubElement(
                body, '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}comments'
            )
            comments_ref_el.set(
                '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id', r_id
            )
            
            with open(doc_path, 'wb') as f:
                f.write(etree.tostring(doc_tree, xml_declaration=True, encoding='UTF-8', standalone=True))
        
        with zipfile.ZipFile(temp_output, 'w', zipfile.ZIP_DEFLATED) as zout:
            for dirpath, dirnames, filenames in os_mod.walk(temp_dir):
                for fname in filenames:
                    full_path = os_mod.path.join(dirpath, fname)
                    arcname = os_mod.path.relpath(full_path, temp_dir)
                    zout.write(full_path, arcname)
        
        if os_mod.path.exists(docx_path):
            os_mod.remove(docx_path)
        move(temp_output, docx_path)
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to inject comments to DOCX: {e}", exc_info=True)
        raise
    finally:
        import shutil
        try:
            shutil.rmtree(temp_dir)
        except:
            pass


def _generate_polish_report(
    report_path: str,
    original_filename: str,
    changes: list,
    sentence_file_name: str = None,
    terminology_file_name: str = None,
    requirements: str = None
):
    """生成润色报告 DOCX 文件"""
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from datetime import datetime
    from docx.oxml.ns import qn
    
    doc = Document()
    
    style = doc.styles['Normal']
    font = style.font
    font.name = '微软雅黑'
    font.size = Pt(10)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    
    title = doc.add_heading('技术文档润色报告', level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    p = doc.add_paragraph()
    p.add_run('生成日期：').bold = True
    p.add_run(now)
    
    doc.add_heading('1. 文档基本信息', level=2)
    
    info_table = doc.add_table(rows=5, cols=2)
    info_table.style = 'Light Shading Accent 1'
    
    info_data = [
        ('原文件名', original_filename),
        ('文件大小', '待计算'),
        ('句式参考', sentence_file_name or '未指定'),
        ('术语库', terminology_file_name or '未指定'),
        ('润色要求', requirements or '无'),
    ]
    
    for i, (label, value) in enumerate(info_data):
        info_table.rows[i].cells[0].text = label
        info_table.rows[i].cells[1].text = str(value)
        for cell in info_table.rows[i].cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(10)
    
    doc.add_heading('2. 改动统计', level=2)
    
    total_changes = len(changes)
    change_types = {}
    for c in changes:
        ct = c.get('type', 'unknown') if isinstance(c, dict) else getattr(c, 'type', 'unknown')
        change_types[ct] = change_types.get(ct, 0) + 1
    
    p = doc.add_paragraph()
    p.add_run('总改动数：').bold = True
    p.add_run(f'{total_changes} 处')
    
    p = doc.add_paragraph()
    p.add_run('改动类型分布：')
    
    type_names = {
        'terminology': '术语替换',
        'format': '格式规范',
        'punctuation': '标点修正',
        'style': '句式检测',
    }
    for ct, count in change_types.items():
        name = type_names.get(ct, ct)
        p = doc.add_paragraph(style='List Bullet')
        p.text = f'{name}：{count} 处'
    
    if total_changes > 0:
        doc.add_heading('3. 主要润色方向', level=2)
        
        direction_table = doc.add_table(rows=1, cols=2)
        direction_table.style = 'Table Grid'
        direction_table.rows[0].cells[0].text = '问题类型'
        direction_table.rows[0].cells[1].text = '修复举例'
        for cell in direction_table.rows[0].cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.bold = True
                    run.font.size = Pt(10)
        
        seen_types = set()
        for c in changes[:10]:
            ct = c.get('type', 'unknown') if isinstance(c, dict) else getattr(c, 'type', 'unknown')
            if ct not in seen_types:
                seen_types.add(ct)
                before = c.get('before', '')[:40] if isinstance(c, dict) else getattr(c, 'before', '')[:40]
                after = c.get('after', '')[:40] if isinstance(c, dict) else getattr(c, 'after', '')[:40]
                row = direction_table.add_row()
                row.cells[0].text = type_names.get(ct, ct)
                row.cells[1].text = f'{before} → {after}'
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            run.font.size = Pt(10)
    
    doc.add_heading('4. 完整改动清单', level=2)
    
    list_table = doc.add_table(rows=1, cols=4)
    list_table.style = 'Table Grid'
    headers = ['序号', '修改前', '修改后', '类型']
    for i, h in enumerate(headers):
        list_table.rows[0].cells[i].text = h
        for run in list_table.rows[0].cells[i].paragraphs[0].runs:
            run.bold = True
            run.font.size = Pt(9)
    
    for idx, c in enumerate(changes, 1):
        row = list_table.add_row()
        before = c.get('before', '')[:50] if isinstance(c, dict) else getattr(c, 'before', '')[:50]
        after = c.get('after', '')[:50] if isinstance(c, dict) else getattr(c, 'after', '')[:50]
        ct = c.get('type', '') if isinstance(c, dict) else getattr(c, 'type', '')
        
        row.cells[0].text = str(idx)
        row.cells[1].text = before
        row.cells[2].text = after
        row.cells[3].text = type_names.get(ct, ct)
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(9)
    
    doc.add_heading('5. 查看修订的方法', level=2)
    
    steps = [
        '在 Microsoft Word 或 WPS 桌面端打开【修订标记版】文件',
        '点击【审阅】选项卡',
        '确保【修订】按钮处于开启状态',
        '即可在文档中看到所有修改痕迹和批注',
        '如需接受所有修改：点击【接受】→【接受所有修订】',
    ]
    for step in steps:
        p = doc.add_paragraph(style='List Number')
        p.text = step
    
    p = doc.add_paragraph()
    run = p.add_run('注意：飞书在线预览不支持显示 OOXML 修订标记/批注，请下载到本地查看。')
    run.bold = True
    run.font.color.rgb = RGBColor(255, 0, 0)
    
    doc.save(report_path)


@router.post("/analyze-file")
async def analyze_file_endpoint(
    file: UploadFile = File(...),
    sentence_file_id: Optional[int] = Form(None),
    terminology_file_id: Optional[int] = Form(None),
    requirements: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    import tempfile
    import docx2txt
    
    user = get_default_user(db)
    temp_path = None
    original_temp_path = None
    try:
        filename = file.filename or "unnamed"
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else "txt"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            content_bytes = await file.read()
            tmp.write(content_bytes)
            temp_path = tmp.name

        content = None
        output_docx_path = None
        is_docx = (ext == 'docx')
        
        if is_docx:    
            output_filename = f"【修订标记版】{filename}"
        else:
            output_filename = filename

        if ext in ['txt', 'md', 'markdown']:
            with open(temp_path, 'r', encoding='utf-8') as f:
                content = f.read()
        elif ext == 'docx':
            from docx import Document
            doc = Document(temp_path)
            content = '\n'.join([p.text for p in doc.paragraphs])
        
        if content is None or content.strip() == "":
            raise HTTPException(status_code=400, detail="无法提取文本内容")

        skill_rules = _load_skill_rules(3, db)
        
        sentence_guide = None
        sentence_file_name = None
        if sentence_file_id:
            sentence_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == sentence_file_id).first()
            if sentence_file:
                sentence_file_name = sentence_file.name
                with open(sentence_file.file_path, 'r', encoding='utf-8') as f:
                    sentence_guide = f.read()
        
        terminology = None
        term_file_name = None
        if terminology_file_id:
            term_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == terminology_file_id).first()
            if term_file:
                term_file_name = term_file.name
                with open(term_file.file_path, 'r', encoding='utf-8') as f:
                    terminology = f.read()
        
        # === AI 润色：将句式清单注入 AI prompt ===
        ai_polished = content
        ai_changes = []
        try:
            from app.utils.ai_client import ai_client
            ai_result = ai_client.polish_text(content, style_guide=sentence_guide)
            if ai_result and ai_result.get("polished") and ai_result["polished"] != content:
                ai_polished = ai_result["polished"]
                ai_changes = ai_result.get("changes") or [{
                    "type": "ai",
                    "summary": "AI 根据句式清单完成智能润色"
                }]
        except Exception as e:
            print(f"AI 润色失败(继续使用规则润色): {e}")
        # === AI 润色结束 ===
        
        if is_docx:
            # === AI 润色后的文本写回 DOCX ===
            if ai_polished != content:
                from docx import Document as DocxDoc
                ai_doc = DocxDoc(temp_path)
                ai_lines = ai_polished.split('\n')
                for i, para in enumerate(ai_doc.paragraphs):
                    if i < len(ai_lines):
                        for run in para.runs:
                            run.text = ''
                        if para.runs:
                            para.runs[0].text = ai_lines[i]
                        else:
                            para.text = ai_lines[i]
                ai_temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".docx").name
                ai_doc.save(ai_temp_path)
                # 切换到 AI 润色后的文件用于后续规则润色
                original_temp_path = temp_path
                temp_path = ai_temp_path
            else:
                original_temp_path = None
            # === AI 润色后的文本写回 DOCX 结束 ===
            _, date_str = _get_date_subfolder_id(db, None, user.id)
            date_dir = os.path.join(UPLOAD_DIR, date_str)
            if not os.path.exists(date_dir):
                os.makedirs(date_dir)
            
            unique_filename = f"【修订标记版】{filename}"
            saved_file_path = os.path.join(date_dir, unique_filename)
            
            changes = _polish_docx_with_comments(
                temp_path, saved_file_path, skill_rules, db,
                sentence_guide, terminology, requirements
            )
            
            from docx import Document
            polished_doc = Document(saved_file_path)
            polished_text = '\n'.join([p.text for p in polished_doc.paragraphs])
            
            report_filename = f"【润色报告】{filename.rsplit('.', 1)[0]}.docx"
            report_path = os.path.join(date_dir, report_filename)
            _generate_polish_report(
                report_path, filename, changes,
                sentence_file_name,
                term_file_name,
                requirements
            )
            
            db_doc = create_polished_document(
                db=db,
                name=f"【修订标记版】{filename}",
                filename=unique_filename,
                file_path=saved_file_path,
                file_size=os.path.getsize(saved_file_path),
                file_type="docx",
                original_content=content,
                polished_content=polished_text,
                report_filename=report_filename,
                report_file_path=report_path,
                folder_id=None,
                created_by=user.id
            )
            
            return {
                "id": db_doc.id,
                "original": content,
                "polished": polished_text,
                "changes": changes,
                "report_file": report_filename
            }
        else:    
            # 在 AI 润色后的文本上执行规则润色
            polished_text, changes = _apply_skill_polish(ai_polished, skill_rules, db, sentence_guide, terminology, requirements)
            # 合并 AI 变更与规则变更
            if ai_changes:
                for ac in ai_changes:
                    if isinstance(ac, dict):
                        changes.insert(0, PolishRuleMatch(
                            rule_name=ac.get("type", "ai"),
                            before=ac.get("summary", "")[:50],
                            after="AI 根据句式清单完成智能润色",
                            type="ai"
                        ))
            
            if not os.path.exists(UPLOAD_DIR):
                os.makedirs(UPLOAD_DIR)
            
            file_extension = f".{ext}" if ext else ".txt"
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            saved_file_path = os.path.join(UPLOAD_DIR, unique_filename)
            
            with open(saved_file_path, "w", encoding="utf-8") as f:
                f.write(polished_text)
            
            db_doc = create_polished_document(
                db=db,
                name=filename,
                filename=unique_filename,
                file_path=saved_file_path,
                file_size=len(content_bytes),
                file_type=ext,
                original_content=content,
                polished_content=polished_text,
                created_by=user.id
            )
            
            return {
                "id": db_doc.id,
                "original": content,
                "polished": polished_text,
                "changes": changes
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        if original_temp_path and os.path.exists(original_temp_path):
            try:
                os.remove(original_temp_path)
            except:
                pass


@router.post("/{document_id}")
async def polish_document(document_id: int, db: Session = Depends(get_db)):
    document = get_document(db, document_id=document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        from app.utils.ai_client import ai_client
        result = ai_client.polish_text(document.content or "")
        changes = result.get("changes") or []
        return {
            "document_id": document_id,
            "original": result.get("original", document.content or ""),
            "polished": result.get("polished", document.content or ""),
            "changes": changes
        }
    except Exception:
        fb = _polish_fallback(document.content or "")
        fb["document_id"] = document_id
        return fb


def _polish_fallback(text: str):
    polished, changes = _apply_skill_polish(text, {}, None, None, None, None)
    return {
        "original": text,
        "polished": polished,
        "changes": changes or [{"line": 1, "original": text[:80], "polished": polished[:80], "type": "format"}]
    }


@router.post("/upload")
async def upload_polished_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user = get_default_user(db)
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
    
    file_extension = os.path.splitext(file.filename)[1] if file.filename else ""
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    content = await file.read()
    with open(file_path, "wb") as buffer:
        buffer.write(content)
    
    file_size = os.path.getsize(file_path)
    file_type = file_extension[1:] if file_extension else "unknown"
    
    # Try to read content for text-based files
    original_content = None
    polished_content = None
    if file_type in ["txt", "md", "docx"]:
        try:
            if file_type == "docx":
                import docx2txt
                original_content = docx2txt.process(file_path)
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    original_content = f.read()
        except:
            pass
    
    db_file = create_polished_document(
        db=db,
        name=file.filename or "unknown",
        filename=unique_filename,
        file_path=file_path,
        file_size=file_size,
        file_type=file_type,
        original_content=original_content,
        polished_content=polished_content,
        created_by=user.id
    )
    
    return {"message": "文件上传成功", "id": db_file.id}


@router.get("/")
async def list_polished_documents(db: Session = Depends(get_db)):
    docs = get_polished_documents(db)
    result = []
    for d in docs:
        created_at_str = None
        if d.created_at:
            created_at_str = (d.created_at + timedelta(hours=8)).strftime("%Y/%m/%d %H:%M:%S")
        result.append({
            "id": d.id,
            "name": d.name,
            "filename": d.filename,
            "file_size": d.file_size,
            "file_type": d.file_type,
            "created_at": created_at_str,
            "has_polished_content": d.polished_content is not None,
            "report_file_path": d.report_file_path or None
        })
    return result


@router.get("/{doc_id}")
async def get_polished_document_info(doc_id: int, db: Session = Depends(get_db)):
    doc = get_polished_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return {
        "id": doc.id,
        "name": doc.name,
        "filename": doc.filename,
        "file_path": doc.file_path,
        "file_size": doc.file_size,
        "file_type": doc.file_type,
        "original_content": doc.original_content,
        "polished_content": doc.polished_content,
        "created_at": (doc.created_at + timedelta(hours=8)).isoformat() if doc.created_at else None
    }


@router.get("/{doc_id}/download")
async def download_polished_file(doc_id: int, db: Session = Depends(get_db)):
    doc = get_polished_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="服务器文件不存在")
    
    return FileResponse(
        path=doc.file_path,
        filename=doc.filename,
        media_type="application/octet-stream"
    )


@router.get("/{doc_id}/download-report")
async def download_polished_file_report(doc_id: int, db: Session = Depends(get_db)):
    doc = get_polished_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    if not doc.report_file_path:
        raise HTTPException(status_code=404, detail="润色报告不存在")
    
    if not os.path.exists(doc.report_file_path):
        raise HTTPException(status_code=404, detail="服务器文件不存在")
    
    return FileResponse(
        path=doc.report_file_path,
        filename=doc.report_filename or "润色报告.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


@router.get("/{doc_id}/preview")
async def preview_polished_file(doc_id: int, db: Session = Depends(get_db)):
    doc = get_polished_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="服务器文件不存在")
    
    file_type = doc.file_type.lower()
    
    if file_type in ["txt", "md", "markdown", "json", "xml", "html", "css", "js", "py"]:
        with open(doc.file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {
            "content": content,
            "type": "text",
            "file_name": doc.filename,
            "polished_content": doc.polished_content
        }
    
    elif file_type in ["jpg", "jpeg", "png", "gif", "bmp", "svg", "webp"]:
        return {
            "file_path": f"/api/polish/{doc_id}/raw",
            "type": "image",
            "file_name": doc.filename
        }
    
    elif file_type == "pdf":
        return {
            "file_path": f"/api/polish/{doc_id}/raw",
            "type": "pdf",
            "file_name": doc.filename
        }
    
    elif file_type == "docx":
        try:
            import docx2txt
            content = docx2txt.process(doc.file_path)
            return {
                "content": content,
                "type": "docx",
                "file_name": doc.filename,
                "polished_content": doc.polished_content
            }
        except Exception as e:
            return {"content": f"DOCX 预览失败：{str(e)}", "type": "error", "file_name": doc.filename}
    
    else:
        return {"content": "此文件类型不支持在线预览，请下载后查看", "type": "unsupported", "file_name": doc.filename}


@router.get("/{doc_id}/raw")
async def get_raw_polished_file(doc_id: int, db: Session = Depends(get_db)):
    doc = get_polished_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="服务器文件不存在")
    
    media_type = mimetypes.guess_type(doc.file_path)[0] or "application/octet-stream"
    
    return FileResponse(
        path=doc.file_path,
        filename=doc.filename,
        media_type=media_type
    )


@router.delete("/{doc_id}")
async def delete_polished_document_endpoint(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user = get_default_user(db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可删除文件")
    
    doc = get_polished_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)
    
    # 同时删除关联的润色报告文件
    if doc.report_file_path and os.path.exists(doc.report_file_path):
        os.remove(doc.report_file_path)
    
    delete_polished_document(db, doc_id)
    return {"message": "删除成功"}
