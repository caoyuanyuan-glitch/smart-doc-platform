from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import timedelta
from difflib import SequenceMatcher
import os
import uuid
import mimetypes
import re
import threading
import datetime
import logging
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
from app.utils.polish_rules_engine import apply_all_rules, apply_custom_rules
from app.crud.polish_learning_rule import get_enabled_engine_keys, get_enabled_custom_rules, record_rule_triggers
from app.crud.term import bulk_create_terms

router = APIRouter()
logger = logging.getLogger(__name__)
POLISH_AI_ONLY = False

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


def _protect_model_numbers(text: str) -> str:
    """保持产品型号内部连写，同时保留编号与术语之间的空格。"""
    if not text:
        return text

    text = re.sub(r'(?<=[A-Za-z-])\s+(?=\d+[A-Za-z])', '', text)
    text = re.sub(r'(?<=[A-Za-z-]\d)\s+(?=[A-Za-z])', '', text)
    text = re.sub(r'(?<=(?:表|图)\d)\s*(?=[A-Za-z]{2,})', ' ', text)
    text = re.sub(r'(?<=\d\.\d)\s*(?=[A-Za-z]{2,})', ' ', text)
    return text


def _use_ai_only() -> bool:
    return POLISH_AI_ONLY


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
    merged = {}

    platform_files = _get_platform_feedback_terminology_targets(db, 1)
    for platform_file in platform_files:
        if platform_file and platform_file.file_path and os.path.exists(platform_file.file_path):
            try:
                platform_terms = _parse_terminology(platform_file.file_path if platform_file.file_path.lower().endswith('.xlsx') else _read_file_safe(platform_file.file_path))
                if platform_terms:
                    if text:
                        lang = _detect_language(text)
                        merged.update(_filter_terms_by_lang(platform_terms, lang))
                    else:
                        merged.update(platform_terms)
            except Exception:
                pass

    if terminology_md:
        parsed = _parse_terminology(terminology_md)
        if parsed:
            if text:
                lang = _detect_language(text)
                merged.update(_filter_terms_by_lang(parsed, lang))
            else:
                merged.update(parsed)

    if merged:
        return merged
    return _load_terms_from_db(db)


def _load_terminology_source(db: Session, terminology_id: int = None) -> Optional[str]:
    """加载术语来源。Excel 返回文件路径，其它文本文件返回文件内容。"""
    if not terminology_id:
        return None

    term_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == terminology_id).first()
    if not term_file or not term_file.file_path or not os.path.exists(term_file.file_path):
        return None

    if term_file.file_path.lower().endswith('.xlsx'):
        return term_file.file_path

    return _read_file_safe(term_file.file_path)


# 句式清单所在知识库文件夹 ID（写作规范 / 句式清单）
SENTENCE_GUIDE_FOLDER_IDS = [8]
SENTENCE_FEEDBACK_FOLDER_IDS = [10]
PLATFORM_FEEDBACK_FILENAME = "平台反馈的句式清单.md"
TERMINOLOGY_FEEDBACK_FOLDER_IDS = [21]
PLATFORM_FEEDBACK_TERMINOLOGY_FILENAME = "平台反馈的术语对照表.md"
PLATFORM_FEEDBACK_SENTENCE_RELATIVE_PATH = os.path.join("写作规范", "句式清单", "来自平台反馈", PLATFORM_FEEDBACK_FILENAME)
PLATFORM_FEEDBACK_TERMINOLOGY_RELATIVE_PATH = os.path.join("资源库", "术语库", "来自平台反馈", PLATFORM_FEEDBACK_TERMINOLOGY_FILENAME)

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
    # 始终加载通用句式清单作为基础
    all_guides = _load_sentence_guides(db)
    if all_guides:
        parts.append(all_guides)
    # 用户指定的句式文件附加进来（优先级更高）
    if sentence_file_id and sentence_file_id != DEFAULT_STYLE_GUIDE_ID:
        selected_guide = _load_sentence_guides(db, style_guide_id=sentence_file_id)
        if selected_guide:
            parts.append(selected_guide)

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


def _invalidate_sentence_guide_cache(style_guide_id: Optional[int] = None):
    """句式文件更新后清理相关缓存，保证新内容立即生效。"""
    _sentence_guide_cache.pop('__all__', None)
    if style_guide_id is not None:
        _sentence_guide_cache.pop(style_guide_id, None)


def _normalize_sentence_for_match(text: str) -> str:
    """去掉空白和常见标点，用于轻量句式相似度匹配。"""
    if not text:
        return ""
    return re.sub(r'[\s，。！？；：,.!?;:""''()（）【】\[\]<>《》-]+', '', text)


def _bigram_set(text: str) -> set:
    """将文本切分为字符 bigram 集合。"""
    if len(text) < 2:
        return {text} if text else set()
    return {text[i:i+2] for i in range(len(text) - 1)}


def _lcs_ratio(a: str, b: str) -> float:
    """最长公共子序列长度与较长字符串长度之比。"""
    if not a or not b:
        return 0.0
    m, n = len(a), len(b)
    if m == 0 or n == 0:
        return 0.0
    # 使用 1D 数组优化 LCS
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        cur = [0] * (n + 1)
        for j in range(1, n + 1):
            if a[i-1] == b[j-1]:
                cur[j] = prev[j-1] + 1
            else:
                cur[j] = max(prev[j], cur[j-1])
        prev = cur
    lcs_len = prev[n]
    return lcs_len / max(m, n)


def _sentence_similarity(a: str, b: str) -> float:
    """
    计算两个中文句子的相似度（分段匹配）。

    综合 bigram Jaccard 相似度（捕捉局部片段重叠）和
    LCS 比率（捕捉整体结构相似度），取加权平均。
    当常规得分不足但存在高重合公共子串时，以子串比例兜底。
    """
    if a == b:
        return 1.0
    a_norm = _normalize_sentence_for_match(a)
    b_norm = _normalize_sentence_for_match(b)
    if not a_norm or not b_norm:
        return 0.0
    if a_norm == b_norm:
        return 1.0
    # Bigram Jaccard
    bigrams_a = _bigram_set(a_norm)
    bigrams_b = _bigram_set(b_norm)
    intersection = len(bigrams_a & bigrams_b)
    union = len(bigrams_a | bigrams_b)
    bigram_score = intersection / union if union > 0 else 0.0
    # LCS ratio
    lcs_score = _lcs_ratio(a_norm, b_norm)
    # 句子结构相似度
    struct_score = _compare_sentence_structure(a, b)
    # 语义关键词重叠
    keyword_score = _compare_semantic_keywords(a, b)
    # 加权：bigram 0.3 + LCS 0.3 + 结构 0.2 + 关键词 0.2
    score = 0.3 * bigram_score + 0.3 * lcs_score + 0.2 * struct_score + 0.2 * keyword_score
    # 高重合子串兜底：常规分不到 0.85 但最长公共子串覆盖 >=75% 时激活
    if score < 0.85:
        s = SequenceMatcher(None, a_norm, b_norm)
        match = s.find_longest_match(0, len(a_norm), 0, len(b_norm))
        shorter = min(len(a_norm), len(b_norm))
        substr_ratio = match.size / shorter if shorter > 0 else 0.0
        if substr_ratio >= 0.75:
            score = 0.80 + (substr_ratio - 0.75) * 0.8  # 0.80~1.00
    return min(score, 1.0)


# 核心动词列表（技术文档常见操作动词）
_CORE_VERBS = {
    '置于', '放置', '安装', '对应', '匹配', '确保', '检查', '设置', '调整',
    '校准', '测量', '分析', '记录', '保存', '删除', '关闭', '打开', '启动',
    '停止', '连接', '断开', '输入', '输出', '读取', '写入', '扫描', '点击',
    '选择', '确认', '取消', '添加', '移除', '插入', '取出', '转移', '等待',
    '观察', '核对', '撕开', '倒入', '拨至', '装入', '置于', '装填',
}

# 方位词列表
_POSITION_WORDS = {'上', '下', '前', '后', '左', '右', '内', '外', '中', '间', '里', '旁', '侧'}


def _extract_semantic_keywords(sentence: str) -> list[str]:
    """提取语义关键词：实体名词 + 核心动词 + 方位词。"""
    keywords = []
    text = _normalize_sentence_for_match(sentence)
    if not text:
        return keywords
    # 提取 2-4 字连续中文字符作为名词实体
    for match in re.finditer(r'[\u4e00-\u9fa5]{2,4}', text):
        w = match.group()
        # 过滤纯数字组合和无效片段
        if w not in ('一个', '一些', '这个', '那个', '每个', '所有', '可以', '需要', '进行'):
            keywords.append(w)
    # 提取核心动词
    for verb in _CORE_VERBS:
        if verb in text:
            keywords.append(verb)
    # 提取方位词
    for pw in _POSITION_WORDS:
        if pw in text:
            keywords.append(pw)
    return list(set(keywords))


def _compare_semantic_keywords(a: str, b: str) -> float:
    """计算两个句子的语义关键词重叠度。"""
    kw_a = _extract_semantic_keywords(a)
    kw_b = _extract_semantic_keywords(b)
    if not kw_a or not kw_b:
        return 0.0
    overlap = len(set(kw_a) & set(kw_b))
    denominator = max(len(kw_a), len(kw_b))
    return overlap / denominator if denominator > 0 else 0.0


def _extract_sentence_structure(sentence: str) -> dict:
    """提取中文技术文档句子的主谓宾结构。"""
    struct = {"verb": "", "subject": "", "object": "", "pattern": ""}
    text = sentence.strip()
    # 模式1: "将A置于B上/中" 或 "将A放置于B"
    m = re.search(r'将(.+?)(置于|放置于|放置在|放入|装到|插入|转移到|拨至|倒[入进])(.+?)([上中下内外]|位置)?', text)
    if m:
        struct["verb"] = m.group(2)
        struct["subject"] = m.group(1)
        struct["object"] = m.group(3) + (m.group(4) or '')
        struct["pattern"] = "将X置于Y"
        return struct
    # 模式2: "确保A与B一致/对应" 或 "检查A与B匹配"
    m = re.search(r'(确保|检查|验证|确认)(.+?)(与|和)(.+?)(一致|匹配|对应|对齐|相同)', text)
    if m:
        struct["verb"] = m.group(1)
        struct["subject"] = m.group(2)
        struct["object"] = m.group(4)
        struct["pattern"] = "X与Y一致"
        return struct
    # 模式3: "用/使用A做B"
    m = re.search(r'(用|使用|利用|通过)(.+?)(进行|完成|实现|执行)(.+)', text)
    if m:
        struct["verb"] = m.group(3)
        struct["subject"] = m.group(2)
        struct["object"] = m.group(4)
        struct["pattern"] = "用X做Y"
        return struct
    # 模式4: "待A后，B" 或 "当A时，B"
    m = re.search(r'(?:待|当|等到)(.+?)(?:后|时|之后)(.+)', text)
    if m:
        struct["verb"] = "等待"
        struct["subject"] = m.group(1)
        struct["object"] = m.group(2)
        struct["pattern"] = "待X后做Y"
        return struct
    # 模式5: "点击/选择/打开/关闭A"
    m = re.search(r'(点击|选择|打开|关闭|进入|退出|切换到)(.+)', text)
    if m:
        struct["verb"] = m.group(1)
        struct["object"] = m.group(2)
        struct["pattern"] = "操作UI元素"
        return struct
    return struct


def _compare_sentence_structure(a: str, b: str) -> float:
    """比较两个句子的主谓宾结构相似度。"""
    sa = _extract_sentence_structure(a)
    sb = _extract_sentence_structure(b)
    if not sa["pattern"] or not sb["pattern"]:
        return 0.5  # 无法提取结构时给中性分数
    if sa["pattern"] != sb["pattern"]:
        return 0.0  # 结构模式不同
    score = 1.0
    if sa["verb"] and sb["verb"]:
        if sa["verb"] != sb["verb"]:
            score -= 0.3
    return max(score, 0.0)


def _generate_sentence_variants(sentence: str) -> list[str]:
    """为精确匹配生成句子的多种变体。"""
    variants = [sentence]
    text = sentence.strip()
    # 去掉标点
    no_punct = re.sub(r'[，。！？；：、,.!?;:""''()（）【】\[\]<>《》]+', '', text)
    variants.append(no_punct)
    # 统一空格
    unified = ' '.join(text.split())
    if unified != text:
        variants.append(unified)
    return list(set(variants))


# 约束润色器配置
_CONSTRAINT_TERMINOLOGY = {
    "机器": "仪器",
    "推板": "载台",
    "平置": "水平放置",
    "探测器": "检测器",
    "分离柱": "色谱柱",
    "底线": "基线",
    "注射": "进样",
    "滞留时间": "保留时间",
}

_COLLOQUIAL_PATTERNS = [
    (r'一下', ''),
    (r'的话', ''),
]

_SYNTAX_OPTIMIZATIONS = [
    (r'要与(.+?)对应', r'确保与\1一致'),
    (r'(.+?[^：：因])\s*为\s*(.+)', r'\1：\2'),
]


def _apply_constraint_polish(sentence: str) -> str:
    """对未匹配到句式的句子进行约束润色。"""
    result = sentence
    # 术语标准化
    for non_std, std in _CONSTRAINT_TERMINOLOGY.items():
        result = result.replace(non_std, std)
    # 删除口语化冗余
    for pattern, replacement in _COLLOQUIAL_PATTERNS:
        result = re.sub(pattern, replacement, result)
    # 句式优化
    for pattern, replacement in _SYNTAX_OPTIMIZATIONS:
        result = re.sub(pattern, replacement, result)
    return result


# 匹配策略配置
_POLISH_MATCH_CONFIG = {
    "l2_auto_replace": True,      # L2 模糊匹配自动替换
    "l3_auto_replace": True,      # L3 语义匹配自动替换
    "l1_confidence": 1.0,         # L1 精确匹配置信度
    "l2_min_confidence": 0.85,    # L2 模糊匹配最低置信度
    "l3_min_confidence": 0.90,    # L3 语义匹配最低置信度
    "l3_auto_confidence": 0.65,   # L3 普通规则匹配阈值（preferred_sentences）
}

def _load_sentence_guides(db: Session, style_guide_id: int = None) -> str:
    """加载句式清单内容（带缓存）。

    若指定了 style_guide_id，仅加载该文件；
    否则递归加载句式清单文件夹下所有 .md 文件。
    """
    cache_key = style_guide_id or '__all__'
    if cache_key in _sentence_guide_cache:
        return _sentence_guide_cache[cache_key]

    platform_guides = []
    selected_file_path = None
    if style_guide_id:
        selected_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == style_guide_id).first()
        selected_file_path = selected_file.file_path if selected_file else None

    for platform_file in _get_platform_feedback_targets(db, 1):
        if platform_file and platform_file.file_path and os.path.exists(platform_file.file_path):
            if selected_file_path and platform_file.file_path == selected_file_path:
                continue
            try:
                content = _read_file_safe(platform_file.file_path)
                if content.strip():
                    platform_guides.append(content)
            except Exception:
                pass

    if style_guide_id:
        style_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == style_guide_id).first()
        if style_file and style_file.file_path and os.path.exists(style_file.file_path):
            try:
                content = _read_file_safe(style_file.file_path)
                if content.strip():
                    result = "\n\n".join([content, *platform_guides]) if platform_guides else content
                    _sentence_guide_cache[cache_key] = result
                    return result
            except Exception as e:
                print(f"加载句式文件失败 (id={style_guide_id}): {e}")
        result = "\n\n".join(platform_guides) if platform_guides else None
        _sentence_guide_cache[cache_key] = result
        return result

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
    guides.extend(platform_guides)
    result = "\n\n".join(guides) if guides else None
    _sentence_guide_cache[cache_key] = result
    return result


def _ensure_platform_feedback_sentence_file(db: Session, user_id: int) -> KnowledgeFile:
    """确保平台反馈句式清单存在于知识库中。"""
    folder_id = SENTENCE_FEEDBACK_FOLDER_IDS[0]
    knowledge_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "knowledge")
    if not os.path.exists(knowledge_dir):
        os.makedirs(knowledge_dir)

    file_path = os.path.join(knowledge_dir, PLATFORM_FEEDBACK_SENTENCE_RELATIVE_PATH)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    initial_content = "# 平台反馈的句式清单\n\n## 用户反馈修正\n\n"

    feedback_file = db.query(KnowledgeFile).filter(
        KnowledgeFile.folder_id == folder_id,
        KnowledgeFile.name == PLATFORM_FEEDBACK_FILENAME,
        KnowledgeFile.file_path == file_path
    ).first()

    if not feedback_file:
        feedback_file = db.query(KnowledgeFile).filter(
            KnowledgeFile.folder_id == folder_id,
            KnowledgeFile.name == PLATFORM_FEEDBACK_FILENAME
        ).order_by(KnowledgeFile.id.asc()).first()
        if feedback_file:
            feedback_file.file_path = file_path
            feedback_file.filename = PLATFORM_FEEDBACK_FILENAME
            feedback_file.file_type = 'md'
            feedback_file.file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            db.commit()
            db.refresh(feedback_file)

    if feedback_file:
        if not os.path.exists(feedback_file.file_path):
            with open(feedback_file.file_path, 'w', encoding='utf-8') as f:
                f.write(initial_content)
            feedback_file.file_size = os.path.getsize(feedback_file.file_path)
            db.commit()
            db.refresh(feedback_file)
        return feedback_file

    if not os.path.exists(file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(initial_content)

    feedback_file = KnowledgeFile(
        folder_id=folder_id,
        name=PLATFORM_FEEDBACK_FILENAME,
        filename=PLATFORM_FEEDBACK_FILENAME,
        file_path=file_path,
        file_size=os.path.getsize(file_path),
        file_type='md',
        created_by=user_id
    )
    db.add(feedback_file)
    db.commit()
    db.refresh(feedback_file)
    return feedback_file


def _ensure_platform_feedback_terminology_file(db: Session, user_id: int) -> KnowledgeFile:
    """确保平台反馈术语对照表存在于知识库中。"""
    folder_id = TERMINOLOGY_FEEDBACK_FOLDER_IDS[0]

    knowledge_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "knowledge")
    if not os.path.exists(knowledge_dir):
        os.makedirs(knowledge_dir)

    file_path = os.path.join(knowledge_dir, PLATFORM_FEEDBACK_TERMINOLOGY_RELATIVE_PATH)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    initial_content = "# 平台反馈的术语对照表\n\n| 非标准词 | 标准词 |\n| --- | --- |\n"

    feedback_file = db.query(KnowledgeFile).filter(
        KnowledgeFile.folder_id == folder_id,
        KnowledgeFile.name == PLATFORM_FEEDBACK_TERMINOLOGY_FILENAME,
        KnowledgeFile.file_path == file_path
    ).first()

    if not feedback_file:
        feedback_file = db.query(KnowledgeFile).filter(
            KnowledgeFile.folder_id == folder_id,
            KnowledgeFile.name == PLATFORM_FEEDBACK_TERMINOLOGY_FILENAME
        ).order_by(KnowledgeFile.id.asc()).first()
        if feedback_file:
            feedback_file.file_path = file_path
            feedback_file.filename = PLATFORM_FEEDBACK_TERMINOLOGY_FILENAME
            feedback_file.file_type = 'md'
            feedback_file.file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            db.commit()
            db.refresh(feedback_file)

    if feedback_file:
        if not os.path.exists(feedback_file.file_path):
            with open(feedback_file.file_path, 'w', encoding='utf-8') as f:
                f.write(initial_content)
            feedback_file.file_size = os.path.getsize(feedback_file.file_path)
            db.commit()
            db.refresh(feedback_file)
        return feedback_file

    if not os.path.exists(file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(initial_content)

    feedback_file = KnowledgeFile(
        folder_id=folder_id,
        name=PLATFORM_FEEDBACK_TERMINOLOGY_FILENAME,
        filename=PLATFORM_FEEDBACK_TERMINOLOGY_FILENAME,
        file_path=file_path,
        file_size=os.path.getsize(file_path),
        file_type='md',
        created_by=user_id
    )
    db.add(feedback_file)
    db.commit()
    db.refresh(feedback_file)
    return feedback_file


def _get_platform_feedback_targets(db: Session, user_id: int) -> list[KnowledgeFile]:
    """返回已有的平台反馈句式清单文件，不执行自动创建。"""
    return db.query(KnowledgeFile).filter(
        KnowledgeFile.name == PLATFORM_FEEDBACK_FILENAME
    ).order_by(KnowledgeFile.id.desc()).all()


def _get_platform_feedback_terminology_targets(db: Session, user_id: int) -> list[KnowledgeFile]:
    """返回平台反馈术语对照表固定主文件。"""
    primary_file = _ensure_platform_feedback_terminology_file(db, user_id)
    return [primary_file] if primary_file else []

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
    accuracy: int              # 0-100
    corrections: str = ""       # 用户修正内容，每行一条 "非标准 → 标准"
    target: str = "terminology" # "terminology" 或 "sentence_guide"
    terminology_file_id: Optional[int] = None
    sentence_file_id: Optional[int] = None


class DocumentFeedbackItem(BaseModel):
    before: str = ""
    after: str = ""
    type: str = ""
    accepted: bool = True
    status: str = ""
    paragraph: Optional[int] = None


class DocumentFeedbackInput(BaseModel):
    document_id: Optional[int] = None
    source_filename: str = ""
    items: List[DocumentFeedbackItem] = []


class PolishRuleMatch(BaseModel):
    rule_name: str
    before: str
    after: str
    type: str
    paragraph: Optional[int] = None


def _normalize_compare_text(text: str) -> str:
    if text is None:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip()


def _strip_doc_trailing_punctuation(text: str) -> str:
    return re.sub(r'[。.!！？?，,;；:：]+$', '', _normalize_compare_text(text))


def _is_low_value_doc_change(before: str, after: str, change_type: str = '', rule_name: str = '') -> bool:
    before_core = _strip_doc_trailing_punctuation(before)
    after_core = _strip_doc_trailing_punctuation(after)
    if not before_core or not after_core:
        return False
    if before_core == after_core:
        return True

    short_limit = 4
    if len(before_core) <= short_limit and after_core == f'请{before_core}':
        return True
    if before_core.startswith('请') and len(before_core) <= short_limit and after_core == before_core[1:]:
        return True

    normalized_type = str(change_type or '').lower()
    normalized_rule = str(rule_name or '')
    is_format_like = normalized_type in {'format', 'punctuation'} or normalized_rule == '基础规范化'
    if is_format_like and len(before_core) <= short_limit and after_core.startswith(before_core):
        return True
    return False


def _doc_change_memory_key(before: str, after: str) -> str:
    return f"{_normalize_compare_text(before)}\u0001{_normalize_compare_text(after)}"


def _load_rejected_doc_change_keys(db: Session) -> set[tuple[str, str]]:
    if db is None:
        return set()
    rows = db.query(PolishFeedback.original_text, PolishFeedback.polished_text).filter(
        PolishFeedback.target == 'document_rejected_change'
    ).all()
    return {(_normalize_compare_text(before), _normalize_compare_text(after)) for before, after in rows if before or after}


def _is_rejected_doc_change(before: str, after: str, rejected_keys: set[tuple[str, str]] = None) -> bool:
    if not rejected_keys:
        return False
    current_before = _normalize_compare_text(before)
    current_after = _normalize_compare_text(after)
    if not current_before or not current_after:
        return False
    for rejected_before, rejected_after in rejected_keys:
        if not rejected_before or not rejected_after:
            continue
        before_matches = current_before == rejected_before or current_before.startswith(rejected_before) or rejected_before.startswith(current_before)
        after_matches = current_after == rejected_after or current_after.startswith(rejected_after) or rejected_after.startswith(current_after)
        if before_matches and after_matches:
            return True
    return False


def _doc_change_display_priority(change_type: str) -> int:
    priority_map = {
        'style': 100,
        'preferred_sentences': 100,
        'sentence_applicability_rule': 100,
        'terminology': 90,
        'term': 90,
        'terminology_rule': 90,
        'forbidden': 80,
        'forbidden_rule': 80,
        'forbidden_words': 80,
        'imperative': 70,
        'imperative_rule': 70,
        'ai': 40,
        'format': 10,
        'punctuation': 10,
    }
    return priority_map.get(str(change_type or ''), 30)


def _is_displayable_doc_change(change_type: str) -> bool:
    return _doc_change_display_priority(change_type) >= 70


def _dedupe_visible_doc_changes(changes: list[dict]) -> list[dict]:
    selected = {}
    order = []
    for item in changes:
        before = _normalize_compare_text(item.get('before', ''))
        after = _normalize_compare_text(item.get('after', ''))
        key = before or after
        if not key:
            continue
        score = _doc_change_display_priority(item.get('type', ''))
        existing = selected.get(key)
        if existing is None:
            selected[key] = item
            order.append(key)
            continue
        existing_score = _doc_change_display_priority(existing.get('type', ''))
        if score > existing_score:
            selected[key] = item
    return [selected[key] for key in order if key in selected]


def _pick_visible_doc_changes(changes: list[dict]) -> list[dict]:
    deduped = _dedupe_visible_doc_changes(changes)
    preferred = [item for item in deduped if _is_displayable_doc_change(item.get('type', ''))]
    return preferred if preferred else deduped


def _build_doc_change_details(original_text: str, polished_text: str, changes: list, rejected_keys: set[str] = None) -> list[dict]:
    original_lines = [line.strip() for line in (original_text or '').split('\n') if line.strip()]
    polished_lines = [line.strip() for line in (polished_text or '').split('\n') if line.strip()]

    matcher = SequenceMatcher(None, original_lines, polished_lines)
    diff_rows = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue

        before_lines = original_lines[i1:i2]
        after_lines = polished_lines[j1:j2]
        max_len = max(len(before_lines), len(after_lines), 1)

        for idx in range(max_len):
            before = before_lines[idx] if idx < len(before_lines) else ''
            after = _protect_model_numbers(after_lines[idx]) if idx < len(after_lines) else ''
            if _normalize_compare_text(before) == _normalize_compare_text(after):
                continue
            if _is_low_value_doc_change(before, after, 'ai', ''):
                continue
            if _is_rejected_doc_change(before, after, rejected_keys):
                continue
            diff_rows.append({
                "before": before,
                "after": after,
                "type": "ai" if before and after else "format"
            })

    if not diff_rows:
        return []

    normalized_changes = []
    for item in changes or []:
        if isinstance(item, dict):
            before = item.get('before', '')
            after = _protect_model_numbers(item.get('after', ''))
            change_type = item.get('type', '')
            paragraph = item.get('paragraph') or item.get('paragraph_index')
        else:
            before = getattr(item, 'before', '')
            after = _protect_model_numbers(getattr(item, 'after', ''))
            change_type = getattr(item, 'type', '')
            paragraph = getattr(item, 'paragraph', None)

        normalized_before = _normalize_compare_text(before)
        normalized_after = _normalize_compare_text(after)
        if normalized_before == normalized_after:
            continue
        if _is_low_value_doc_change(before, after, change_type, getattr(item, 'rule_name', '') if not isinstance(item, dict) else item.get('rule_name', '')):
            continue
        if _is_rejected_doc_change(before, after, rejected_keys):
            continue
        normalized_changes.append({
            "before": before,
            "after": after,
            "type": change_type,
            "paragraph": paragraph,
        })

    for row in diff_rows:
        row_before = _normalize_compare_text(row['before'])
        row_after = _normalize_compare_text(row['after'])
        matched_type = row['type']
        for item in normalized_changes:
            item_before = _normalize_compare_text(item['before'])
            item_after = _normalize_compare_text(item['after'])
            if item_before and item_before in row_before:
                matched_type = item['type'] or matched_type
                row['paragraph'] = item.get('paragraph')
                break
            if item_after and item_after in row_after:
                matched_type = item['type'] or matched_type
                row['paragraph'] = item.get('paragraph')
                break
        row['type'] = matched_type

    return _pick_visible_doc_changes(diff_rows)


def _filter_visible_doc_changes(changes: list, rejected_keys: set[str] = None) -> list[dict]:
    visible = []
    for item in changes or []:
        if isinstance(item, dict):
            before = item.get('before', '')
            after = _protect_model_numbers(item.get('after', ''))
            change_type = item.get('type', '')
            rule_name = item.get('rule_name', '')
            paragraph = item.get('paragraph') or item.get('paragraph_index')
        else:
            before = getattr(item, 'before', '')
            after = _protect_model_numbers(getattr(item, 'after', ''))
            change_type = getattr(item, 'type', '')
            rule_name = getattr(item, 'rule_name', '')
            paragraph = getattr(item, 'paragraph', None)

        if _normalize_compare_text(before) == _normalize_compare_text(after):
            continue

        if not _normalize_compare_text(before) and not _normalize_compare_text(after):
            continue

        if _is_low_value_doc_change(before, after, change_type, rule_name):
            continue

        if _is_rejected_doc_change(before, after, rejected_keys):
            continue

        visible.append({
            'before': before,
            'after': after,
            'type': change_type,
            'rule_name': rule_name,
            'paragraph': paragraph,
        })
    return _pick_visible_doc_changes(visible)



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

    def _should_show_basic_change(before: str, after: str, change_type: str) -> bool:
        before_text = (before or '').strip()
        after_text = (after or '').strip()
        if not before_text or before_text == after_text:
            return False
        if change_type == 'punctuation':
            return False
        if len(before_text) <= 4:
            return False
        if _is_noun_phrase(before_text):
            return False
        before_core = before_text.rstrip('。.!！？?，,;；:：')
        after_core = after_text.rstrip('。.!！？?，,;；:：')
        return before_core != after_core
    if _use_ai_only():
        return text, []

    sentence_only_mode = False
    changes = []
    lines = text.split('\n')
    polished_lines = []
    triggered_rule_ids = []
    triggered_engine_keys = []
    
    style_rules = []
    if sentence_guide:
        style_rules = _extract_style_rules(sentence_guide)
        logger.warning(
            "polish sentence guide parsed: text_len=%s rules=%s rule_types=%s",
            len(sentence_guide or ''),
            len(style_rules),
            [rule.get('type') for rule in style_rules[:10]],
        )
    
    term_dict = {}
    # 先解析文件中的术语替换（支持中英文多列表，自动语言过滤）
    if terminology and not sentence_only_mode:
        try:
            parsed = _parse_terminology(terminology)
            if parsed:
                lang = _detect_language(text)
                term_dict = _filter_terms_by_lang(parsed, lang)
        except Exception:
            pass
    # 合并数据库术语库（优先级高于文件术语）
    if db_terminology and not sentence_only_mode:
        term_dict.update(db_terminology)
    
    engine_enabled_rules = [] if sentence_only_mode else (get_enabled_engine_keys(db) if db else None)
    if is_title and engine_enabled_rules:
        engine_enabled_rules = [key for key in engine_enabled_rules if key != 'punctuation']
    custom_rules = [] if sentence_only_mode else (get_enabled_custom_rules(db) if db else [])

    def _rule_type(rule) -> str:
        return str(getattr(rule, 'rule_type', '') or '')

    sentence_custom_rules = [rule for rule in custom_rules if _rule_type(rule) == 'sentence_applicability_rule']
    term_custom_rules = [rule for rule in custom_rules if _rule_type(rule) == 'replacement_rule']
    other_custom_rules = [
        rule for rule in custom_rules
        if _rule_type(rule) not in {'sentence_applicability_rule', 'replacement_rule'}
    ]

    term_enabled_rules = None
    other_engine_rules = None
    if engine_enabled_rules is not None:
        term_enabled_rules = [key for key in engine_enabled_rules if key == 'termReplace']
        other_engine_rules = [key for key in engine_enabled_rules if key != 'termReplace']
    else:
        term_enabled_rules = ['termReplace']
        other_engine_rules = ['imperativePlease', 'numberSpace', 'cnEnSpace', 'punctuation']
    if is_title:
        other_engine_rules = [key for key in other_engine_rules if key != 'punctuation']

    def _append_custom_issues(issues: list[dict]):
        nonlocal has_changes
        if not issues:
            return
        for issue in issues:
            if issue.get('rule_id'):
                triggered_rule_ids.append(issue.get('rule_id'))
            changes.append(PolishRuleMatch(
                rule_name=issue.get('rule_name', '自定义规则'),
                before=issue.get('before', issue.get('original', ''))[:80],
                after=issue.get('after', issue.get('replacement', ''))[:80],
                type=issue.get('type', 'custom')
            ))
        has_changes = True

    def _append_engine_issues(issues: list[dict]):
        nonlocal has_changes
        if not issues:
            return
        for issue in issues:
            if issue.get('engine_key'):
                triggered_engine_keys.append(issue.get('engine_key'))
            changes.append(PolishRuleMatch(
                rule_name=issue.get('rule_name', '规则检测'),
                before=issue.get('original', ''),
                after=issue.get('replacement', ''),
                type=issue.get('type', 'format')
            ))
        has_changes = True

    for line in lines:
        original = line
        new_line = line.strip()
        # 剥离编号前缀（如 "5. "、"1、"、"3) "），正文独立匹配
        step_prefix = ""
        step_match = re.match(r'^(\d+[.、)\s]+)\s*(.+)$', new_line)
        if step_match:
            step_prefix = step_match.group(1)
            new_line = step_match.group(2)
        
        has_changes = False
        
        if style_rules and not is_title:
            # 拆分子句检测匹配，匹配到后在全文级执行替换以避免子句边界重复
            clauses = [c.strip() for c in re.split(r'[，。；！？,;!?]+', new_line) if c.strip()]
            if len(clauses) > 1:
                # 阶段1: 子句级检测最佳匹配模板
                best_template = None
                for clause in clauses:
                    for rule in style_rules:
                        if rule["type"] != "preferred_sentences":
                            continue
                        tmpl, score, level = _three_tier_match(clause, rule.get("sentences", []))
                        if tmpl and score >= _POLISH_MATCH_CONFIG["l2_min_confidence"]:
                            best_template = tmpl
                            break
                    if best_template:
                        break
                if best_template:
                    # 阶段2: 全文级替换，避免子句边界处重复
                    original_before = new_line
                    new_line = replace_with_context(new_line, best_template)
                    if new_line != original_before:
                        changes.append(PolishRuleMatch(
                            rule_name="句式模板匹配",
                            before=original_before[:80],
                            after=new_line[:80],
                            type="style"
                        ))
                        logger.warning(
                            "polish sentence guide matched: before=%r after=%r template=%r",
                            original_before[:120],
                            new_line[:120],
                            best_template[:80],
                        )
                        has_changes = True
                # 阶段3: 应用非句式规则（禁用词、被动语态、约束润色等）
                non_tmpl_rules = [r for r in style_rules if r["type"] != "preferred_sentences"]
                if non_tmpl_rules:
                    new_line, rule_changes = _apply_style_rules(new_line, non_tmpl_rules)
                    if rule_changes:
                        changes.extend(rule_changes)
                        has_changes = True
            else:
                new_line, rule_changes = _apply_style_rules(new_line, style_rules)
                if rule_changes:
                    logger.warning(
                        "polish sentence guide matched: before=%r after=%r matches=%s",
                        original[:120],
                        new_line[:120],
                        [change.rule_name for change in rule_changes],
                    )
                    changes.extend(rule_changes)
                    has_changes = True

        if sentence_custom_rules and not is_title:
            new_line, custom_issues = apply_custom_rules(new_line, sentence_custom_rules)
            if custom_issues:
                logger.warning(
                    "polish sentence custom matched: before=%r after=%r matches=%s",
                    original[:120],
                    new_line[:120],
                    [issue.get('rule_name') for issue in custom_issues],
                )
            _append_custom_issues(custom_issues)

        if not sentence_only_mode:
            term_line, term_issues = apply_all_rules(
                new_line,
                term_dict=term_dict,
                enabled_rules=term_enabled_rules,
                context_text=text
            )
            _append_engine_issues(term_issues)
            new_line = term_line

        if term_custom_rules:
            new_line, custom_issues = apply_custom_rules(new_line, term_custom_rules)
            _append_custom_issues(custom_issues)

        if other_custom_rules:
            new_line, custom_issues = apply_custom_rules(new_line, other_custom_rules)
            _append_custom_issues(custom_issues)

        # ── 应用其余系统规则（从 DB 读取启用的规则） ──
        if not sentence_only_mode:
            polished_line, engine_issues = apply_all_rules(
                new_line,
                term_dict={},
                enabled_rules=other_engine_rules,
                context_text=text
            )
            _append_engine_issues(engine_issues)
            new_line = polished_line
        
        if not sentence_only_mode:
            new_line = re.sub(r'\s+', ' ', new_line)
            new_line = _protect_model_numbers(new_line)
        
        # 标题、表标题、图标题等不加句号，也不做空间距规整
        if not is_title and not sentence_only_mode:
            if new_line and not new_line.endswith(('。', '.', '！', '!', '？', '?')):
                if not _is_noun_phrase(new_line):
                    if re.search(r'[\u4e00-\u9fff]', new_line):
                        new_line = new_line.rstrip('，,;；;：:') + '。'
                    else:
                        new_line = new_line.rstrip(',,;;::') + '.'
            new_line = re.sub(r'(\d)([℃%μ])', r'\1 \2', new_line)
            new_line = re.sub(r'([\u4e00-\u9fff])(?!表\d|图\d)([A-Za-z0-9])', r'\1 \2', new_line)
            new_line = re.sub(r'([A-Za-z0-9])([\u4e00-\u9fff])', r'\1 \2', new_line)
            new_line = _protect_model_numbers(new_line)
        elif sentence_only_mode and not has_changes:
            new_line = original
        
        if not sentence_only_mode and (new_line != original or has_changes):
            change_type = "format"
            if '。' in new_line[-2:] and original[-1] not in '。.!！？?':
                change_type = "punctuation"
            elif terminology and term_dict:
                change_type = "terminology"
            elif style_rules:
                change_type = "style"
            
            if _should_show_basic_change(original, new_line, change_type):
                changes.append(PolishRuleMatch(
                    rule_name="基础规范化",
                    before=original[:80],
                    after=new_line[:80],
                    type=change_type
                ))
        
        if step_prefix and not new_line.startswith(step_prefix):
            new_line = step_prefix + new_line
        polished_lines.append(new_line)
    
    if db and (triggered_rule_ids or triggered_engine_keys):
        record_rule_triggers(db, triggered_rule_ids, triggered_engine_keys)

    return '\n'.join(polished_lines), changes


def _parse_table_sentence_templates(section: str) -> list[str]:
    """从 Markdown 表格中提取句式模板列的内容。
    
    优先提取"示例"列（包含真实句子），没有示例列时回退到"句式模板"列。
    """
    sentences = []
    table_blocks = re.findall(r'(\|[^\n]+\|\n\|[-:\s|]+\|\n(?:\|[^\n]+\|\n?)+)', section)
    for block in table_blocks:
        lines = [l for l in block.strip().split('\n') if l.strip()]
        if len(lines) < 2:
            continue
        header_row = [c.strip() for c in lines[0].strip('|').split('|')]
        # 优先查找"示例"列（包含真实例句，适合规则匹配）
        example_col_idx = None
        template_col_idx = None
        for i, h in enumerate(header_row):
            if any(kw in h for kw in ['示例', '例子']):
                example_col_idx = i
            if any(kw in h for kw in ['句式模板', '句式', '模板', '句型', '标准句式']):
                template_col_idx = i
        # 优先用示例列，回退到模板列，再回退到第二列
        col_idx = example_col_idx if example_col_idx is not None else template_col_idx
        if col_idx is None and len(header_row) >= 2:
            col_idx = 1
        if col_idx is None:
            continue
        for line in lines[2:]:
            cells = [c.strip() for c in line.strip('|').split('|')]
            if col_idx < len(cells):
                val = cells[col_idx].strip().strip('"\'""''').strip()
                # 去掉 Markdown 转义（\* \_ \- 等）
                val = re.sub(r'\\([*_\-])', r'\1', val)
                if val and not re.match(r'^\d+$', val) and val not in ('...', '....'):
                    sentences.append(val)
    return sentences


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
            
            # 同时解析 Markdown 表格中的句式模板
            table_sentences = _parse_table_sentence_templates(section)
            
            if not items and not table_sentences:
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

            elif any(kw in lower_header for kw in ['用户反馈修正', '推荐句式', '优先句式', '反馈句式']):
                preferred_sentences = []
                for item in items:
                    sentence = item.strip().strip('`').strip()
                    if sentence:
                        preferred_sentences.append(sentence)
                # 如果表格中也有句式模板，合并进来
                if table_sentences:
                    preferred_sentences.extend(table_sentences)
                if preferred_sentences:
                    rules.append({
                        "type": "preferred_sentences",
                        "name": header,
                        "sentences": preferred_sentences,
                        "fix": "优先采用用户确认过的句式"
                    })
            
            # 表格句式模板：从句式参考表中提取句型（跳过统计表）
            elif table_sentences and '统计' not in header:
                rules.append({
                    "type": "preferred_sentences",
                    "name": header,
                    "sentences": table_sentences,
                    "fix": "采用规范句式"
                })
    
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


def _three_tier_match(sentence: str, templates: list[str]) -> tuple:
    """
    三层匹配策略：L1 精确 → L2 模糊 → L3 语义。
    返回: (best_template, best_score, match_level)
    """
    normalized = _normalize_sentence_for_match(sentence)
    if not normalized:
        return None, 0.0, "NONE"

    # ===== L1: 精确匹配（含变体） =====
    variants = _generate_sentence_variants(sentence)
    for tmpl in templates:
        tmpl_normalized = _normalize_sentence_for_match(tmpl)
        if not tmpl_normalized:
            continue
        # 检查输入变体 → 模板
        for variant in variants:
            var_normalized = _normalize_sentence_for_match(variant)
            if var_normalized == tmpl_normalized:
                return tmpl, 1.0, "L1"
        # 检查输入变体 → 模板变体
        tmpl_variants = _generate_sentence_variants(tmpl)
        for tv in tmpl_variants:
            tv_normalized = _normalize_sentence_for_match(tv)
            for variant in variants:
                var_normalized = _normalize_sentence_for_match(variant)
                if var_normalized == tv_normalized:
                    return tmpl, 1.0, "L1"
    
    # ===== L2: 模糊匹配（bigram+LCS+结构+关键词 高阈值） =====
    best_tmpl = None
    best_score = 0.0
    for tmpl in templates:
        tmpl_normalized = _normalize_sentence_for_match(tmpl)
        if not tmpl_normalized:
            continue
        contains_match = (
            normalized in tmpl_normalized or
            tmpl_normalized in normalized
        )
        if contains_match:
            score = max(0.92, _sentence_similarity(sentence, tmpl))
        else:
            score = _sentence_similarity(sentence, tmpl)
        if score > best_score:
            best_score = score
            best_tmpl = tmpl
    
    if best_tmpl and best_score >= _POLISH_MATCH_CONFIG["l2_min_confidence"]:
        return best_tmpl, best_score, "L2"
    
    # ===== L3: 语义匹配（低阈值，仅做提示） =====
    l3_threshold = _POLISH_MATCH_CONFIG["l3_auto_confidence"]
    if best_tmpl and best_score >= l3_threshold:
        return best_tmpl, best_score, "L3"
    
    return best_tmpl, best_score, "NONE"


def replace_with_context(original: str, template: str) -> str:
    """将原文与模板逐块融合。

    前缀/后缀上下文保留，匹配块之间的内部间隙移除。
    """
    s = SequenceMatcher(None, original, template)
    opcodes = list(s.get_opcodes())
    # 标记内部 delete 为 replace：位于匹配块之间的原文多余内容应移除
    for idx, (op, i1, i2, j1, j2) in enumerate(opcodes):
        if op == 'delete':
            has_before = any(o[0] in ('equal', 'replace') for o in opcodes[:idx])
            has_after = any(o[0] in ('equal', 'replace') for o in opcodes[idx+1:])
            if has_before and has_after:
                opcodes[idx] = ('replace', i1, i2, j1, j2)
    chars = list(original)
    offset = 0
    for op, i1, i2, j1, j2 in opcodes:
        if op in ('equal', 'delete'):
            continue
        elif op == 'replace':
            chars[i1 + offset : i2 + offset] = list(template[j1:j2])
            offset += (j2 - j1) - (i2 - i1)
        elif op == 'insert':
            chars[i1 + offset : i1 + offset] = list(template[j1:j2])
            offset += j2 - j1
    return ''.join(chars)


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

        elif rule["type"] == "preferred_sentences":
            best_sentence, best_score, match_level = _three_tier_match(result, rule.get("sentences", []))
            if not best_sentence:
                continue
            
            l3_threshold = _POLISH_MATCH_CONFIG["l3_auto_confidence"]
            should_replace = (
                (match_level == "L1" and best_score >= _POLISH_MATCH_CONFIG["l1_confidence"]) or
                (match_level == "L2" and best_score >= _POLISH_MATCH_CONFIG["l2_min_confidence"]) or
                (match_level == "L3" and best_score >= l3_threshold)
            )
            
            if should_replace and result.strip() != best_sentence.strip():
                original = result
                result = replace_with_context(original, best_sentence)
                changes.append(PolishRuleMatch(
                    rule_name=rule["name"],
                    before=original[:50],
                    after=result[:50],
                    type="style"
                ))
            elif should_replace and result.strip() == best_sentence.strip():
                # 完全匹配无变化，记录为空匹配
                pass
        
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
    
    # 约束润色：无匹配时进行术语标准化 + 去口语化
    if not changes or all(c.type != 'style' for c in changes):
        polished = _apply_constraint_polish(result)
        if polished != result:
            changes.append(PolishRuleMatch(
                rule_name="约束润色",
                before=result[:50],
                after=polished[:50],
                type="style"
            ))
            result = polished
    
    return result, changes


@router.post("/text")
async def polish_text_endpoint(input_data: TextPolishInput, db: Session = Depends(get_db)):
    """基础文本润色（自动加载句式清单和术语库）"""
    terminology_md = _load_terminology_source(db, input_data.terminology_id)
    sentence_guide = _load_sentence_guides(db, style_guide_id=input_data.style_guide_id)
    try:
        from app.utils.ai_client import ai_client
        resolved_terminology = _resolve_terminology(db, terminology_md, input_data.text)
        result = ai_client.polish_text(
            input_data.text,
            style_guide=sentence_guide,
            terminology=resolved_terminology if resolved_terminology else None
        )
        ai_polished = _protect_model_numbers(result.get("polished", input_data.text))
        changes = []
        if ai_polished != input_data.text:
            changes.append({
                "line": 1,
                "original": input_data.text[:200],
                "polished": ai_polished[:200],
                "type": "ai"
            })
        return {
            "original": result.get("original", input_data.text),
            "polished": ai_polished,
            "changes": changes
        }
    except Exception:
        return {
            "original": input_data.text,
            "polished": input_data.text,
            "changes": []
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
    terminology_md = _load_terminology_source(db, input_data.terminology_id)
    ai_polished = input_data.text
    ai_changes = []
    try:
        from app.utils.ai_client import ai_client
        resolved_terminology = _resolve_terminology(db, terminology_md, input_data.text)
        ai_result = ai_client.polish_text(input_data.text, style_guide=sentence_guide, terminology=resolved_terminology if resolved_terminology else None)
        if ai_result and ai_result.get("polished"):
            ai_polished = _protect_model_numbers(ai_result["polished"])
            if ai_polished != input_data.text:
                ai_changes = [{
                    "rule_name": "ai",
                    "before": input_data.text[:50],
                    "after": ai_polished[:50],
                    "type": "ai"
                }]
    except Exception:
        pass
    
    return {
        "original": input_data.text,
        "polished": ai_polished,
        "changes": ai_changes,
        "skill_name": "技术文档智能润色",
        "rules_applied": skill_rules.get("rules", {})
    }



# ============================================================
# DOCX 润色与批注注入
# ============================================================

def _xml_local_name(element) -> str:
    tag = getattr(element, 'tag', '')
    if not tag:
        return ''
    return tag.split('}')[-1] if '}' in tag else tag


def _read_docx_document_root(docx_path: str):
    import zipfile
    from lxml import etree

    with zipfile.ZipFile(docx_path, 'r') as zin:
        document_xml = zin.read('word/document.xml')
    return etree.fromstring(document_xml)


def _is_simple_revision_paragraph(p_element, w_ns: str) -> bool:
    """判断段落是否为纯文本段落，可安全写入修订标记。
    仅允许单 run 段落，每个 run 必须仅包含 rPr + 单个 t。
    多 run / 复杂格式段落跳过修订写回，避免 Word 中出现原文误删。"""
    allowed_children = {'pPr', 'r'}
    allowed_run_children = {'rPr', 't'}

    run_count = 0
    for child in list(p_element):
        child_name = _xml_local_name(child)
        if child_name not in allowed_children:
            return False
        if child_name == 'r':
            run_count += 1
            text_child_count = 0
            for run_child in list(child):
                run_child_name = _xml_local_name(run_child)
                if run_child_name not in allowed_run_children:
                    return False
                if run_child_name == 't':
                    text_child_count += 1
            if text_child_count != 1:
                return False

    return run_count == 1


def _extract_run_visible_text(run_element, w_ns: str) -> str:
    parts = []
    for child in list(run_element):
        child_name = _xml_local_name(child)
        if child_name in {'t', 'delText'}:
            parts.append(child.text or '')
        elif child_name == 'tab':
            parts.append('\t')
        elif child_name in {'br', 'cr'}:
            parts.append('\n')
    return ''.join(parts)


def _split_text_by_run_lengths(text: str, run_lengths: list[int]) -> list[str]:
    if not run_lengths:
        return [text]
    if len(run_lengths) == 1:
        return [text]

    total = sum(max(length, 0) for length in run_lengths)
    if total <= 0:
        return [text] + [''] * (len(run_lengths) - 1)

    chunks = []
    consumed = 0
    cumulative = 0
    text_length = len(text)
    for index, run_length in enumerate(run_lengths):
        if index == len(run_lengths) - 1:
            chunks.append(text[consumed:])
            break
        cumulative += max(run_length, 0)
        next_consumed = round(text_length * cumulative / total)
        chunks.append(text[consumed:next_consumed])
        consumed = next_consumed
    return chunks


def _strip_revision_display_props(rpr_element, w_ns: str):
    if rpr_element is None:
        return
    for child in list(rpr_element):
        if _xml_local_name(child) in {'color', 'highlight', 'shd'}:
            rpr_element.remove(child)


def _apply_paragraph_revision_xml(p_element, polished_text: str, author: str, now: str, rid_del: str, rid_ins: str, w_ns: str):
    from copy import deepcopy
    from lxml import etree

    children = list(p_element)
    run_indexes = [index for index, child in enumerate(children) if _xml_local_name(child) == 'r']
    if not run_indexes:
        return False

    first_run = children[run_indexes[0]]
    is_single_run = len(run_indexes) == 1

    # ── <w:del>: 保留所有原始 run 的完整格式 ──
    del_element = etree.Element(f'{{{w_ns}}}del')
    del_element.set(f'{{{w_ns}}}id', rid_del)
    del_element.set(f'{{{w_ns}}}author', author)
    del_element.set(f'{{{w_ns}}}date', now)

    for run_index in run_indexes:
        cloned_run = deepcopy(children[run_index])
        for text_element in cloned_run.findall(f'.//{{{w_ns}}}t'):
            text_element.tag = f'{{{w_ns}}}delText'
        del_element.append(cloned_run)

    # ── <w:ins>: 单 run 切分文本，多 run 仅写一个干净 run ──
    ins_element = etree.Element(f'{{{w_ns}}}ins')
    ins_element.set(f'{{{w_ns}}}id', rid_ins)
    ins_element.set(f'{{{w_ns}}}author', author)
    ins_element.set(f'{{{w_ns}}}date', now)

    if is_single_run:
        original_runs = [children[index] for index in run_indexes]
        run_lengths = [len(_extract_run_visible_text(run, w_ns)) for run in original_runs]
        text_chunks = _split_text_by_run_lengths(polished_text, run_lengths)

        appended = False
        for run_element, text_chunk in zip(original_runs, text_chunks):
            if not text_chunk and appended:
                continue
            inserted_run = etree.Element(f'{{{w_ns}}}r')
            first_rpr = run_element.find(f'{{{w_ns}}}rPr')
            if first_rpr is not None:
                cloned_rpr = deepcopy(first_rpr)
                _strip_revision_display_props(cloned_rpr, w_ns)
                inserted_run.append(cloned_rpr)
            text_element = etree.SubElement(inserted_run, f'{{{w_ns}}}t')
            if text_chunk[:1].isspace() or text_chunk[-1:].isspace():
                text_element.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            text_element.text = text_chunk or ''
            ins_element.append(inserted_run)
            appended = True

        if not appended:
            inserted_run = etree.Element(f'{{{w_ns}}}r')
            first_rpr = first_run.find(f'{{{w_ns}}}rPr')
            if first_rpr is not None:
                cloned_rpr = deepcopy(first_rpr)
                _strip_revision_display_props(cloned_rpr, w_ns)
                inserted_run.append(cloned_rpr)
            text_element = etree.SubElement(inserted_run, f'{{{w_ns}}}t')
            text_element.text = polished_text
            ins_element.append(inserted_run)
    else:
        # 多 run 段落：仅插入一个干净 run，不再切分文本以避免格式漂移
        inserted_run = etree.Element(f'{{{w_ns}}}r')
        first_rpr = first_run.find(f'{{{w_ns}}}rPr')
        if first_rpr is not None:
            cloned_rpr = deepcopy(first_rpr)
            _strip_revision_display_props(cloned_rpr, w_ns)
            inserted_run.append(cloned_rpr)
        text_element = etree.SubElement(inserted_run, f'{{{w_ns}}}t')
        if polished_text[:1].isspace() or polished_text[-1:].isspace():
            text_element.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        text_element.text = polished_text
        ins_element.append(inserted_run)

    # ── 重建段落子元素 ──
    first_run_index = run_indexes[0]
    last_run_index = run_indexes[-1]
    new_children = []
    for index, child in enumerate(children):
        if index == first_run_index:
            new_children.append(del_element)
            new_children.append(ins_element)
        if first_run_index <= index <= last_run_index and _xml_local_name(child) == 'r':
            continue
        new_children.append(child)

    for child in list(p_element):
        p_element.remove(child)
    for child in new_children:
        p_element.append(child)
    return True

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
    from lxml import etree
    
    all_changes = []
    w_ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    
    doc = Document(docx_path)
    document_root = _read_docx_document_root(docx_path)
    xml_paragraphs = document_root.findall(f'.//{{{w_ns}}}body/{{{w_ns}}}p')
    
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
    rejected_change_keys = _load_rejected_doc_change_keys(db)
    
    toc_prefixes = ("TOC", "Table of Contents", "目录")
    
    non_empty_paras = [(idx, para) for idx, para in enumerate(doc.paragraphs) 
                       if para.text and para.text.strip()]
    non_empty_ai_lines = [l.strip() for l in ai_lines if l.strip()] if ai_lines else []
    if non_empty_ai_lines and len(non_empty_ai_lines) != len(non_empty_paras):
        # 行数不一致时无法可靠映射到 Word 段落，避免标题/图注错位被覆盖。
        non_empty_ai_lines = []
    
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
        if (not is_title) and i < len(non_empty_ai_lines):
            ai_line = non_empty_ai_lines[i]
            if ai_line and ai_line != original_text:
                intermediate_text = ai_line
                para_ai_change = PolishRuleMatch(
                    rule_name="ai", before=original_text[:100], after=intermediate_text[:100], type="ai"
                )
        
        # Step 2: Rule polish + 术语替换
        polished_text, rule_changes = _apply_skill_polish(
            intermediate_text, skill_rules, db, sentence_guide, terminology, requirements,
            is_title=is_title, db_terminology=db_terminology
        )
        para_changes = ([para_ai_change] if para_ai_change else []) + rule_changes
        
        # 最终术语替换（无论 AI 是否已改，确保术语库强制生效）
        term_changes = []
        if term_dict:
            polished_text, term_changes = _apply_term_only(polished_text, term_dict)
            if term_changes:
                para_changes.extend(term_changes)

        if polished_text != original_text and (para_changes or polished_text.strip() != original_text.strip()):
            primary_change = next((change for change in para_changes if change.type != 'ai'), para_changes[0] if para_changes else None)
            primary_type = primary_change.type if primary_change else ('terminology' if term_changes else 'format')
            primary_rule = primary_change.rule_name if primary_change else 'Word修订标记'
            if _is_low_value_doc_change(original_text, polished_text, primary_type, primary_rule):
                continue
            if _is_rejected_doc_change(original_text, polished_text, rejected_change_keys):
                continue

            if para_idx >= len(xml_paragraphs):
                continue

            p_element = xml_paragraphs[para_idx]
            if not _is_simple_revision_paragraph(p_element, w_ns):
                continue

            revision_id += 1
            rid_del = str(revision_id)
            now = '2026-06-18T00:00:00Z'
            revision_id += 1
            rid_ins = str(revision_id)
            if _apply_paragraph_revision_xml(p_element, polished_text, author, now, rid_del, rid_ins, w_ns):
                all_changes.append(PolishRuleMatch(
                    rule_name=primary_rule,
                    before=original_text,
                    after=polished_text,
                    type=primary_type,
                    paragraph=para_idx + 1,
                ))
    
    document_xml = etree.tostring(document_root, xml_declaration=True, encoding='UTF-8')
    _write_revised_docx(docx_path, output_path, document_xml)
    
    return all_changes


def _write_revised_docx(source_docx_path: str, output_docx_path: str, document_xml: bytes):
    """基于原始 DOCX 仅替换 document.xml 与 settings.xml，保留 Word 原始排版结构。"""
    import zipfile
    import os as os_mod
    from lxml import etree
    
    w_ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    temp_path = output_docx_path + '.tmp'
    
    try:
        with zipfile.ZipFile(source_docx_path, 'r') as zin, \
             zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            settings_found = False
            
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == 'word/document.xml':
                    data = document_xml
                elif item.filename == 'word/settings.xml':
                    settings_found = True
                    root = etree.fromstring(data)
                    existing = root.findall(f'{{{w_ns}}}trackRevisions')
                    if not existing:
                        etree.SubElement(root, f'{{{w_ns}}}trackRevisions')
                    revision_view = root.find(f'{{{w_ns}}}revisionView')
                    if revision_view is None:
                        revision_view = etree.SubElement(root, f'{{{w_ns}}}revisionView')
                    revision_view.set(f'{{{w_ns}}}markup', '1')
                    revision_view.set(f'{{{w_ns}}}comments', '0')
                    revision_view.set(f'{{{w_ns}}}insDel', '1')
                    revision_view.set(f'{{{w_ns}}}formatting', '1')
                    data = etree.tostring(root, xml_declaration=True, encoding='UTF-8')
                
                zout.writestr(item, data)
            
            if not settings_found:
                root = etree.Element(f'{{{w_ns}}}settings')
                etree.SubElement(root, f'{{{w_ns}}}trackRevisions')
                revision_view = etree.SubElement(root, f'{{{w_ns}}}revisionView')
                revision_view.set(f'{{{w_ns}}}markup', '1')
                revision_view.set(f'{{{w_ns}}}comments', '0')
                revision_view.set(f'{{{w_ns}}}insDel', '1')
                revision_view.set(f'{{{w_ns}}}formatting', '1')
                data = etree.tostring(root, xml_declaration=True, encoding='UTF-8')
                zi = zipfile.ZipInfo('word/settings.xml')
                zout.writestr(zi, data)
        
        os_mod.replace(temp_path, output_docx_path)
    finally:
        if os_mod.path.exists(temp_path):
            os_mod.remove(temp_path)


def _revision_element_text(element, w_ns: str, text_tags: set[str]) -> str:
    parts = []
    for node in element.iter():
        if _xml_local_name(node) in text_tags:
            parts.append(node.text or '')
    return ''.join(parts)


def _restore_deleted_runs(del_element, w_ns: str):
    from copy import deepcopy

    restored = []
    for run in del_element.findall(f'{{{w_ns}}}r'):
        cloned = deepcopy(run)
        for text_element in cloned.findall(f'.//{{{w_ns}}}delText'):
            text_element.tag = f'{{{w_ns}}}t'
        restored.append(cloned)
    return restored


def _replace_revision_insert_text(ins_element, text: str, w_ns: str):
    text_nodes = [node for node in ins_element.iter() if _xml_local_name(node) == 't']
    if text_nodes:
        text_nodes[0].text = text
        if text[:1].isspace() or text[-1:].isspace():
            text_nodes[0].set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        for node in text_nodes[1:]:
            node.text = ''


def _accepted_revision_runs(ins_element, text: str, w_ns: str):
    from copy import deepcopy
    from lxml import etree

    runs = ins_element.findall(f'{{{w_ns}}}r')
    if runs:
        cloned = deepcopy(runs[0])
        for node in list(cloned):
            if _xml_local_name(node) in {'delText'}:
                cloned.remove(node)
        text_nodes = [node for node in cloned.iter() if _xml_local_name(node) == 't']
        if text_nodes:
            text_nodes[0].text = text
            if text[:1].isspace() or text[-1:].isspace():
                text_nodes[0].set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            for node in text_nodes[1:]:
                node.text = ''
        else:
            text_element = etree.SubElement(cloned, f'{{{w_ns}}}t')
            text_element.text = text
        return [cloned]

    run = etree.Element(f'{{{w_ns}}}r')
    text_element = etree.SubElement(run, f'{{{w_ns}}}t')
    if text[:1].isspace() or text[-1:].isspace():
        text_element.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    text_element.text = text
    return [run]


def _paragraph_revision_text(paragraph, w_ns: str) -> str:
    parts = []
    for node in paragraph.iter():
        if _xml_local_name(node) in {'t', 'delText'}:
            parts.append(node.text or '')
    return ''.join(parts)


def _paragraph_visible_text(paragraph, w_ns: str) -> str:
    parts = []
    for node in paragraph.iter():
        if _xml_local_name(node) == 't':
            parts.append(node.text or '')
    return ''.join(parts)


def _replace_paragraph_text_xml(paragraph, text: str, w_ns: str):
    from copy import deepcopy
    from lxml import etree

    ppr = None
    for child in list(paragraph):
        if _xml_local_name(child) == 'pPr':
            ppr = deepcopy(child)
            break

    for child in list(paragraph):
        paragraph.remove(child)
    if ppr is not None:
        paragraph.append(ppr)

    run = etree.SubElement(paragraph, f'{{{w_ns}}}r')
    text_element = etree.SubElement(run, f'{{{w_ns}}}t')
    if text[:1].isspace() or text[-1:].isspace():
        text_element.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    text_element.text = text


def _target_paragraph_by_index(root, paragraph_index: Optional[int], w_ns: str):
    if not paragraph_index or paragraph_index < 1:
        return None
    paragraphs = root.findall(f'.//{{{w_ns}}}body/{{{w_ns}}}p')
    index = paragraph_index - 1
    if index < 0 or index >= len(paragraphs):
        return None
    return paragraphs[index]


def _text_matches_decision(candidate: str, expected: str) -> bool:
    candidate_key = _normalize_compare_text(candidate)
    expected_key = _normalize_compare_text(expected)
    if not candidate_key or not expected_key:
        return False
    return (
        candidate_key == expected_key or
        candidate_key.startswith(expected_key) or
        expected_key.startswith(candidate_key)
    )


def _force_apply_feedback_to_document_xml(root, decisions: list[DocumentFeedbackItem], w_ns: str) -> list[dict]:
    """最终 XML 兜底：按段落文本强制落地接受/拒绝后的正文。"""
    applied = []
    for decision in decisions or []:
        before = (decision.before or '').strip()
        after = (decision.after or '').strip()
        status = (decision.status or '').strip()
        if not before or not after:
            continue
        if decision.accepted:
            match_text = before
            target_text = after
        elif status == 'rejected':
            match_text = after
            target_text = before
        else:
            continue

        target_paragraph = _target_paragraph_by_index(root, decision.paragraph, w_ns)
        if target_paragraph is not None:
            visible_text = _paragraph_visible_text(target_paragraph, w_ns)
            if _normalize_compare_text(visible_text) != _normalize_compare_text(target_text):
                _replace_paragraph_text_xml(target_paragraph, target_text, w_ns)
                applied.append({
                    'before': before,
                    'after': target_text,
                    'type': decision.type,
                    'rule_name': '用户确认',
                    'paragraph': decision.paragraph,
                })
            continue

        for paragraph in root.findall(f'.//{{{w_ns}}}p'):
            visible_text = _paragraph_visible_text(paragraph, w_ns)
            revision_text = _paragraph_revision_text(paragraph, w_ns)
            if _normalize_compare_text(visible_text) == _normalize_compare_text(target_text):
                break
            if _text_matches_decision(visible_text, match_text) or _text_matches_decision(revision_text, match_text):
                _replace_paragraph_text_xml(paragraph, target_text, w_ns)
                applied.append({
                    'before': before,
                    'after': target_text,
                    'type': decision.type,
                    'rule_name': '用户确认',
                    'paragraph': decision.paragraph,
                })
                break
    return applied


def _apply_feedback_plaintext_fallback(docx_path: str, decisions: list[DocumentFeedbackItem], already_applied: list[dict]) -> list[dict]:
    """兜底写回：按段落文本确认接受/拒绝决策已经落到正文。"""
    if not docx_path or not os.path.exists(docx_path):
        return []

    from docx import Document

    pending = []
    for decision in decisions or []:
        before = (decision.before or '').strip()
        after = (decision.after or '').strip()
        if not before or not after:
            continue
        pending.append(decision)

    if not pending:
        return []

    doc = Document(docx_path)
    fallback_applied = []
    changed = False
    for decision in pending:
        before = (decision.before or '').strip()
        after = (decision.after or '').strip()
        status = (decision.status or '').strip()
        if decision.accepted:
            target_text = after
            match_text = before
        elif status == 'rejected':
            target_text = before
            match_text = after
        else:
            continue

        for paragraph in doc.paragraphs:
            if _normalize_compare_text(paragraph.text) == _normalize_compare_text(target_text):
                break
            if _text_matches_decision(paragraph.text, match_text):
                paragraph.text = target_text
                fallback_applied.append({
                    'before': before,
                    'after': target_text,
                    'type': decision.type,
                    'rule_name': '用户确认',
                })
                changed = True
                break

    if changed:
        doc.save(docx_path)
    return fallback_applied


def _apply_feedback_to_revised_docx(source_docx_path: str, output_docx_path: str, decisions: list[DocumentFeedbackItem]) -> list[dict]:
    """按用户接受/拒绝/自定义决策重写修订版 DOCX。"""
    from lxml import etree

    if not source_docx_path or not output_docx_path or not os.path.exists(source_docx_path):
        return []

    w_ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    root = _read_docx_document_root(source_docx_path)
    decisions_by_before = {}
    for item in decisions or []:
        before_key = _normalize_compare_text(item.before)
        if not before_key:
            continue
        decisions_by_before.setdefault(before_key, []).append(item)

    def _pop_decision(before_text: str):
        before_key = _normalize_compare_text(before_text)
        candidates = decisions_by_before.get(before_key)
        if candidates:
            return candidates.pop(0)
        for decision_key, decision_items in decisions_by_before.items():
            if not decision_items:
                continue
            if before_key.startswith(decision_key) or decision_key.startswith(before_key):
                return decision_items.pop(0)
        return None

    applied = []
    for paragraph in root.findall(f'.//{{{w_ns}}}p'):
        children = list(paragraph)
        new_children = []
        index = 0
        paragraph_replaced = False
        while index < len(children):
            current = children[index]
            next_child = children[index + 1] if index + 1 < len(children) else None
            if _xml_local_name(current) == 'del' and next_child is not None and _xml_local_name(next_child) == 'ins':
                before = _revision_element_text(current, w_ns, {'delText'})
                original_after = _revision_element_text(next_child, w_ns, {'t'})
                decision = _pop_decision(before)
                decision_status = (decision.status or '').strip() if decision else ''
                if decision and decision.accepted and (decision.after or '').strip():
                    after = (decision.after or '').strip()
                    _replace_paragraph_text_xml(paragraph, after, w_ns)
                    paragraph_replaced = True
                    applied.append({
                        'before': before,
                        'after': after or original_after,
                        'type': decision.type,
                        'rule_name': '用户确认',
                        'paragraph': decision.paragraph,
                    })
                    break
                elif decision_status == 'rejected':
                    new_children.extend(_restore_deleted_runs(current, w_ns))
                else:
                    new_children.append(current)
                    new_children.append(next_child)
                index += 2
                continue
            new_children.append(current)
            index += 1

        if paragraph_replaced:
            continue

        if len(new_children) != len(children):
            for child in list(paragraph):
                paragraph.remove(child)
            for child in new_children:
                paragraph.append(child)

    applied.extend(_force_apply_feedback_to_document_xml(root, decisions, w_ns))
    document_xml = etree.tostring(root, xml_declaration=True, encoding='UTF-8')
    _write_revised_docx(source_docx_path, output_docx_path, document_xml)
    applied.extend(_apply_feedback_plaintext_fallback(output_docx_path, decisions, applied))
    return applied




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
                    "summary": "AI 完成润色"
                }]
        except Exception as e:
            print(f"AI 润色失败(返回原文): {e}")

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
            import shutil
            shutil.copy2(saved_file_path, f"{saved_file_path}.all-revisions.docx")
            
            from docx import Document
            polished_doc = Document(saved_file_path)
            # 从修订标记版 DOCX 读取润色后文本（<w:delText> 被忽略，仅读 <w:t> 即插入文本）
            preview_text = '\n'.join([p.text for p in polished_doc.paragraphs])
            polished_text = preview_text
            rejected_change_keys = _load_rejected_doc_change_keys(db)
            display_changes = _filter_visible_doc_changes(changes, rejected_change_keys)
            if not display_changes:
                display_changes = _build_doc_change_details(content, polished_text, changes, rejected_change_keys)
            
            _update_progress(80, "生成润色报告...")
            report_filename = f"【润色报告】{filename.rsplit('.', 1)[0]}.docx"
            report_path = os.path.join(date_dir, report_filename)
            _generate_polish_report(
                report_path, filename, display_changes,
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
                "changes": display_changes,
                "report_file": report_filename,
                "download_filename": unique_filename,
                "file_type": "docx"
            }
            _finish_task(result_data)
            return result_data
        else:    
            _update_progress(70, "整理润色结果...")
            polished_text = _protect_model_numbers(ai_polished)
            changes = []
            if ai_changes and polished_text != content:
                changes.append(PolishRuleMatch(
                    rule_name="ai",
                    before=content[:50],
                    after=polished_text[:50],
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
    """提交润色反馈：记录准确率评分，并将修正词写入选中的术语文件或句式文件。"""
    current_user = get_default_user(db)
    corrections_pairs = _parse_corrections(feedback.corrections)
    raw_lines = [line.strip() for line in (feedback.corrections or '').splitlines() if line.strip()]
    processed_count = 0
    errors = []

    if not raw_lines and feedback.accuracy >= 100:
        processed_count = 0

    elif feedback.target == "terminology":
        # 术语修正 → 固定写入平台反馈术语文件
        try:
            target_files = _get_platform_feedback_terminology_targets(db, current_user.id if current_user else 1)
            new_pairs = []
            for term_file in target_files:
                existing = ""
                if term_file.file_path and os.path.exists(term_file.file_path):
                    with open(term_file.file_path, 'r', encoding='utf-8') as f:
                        existing = f.read()

                file_new_pairs = []
                for old_term, new_term in corrections_pairs:
                    normalized_old = old_term.strip()
                    normalized_new = new_term.strip()
                    if (
                        f'| {normalized_old} | {normalized_new} |' in existing or
                        f'|{normalized_old}|{normalized_new}|' in existing
                    ):
                        continue
                    file_new_pairs.append((normalized_old, normalized_new))

                if not file_new_pairs:
                    term_file.file_size = os.path.getsize(term_file.file_path)
                    continue

                with open(term_file.file_path, 'a', encoding='utf-8') as f:
                    for old_term, new_term in file_new_pairs:
                        f.write(f'| {old_term} | {new_term} |\n')

                term_file.file_size = os.path.getsize(term_file.file_path)
                if not new_pairs:
                    new_pairs = file_new_pairs

            processed_count = len(new_pairs)
            db.commit()
        except Exception as e:
            errors.append(str(e))

    elif feedback.target == "sentence_guide":
        # 句式修正 → 固定写入平台反馈句式文件
        if not raw_lines:
            raise HTTPException(status_code=400, detail="请填写需修正的词语或句子")
        timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        try:
            target_files = _get_platform_feedback_targets(db, current_user.id if current_user else 1)
            feedback_file_id = target_files[0].id if target_files else None
            new_lines = []

            for guide_file in target_files:
                existing = ""
                if guide_file.file_path and os.path.exists(guide_file.file_path):
                    with open(guide_file.file_path, 'r', encoding='utf-8') as f:
                        existing = f.read()

                file_new_lines = []
                for line in raw_lines:
                    if f"- {line}\n" in existing:
                        continue
                    file_new_lines.append(line)

                if not file_new_lines:
                    guide_file.file_size = os.path.getsize(guide_file.file_path)
                    continue

                with open(guide_file.file_path, 'a', encoding='utf-8') as f:
                    f.write(f'\n## 用户反馈修正 ({timestamp})\n\n')
                    for line in file_new_lines:
                        f.write(f'- {line}\n')
                    f.write('\n')

                guide_file.file_size = os.path.getsize(guide_file.file_path)
                if not new_lines:
                    new_lines = file_new_lines

            processed_count = len(new_lines)
            db.commit()
            if feedback_file_id is not None:
                _invalidate_sentence_guide_cache(feedback_file_id)
        except Exception as e:
            errors.append(str(e))

    db.add(PolishFeedback(
        original_text=feedback.original_text,
        polished_text=feedback.polished_text,
        accuracy=feedback.accuracy,
        corrections=feedback.corrections,
        target=feedback.target,
        processed_count=processed_count,
        created_by=current_user.username if current_user else "guest"
    ))
    db.commit()

    return {
        "message": "反馈已提交",
        "accuracy": feedback.accuracy,
        "corrections_count": len(raw_lines) if feedback.target == "sentence_guide" else len(corrections_pairs),
        "processed_count": processed_count,
        "target": feedback.target,
        "errors": errors if errors else None
    }


@router.post("/feedback/document", response_model=None)
def submit_document_feedback(
    feedback: DocumentFeedbackInput,
    db: Session = Depends(get_db)
):
    """提交文档润色反馈，将接受项写入句式清单并同步修订版 Word。"""
    from sqlalchemy import func

    current_user = get_default_user(db)
    total_items = len(feedback.items or [])
    if total_items == 0:
        raise HTTPException(status_code=400, detail="当前没有可提交的润色结果")

    doc = get_polished_document(db, feedback.document_id) if feedback.document_id else None
    applied_changes = []
    if doc and doc.file_type == 'docx' and doc.file_path:
        import shutil

        source_revision_path = f"{doc.file_path}.all-revisions.docx"
        if not os.path.exists(source_revision_path) and os.path.exists(doc.file_path):
            shutil.copy2(doc.file_path, source_revision_path)
        applied_changes = _apply_feedback_to_revised_docx(source_revision_path, doc.file_path, feedback.items)
        doc.file_size = os.path.getsize(doc.file_path)
        doc.polished_content = '\n'.join(item['after'] for item in applied_changes)
        if doc.report_file_path:
            _generate_polish_report(
                doc.report_file_path,
                feedback.source_filename or doc.name or doc.filename,
                applied_changes,
            )

    accepted_items = [item for item in feedback.items if item.accepted and (item.after or '').strip()]
    rejected_items = [
        item for item in feedback.items
        if (item.status or '').strip() == 'rejected' and (item.before or '').strip() and (item.after or '').strip()
    ]
    accepted_lines = []
    seen_lines = set()
    for item in accepted_items:
        line = item.after.strip()
        if line in seen_lines:
            continue
        seen_lines.add(line)
        accepted_lines.append(line)

    processed_count = 0
    feedback_file_id = None
    if accepted_lines:
        target_files = _get_platform_feedback_targets(db, current_user.id if current_user else 1)
        feedback_file_id = target_files[0].id if target_files else None
        timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        source_name = (feedback.source_filename or '').strip() or f"文档{feedback.document_id or ''}".strip()
        new_lines = []
        for file in target_files:
            existing = ""
            if file.file_path and os.path.exists(file.file_path):
                with open(file.file_path, 'r', encoding='utf-8') as f:
                    existing = f.read()

            file_new_lines = []
            for line in accepted_lines:
                if f"- {line}\n" in existing:
                    continue
                file_new_lines.append(line)

            if not file_new_lines:
                file.file_size = os.path.getsize(file.file_path)
                continue

            with open(file.file_path, 'a', encoding='utf-8') as f:
                f.write(f"\n## 用户反馈修正 ({timestamp} / 来源：{source_name})\n\n")
                for line in file_new_lines:
                    f.write(f"- {line}\n")
                f.write("\n")

            file.file_size = os.path.getsize(file.file_path)
            if not new_lines:
                new_lines = file_new_lines

        processed_count = len(new_lines)
        db.commit()
        if feedback_file_id is not None:
            _invalidate_sentence_guide_cache(feedback_file_id)

    rejected_count = 0
    if rejected_items:
        existing_rejected = _load_rejected_doc_change_keys(db)
        for item in rejected_items:
            key = (_normalize_compare_text(item.before), _normalize_compare_text(item.after))
            if key in existing_rejected:
                continue
            db.add(PolishFeedback(
                original_text=item.before.strip(),
                polished_text=item.after.strip(),
                accuracy=0,
                corrections=item.type or '',
                target='document_rejected_change',
                processed_count=1,
                created_by=current_user.username if current_user else 'guest'
            ))
            existing_rejected.add(key)
            rejected_count += 1

    db.add(PolishFeedback(
        original_text=feedback.source_filename or '',
        polished_text='\n'.join(accepted_lines),
        accuracy=len(accepted_items),
        corrections='\n'.join(accepted_lines),
        target='document_sentence_guide',
        processed_count=total_items,
        created_by=current_user.username if current_user else 'guest'
    ))
    db.commit()

    total_docs = db.query(func.count(PolishFeedback.id)).filter(
        PolishFeedback.target == 'document_sentence_guide'
    ).scalar() or 0

    return {
        "message": "文档润色反馈已提交",
        "document_id": doc.id if doc else feedback.document_id,
        "raw_url": f"/api/polish/{doc.id}/raw" if doc else None,
        "processed_count": processed_count,
        "accepted_count": len(accepted_lines),
        "rejected_count": rejected_count,
        "applied_changes": applied_changes,
        "total_count": total_items,
        "feedback_file_id": feedback_file_id,
        "total_docs": total_docs
    }


@router.get("/feedback/stats", response_model=None)
def get_feedback_stats(db: Session = Depends(get_db)):
    """获取润色准确率统计：总准确率总和 ÷ 总反馈次数。"""
    from sqlalchemy import func
    total = db.query(func.count(PolishFeedback.id)).scalar() or 0
    if total == 0:
        return {"total_count": 0, "average_accuracy": 0}
    accuracy_sum = db.query(func.sum(PolishFeedback.accuracy)).scalar() or 0
    return {
        "total_count": total,
        "average_accuracy": round(accuracy_sum / total, 1)
    }


@router.get("/feedback/document-stats", response_model=None)
def get_document_feedback_stats(db: Session = Depends(get_db)):
    """获取文档润色页统计。准确率 = 每次润色(修改条数 / 总润色条数)的平均值。"""
    records = db.query(PolishFeedback).filter(
        PolishFeedback.target == 'document_sentence_guide'
    ).all()

    total_docs = len(records)
    if total_docs == 0:
        return {"total_docs": 0, "average_accuracy": 0}

    ratios = []
    for record in records:
        total_changes = record.processed_count or 0
        if total_changes <= 0:
            ratios.append(0)
            continue
        ratios.append((record.accuracy or 0) / total_changes)

    average_accuracy = round((sum(ratios) / total_docs) * 100, 1)
    return {"total_docs": total_docs, "average_accuracy": average_accuracy}


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
        terminology = _resolve_terminology(db, text=document.content or "")
        result = ai_client.polish_text(document.content or "", terminology=terminology if terminology else None)
        polished = _protect_model_numbers(result.get("polished", document.content or ""))
        changes = []
        if polished != (document.content or ""):
            changes.append({"line": 1, "original": (document.content or "")[:80], "polished": polished[:80], "type": "ai"})
        return {
            "document_id": document_id,
            "original": result.get("original", document.content or ""),
            "polished": polished,
            "changes": changes
        }
    except Exception:
        return {
            "document_id": document_id,
            "original": document.content or "",
            "polished": document.content or "",
            "changes": []
        }


def _polish_fallback(text: str, db_terminology: dict = None):
    polished, changes = _apply_skill_polish(text, {}, None, None, None, None, db_terminology=db_terminology)
    return {
        "original": text,
        "polished": polished,
        "changes": changes
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


class BatchDeleteRequest(BaseModel):
    ids: list[int]


@router.delete("/batch")
async def batch_delete_polished_documents(
    payload: BatchDeleteRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user = get_default_user(db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可删除文件")
    
    deleted = 0
    for doc_id in payload.ids:
        doc = get_polished_document(db, doc_id)
        if not doc:
            continue
        if os.path.exists(doc.file_path):
            os.remove(doc.file_path)
        if doc.report_file_path and os.path.exists(doc.report_file_path):
            os.remove(doc.report_file_path)
        delete_polished_document(db, doc_id)
        deleted += 1
    
    return {"message": f"已删除 {deleted} 个文件", "deleted_count": deleted}


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
