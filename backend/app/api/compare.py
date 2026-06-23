from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
import os
import json
import time
import xml.etree.ElementTree as ET
from app.database import get_db

router = APIRouter()

UPLOAD_DIR = "./static/uploads"

_MEMORY_TASKS = {}
_MEMORY_DIFFS = {}
_MEMORY_NEXT_ID = [1000]


def _ensure_upload_dir():
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR, exist_ok=True)


def _read_upload_as_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def _extract_pdf(path: str) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:
        try:
            from pypdf import PdfReader
            return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
        except Exception:
            return _read_upload_as_text(path)


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _extract_dita_text(dita_file_path):
    """
    提取 DITA 文件中的句段。
    规则：
    - 表格按行拆分（每行一个句段，合并所有单元格文本）
    - 列表按项拆分（每项一个句段）
    - 提取文本标签：p、li、entry、note、title、shortdesc、step、cmd 等
    - 过滤空句段和纯空格句段
    - 过滤纯 XML 标签内容（如 ph、b、i、u 等内联标签不单独成句段）
    """
    try:
        tree = ET.parse(dita_file_path)
        root = tree.getroot()
        topic_id = root.attrib.get("id", "")
        title_el = root.find(".//title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        
        segments = []
        if title:
            segments.append({"text": title, "tag": "title"})
        
        # 需要处理的文本标签
        block_tags = {"p", "li", "note", "step", "shortdesc", "cmd", "entry", 
                      "dt", "dd", "li", "stentry", "refsyn", "conbodydiv",
                      "section", "paragraph"}
        
        # 内联标签（不单独成句段）
        inline_tags = {"ph", "b", "i", "u", "strong", "em", "tt", "codeph",
                       "keyword", "tm", "sup", "sub", "xref", "linktext"}
        
        def get_text(elem, include_tail=True):
            """递归获取元素的文本内容，包括 tail"""
            parts = []
            if elem.text:
                parts.append(elem.text)
            for child in elem:
                if _strip_ns(child.tag) not in inline_tags:
                    parts.append(get_text(child))
                else:
                    if child.text:
                        parts.append(child.text)
                    if include_tail and child.tail:
                        parts.append(child.tail)
            if include_tail and elem.tail:
                parts.append(elem.tail)
            return "".join(parts).strip()
        
        def process_table(table_elem):
            """处理表格，按行拆分"""
            rows = table_elem.findall(".//tr")
            for row in rows:
                cells = row.findall(".//entry")
                if cells:
                    cell_texts = []
                    for cell in cells:
                        cell_text = get_text(cell)
                        if cell_text:
                            cell_texts.append(cell_text)
                    if cell_texts:
                        row_text = " | ".join(cell_texts)
                        if row_text.strip():
                            segments.append({"text": row_text, "tag": "table-row"})
        
        def process_list(list_elem, list_type="ul"):
            """处理列表，按项拆分"""
            items = list_elem.findall(f"./{list_type}/li") or list_elem.findall(".//li")
            for item in items:
                item_text = get_text(item)
                if item_text.strip():
                    segments.append({"text": item_text, "tag": "list-item"})
        
        def walk_elem(elem):
            """遍历元素并提取文本"""
            tag = _strip_ns(elem.tag)
            
            # 处理表格
            if tag in ("table", "simpletable"):
                process_table(elem)
                return
            
            # 处理列表
            if tag in ("ul", "ol", "sl"):
                process_list(elem, tag)
                return
            
            # 处理块级标签
            if tag in block_tags:
                text = get_text(elem)
                if text:
                    segments.append({"text": text, "tag": tag})
            
            # 处理图片
            if tag == "fig":
                caption_el = elem.find(".//title")
                if caption_el is not None and caption_el.text:
                    segments.append({"text": f"[图] {caption_el.text.strip()}", "tag": "fig"})
            
            # 递归处理子元素
            for child in elem:
                walk_elem(child)
        
        # 从 topic 或 concept/mainbody 开始遍历
        main_body = root.find(".//topic") or root.find(".//concept") or root.find(".//task") or root
        walk_elem(main_body)
        
        # 过滤空句段和纯空格句段
        segments = [s for s in segments if s["text"].strip()]
        
        # 去重，相邻重复的句段只保留一个
        deduped = []
        prev_text = None
        for s in segments:
            if s["text"] != prev_text:
                deduped.append(s)
                prev_text = s["text"]
        
        return topic_id, title, deduped
    except Exception as e:
        text = _read_upload_as_text(dita_file_path)
        return "", "", [{"text": text, "tag": "text"}]


def _parse_ditamap(ditamap_path, base_dir):
    """
    解析 ditamap，按文档顺序提取 topic 列表。
    每条记录: {level_path, navtitle, href, tag, topicref_type}
    支持单行 XML 格式（用 > 拼接的 topicref）。
    """
    topics = []
    
    try:
        tree = ET.parse(ditamap_path)
        root = tree.getroot()
    except Exception:
        return topics
    
    def walk(node, ancestors):
        tag = _strip_ns(node.tag)
        nav = (node.attrib.get("navtitle") or 
               node.attrib.get("{http://www.w3.org/ime/cms}title") or "")
        href = node.attrib.get("href", "")
        keys = node.attrib.get("keys", "")
        level_attr = node.attrib.get("level", "")
        type_attr = node.attrib.get("{http://www.w3.org/ime/cms}type") or node.attrib.get("type", "")
        
        path = ancestors + [nav] if nav else ancestors
        
        if href and href.endswith(".dita"):
            topics.append({
                "tag": tag,
                "navtitle": nav,
                "href": href,
                "path": path,
                "level": int(level_attr) if level_attr.isdigit() else len(path),
                "topic_type": type_attr or tag,
                "keys": keys,
            })
        
        for child in node:
            walk(child, path)
    
    walk(root, [])
    return topics


def _parse_dita_dir(path: str):
    """
    解析 DITA 目录，返回：
    {
        "ditamap_path": ...,
        "topics": [{"navtitle", "href", "file_path", "path", "level", "topic_id", "title", "segments"}],
        "all_segments": [...]  # 供 backward compat
    }
    """
    ditamap_files = []
    for root_dir, _, files in os.walk(path):
        for fn in files:
            if fn.lower().endswith(".ditamap"):
                ditamap_files.append(os.path.join(root_dir, fn))
    
    raw_topics = []
    ditamap_path = None
    if ditamap_files:
        ditamap_path = ditamap_files[0]
        base_dir = os.path.dirname(ditamap_path)
        raw_topics = _parse_ditamap(ditamap_path, base_dir)
    
    if not raw_topics:
        # 没找到 ditamap，按文件顺序处理所有 .dita
        for root_dir, _, files in os.walk(path):
            for fn in sorted(files):
                if fn.lower().endswith(".dita"):
                    raw_topics.append({
                        "tag": "topic",
                        "navtitle": fn.replace(".dita", ""),
                        "href": os.path.relpath(os.path.join(root_dir, fn), path),
                        "path": [fn.replace(".dita", "")],
                        "level": 1,
                        "topic_type": "topic",
                        "keys": "",
                    })
    
    topics = []
    for t in raw_topics:
        full_path = os.path.join(os.path.dirname(ditamap_path) if ditamap_path else path, t["href"])
        if not os.path.exists(full_path):
            full_path = os.path.join(path, t["href"])
        
        if os.path.exists(full_path):
            topic_id, title, segments = _extract_dita_text(full_path)
        else:
            topic_id, title, segments = "", t["navtitle"], []
        
        if not title:
            title = t["navtitle"]
        
        # 一级章节 = path[0] (如 "Device overview")
        # 小节 = 最后一个 navtitle
        chapter = t["path"][0] if len(t["path"]) >= 1 else title
        section = title or t["navtitle"]
        
        topics.append({
            "navtitle": t["navtitle"],
            "href": t["href"],
            "file_path": full_path,
            "path": t["path"],
            "level": t["level"],
            "topic_id": topic_id,
            "title": title,
            "topic_type": t["topic_type"],
            "chapter": chapter,
            "section": section,
            "segments": segments,
            "keys": t.get("keys", ""),
        })
    
    # 为 backward compat 也生成 all_segments
    all_segments = []
    for topic in topics:
        all_segments.append({
            "text": topic["title"],
            "chapter": topic["chapter"],
            "section": topic["section"],
            "level": topic["level"],
            "tag": "title",
            "topic_id": topic["topic_id"],
            "file_path": topic["file_path"],
        })
        for seg in topic["segments"]:
            if seg["text"] != topic["title"]:
                all_segments.append({
                    "text": seg["text"],
                    "chapter": topic["chapter"],
                    "section": topic["section"],
                    "level": topic["level"],
                    "tag": seg["tag"],
                    "topic_id": topic["topic_id"],
                    "file_path": topic["file_path"],
                })
    
    text_parts = []
    for topic in topics:
        text_parts.append(f"# {'#' * min(topic['level'], 6)} {topic['title']}")
        for seg in topic["segments"]:
            text_parts.append(seg["text"])
        text_parts.append("")
    
    return {
        "text": "\n".join(text_parts),
        "segments": all_segments,
        "topics": topics,
        "structure": topics,  # backward compat
        "ditamap_path": ditamap_path,
    }


def _extract_dita_dir(path: str):
    """backward compat wrapper"""
    return _parse_dita_dir(path)


def _simple_compare(text_a, text_b):
    from difflib import SequenceMatcher

    lines_a = [ln.strip() for ln in text_a.split("\n") if ln.strip()]
    lines_b = [ln.strip() for ln in text_b.split("\n") if ln.strip()]

    diffs = []
    matched_pairs = []
    matched_b = set()
    exact_match = 0
    
    for i, la in enumerate(lines_a):
        best_j = -1
        best_sim = 0.0
        for j, lb in enumerate(lines_b):
            if j in matched_b:
                continue
            sim = SequenceMatcher(None, la, lb).ratio()
            if sim > best_sim:
                best_sim = sim
                best_j = j
        if best_j >= 0:
            matched_b.add(best_j)
            if best_sim >= 0.99:
                exact_match += 1
            matched_pairs.append((i, best_j, best_sim, la, lines_b[best_j], "", ""))
            if best_sim < 0.85:
                diffs.append({
                    "diff_type": "modify",
                    "severity": "high" if best_sim < 0.7 else "medium",
                    "similarity": round(best_sim, 4),
                    "text_a": la,
                    "text_b": lines_b[best_j],
                    "position_a": {"line": i},
                    "position_b": {"line": best_j},
                    "chapter": "",
                    "section": "",
                })
        else:
            diffs.append({
                "diff_type": "delete",
                "severity": "medium",
                "similarity": 0.0,
                "text_a": la,
                "text_b": "",
                "position_a": {"line": i},
                "position_b": {},
                "chapter": "",
                "section": "",
            })
    
    matched_a = set(p[0] for p in matched_pairs)
    only_a = [(i, "", "") for i in range(len(lines_a)) if i not in matched_a]
    only_b = []
    
    for j, lb in enumerate(lines_b):
        if j not in matched_b:
            diffs.append({
                "diff_type": "add",
                "severity": "medium",
                "similarity": 0.0,
                "text_a": "",
                "text_b": lb,
                "position_a": {},
                "position_b": {"line": j},
                "chapter": "",
                "section": "",
            })
            only_b.append((j, "", ""))

    total = max(len(lines_a) + len(lines_b), 1)
    matched_count = (len(lines_a) + len(lines_b) - len(diffs))
    similarity = round(matched_count / total, 4) if total else 1.0
    if similarity > 1.0:
        similarity = 1.0

    stats = {
        "add": len([d for d in diffs if d["diff_type"] == "add"]),
        "delete": len([d for d in diffs if d["diff_type"] == "delete"]),
        "modify": len([d for d in diffs if d["diff_type"] == "modify"]),
    }
    verdict = "✅ 自动通过（≥80%）" if similarity >= 0.8 else ("⚠️ 建议复核（50% ~ 80%）" if similarity >= 0.5 else "🟥 强制人工复核（<50%，不可互换）")
    return {
        "similarity": similarity,
        "verdict": verdict,
        "total_diffs": len(diffs),
        "diff_stats": stats,
        "diffs": diffs,
        "exact_match": exact_match,
        "matched_pairs": matched_pairs,
        "only_a": only_a,
        "only_b": only_b,
        "n_a": len(lines_a),
        "n_b": len(lines_b),
    }


def _is_dita_package(filename: str) -> bool:
    """判断是否为 DITA 包（.zip 且包含 .ditamap）"""
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext in (".zip", ".dita", ".ditamap")


def _parse_file(file_path: str, filename: str):
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".pdf",):
        text = _extract_pdf(file_path)
        return {"text": text, "segments": [], "structure": [], "type": "pdf"}
    elif ext in (".dita", ".ditamap"):
        result = _extract_dita_dir(file_path)
        if isinstance(result, str):
            return {"text": result, "segments": [], "structure": [], "type": "dita"}
        result["type"] = "dita"
        return result
    elif ext == ".zip":
        import zipfile
        temp_dir = os.path.join(UPLOAD_DIR, f"tmp_{int(time.time()*1000)}_{os.path.basename(filename).replace('.zip','')}")
        os.makedirs(temp_dir, exist_ok=True)
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                zf.extractall(temp_dir)
            result = _extract_dita_dir(temp_dir)
            if isinstance(result, str):
                return {"text": result, "segments": [], "structure": [], "type": "dita", "temp_dir": temp_dir}
            result["type"] = "dita"
            result["temp_dir"] = temp_dir
            return result
        except Exception:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {"text": "", "segments": [], "structure": [], "type": "unknown"}
    else:
        text = _read_upload_as_text(file_path)
        return {"text": text, "segments": [], "structure": [], "type": "text"}


@router.post("/")
async def create_compare(
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    _ensure_upload_dir()
    task_id = None
    file_a_path = os.path.join(UPLOAD_DIR, f"{int(time.time() * 1000)}_{file_a.filename}")
    file_b_path = os.path.join(UPLOAD_DIR, f"{int(time.time() * 1000)}_{file_b.filename}")

    try:
        with open(file_a_path, "wb") as buffer:
            buffer.write(await file_a.read())
        with open(file_b_path, "wb") as buffer:
            buffer.write(await file_b.read())
    except Exception:
        if os.path.exists(file_a_path):
            try: os.remove(file_a_path)
            except Exception: pass
        if os.path.exists(file_b_path):
            try: os.remove(file_b_path)
            except Exception: pass
        raise HTTPException(status_code=500, detail="File upload failed")

    try:
        parsed_a = _parse_file(file_a_path, file_a.filename)
        parsed_b = _parse_file(file_b_path, file_b.filename)

        text_a = parsed_a["text"] if isinstance(parsed_a, dict) else parsed_a
        text_b = parsed_b["text"] if isinstance(parsed_b, dict) else parsed_b
        
        segments_a = parsed_a.get("segments", []) if isinstance(parsed_a, dict) else []
        segments_b = parsed_b.get("segments", []) if isinstance(parsed_b, dict) else []
        structure_a = parsed_a.get("structure", []) if isinstance(parsed_a, dict) else []
        structure_b = parsed_b.get("structure", []) if isinstance(parsed_b, dict) else []

        # 判断是否为 DITA 包：两边都是 DITA 类型且有 topic 数据
        is_dita = (
            parsed_a.get("type") == "dita" and parsed_b.get("type") == "dita"
            and parsed_a.get("topics") and parsed_b.get("topics")
        )

        result = None
        dita_full = None
        if is_dita:
            try:
                from app.utils.dita_compare import compare_dita_packages
                dita_full = compare_dita_packages(
                    parsed_a.get("temp_dir") or os.path.dirname(parsed_a.get("ditamap_path", "")),
                    parsed_b.get("temp_dir") or os.path.dirname(parsed_b.get("ditamap_path", "")),
                    threshold=0.80,
                )
                # 转成统一 result 格式
                diffs = []
                for tr in dita_full.get("topics", []):
                    for d in tr.get("diffs", []):
                        diffs.append({
                            "diff_type": d.get("type", "modify"),
                            "severity": (
                                "high" if d.get("type") in ("only_a", "only_b")
                                else "medium" if d.get("similarity", 0) < 0.7
                                else "low"
                            ),
                            "similarity": float(d.get("similarity", 0.0)),
                            "text_a": d.get("text_a", ""),
                            "text_b": d.get("text_b", ""),
                            "position_a": {},
                            "position_b": {},
                            "chapter": tr.get("chapter_a", "") or tr.get("chapter_b", ""),
                        })

                result = {
                    "similarity": dita_full.get("overall_jaccard", 0.0),
                    "verdict": (
                        "✅ 自动通过（≥80%）" if dita_full.get("overall_jaccard", 0.0) >= 0.80
                        else "⚠️ 建议复核（50% ~ 80%）" if dita_full.get("overall_jaccard", 0.0) >= 0.50
                        else "🟥 强制人工复核（<50%，不可互换）"
                    ),
                    "total_diffs": sum(tr.get("n_diffs", 0) for tr in dita_full.get("topics", [])),
                    "diff_stats": {
                        "add": dita_full.get("n_only_b", 0),
                        "delete": dita_full.get("n_only_a", 0),
                        "modify": dita_full.get("stat_low", 0) + dita_full.get("stat_partial", 0),
                    },
                    "diffs": diffs,
                    "exact_match": dita_full.get("n_exact", 0),
                    "matched_pairs": [],
                    "only_a": [{"chapter": tr.get("chapter_a", ""), "section": tr.get("navtitle", "")}
                               for tr in dita_full.get("topics", []) if tr.get("type") == "only_a"],
                    "only_b": [{"chapter": tr.get("chapter_b", ""), "section": tr.get("navtitle", "")}
                               for tr in dita_full.get("topics", []) if tr.get("type") == "only_b"],
                    "n_a": dita_full.get("n_sentences_a", 0),
                    "n_b": dita_full.get("n_sentences_b", 0),
                    "dita_full": dita_full,
                }
            except Exception as e:
                is_dita = False
                print(f"[DITA对比失败] 走通用对比: {e}")

        if result is None:
            try:
                from app.utils.compare_utils import compare_documents
                result = compare_documents(text_a, text_b, {
                    "segments_a": segments_a,
                    "segments_b": segments_b,
                    "structure_a": structure_a,
                    "structure_b": structure_b,
                })
            except Exception:
                result = _simple_compare(text_a, text_b)

        try:
            from app.crud.compare import create_compare_task, update_compare_task, create_compare_diff
            task = create_compare_task(db, file_a.filename, file_b.filename, 1)
            # 序列化 dita_full 用于存储
            dita_full_json = json.dumps(dita_full, ensure_ascii=False) if dita_full else ""
            update_compare_task(
                db, task.id,
                result["similarity"], result["verdict"],
                result["total_diffs"], result["diff_stats"],
                result.get("exact_match", 0),
                result.get("n_a", 0),
                result.get("n_b", 0),
                result.get("matched_pairs", []),
                result.get("only_a", []),
                result.get("only_b", []),
                dita_full_json=dita_full_json,
            )
            # 把 topic 级差异保存到 diff 表
            diffs_to_save = result["diffs"][:200]
            if dita_full:
                for tr in dita_full.get("topics", []):
                    for d in tr.get("diffs", []):
                        if len(diffs_to_save) >= 200:
                            break
                        diffs_to_save.append({
                            "diff_type": d.get("type", "modify"),
                            "severity": (
                                "high" if d.get("type") in ("only_a", "only_b")
                                else "medium" if d.get("similarity", 0) < 0.7
                                else "low"
                            ),
                            "similarity": float(d.get("similarity", 0.0)),
                            "text_a": d.get("text_a", ""),
                            "text_b": d.get("text_b", ""),
                            "position_a": {},
                            "position_b": {},
                            "chapter": tr.get("chapter_a", "") or tr.get("chapter_b", ""),
                        })
                    if len(diffs_to_save) >= 200:
                        break

            for diff in diffs_to_save[:200]:
                try:
                    create_compare_diff(
                        db, task.id,
                        diff.get("diff_type", "modify"),
                        diff.get("severity", "medium"),
                        float(diff.get("similarity", 0.0)),
                        diff.get("text_a", ""),
                        diff.get("text_b", ""),
                        diff.get("position_a") or {},
                        diff.get("position_b") or {},
                        diff.get("chapter", ""),
                    )
                except Exception:
                    continue
            task_id = task.id
        except Exception:
            task_id = _MEMORY_NEXT_ID[0]
            _MEMORY_NEXT_ID[0] += 1
            dita_full_json = json.dumps(dita_full, ensure_ascii=False) if dita_full else ""
            _MEMORY_TASKS[task_id] = {
                "id": task_id,
                "file_a_name": file_a.filename,
                "file_b_name": file_b.filename,
                "similarity": result["similarity"],
                "verdict": result["verdict"],
                "total_diffs": result["total_diffs"],
                "diff_stats": json.dumps(result["diff_stats"]),
                "status": "completed",
                "user_id": 1,
                "created_at": int(time.time()),
                "exact_match": result.get("exact_match", 0),
                "n_a": result.get("n_a", 0),
                "n_b": result.get("n_b", 0),
                "matched_pairs": json.dumps(result.get("matched_pairs", [])),
                "only_a": json.dumps(result.get("only_a", [])),
                "only_b": json.dumps(result.get("only_b", [])),
                "dita_full": dita_full_json,
            }
            _MEMORY_DIFFS[task_id] = result["diffs"][:200]

        try:
            os.remove(file_a_path)
            os.remove(file_b_path)
        except Exception:
            pass

        return {
            "comparison_id": task_id,
            "task_id": task_id,
            "stats": result["diff_stats"],
            "similarity": result["similarity"],
            "verdict": result["verdict"],
            "total_diffs": result["total_diffs"],
            "diffs": result["diffs"][:200],
            "status": "completed",
            "exact_match": result.get("exact_match", 0),
            "n_a": result.get("n_a", 0),
            "n_b": result.get("n_b", 0),
            "is_dita": is_dita,
            "dita_full": dita_full,
        }
    except Exception as exc:
        try:
            os.remove(file_a_path)
            os.remove(file_b_path)
        except Exception:
            pass
        task_id = _MEMORY_NEXT_ID[0]
        _MEMORY_NEXT_ID[0] += 1
        fallback = _simple_compare("", "")
        _MEMORY_TASKS[task_id] = {
            "id": task_id,
            "file_a_name": file_a.filename,
            "file_b_name": file_b.filename,
            "similarity": fallback["similarity"],
            "verdict": fallback["verdict"],
            "total_diffs": fallback["total_diffs"],
            "diff_stats": json.dumps(fallback["diff_stats"]),
            "status": "completed",
            "user_id": 1,
            "created_at": int(time.time()),
        }
        _MEMORY_DIFFS[task_id] = fallback["diffs"]
        return {
            "comparison_id": task_id,
            "task_id": task_id,
            "stats": fallback["diff_stats"],
            "similarity": fallback["similarity"],
            "verdict": fallback["verdict"],
            "total_diffs": fallback["total_diffs"],
            "diffs": fallback["diffs"][:50],
            "status": "completed",
            "error": str(exc),
        }


@router.get("/")
async def read_compare_tasks(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    items = []
    
    db_tasks = []
    try:
        from app.crud.compare import get_compare_tasks
        db_tasks = get_compare_tasks(db, skip=0, limit=1000) or []
    except Exception:
        pass
    
    for t in db_tasks:
        items.append({
            "id": t.id,
            "file_a_name": getattr(t, "file_a_name", ""),
            "file_b_name": getattr(t, "file_b_name", ""),
            "similarity": getattr(t, "similarity", 0.0),
            "verdict": getattr(t, "verdict", ""),
            "total_diffs": getattr(t, "total_diffs", 0),
            "status": getattr(t, "status", "completed"),
            "user_id": getattr(t, "user_id", 1),
            "created_at": getattr(t, "created_at", None),
        })

    mem_list = sorted(_MEMORY_TASKS.values(), key=lambda x: -x["id"])
    for m in mem_list:
        exists = any(item["id"] == m["id"] for item in items)
        if not exists:
            items.append({
                "id": m["id"],
                "file_a_name": m["file_a_name"],
                "file_b_name": m["file_b_name"],
                "similarity": m["similarity"],
                "verdict": m["verdict"],
                "total_diffs": m["total_diffs"],
                "status": m["status"],
                "user_id": m["user_id"],
                "created_at": m["created_at"],
            })

    items.sort(key=lambda x: x["id"] if isinstance(x["id"], int) else 0, reverse=True)
    
    return items[skip: skip + limit]


@router.get("/{task_id}")
async def read_compare(task_id: int, db: Session = Depends(get_db)):
    task_obj = None
    diffs = []
    matched_pairs = []
    only_a = []
    only_b = []

    try:
        from app.crud.compare import get_compare_task, get_compare_diffs
        task = get_compare_task(db, task_id=task_id)
        if task:
            task_obj = {
                "id": task.id,
                "file_a_name": getattr(task, "file_a_name", ""),
                "file_b_name": getattr(task, "file_b_name", ""),
                "similarity": getattr(task, "similarity", 0.0),
                "verdict": getattr(task, "verdict", ""),
                "total_diffs": getattr(task, "total_diffs", 0),
                "diff_stats": getattr(task, "diff_stats", None),
                "status": getattr(task, "status", "completed"),
                "user_id": getattr(task, "user_id", 1),
                "created_at": getattr(task, "created_at", None),
                "exact_match": getattr(task, "exact_match", 0),
                "n_a": getattr(task, "n_a", 0),
                "n_b": getattr(task, "n_b", 0),
                "matched_pairs": getattr(task, "matched_pairs", "[]"),
                "only_a": getattr(task, "only_a", "[]"),
                "only_b": getattr(task, "only_b", "[]"),
                "dita_full": getattr(task, "dita_full", "") or "",
            }
            db_diffs = get_compare_diffs(db, task_id=task_id) or []
            for d in db_diffs:
                diffs.append({
                    "id": getattr(d, "id", 0),
                    "task_id": getattr(d, "task_id", task_id),
                    "diff_type": getattr(d, "diff_type", "modify"),
                    "severity": getattr(d, "severity", "medium"),
                    "similarity": getattr(d, "similarity", 0.0),
                    "text_a": getattr(d, "text_a", ""),
                    "text_b": getattr(d, "text_b", ""),
                    "position_a": getattr(d, "position_a", "{}"),
                    "position_b": getattr(d, "position_b", "{}"),
                    "chapter": getattr(d, "chapter", ""),
                })
    except Exception:
        pass

    if task_obj is None and task_id in _MEMORY_TASKS:
        task_obj = _MEMORY_TASKS[task_id]
        diffs = _MEMORY_DIFFS.get(task_id, [])

    if task_obj is None:
        raise HTTPException(status_code=404, detail="Task not found")

    diff_stats = {}
    try:
        stats_raw = task_obj.get("diff_stats") if isinstance(task_obj, dict) else None
        if stats_raw:
            diff_stats = json.loads(stats_raw) if isinstance(stats_raw, str) else stats_raw
    except Exception:
        diff_stats = {}

    try:
        mp_raw = task_obj.get("matched_pairs") if isinstance(task_obj, dict) else None
        if mp_raw:
            matched_pairs = json.loads(mp_raw) if isinstance(mp_raw, str) else mp_raw
    except Exception:
        matched_pairs = []

    try:
        oa_raw = task_obj.get("only_a") if isinstance(task_obj, dict) else None
        if oa_raw:
            only_a = json.loads(oa_raw) if isinstance(oa_raw, str) else oa_raw
    except Exception:
        only_a = []

    try:
        ob_raw = task_obj.get("only_b") if isinstance(task_obj, dict) else None
        if ob_raw:
            only_b = json.loads(ob_raw) if isinstance(ob_raw, str) else ob_raw
    except Exception:
        only_b = []

    # 解析 dita_full JSON
    dita_full = None
    try:
        df_raw = task_obj.get("dita_full") if isinstance(task_obj, dict) else None
        if df_raw:
            dita_full = json.loads(df_raw) if isinstance(df_raw, str) else df_raw
    except Exception:
        dita_full = None

    return {
        "task_id": task_obj.get("id") if isinstance(task_obj, dict) else task_id,
        "comparison_id": task_obj.get("id") if isinstance(task_obj, dict) else task_id,
        "similarity": task_obj.get("similarity") if isinstance(task_obj, dict) else 0.0,
        "verdict": task_obj.get("verdict") if isinstance(task_obj, dict) else "",
        "total_diffs": task_obj.get("total_diffs") if isinstance(task_obj, dict) else 0,
        "diff_stats": diff_stats,
        "stats": diff_stats,
        "diffs": diffs,
        "status": task_obj.get("status") if isinstance(task_obj, dict) else "completed",
        "file_a_name": task_obj.get("file_a_name") if isinstance(task_obj, dict) else "",
        "file_b_name": task_obj.get("file_b_name") if isinstance(task_obj, dict) else "",
        "exact_match": int(task_obj.get("exact_match") or 0),
        "n_a": int(task_obj.get("n_a") or 0),
        "n_b": int(task_obj.get("n_b") or 0),
        "matched_pairs": matched_pairs,
        "only_a": only_a,
        "only_b": only_b,
        "dita_full": dita_full,
    }


@router.delete("/{task_id}")
async def delete_compare(task_id: int, db: Session = Depends(get_db)):
    deleted = False
    try:
        from app.crud.compare import delete_compare_task
        t = delete_compare_task(db, task_id=task_id)
        if t:
            deleted = True
    except Exception:
        pass
    if task_id in _MEMORY_TASKS:
        _MEMORY_TASKS.pop(task_id, None)
        _MEMORY_DIFFS.pop(task_id, None)
        deleted = True
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted successfully", "task_id": task_id}


@router.get("/{task_id}/report")
async def generate_report(task_id: int, format: str = "html", db: Session = Depends(get_db)):
    data = None
    try:
        data = await read_compare(task_id, db)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Task not found")

    diffs = data.get("diffs", [])
    stats = data.get("diff_stats") or data.get("stats") or {}
    similarity = data.get("similarity", 0.0)
    verdict = data.get("verdict", "")
    file_a_name = data.get("file_a_name", "Document A")
    file_b_name = data.get("file_b_name", "Document B")
    total_diffs = data.get("total_diffs", 0)
    exact_match = data.get("exact_match", 0)
    n_a = data.get("n_a", 0)
    n_b = data.get("n_b", 0)
    
    matched_pairs = data.get("matched_pairs", [])
    only_a = data.get("only_a", [])
    only_b = data.get("only_b", [])
    dita_full = data.get("dita_full")

    # 优先 DITA 报告（HTML 格式时）
    if dita_full and format == "html":
        try:
            from app.utils.dita_report import render_dita_html_report
            html_content = render_dita_html_report(dita_full, file_a_name, file_b_name)
            return {"content": html_content, "format": "html"}
        except Exception as e:
            import traceback
            print(f"DITA report error: {e}")
            print(traceback.format_exc())

    if format == "html":
        html_content = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>文档对比报告</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
.header {{ text-align: center; margin-bottom: 30px; }}
.similarity {{ font-size: 48px; color: {'#28a745' if similarity >= 0.8 else '#dc3545'}; }}
.summary {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
.summary td {{ border: 1px solid #ddd; padding: 8px; }}
.diff {{ border: 1px solid #ddd; padding: 15px; margin-bottom: 10px; }}
.add {{ background-color: #d4edda; }}
.delete {{ background-color: #f8d7da; }}
.modify {{ background-color: #fff3cd; }}
.severity-critical {{ border-left: 4px solid #dc3545; }}
.severity-high {{ border-left: 4px solid #fd7e14; }}
.severity-medium {{ border-left: 4px solid #ffc107; }}
.severity-low {{ border-left: 4px solid #28a745; }}
</style></head><body>
<div class="header"><h1>文档对比报告</h1></div>
<h2>对比概览</h2>
<p class="similarity">相似度: {similarity*100:.1f}%</p>
<p><strong>判定:</strong> {verdict}</p>
<table class="summary">
<tr><td>差异总数</td><td>{total_diffs}</td></tr>
<tr><td>新增</td><td>{stats.get('add', 0)}</td></tr>
<tr><td>删除</td><td>{stats.get('delete', 0)}</td></tr>
<tr><td>修改</td><td>{stats.get('modify', 0)}</td></tr>
</table>
<h2>详细差异</h2>
"""
        for idx, d in enumerate(diffs[:100], 1):
            dtype = d.get("diff_type", "modify")
            severity = d.get("severity", "medium")
            html_content += f"""<div class="diff {dtype} severity-{severity}">
<h3>差异 #{idx}</h3>
<p><strong>类型:</strong> {dtype}</p>
<p><strong>严重程度:</strong> {severity}</p>
<p><strong>相似度:</strong> {d.get('similarity', 0.0)*100:.1f}%</p>
<p><strong>原文:</strong> {d.get('text_a', '')}</p>
<p><strong>修改后:</strong> {d.get('text_b', '')}</p>
</div>"""
        html_content += "</body></html>"
        return {"content": html_content, "format": "html"}

    try:
        from app.utils.compare_utils import render_report
        import traceback
        report = render_report(
            file_a_name,
            file_b_name,
            "",
            "",
            {
                "similarity": similarity,
                "verdict": verdict,
                "total_diffs": total_diffs,
                "diff_stats": stats,
                "exact_match": exact_match,
                "matched_pairs": matched_pairs,
                "only_a": only_a,
                "only_b": only_b,
                "n_a": n_a,
                "n_b": n_b,
            }
        )
        return {"content": report, "format": "md"}
    except Exception as e:
        print(f"render_report error: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        md_lines = [
            "# 文档对比报告",
            "",
            "## 对比概览",
            "",
            f"- 文件A: {file_a_name}",
            f"- 文件B: {file_b_name}",
            f"- 相似度: {similarity*100:.1f}%",
            f"- 判定: {verdict}",
            f"- 差异总数: {total_diffs}",
            f"- 新增: {stats.get('add', 0)}",
            f"- 删除: {stats.get('delete', 0)}",
            f"- 修改: {stats.get('modify', 0)}",
            "",
            "## 详细差异",
            "",
        ]
        for idx, d in enumerate(diffs[:100], 1):
            md_lines += [
                f"### 差异 #{idx}",
                "",
                f"- 类型: {d.get('diff_type', 'modify')}",
                f"- 严重程度: {d.get('severity', 'medium')}",
                f"- 相似度: {d.get('similarity', 0.0)*100:.1f}%",
                "",
                f"**原文:**\n{d.get('text_a', '')}",
                "",
                f"**修改后:**\n{d.get('text_b', '')}",
                "",
                "---",
                "",
            ]
        return {"content": "\n".join(md_lines), "format": "md"}


@router.get("/config")
async def get_config(db: Session = Depends(get_db)):
    try:
        from app.crud.compare import get_compare_config
        config = get_compare_config(db)
        whitelist = []
        try:
            if getattr(config, "whitelist", None):
                whitelist = json.loads(config.whitelist)
        except Exception:
            whitelist = []
        return {
            "threshold": getattr(config, "threshold", 0.8),
            "alpha": getattr(config, "alpha", 0.6),
            "beta": getattr(config, "beta", 0.4),
            "tolerance": getattr(config, "tolerance", 0.01),
            "whitelist": whitelist,
        }
    except Exception:
        return {"threshold": 0.8, "alpha": 0.6, "beta": 0.4, "tolerance": 0.01, "whitelist": []}


@router.put("/config")
async def update_config(
    threshold: float = None, alpha: float = None, beta: float = None,
    tolerance: float = None, whitelist: list = None,
    db: Session = Depends(get_db),
):
    try:
        from app.crud.compare import update_compare_config
        update_compare_config(db, threshold, alpha, beta, tolerance, whitelist)
    except Exception:
        pass
    return {"message": "Config updated successfully"}
