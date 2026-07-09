#!/usr/bin/env python3
"""
说明书问答测试数据生成脚本 v2
- 基于 PDF 提取实体词 + 模板批量生成问题（无需 Kimi，绕过限流）
- 逐条执行检索+AI回答，记录 search_hit
"""
import sys, os, json, time, uuid, random
from typing import List
os.environ.setdefault('DATABASE_URL', f'sqlite:////workspace/backend/app.db')
sys.path.insert(0, '/workspace/backend')

import fitz
import jieba
import jieba.posseg as pseg
import re
from collections import Counter
from app.database import SessionLocal, create_tables
from app.models.qa_history import QaSession, QaMessage

create_tables()
from app.api.manual_search import (
    _extract_pdf_pages, _build_context,
    _call_ai_with_citations, _split_pages_to_chunks, UPLOAD_SESSIONS
)

# ─── 配置 ───
PDF_PATHS = [
    ('中文说明书', '/workspace/backend/app/static/manual_uploads/59183f587b86.pdf'),
    ('越南说明书', '/workspace/backend/app/static/manual_uploads/2e39b1001325.pdf'),
    ('测试手册', '/workspace/backend/seed/knowledge/资源库/文件资料/测试用说明书.pdf'),
]
TARGET = 400           # 目标问题数
HIT_RATIO = 0.75       # 正样本比例
ASK_INTERVAL = 0.1     # 问题间隔秒
USER_ID = 1
db = SessionLocal()

# ─── 步骤1: 提取 PDF 并抽取实体 ───
print("=" * 60, flush=True)
print("[1/3] 提取 PDF 并抽取关键词实体", flush=True)

all_documents = []
all_text = ""
for doc_title, path in PDF_PATHS:
    if not os.path.exists(path):
        continue
    pages = _extract_pdf_pages(path)
    if not pages:
        continue
    total_chars = sum(len(p.get('text','')) for p in pages)
    all_documents.append({'title': doc_title, 'pages': pages, 'total_pages': len(pages), 'file_path': path})
    for p in pages:
        all_text += p.get('text', '') + "\n"
    print(f"  {doc_title}: {len(pages)}页, {total_chars}字符", flush=True)

# 提取中文词（2-8字）作为实体
def extract_entities(text):
    words = []
    for w, flag in pseg.cut(text):
        w = w.strip()
        # 只保留有意义的词：长度2-8，包含中文，有实义词性
        if not (2 <= len(w) <= 8):
            continue
        if flag not in ('n', 'v', 'a', 'l', 'nr', 'ns', 'nt', 'nz', 'vn', 'an', 'eng'):
            continue
        # 过滤纯数字/符号/英文字母
        if not re.search(r'[\u4e00-\u9fff]', w):
            continue
        # 过滤纯中文标点/助词
        if w in ('说明', '使用', '操作', '进行', '提供', '包括', '需要', '可以', '可能', '通过',
                 '按照', '根据', '以下', '以上', '相关', '具体', '一般', '其他', '不同', '如下',
                 '作为', '方面', '部分', '方式', '情况', '过程', '内容', '功能', '作用', '目的'):
            continue
        words.append(w)
    return Counter(words)

entities = extract_entities(all_text)
# 取频率最高的200个词
top_entities = [w for w, c in entities.most_common(200) if c >= 2 and len(w) >= 2]

# 提取章节标题（以数字编号开头或全大写的行）
headings = []
for line in all_text.split('\n'):
    line = line.strip()
    if re.match(r'^第[一二三四五六七八九十]|[0-9]+\.[0-9]*\s', line) or \
       (len(line) >= 4 and len(line) <= 30 and not re.search(r'[，。；：、\.\,\;\:\(\)（）]', line)):
        headings.append(line)
headings = list(set(headings))[:50]

# 提取参数型短语（包含数字+单位的组合）
params = re.findall(r'[\u4e00-\u9fff]{2,8}[:：]?\s*[0-9]+[\.]?[0-9]*[\s]*(V|W|A|℃|mm|cm|m|kg|g|L|mL|s|min|h|Hz|rpm|bar|Pa|%|×|x)', all_text)
params = [p.strip() for p in params if len(p) >= 3]

# 合并去重
all_terms = list(set(top_entities + headings + params))
print(f"  提取到 {len(all_terms)} 个关键词/实体", flush=True)

# 预分块缓存（避免每条问题都重新分块）
from app.api.qa import _score_chunk
print("  预分块...", flush=True, end=" ")
_chunk_cache = {}
for d in all_documents:
    chunks = _split_pages_to_chunks(d.get("pages", []))
    _chunk_cache[d['title']] = chunks
    print(f"[{d['title']}={len(chunks)}]", end=" ", flush=True)
print("\n")

# 优化版排名函数（使用缓存）
def _rank_cached(question: str, documents: List[dict], limit: int = 10) -> List[dict]:
    all_chunks = []
    for doc in documents:
        chunks = _chunk_cache.get(doc.get("title", ""), [])
        for ch in chunks:
            score = _score_chunk(question, ch["text"], doc.get("title", ""))
            all_chunks.append({
                "title": doc.get("title", "未知"),
                "chunk": ch["text"],
                "page_num": ch["page_num"],
                "score": score,
            })
    all_chunks.sort(key=lambda x: x["score"], reverse=True)
    return all_chunks[:limit]

# ─── 步骤2: 模板生成问题 ───
print("\n[2/3] 模板生成测试问题", flush=True)

# 正样本模板（文档内能找到答案的）
HIT_TEMPLATES = [
    "{term}是什么？",
    "什么是{term}？",
    "{term}的参数规格是多少？",
    "{term}的主要功能有哪些？",
    "如何操作{term}？",
    "{term}的操作步骤是什么？",
    "使用{term}时需要注意什么？",
    "{term}有哪些安全要求？",
    "{term}的维护周期是多久？",
    "如何清洁{term}？",
    "{term}的适用范围是什么？",
    "{term}对环境有什么要求？",
    "{term}的技术指标是多少？",
    "怎样安装{term}？",
    "{term}出现异常怎么处理？",
    "请说明{term}的工作原理",
    "{term}支持哪些模式？",
    "{term}的电源要求是什么？",
    "{term}需要什么耗材？",
    "怎么判断{term}是否正常工作？",
]

# 中等确定性模板（部分能在文档找到）
MIXED_TEMPLATES = [
    "{term}和其他型号有什么区别？",
    "{term}可以用于哪些实验？",
    "{term}出现警告怎么解决？",
    "{term}长时间不用怎么保存？",
    "更换{term}需要什么工具？",
    "{term}的保修期是多久？",
    "{term}对操作人员有什么资质要求？",
]

# 负样本关键词（文档中不存在的概念，用于测试未命中）
NEGATIVE_TERMS = [
    "WiFi模块", "蓝牙连接", "手机APP", "云端存储",
    "自动对焦", "语音控制", "远程升级", "面部识别",
    "虚拟助手", "智能推荐", "3D打印", "激光切割",
    "深度学习", "指纹解锁", "太阳能供电", "无线充电",
    "磁悬浮系统", "量子计算", "脑机接口", "纳米芯片",
    "生物传感器", "电动升降台", "水冷系统",
    "墨水屏", "触摸屏导航", "AI分析", "实时直播",
]

def generate_questions(terms, templates, count):
    qs = []
    for _ in range(count):
        term = random.choice(terms)
        tpl = random.choice(templates)
        q = tpl.replace("{term}", term)
        qs.append(q)
    return qs

# 多实体模板（需要2个实体）
DUAL_TEMPLATES = [
    "在配置{term1}时，{term2}需要怎么设置？",
    "{term1}和{term2}之间有什么关联？",
    "{term1}对{term2}有什么影响？",
]

def generate_dual_questions(terms, templates, count):
    qs = []
    for _ in range(count):
        t1, t2 = random.sample(terms, 2)
        tpl = random.choice(templates)
        q = tpl.replace("{term1}", t1).replace("{term2}", t2)
        qs.append(q)
    return qs

# 参数型问题
PARAM_TEMPLATES = [
    "{param}参数的合理范围是多少？",
    "如何调节{param}？",
    "如果{param}超出范围会怎样？",
]

def generate_param_questions(params_list, templates, count):
    if not params_list:
        return []
    qs = []
    for _ in range(count):
        p = random.choice(params_list)
        tpl = random.choice(templates)
        q = tpl.replace("{param}", p[:12])
        qs.append(q)
    return qs

# 生成各类问题
hit_count = int(TARGET * HIT_RATIO)
miss_count = TARGET - hit_count

hit_questions = generate_questions(all_terms, HIT_TEMPLATES, int(hit_count * 0.6))
hit_questions += generate_dual_questions(all_terms, DUAL_TEMPLATES, int(hit_count * 0.25))
hit_questions += generate_param_questions(params[:50] if params else all_terms[:50],
                                           PARAM_TEMPLATES, int(hit_count * 0.15))
miss_questions = generate_questions(NEGATIVE_TERMS, HIT_TEMPLATES + MIXED_TEMPLATES, miss_count)

all_questions = hit_questions + miss_questions
random.shuffle(all_questions)
all_questions = list(set(all_questions))
random.shuffle(all_questions)
all_questions = all_questions[:TARGET]

# 记录每条问题的预期命中状态（用于统计）
_expected_miss_set = set(miss_questions)
questions_with_labels = []
for q in all_questions:
    expected_hit = 0 if q in _expected_miss_set else 1
    questions_with_labels.append((q, expected_hit))

print(f"  正样本（预计命中）: {hit_count}")
print(f"  负样本（预计未命中）: {miss_count}")
print(f"  去重后总数: {len(all_questions)}\n")

# 展示前5条样例
print("  样例问题：")
for q in all_questions[:5]:
    print(f"    - {q}")
print()

# ─── 步骤3: 设置会话并批量执行 ───
print("[3/3] 批量执行问答检索", flush=True)

# 命中阈值：top chunk score >= 0.5 视为命中
SCORE_THRESHOLD = 0.5

# 构造会话数据
file_id = uuid.uuid4().hex[:12]
file_key = USER_ID
if file_key not in UPLOAD_SESSIONS:
    UPLOAD_SESSIONS[file_key] = {}
UPLOAD_SESSIONS[file_key][file_id] = {
    'file_id': file_id, 'filename': '说明书合集.pdf',
    'title': all_documents[0]['title'], 'pages': all_documents[0]['pages'],
    'total_pages': all_documents[0]['total_pages'],
    'file_path': all_documents[0].get('file_path', ''), 'file_size': 0,
}

session_title = f"{all_documents[0]['title']}等{len(all_documents)}份说明书"[:80]
sess = QaSession(user_id=USER_ID, session_type='manual', title=session_title)
db.add(sess)
db.commit()
db.refresh(sess)

session_docs = []
for d in all_documents:
    session_docs.append({'title': d['title'], 'pages': d['pages'], 'file_path': d.get('file_path','')})

session_data = {
    'session_id': sess.id, 'title': session_title,
    'titles': [d['title'] for d in all_documents],
    'documents': session_docs,
    'total_pages': sum(d['total_pages'] for d in all_documents),
    'total_chars': sum(sum(len(p['text']) for p in d['pages']) for d in all_documents),
}
if 'sessions' not in UPLOAD_SESSIONS:
    UPLOAD_SESSIONS['sessions'] = {}
UPLOAD_SESSIONS['sessions'][str(sess.id)] = session_data

print(f"  会话 ID: {sess.id}", flush=True)
print(f"  开始处理 {len(questions_with_labels)} 条问题...\n", flush=True)

stats = {'hit': 0, 'miss': 0, 'error': 0}
for qi, (question, expected_hit) in enumerate(questions_with_labels):
    try:
        ranked = _rank_cached(question, session_docs, limit=10)
        context = _build_context(ranked, max_chars=10000)
        titles_list = [d['title'] for d in all_documents]
        result = _call_ai_with_citations(question, context, titles_list)

        relevance_score = round(ranked[0]['score'], 4) if ranked else 0.0
        search_hit = 1 if relevance_score >= SCORE_THRESHOLD else 0

        if search_hit:
            stats['hit'] += 1
        else:
            stats['miss'] += 1

        source_for_db = []
        seen = set()
        for s in ranked[:4]:
            key = f"{s['title']}_{s['page_num']}"
            if key not in seen:
                seen.add(key)
                source_for_db.append({'title': s['title'], 'page': s['page_num']})

        sess.updated_at = __import__('datetime').datetime.utcnow()
        db.add(QaMessage(session_id=sess.id, role='user', content=question))
        db.add(QaMessage(
            session_id=sess.id, role='assistant',
            content=result.get('answer', ''),
            sources=json.dumps(source_for_db, ensure_ascii=False),
            search_hit=search_hit, relevance_score=relevance_score,
        ))
        db.commit()

        processed = qi + 1
        if processed % 50 == 0 or processed == len(questions_with_labels):
            total = stats['hit'] + stats['miss']
            rate = round(stats['hit'] / max(total, 1) * 100, 1)
            print(f"  [{processed}/{len(questions_with_labels)}] 命中率: {rate}% (命中{stats['hit']}/未命中{stats['miss']})", flush=True)

        time.sleep(ASK_INTERVAL)
    except Exception as e:
        stats['error'] += 1
        if (qi + 1) % 20 == 0:
            print(f"  [{qi+1}] ERR: {str(e)[:60]}", flush=True)

# ─── 输出报告 ───
print("\n" + "=" * 60, flush=True)
print("统计报告", flush=True)
print(f"  生成问题:     {len(questions_with_labels)}", flush=True)
print(f"  检索命中:     {stats['hit']}", flush=True)
print(f"  检索未命中:   {stats['miss']}", flush=True)
print(f"  处理异常:     {stats['error']}", flush=True)
total_ok = stats['hit'] + stats['miss']
if total_ok > 0:
    print(f"  命中率:       {round(stats['hit']/total_ok*100,1)}%", flush=True)
print(f"  会话 ID:      {sess.id}", flush=True)
db.close()
