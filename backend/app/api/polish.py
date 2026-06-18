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
import threading
import datetime
from app.database import get_db
from app.crud.document import get_document
from app.crud.polished_document import (
    get_polished_documents, get_polished_document, create_polished_document, delete_polished_document
)
from app.api.auth import get_current_user, get_default_user
from app.models.knowledge import KnowledgeFile, Folder
from app.models.term import Term
from app.models.polish_feedback import PolishFeedback
from app.utils.file_utils import read_file_safe as _read_file_safe
from app.crud.term import bulk_create_terms

router = APIRouter()

# 润色任务进度追踪
_polish_tasks: dict = {}  # {task_id: {"status", "progress", "message", "result"}}
_polish_tasks_lock = threading.Lock()


# ============================================================
# 术语库加载 & 语言检测
# ============================================================

def _load_terms_from_db(db: Session) -> dict:
    """从术语库表中加载所有术语，返回 {非标准用语: 标准用语} 映射（带缓存）。"""
    if '__db_terms__' in _term_cache:
        return dict(_term_cache['__db_terms__'])

    terms = db.query(Term).all()
    term_dict = {}
    for t in terms:
        if t.non_standard and t.standard and t.non_standard.strip() != t.standard.strip():
            term_dict[t.non_standard.strip()] = t.standard.strip()
    _term_cache['__db_terms__'] = dict(term_dict)
    return term_dict


def _detect_language(text: str) -> str:
    """检测文本语言。返回 'zh' (中文) 或 'en' (英文)。"""
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    total_chars = len(text.replace(' ', '').replace('\n', ''))
    if total_chars == 0:
        return 'zh'
    ratio = chinese_chars / total_chars
    return 'zh' if ratio > 0.3 else 'en'


def _term_column_lang(header: str) -> str:
    """根据列表头判断该列的语言倾向：zh / en / None（中性）。"""
    zh_keywords = ['中', '中文', 'zh', '汉语', '汉']
    en_keywords = ['英', '英文', 'en', 'english', 'eng']
    for kw in zh_keywords:
        if kw in header.lower():
            return 'zh'
    for kw in en_keywords:
        if kw in header.lower():
            return 'en'
    return None


def _parse_terminology(terminology_input: str) -> dict:
    """统一术语解析入口：自动识别 Markdown 文本或 Excel 文件路径。"""
    if not terminology_input:
        return {}
    # 如果是 .xlsx 文件路径
    if terminology_input.lower().endswith('.xlsx'):
        return _parse_terminology_xlsx(terminology_input)
    # 否则作为 Markdown 文本解析
    return _parse_terminology_md(terminology_input)


def _parse_terminology_md(md_content: str) -> dict:
    """解析术语库 Markdown 文件，返回 {非标准: 标准} 映射。

    支持的列格式：
    - 简单格式：| 非标准 | 标准 |
    - 分语言格式：| 非标准(中) | 标准(中) | 非标准(英) | 标准(英) |
    - 带语言列：| 非标准 | 标准 | 语言 |
    
    兼容全角竖线 ｜ 和半角竖线 |。
    """
    term_dict = {}
    if not md_content:
        return term_dict

    # 兼容全角竖线和全角横线
    content = md_content
    # 分隔符行全角转半角：｜---｜ → |---|
    content = content.replace('\uff5c', '|')  # fullwidth vertical bar
    content = content.replace('\u2502', '|')  # box drawing light vertical

    lines = content.split('\n')
    header = ''
    col_langs = []
    has_lang_col = False
    lang_col_idx = -1

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 捕获表头行（第一个含 | 且不含分隔符的行）
        if not header and '|' in stripped and '---' not in stripped:
            header = stripped
            cells = [c.strip() for c in stripped.split('|') if c.strip()]
            # 检查是否有"语言"列
            for idx, cell in enumerate(cells):
                if any(kw in cell.lower() for kw in ['语言', 'lang', 'language']):
                    has_lang_col = True
                    lang_col_idx = idx
                col_langs.append(_term_column_lang(cell))
            continue

        if '|' not in stripped:
            continue
        if stripped.startswith('#'):
            continue
        if stripped.startswith('|---') or stripped.startswith('| :--') or stripped.startswith('|:--'):
            continue
        if stripped.startswith('|序号') or stripped.startswith('| 序号'):
            continue

        cells = [c.strip() for c in stripped.split('|') if c.strip()]
        clean_cells = [c for c in cells if c.strip() and c.strip() != '---']
        if len(clean_cells) < 2:
            continue

        # 模式 A：带语言列
        if has_lang_col and lang_col_idx >= 0 and lang_col_idx < len(clean_cells):
            lang_val = clean_cells[lang_col_idx].lower()
            is_zh = any(kw in lang_val for kw in ['zh', '中', 'cn', 'chinese'])
            is_en = any(kw in lang_val for kw in ['en', '英', 'english', 'eng'])
            # 构建不包含语言列的数据列
            data_cells = [c for i, c in enumerate(clean_cells) if i != lang_col_idx]
            # 数据列两两配对
            for i in range(0, len(data_cells) - 1, 2):
                old_term = data_cells[i].strip().strip('!')
                new_term = data_cells[i + 1].strip().strip('!')
                if old_term and new_term and old_term != new_term and len(old_term) > 1:
                    # 根据语言列值分配语言标记
                    lang_suffix = ''
                    if is_zh:
                        lang_suffix = '##zh'
                    elif is_en:
                        lang_suffix = '##en'
                    key = f"{old_term}{lang_suffix}" if lang_suffix else old_term
                    if key not in term_dict:
                        term_dict[key] = new_term
            continue

        # 模式 B：无语言列，但有表头指示列语言
        if col_langs and len(col_langs) == len(clean_cells):
            for i in range(0, len(clean_cells) - 1, 2):
                old_term = clean_cells[i].strip().strip('!')
                new_term = clean_cells[i + 1].strip().strip('!')
                if old_term and new_term and old_term != new_term and len(old_term) > 1:
                    lang = col_langs[i] or col_langs[i + 1] or ''
                    lang_suffix = f'##{lang}' if lang else ''
                    key = f"{old_term}{lang_suffix}" if lang_suffix else old_term
                    if key not in term_dict:
                        term_dict[key] = new_term
            continue

        # 模式 C：无语言信息，简单两列配对
        for i in range(0, len(clean_cells) - 1, 2):
            old_term = clean_cells[i].strip().strip('!')
            new_term = clean_cells[i + 1].strip().strip('!')
            if old_term and new_term and old_term != new_term and len(old_term) > 1:
                if old_term not in term_dict:
                    term_dict[old_term] = new_term

    return term_dict


def _parse_terminology_xlsx(file_path: str) -> dict:
    """解析 Excel (.xlsx) 术语文件，返回 {非标准: 标准} 映射。
    
    支持两种格式：
    - 替换表：| 非标准 | 标准 |   → 直接作为 old→new 映射
    - 双语表：| zh-CN | en-US | → 仅提取中文列作为标准术语（不做替换，避免中文→英文错乱）
    """
    term_dict = {}
    try:
        import openpyxl
    except ImportError:
        return term_dict
    
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True)
        ws = wb.active
        
        rows = list(ws.iter_rows(min_row=1, max_row=min(ws.max_row, 500), values_only=True))
        if not rows:
            wb.close()
            return term_dict
        
        headers = [str(h).strip().lower() if h else '' for h in rows[0]]
        is_replacement = any(kw in h for h in headers for kw in ['非标准', '旧', 'old', '非标', 'source'])
        is_bilingual = any(kw in h for h in headers for kw in ['zh', 'cn', '中文', 'en', '英', 'us'])
        
        for row in rows[1:]:
            cells = [str(c).strip() if c else '' for c in row]
            cells = [c for c in cells if c]
            if len(cells) < 2:
                continue
            
            if is_replacement:
                # 替换表：col1=非标准, col2=标准
                old_term = cells[0]
                new_term = cells[1]
                if old_term and new_term and old_term != new_term and len(old_term) > 0:
                    if old_term not in term_dict:
                        term_dict[old_term] = new_term
            elif is_bilingual:
                # 双语表：col1=中文标准术语, col2=英文 —— 仅提取中文列，不做替换
                # 将中文标准术语自身作为 key（标识已知标准术语，供 AI 参考）
                std_cn = cells[0]
                if std_cn and len(std_cn) > 0:
                    term_dict[f"__std__{std_cn}"] = std_cn
            else:
                # 未知格式：假设 col1→col2 替换
                old_term = cells[0]
                new_term = cells[1]
                if old_term and new_term and old_term != new_term and len(old_term) > 0:
                    if old_term not in term_dict:
                        term_dict[old_term] = new_term
        
        wb.close()
        if is_bilingual and not is_replacement:
            std_terms = [v for k, v in term_dict.items() if k.startswith('__std__')]
            print(f"[TERM] Excel 双语对照表: 标准中文术语 {len(std_terms)} 条 ({', '.join(std_terms[:5])})")
    except Exception as e:
        print(f"[TERM] Excel 解析失败: {e}")
    
    return term_dict
    term_dict = {}
    if not md_content:
        return term_dict

    # 统一处理全角竖线
    md_content = md_content.replace('\uFF5C', '|')
    lines = md_content.split('\n')
    header = ''
    col_langs = []
    has_lang_col = False
    lang_col_idx = -1

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 捕获表头行（第一个含 | 且不含分隔符的行）
        if not header and '|' in stripped and '---' not in stripped:
            header = stripped
            cells = [c.strip() for c in stripped.split('|') if c.strip()]
            # 检查是否有"语言"列
            for idx, cell in enumerate(cells):
                if any(kw in cell.lower() for kw in ['语言', 'lang', 'language']):
                    has_lang_col = True
                    lang_col_idx = idx
                col_langs.append(_term_column_lang(cell))
            continue

        if '|' not in stripped:
            continue
        if stripped.startswith('#'):
            continue
        if stripped.startswith('|---') or stripped.startswith('| :--') or stripped.startswith('|:--'):
            continue
        if stripped.startswith('|序号') or stripped.startswith('| 序号'):
            continue

        cells = [c.strip() for c in stripped.split('|') if c.strip()]
        clean_cells = [c for c in cells if c.strip() and c.strip() != '---']
        if len(clean_cells) < 2:
            continue

        # 模式 A：带语言列
        if has_lang_col and lang_col_idx >= 0 and lang_col_idx < len(clean_cells):
            lang_val = clean_cells[lang_col_idx].lower()
            is_zh = any(kw in lang_val for kw in ['zh', '中', 'cn', 'chinese'])
            is_en = any(kw in lang_val for kw in ['en', '英', 'english', 'eng'])
            # 构建不包含语言列的数据列
            data_cells = [c for i, c in enumerate(clean_cells) if i != lang_col_idx]
            # 数据列两两配对
            for i in range(0, len(data_cells) - 1, 2):
                old_term = data_cells[i].strip().strip('!')
                new_term = data_cells[i + 1].strip().strip('!')
                if old_term and new_term and old_term != new_term and len(old_term) > 1:
                    # 根据语言列值分配语言标记
                    lang_suffix = ''
                    if is_zh:
                        lang_suffix = '##zh'
                    elif is_en:
                        lang_suffix = '##en'
                    # 存入时带语言标记
                    key = f"{old_term}{lang_suffix}" if lang_suffix else old_term
                    if key not in term_dict:
                        term_dict[key] = new_term
            continue

        # 模式 B：无语言列，但有表头指示列语言
        if col_langs and len(col_langs) == len(clean_cells):
            # 两列配对，每对继承对应表头的语言
            for i in range(0, len(clean_cells) - 1, 2):
                old_term = clean_cells[i].strip().strip('!')
                new_term = clean_cells[i + 1].strip().strip('!')
                if old_term and new_term and old_term != new_term and len(old_term) > 1:
                    lang = col_langs[i] or col_langs[i + 1] or ''
                    lang_suffix = f'##{lang}' if lang else ''
                    key = f"{old_term}{lang_suffix}" if lang_suffix else old_term
                    if key not in term_dict:
                        term_dict[key] = new_term
            continue

        # 模式 C：无语言信息，简单两列配对
        for i in range(0, len(clean_cells) - 1, 2):
            old_term = clean_cells[i].strip().strip('!')
            new_term = clean_cells[i + 1].strip().strip('!')
            if old_term and new_term and old_term != new_term and len(old_term) > 1:
                if old_term not in term_dict:
                    term_dict[old_term] = new_term

    return term_dict


def _filter_terms_by_lang(term_dict: dict, target_lang: str) -> dict:
    """从带语言标记的术语字典中筛选出目标语言的术语。返回纯净的 {非标准: 标准}。"""
    filtered = {}
    for key, val in term_dict.items():
        # 跳过 Excel 双语表的标准术语标记（__std__ 前缀）
        if key.startswith('__std__'):
            continue
        if '##zh' in key:
            if target_lang == 'zh':
                clean_key = key.replace('##zh', '')
                filtered[clean_key] = val
        elif '##en' in key:
            if target_lang == 'en':
                clean_key = key.replace('##en', '')
                filtered[clean_key] = val
        else:
            # 无语言标记，通用术语，适用于所有语言
            filtered[key] = val
    return filtered


def _resolve_terminology(db: Session, terminology_md: str = None, text: str = None) -> dict:
    """加载术语：文件术语优先，自动按文本语言过滤。返回纯净 {非标准: 标准}。"""
    if terminology_md:
        parsed = _parse_terminology(terminology_md)
        if parsed:
            # 自动检测语言并过滤
            if text:
                lang = _detect_language(text)
                return _filter_terms_by_lang(parsed, lang)
            return parsed
    return _load_terms_from_db(db)


# 句式清单所在知识库文件夹 ID（写作规范 / 句式清单）
SENTENCE_GUIDE_FOLDER_IDS = [3]

# 默认写作风格指南文件 ID（写作规范 / 写作风格指南 / 中文技术文档写作风格指南）
DEFAULT_STYLE_GUIDE_ID = 1




def _load_file_content(db: Session, file_id: int) -> str:
    """加载单个知识库文件的内容"""
    kf = db.query(KnowledgeFile).filter(KnowledgeFile.id == file_id).first()
    if kf and kf.file_path and os.path.exists(kf.file_path):
        try:
            return _read_file_safe(kf.file_path).strip()
        except Exception:
            pass
    return None


def _build_document_polish_guide(
    db: Session,
    sentence_file_id: int = None,
    requirements: str = None
) -> str:
    """构建文档润色的完整规则指南。

    优先级: 句式匹配 > 术语匹配 > 风格指南 > 数据库规则
    句式文件在前，风格指南在后，AI 按顺序给予优先权重。
    """
    parts = []

    # 1. 句式清单（优先匹配）
    if sentence_file_id and sentence_file_id != DEFAULT_STYLE_GUIDE_ID:
        sentence_guide = _load_sentence_guides(db, style_guide_id=sentence_file_id)
        if sentence_guide:
            parts.append(sentence_guide)
    elif not sentence_file_id:
        all_guides = _load_sentence_guides(db)
        if all_guides:
            parts.append(all_guides)

    # 2. 用户额外的润色要求
    if requirements and requirements.strip():
        parts.append(f"## 额外润色要求\n\n{requirements.strip()}")

    # 3. 写作风格指南（句式匹配后再套用风格规范）
    default_guide = _load_file_content(db, DEFAULT_STYLE_GUIDE_ID)
    if default_guide:
        parts.append(default_guide)

    return "\n\n".join(parts) if parts else None


# 句式清单缓存
_sentence_guide_cache: dict = {}
_term_cache: dict = {}

def _load_sentence_guides(db: Session, style_guide_id: int = None) -> str:
    """加载句式清单内容（带缓存）。

    若指定了 style_guide_id，仅加载该文件；
    否则递归加载句式清单文件夹下所有 .md 文件。
    """
    cache_key = style_guide_id or '__all__'
    if cache_key in _sentence_guide_cache:
        return _sentence_guide_cache[cache_key]

    if style_guide_id:
        style_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == style_guide_id).first()
        if style_file and style_file.file_path and os.path.exists(style_file.file_path):
            try:
                content = _read_file_safe(style_file.file_path)
                if content.strip():
                    _sentence_guide_cache[cache_key] = content
                    return content
            except Exception as e:
                print(f"加载句式文件失败 (id={style_guide_id}): {e}")
        _sentence_guide_cache[cache_key] = None
        return None

    # 未指定文件，递归加载句式清单文件夹下所有 .md
    guides = []
    # 一次性收集所有相关文件夹 ID 及其后代
    all_folder_ids = set(SENTENCE_GUIDE_FOLDER_IDS)
    stack = list(SENTENCE_GUIDE_FOLDER_IDS)
    while stack:
        fid = stack.pop()
        subfolders = db.query(Folder).filter(Folder.parent_id == fid).all()
        for sf in subfolders:
            all_folder_ids.add(sf.id)
            stack.append(sf.id)

    files = db.query(KnowledgeFile).filter(
        KnowledgeFile.folder_id.in_(all_folder_ids),
        KnowledgeFile.file_type == "md"
    ).all()

    for kf in files:
        if kf.file_path and os.path.exists(kf.file_path):
            try:
                content = _read_file_safe(kf.file_path)
                if content.strip():
                    guides.append(content)
            except Exception:
                pass
    result = "\n\n".join(guides) if guides else None
    _sentence_guide_cache[cache_key] = result
    return result

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "polished")

# ============================================================
# 模型定义
# ============================================================

def _get_date_subfolder_id(db, folder_id: int, user_id: int) -> tuple:
    """返回物理目录路径和 None 作为 folder_id"""
    from datetime import datetime
    date_str = datetime.now().strftime("%Y%m%d")
    return None, date_str


class TextPolishInput(BaseModel):
    text: str
    style_guide_id: Optional[int] = None
    terminology_id: Optional[int] = None


class SkillPolishInput(BaseModel):
    text: str
    skill_id: int = 3
    style_guide_id: int = 1
    terminology_id: Optional[int] = None


class FeedbackInput(BaseModel):
    original_text: str
    polished_text: str
    accuracy: int          # 0-100
    corrections: str = ""   # 用户修正内容，每行一条 "非标准 → 标准"
    target: str = "terminology"  # "terminology" 或 "sentence_guide"


class PolishRuleMatch(BaseModel):
    rule_name: str
    before: str
    after: str
    type: str



# ============================================================
# 规则引擎：skill 加载、句式风格规则
# ============================================================

def _load_skill_rules(skill_id: int, db: Session) -> dict:
    """从知识库加载skill规则"""
    skill_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == skill_id).first()
    if not skill_file:
        return {}
    
    content = _read_file_safe(skill_file.file_path)
    
    return {
        "skill_content": content,
        "rules": {
            "句式规范化": True,
            "术语统一": True,
            "格式规范": True
        }
    }


def _apply_term_only(text: str, term_dict: dict) -> tuple[str, list[PolishRuleMatch]]:
    """仅按术语库逐行替换（不触发样式规则），用于 AI 已润色后的术语修正。"""
    if not term_dict:
        return text, []
    changes = []
    lines = text.split('\n')
    result_lines = []
    for line in lines:
        new_line = line
        for old_term, new_term in term_dict.items():
            if old_term in new_line:
                new_line = new_line.replace(old_term, new_term)
                changes.append(PolishRuleMatch(
                    rule_name="术语替换",
                    before=old_term,
                    after=new_term,
                    type="terminology"
                ))
        result_lines.append(new_line)
    return '\n'.join(result_lines), changes


def _apply_skill_polish(
    text: str, 
    skill_rules: dict, 
    db: Session,
    sentence_guide: str = None,
    terminology: str = None,
    requirements: str = None,
    is_title: bool = False,
    db_terminology: dict = None
) -> tuple[str, list[PolishRuleMatch]]:
    """应用skill规则进行润色。is_title=True 时跳过尾部标点规范化。"""

    def _is_noun_phrase(text: str) -> bool:
        """判断文本是否为纯名词短语（标题、标签、参数说明等），不需要追加标点。"""
        t = text.strip()
        if not t:
            return False
        # 1. 极短文本（<=4字）通常是标签/名称
        if len(t) <= 4:
            return True
        # 2. 以冒号结尾，通常是字段标签（如"试剂名称："）
        if t.endswith(('：', ':')):
            return True
        # 3. 包含编号/列表标记，通常是标题（如"1. 概述"、"第2章"）
        if re.match(r'^[\d一二三四五六七八九十]+[\.、\s]', t):
            return True
        # 4. 不包含任何谓语动词标记，判定为名词短语
        verb_markers = [
            '将', '请', '按', '点击', '选择', '输入', '打开', '关闭',
            '启动', '停止', '设置', '检查', '确认', '安装', '连接',
            '使用', '进行', '可以', '需要', '应该', '必须', '确保',
            '是', '为', '有', '在', '可', '会', '能', '要',
            '按下', '旋转', '调节', '插入', '取出', '放置', '点击',
            '执行', '访问', '查看', '显示', '支持', '提供', '包含',
            '通过', '根据', '按照', '用于', '适用于', '分为',
        ]
        if not any(marker in t for marker in verb_markers):
            return True
        return False
    changes = []
    lines = text.split('\n')
    polished_lines = []
    
    style_rules = []
    if sentence_guide:
        style_rules = _extract_style_rules(sentence_guide)
    
    term_dict = {}
    # 先解析文件中的术语替换（支持中英文多列表，自动语言过滤）
    if terminology:
        try:
            parsed = _parse_terminology(terminology)
            if parsed:
                lang = _detect_language(text)
                term_dict = _filter_terms_by_lang(parsed, lang)
        except Exception:
            pass
    # 合并数据库术语库（优先级高于文件术语）
    if db_terminology:
        term_dict.update(db_terminology)
    
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
        
        # 标题、表标题、图标题等不加句号，也不做空间距规整
        if not is_title:
            if new_line and not new_line.endswith(('。', '.', '！', '!', '？', '?')):
                if not _is_noun_phrase(new_line):
                    if re.search(r'[\u4e00-\u9fff]', new_line):
                        new_line = new_line.rstrip('，,;；;：:') + '。'
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
async def polish_text_endpoint(input_data: TextPolishInput, db: Session = Depends(get_db)):
    """基础文本润色（自动加载句式清单和术语库）"""
    import os
    try:
        from app.utils.ai_client import ai_client
        # 术语优先级：文件 > 数据库
        terminology_md = None
        if input_data.terminology_id:
            term_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == input_data.terminology_id).first()
            if term_file and term_file.file_path and os.path.exists(term_file.file_path):
                if term_file.file_path.lower().endswith('.xlsx'):
                    terminology_md = term_file.file_path  # Excel: 传路径
                else:
                    terminology_md = _read_file_safe(term_file.file_path)
        resolved_terminology = _resolve_terminology(db, terminology_md, input_data.text)
        sentence_guide = _load_sentence_guides(db, style_guide_id=input_data.style_guide_id)
        result = ai_client.polish_text(input_data.text, style_guide=sentence_guide, terminology=resolved_terminology if resolved_terminology else None)
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
        db_terminology = _load_terms_from_db(db)
        sentence_guide = _load_sentence_guides(db, style_guide_id=input_data.style_guide_id)
        polished, changes = _apply_skill_polish(input_data.text, {}, None, sentence_guide, None, None, db_terminology=db_terminology if db_terminology else None)
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
    
    # 构建完整润色指南：写作风格指南 + 句式文件 + 额外要求
    sentence_guide = _build_document_polish_guide(
        db,
        sentence_file_id=input_data.style_guide_id if input_data.style_guide_id != DEFAULT_STYLE_GUIDE_ID else None,
        requirements=None
    )

    # 加载术语：文件术语优先，否则回退数据库术语
    terminology_md = None
    if input_data.terminology_id:
        term_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == input_data.terminology_id).first()
        if term_file and term_file.file_path and os.path.exists(term_file.file_path):
            terminology_md = _read_file_safe(term_file.file_path)
    resolved_terminology = _resolve_terminology(db, terminology_md, input_data.text)

    # 先执行 AI 润色
    ai_polished = input_data.text
    ai_changes = []
    try:
        from app.utils.ai_client import ai_client
        ai_result = ai_client.polish_text(input_data.text, style_guide=sentence_guide, terminology=resolved_terminology if resolved_terminology else None)
        if ai_result and ai_result.get("polished") and ai_result["polished"] != input_data.text:
            ai_polished = ai_result["polished"]
            ai_changes = ai_result.get("changes") or [{"type": "ai", "summary": "AI 根据句式清单完成智能润色"}]
    except Exception as e:
        print(f"AI 润色失败(继续使用规则润色): {e}")
    
    # 在 AI 润色结果上执行规则润色
    db_terms_for_rule = None if terminology_md else _load_terms_from_db(db)
    polished, changes = _apply_skill_polish(ai_polished, skill_rules, db, sentence_guide, terminology_md, None, db_terminology=db_terms_for_rule)
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



# ============================================================
# DOCX 润色与批注注入
# ============================================================

def _polish_docx_with_comments(
    docx_path: str,
    output_path: str,
    skill_rules: dict,
    db: Session,
    sentence_guide: str = None,
    terminology: str = None,
    requirements: str = None,
    ai_lines: list = None,
    db_terminology: dict = None
) -> list[PolishRuleMatch]:
    """对 DOCX 文件进行润色，保留排版并添加批注。
    
    ai_lines: AI 预润色后的文本行列表，与原始段落逐行对应。用于句式清单匹配润色。
    """
    from docx import Document
    from docx.oxml.ns import qn, nsdecls
    from lxml import etree
    from copy import deepcopy
    import zipfile
    import tempfile
    import os as os_mod
    
    all_changes = []
    
    doc = Document(docx_path)
    
    term_dict = {}
    if terminology:
        try:
            parsed = _parse_terminology(terminology)
            if parsed:
                all_text = '\n'.join([p.text for p in doc.paragraphs if p.text and p.text.strip()])
                lang = _detect_language(all_text)
                term_dict = _filter_terms_by_lang(parsed, lang)
        except Exception:
            pass
    if db_terminology:
        term_dict.update(db_terminology)
    
    author = "技术文档智能润色助手"
    revision_id = 0
    w_ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    
    toc_prefixes = ("TOC", "Table of Contents", "目录")
    
    non_empty_paras = [(idx, para) for idx, para in enumerate(doc.paragraphs) 
                       if para.text and para.text.strip()]
    non_empty_ai_lines = [l.strip() for l in ai_lines if l.strip()] if ai_lines else []
    
    for i, (para_idx, para) in enumerate(non_empty_paras):
        original_text = para.text.strip()
        
        style_name = (para.style.name or "").lower()
        
        # 仅跳过确认为目录的段落（样式名以 "toc" 开头或为 "toc heading"）
        is_toc = style_name.startswith('toc') or style_name == 'table of contents'
        
        if is_toc:
            continue
        
        title_keywords = ['heading', 'title', '目录', '标题', 'toc', '表', '图', 'table', 'figure', 'caption']
        is_title = any(kw in (style_name or "").lower() for kw in title_keywords) if style_name else False
        if not is_title and original_text.strip():
            if re.match(r'^(表|图|Table|Figure)\s*\d', original_text.strip()):
                is_title = True
        
        # Step 1: AI polish
        intermediate_text = original_text
        para_ai_change = None
        if i < len(non_empty_ai_lines):
            ai_line = non_empty_ai_lines[i]
            if ai_line and ai_line != original_text:
                intermediate_text = ai_line
                para_ai_change = PolishRuleMatch(
                    rule_name="ai", before=original_text[:100], after=ai_line[:100], type="ai"
                )
        
        # Step 2: Rule polish + 术语替换
        if para_ai_change:
            polished_text = intermediate_text
            para_changes = [para_ai_change]
        else:
            polished_text, para_changes = _apply_skill_polish(
                intermediate_text, skill_rules, db, sentence_guide, terminology, requirements,
                is_title=is_title, db_terminology=db_terminology
            )
        
        # 最终术语替换（无论 AI 是否已改，确保术语库强制生效）
        if term_dict:
            polished_text, term_changes = _apply_term_only(polished_text, term_dict)
            if term_changes:
                para_changes.extend(term_changes)
        
        if polished_text != original_text and (para_changes or polished_text.strip() != original_text.strip()):
            all_changes.extend(para_changes)
            p_element = para._p
            
            # ---- 1. 将原文所有 run 标记为删除（保留各自原有格式） ----
            revision_id += 1
            rid_del = str(revision_id)
            now = '2026-06-18T00:00:00Z'
            
            for child in list(p_element):
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if tag != 'r':
                    continue
                rPr = child.find(f'{{{w_ns}}}rPr')
                if rPr is None:
                    rPr = etree.SubElement(child, f'{{{w_ns}}}rPr')
                    child.insert(0, rPr)
                del_el = etree.SubElement(rPr, f'{{{w_ns}}}del')
                del_el.set(f'{{{w_ns}}}id', rid_del)
                del_el.set(f'{{{w_ns}}}author', author)
                del_el.set(f'{{{w_ns}}}date', now)
                # 把 <w:t> 改名为 <w:delText>
                for t_elem in child.findall(f'{{{w_ns}}}t'):
                    t_elem.tag = f'{{{w_ns}}}delText'
            
            # ---- 2. 追加润色后文字 run（标记为插入，沿用首个原 run 字体） ----
            revision_id += 1
            rid_ins = str(revision_id)
            first_run = para.runs[0] if para.runs else None
            new_run = para.add_run(polished_text)
            if first_run and first_run.font:
                try:
                    new_run.font.name = first_run.font.name
                    new_run.font.size = first_run.font.size
                    new_run.font.bold = first_run.font.bold
                    new_run.font.italic = first_run.font.italic
                    new_run.font.color.rgb = first_run.font.color.rgb
                except Exception:
                    pass
            # 在 XML 层给新 run 加上 <w:ins>
            new_r_element = new_run._r
            new_rPr = new_r_element.find(f'{{{w_ns}}}rPr')
            if new_rPr is None:
                new_rPr = etree.SubElement(new_r_element, f'{{{w_ns}}}rPr')
                new_r_element.insert(0, new_rPr)
            ins_el = etree.SubElement(new_rPr, f'{{{w_ns}}}ins')
            ins_el.set(f'{{{w_ns}}}id', rid_ins)
            ins_el.set(f'{{{w_ns}}}author', author)
            ins_el.set(f'{{{w_ns}}}date', now)
    
    doc.save(output_path)
    _inject_revision_settings(output_path)
    
    return all_changes


def _inject_revision_settings(docx_path: str):
    """向 DOCX 的 settings.xml 注入 <w:trackRevisions/>，使文档打开即显示修订标记。
    
    直接在 ZIP 内替换 word/settings.xml，保留所有其他 ZIP 条目的原始结构。
    """
    import zipfile
    import tempfile
    import os as os_mod
    from lxml import etree
    
    w_ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    temp_path = docx_path + '.tmp'
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zin, \
             zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            
            settings_xml = None
            settings_found = False
            
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == 'word/settings.xml':
                    settings_found = True
                    root = etree.fromstring(data)
                    existing = root.findall(f'{{{w_ns}}}trackRevisions')
                    if not existing:
                        etree.SubElement(root, f'{{{w_ns}}}trackRevisions')
                    # 写入时不添加 standalone
                    data = etree.tostring(root, xml_declaration=True, encoding='UTF-8')
                elif item.filename == 'word/settings.xml':
                    pass  # already handled
                
                zout.writestr(item, data)
            
            # 如果原文档没有 settings.xml，创建并添加
            if not settings_found:
                root = etree.Element(f'{{{w_ns}}}settings')
                etree.SubElement(root, f'{{{w_ns}}}trackRevisions')
                data = etree.tostring(root, xml_declaration=True, encoding='UTF-8')
                zi = zipfile.ZipInfo('word/settings.xml')
                zout.writestr(zi, data)
        
        # 替换原文件
        os_mod.replace(temp_path, docx_path)
    finally:
        if os_mod.path.exists(temp_path):
            os_mod.remove(temp_path)




# ============================================================
# 润色报告生成
# ============================================================

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
        'ai': 'AI句式润色',
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
    
    task_id = str(uuid.uuid4())
    with _polish_tasks_lock:
        _polish_tasks[task_id] = {"status": "running", "progress": 0, "message": "开始润色..."}
    
    def _update_progress(pct: int, msg: str):
        with _polish_tasks_lock:
            if task_id in _polish_tasks:
                _polish_tasks[task_id] = {"status": "running", "progress": pct, "message": msg}
    
    def _finish_task(result=None, error=None):
        with _polish_tasks_lock:
            if error:
                _polish_tasks[task_id] = {"status": "error", "progress": 100, "message": str(error)}
            else:
                _polish_tasks[task_id] = {"status": "done", "progress": 100, "message": "润色完成", "result": result}
    
    user = get_default_user(db)
    temp_path = None
    original_temp_path = None
    try:
        filename = file.filename or "unnamed"
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else "txt"
        
        _update_progress(5, "读取文件中...")
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

        _update_progress(10, "解析文本内容...")
        if ext in ['txt', 'md', 'markdown']:
            content = _read_file_safe(temp_path)
        elif ext == 'docx':
            from docx import Document
            doc = Document(temp_path)
            content = '\n'.join([p.text for p in doc.paragraphs])
        
        if content is None or content.strip() == "":
            raise HTTPException(status_code=400, detail="无法提取文本内容")

        _update_progress(15, "加载润色规则...")
        skill_rules = _load_skill_rules(3, db)
        
        sentence_guide = _build_document_polish_guide(
            db,
            sentence_file_id=sentence_file_id,
            requirements=requirements
        )
        sentence_file_name = None
        if sentence_file_id:
            sf = db.query(KnowledgeFile).filter(KnowledgeFile.id == sentence_file_id).first()
            if sf:
                sentence_file_name = sf.name
        
        terminology = None
        term_file_name = None
        if terminology_file_id:
            term_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == terminology_file_id).first()
            if term_file:
                term_file_name = term_file.name
                # Excel 文件直接用路径，Markdown 读文本内容
                if term_file.file_path and term_file.file_path.lower().endswith('.xlsx'):
                    terminology = term_file.file_path  # 传路径给 _parse_terminology_xlsx
                    print(f"[POLISH] 已加载术语Excel: {term_file_name}")
                else:
                    terminology = _read_file_safe(term_file.file_path)
                    print(f"[POLISH] 已加载术语文件: {term_file_name} ({len(terminology or '')} 字节)")

        db_terms = None if terminology else _load_terms_from_db(db)

        _update_progress(20, "AI 智能润色中...")
        ai_polished = content
        ai_changes = []
        try:
            from app.utils.ai_client import ai_client
            resolved_terms = _resolve_terminology(db, terminology, content)
            ai_result = ai_client.polish_text(content, style_guide=sentence_guide, terminology=resolved_terms if resolved_terms else None)
            if ai_result and ai_result.get("polished") and ai_result["polished"] != content:
                ai_polished = ai_result["polished"]
                ai_changes = ai_result.get("changes") or [{
                    "type": "ai",
                    "summary": "AI 根据句式清单完成智能润色"
                }]
        except Exception as e:
            print(f"AI 润色失败(继续使用规则润色): {e}")

        _update_progress(50, "应用修订标记...")
        if is_docx:
            ai_lines = [l for l in ai_polished.split('\n') if l.strip()] if ai_polished != content else None
            _, date_str = _get_date_subfolder_id(db, None, user.id)
            date_dir = os.path.join(UPLOAD_DIR, date_str)
            if not os.path.exists(date_dir):
                os.makedirs(date_dir)
            
            unique_filename = f"【修订标记版】{filename}"
            saved_file_path = os.path.join(date_dir, unique_filename)
            
            _update_progress(60, "生成修订版 DOCX...")
            changes = _polish_docx_with_comments(
                temp_path, saved_file_path, skill_rules, db,
                sentence_guide, terminology, requirements,
                ai_lines=ai_lines,
                db_terminology=db_terms
            )
            
            from docx import Document
            polished_doc = Document(saved_file_path)
            # 从修订标记版 DOCX 读取润色后文本（<w:delText> 被忽略，仅读 <w:t> 即插入文本）
            preview_text = '\n'.join([p.text for p in polished_doc.paragraphs])
            polished_text = preview_text
            
            _update_progress(80, "生成润色报告...")
            report_filename = f"【润色报告】{filename.rsplit('.', 1)[0]}.docx"
            report_path = os.path.join(date_dir, report_filename)
            _generate_polish_report(
                report_path, filename, changes,
                sentence_file_name,
                term_file_name,
                requirements
            )
            
            _update_progress(90, "保存到知识库...")
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
            
            result_data = {
                "task_id": task_id,
                "id": db_doc.id,
                "original": content,
                "polished": polished_text,
                "changes": changes,
                "report_file": report_filename,
                "download_filename": unique_filename,
                "file_type": "docx"
            }
            _finish_task(result_data)
            return result_data
        else:    
            _update_progress(70, "规则润色中...")
            polished_text, changes = _apply_skill_polish(ai_polished, skill_rules, db, sentence_guide, terminology, requirements, db_terminology=db_terms)
            if ai_changes:
                for ac in ai_changes:
                    if isinstance(ac, dict):
                        changes.insert(0, PolishRuleMatch(
                            rule_name=ac.get("type", "ai"),
                            before=ac.get("summary", "")[:50],
                            after="AI 根据句式清单完成智能润色",
                            type="ai"
                        ))
            
            _update_progress(90, "保存结果...")
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
            
            result_data = {
                "task_id": task_id,
                "id": db_doc.id,
                "original": content,
                "polished": polished_text,
                "changes": changes,
                "download_filename": unique_filename,
                "file_type": ext
            }
            _finish_task(result_data)
            return result_data

    except HTTPException:
        _finish_task(error="请求参数错误")
        raise
    except Exception as e:
        _finish_task(error=str(e))
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


@router.get("/progress/{task_id}")
async def get_polish_progress(task_id: str):
    """查询润色任务进度"""
    with _polish_tasks_lock:
        task = _polish_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


# ============================================================
# 润色反馈：准确率评分 + 修正词自动入库
# ============================================================

@router.post("/feedback", response_model=None)
def submit_polish_feedback(
    feedback: FeedbackInput,
    db: Session = Depends(get_db)
):
    """提交润色反馈：记录准确率评分，并将修正词写入术语库或句式清单。"""
    current_user = get_default_user(db)
    corrections_pairs = _parse_corrections(feedback.corrections)
    processed_count = 0
    errors = []
    
    if feedback.target == "terminology":
        for old_term, new_term in corrections_pairs:
            try:
                existing = db.query(Term).filter(
                    Term.non_standard == old_term,
                    Term.standard == new_term
                ).first()
                if existing:
                    continue
                term = Term(
                    non_standard=old_term,
                    standard=new_term,
                    category="用户反馈"
                )
                db.add(term)
                processed_count += 1
            except Exception as e:
                errors.append(f"{old_term}→{new_term}: {str(e)}")
        db.commit()
    
    elif feedback.target == "sentence_guide":
        feedback_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "knowledge")
        feedback_file = os.path.join(feedback_dir, "_polish_feedback.md")
        os.makedirs(feedback_dir, exist_ok=True)
        
        timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        with open(feedback_file, 'a', encoding='utf-8') as f:
            if not os.path.getsize(feedback_file):
                f.write("# 润色反馈修正记录\n\n")
                f.write("| 时间 | 准确率 | 原文(摘要) | 修正内容 |\n")
                f.write("|------|--------|-----------|----------|\n")
            summary = feedback.original_text[:50].replace('\n', ' ') + ('...' if len(feedback.original_text) > 50 else '')
            corrections_summary = '; '.join(f'{o}→{n}' for o, n in corrections_pairs) if corrections_pairs else '-'
            f.write(f"| {timestamp} | {feedback.accuracy}% | {summary} | {corrections_summary} |\n")
        
        processed_count = len(corrections_pairs)
    
    fb = PolishFeedback(
        original_text=feedback.original_text,
        polished_text=feedback.polished_text,
        accuracy=feedback.accuracy,
        corrections=feedback.corrections,
        target=feedback.target,
        processed_count=processed_count,
        created_by=current_user.username if current_user else "guest"
    )
    db.add(fb)
    db.commit()
    
    return {
        "message": "反馈已提交",
        "accuracy": feedback.accuracy,
        "corrections_count": len(corrections_pairs),
        "processed_count": processed_count,
        "target": feedback.target,
        "errors": errors if errors else None
    }


# ============================================================
# 文档润色端点（历史文档 / 种子导出）
# ============================================================

@router.post("/export-seed")
def export_polished_seed(db: Session = Depends(get_db)):
    """将已润色文档导出到种子目录，用于 Git 团队共享"""
    current_user = get_default_user(db)
    try:
        from seed.polished_seed import export_polished_to_seed
        export_polished_to_seed()
        return {"message": "已润色文档已导出到 seed/polished/ 目录，请执行 git add/commit/push 分享给团队"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.post("/{document_id}")
async def polish_document(document_id: int, db: Session = Depends(get_db)):
    document = get_document(db, document_id=document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        from app.utils.ai_client import ai_client
        terminology = _load_terms_from_db(db)
        result = ai_client.polish_text(document.content or "", terminology=terminology if terminology else None)
        changes = result.get("changes") or []
        return {
            "document_id": document_id,
            "original": result.get("original", document.content or ""),
            "polished": result.get("polished", document.content or ""),
            "changes": changes
        }
    except Exception:
        fb = _polish_fallback(document.content or "", db_terminology=terminology if terminology else None)
        fb["document_id"] = document_id
        return fb


def _polish_fallback(text: str, db_terminology: dict = None):
    polished, changes = _apply_skill_polish(text, {}, None, None, None, None, db_terminology=db_terminology)
    return {
        "original": text,
        "polished": polished,
        "changes": changes or [{"line": 1, "original": text[:80], "polished": polished[:80], "type": "format"}]
    }



# ============================================================
# 已润色文档 CRUD
# ============================================================

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
    
    # 文件在磁盘上不存在时，回退到 DB 中已保存的文字内容
    if not doc.file_path or not os.path.exists(doc.file_path):
        fallback_content = doc.polished_content or doc.original_content or ""
        if fallback_content:
            return {
                "content": fallback_content,
                "type": "text",
                "file_name": doc.filename,
                "polished_content": doc.polished_content,
                "fallback": True
            }
        else:
            raise HTTPException(status_code=404, detail="文件内容不可用")
    
    file_type = doc.file_type.lower()
    
    # Text-based files
    if file_type in ["txt", "md", "markdown", "json", "xml", "html", "css", "js", "py"]:
        with open(doc.file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {
            "content": content,
            "type": "text",
            "file_name": doc.filename,
            "polished_content": doc.polished_content
        }
    
    # Images
    elif file_type in ["jpg", "jpeg", "png", "gif", "bmp", "svg", "webp"]:
        return {
            "file_path": f"/api/polish/{doc_id}/raw",
            "type": "image",
            "file_name": doc.filename
        }
    
    # PDF - extract text
    elif file_type == "pdf":
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(doc.file_path)
            content = "\n".join([page.extract_text() or "" for page in reader.pages])
            return {"content": content, "type": "text", "file_name": doc.filename}
        except Exception:
            fallback = doc.polished_content or doc.original_content or ""
            return {"content": fallback, "type": "text", "file_name": doc.filename, "fallback": True}
    
    # DOCX - extract text
    elif file_type == "docx":
        try:
            content = docx2txt.process(doc.file_path)
            return {
                "content": content,
                "type": "text",
                "file_name": doc.filename,
                "polished_content": doc.polished_content
            }
        except Exception:
            fallback = doc.polished_content or doc.original_content or ""
            return {"content": fallback, "type": "text", "file_name": doc.filename, "fallback": True}
    
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


# ============================================================
# 润色反馈：准确率评分 + 修正词自动入库
# ============================================================

def _parse_corrections(text: str) -> list[tuple[str, str]]:
    """解析用户输入的修正内容，返回 [(非标准, 标准), ...] 列表。
    支持格式：'非标准→标准'、'非标准|标准'、'非标准 标准'
    """
    pairs = []
    if not text or not text.strip():
        return pairs
    
    for line in text.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # 尝试多种分隔符
        for sep in ['→', '->', '|', '\t']:
            if sep in line:
                parts = line.split(sep, 1)
                old = parts[0].strip()
                new = parts[1].strip() if len(parts) > 1 else ''
                if old and new and old != new and len(old) >= 1:
                    pairs.append((old, new))
                break
        else:
            # 空格分隔（取前两个词）
            words = line.split()
            if len(words) >= 2:
                old = words[0].strip()
                new = words[1].strip()
                if old and new and old != new and len(old) >= 1:
                    pairs.append((old, new))
    
    return pairs
