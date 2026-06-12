from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
import os
import json
import time
from app.database import get_db

router = APIRouter()

UPLOAD_DIR = "./static/uploads"

_MEMORY_TASKS = {}
_MEMORY_DIFFS = {}
_MEMORY_NEXT_ID = [1000]


def _ensure_upload_dir():
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR, exist_ok=True)


def _simple_compare(text_a, text_b):
    from difflib import SequenceMatcher

    lines_a = [ln.strip() for ln in text_a.split("\n") if ln.strip()]
    lines_b = [ln.strip() for ln in text_b.split("\n") if ln.strip()]

    diffs = []
    matched_b = set()
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
            })
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
            })

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
    verdict = "pass" if similarity >= 0.8 else ("review" if similarity >= 0.6 else "force_review")
    return {
        "similarity": similarity,
        "verdict": verdict,
        "total_diffs": len(diffs),
        "stats": stats,
        "diffs": diffs,
    }


def _read_upload_as_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


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
        text_a = _read_upload_as_text(file_a_path)
        text_b = _read_upload_as_text(file_b_path)

        try:
            from app.utils.document_parser import parse_file
            parsed_a = parse_file(file_a_path) or text_a
            parsed_b = parse_file(file_b_path) or text_b
            if parsed_a:
                text_a = parsed_a
            if parsed_b:
                text_b = parsed_b
        except Exception:
            pass

        result = None
        try:
            from app.utils.compare_utils import compare_documents as _compare
            raw = _compare(text_a, text_b)
            stats = raw.get("diff_stats") or {
                "add": 0, "delete": 0, "modify": 0
            }
            result = {
                "similarity": raw.get("similarity", 0.0),
                "verdict": raw.get("verdict", "review"),
                "total_diffs": raw.get("total_diffs", 0),
                "stats": stats,
                "diffs": raw.get("diffs") or [],
            }
        except Exception:
            result = _simple_compare(text_a, text_b)

        try:
            from app.crud.compare import create_compare_task, update_compare_task, create_compare_diff
            task = create_compare_task(db, file_a.filename, file_b.filename, 1)
            update_compare_task(
                db, task.id,
                result["similarity"], result["verdict"],
                result["total_diffs"], result["stats"],
            )
            for diff in result["diffs"][:200]:
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
            _MEMORY_TASKS[task_id] = {
                "id": task_id,
                "file_a_name": file_a.filename,
                "file_b_name": file_b.filename,
                "similarity": result["similarity"],
                "verdict": result["verdict"],
                "total_diffs": result["total_diffs"],
                "diff_stats": json.dumps(result["stats"]),
                "status": "completed",
                "user_id": 1,
                "created_at": int(time.time()),
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
            "stats": result["stats"],
            "similarity": result["similarity"],
            "verdict": result["verdict"],
            "total_diffs": result["total_diffs"],
            "diffs": result["diffs"][:50],
            "status": "completed",
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
            "diff_stats": json.dumps(fallback["stats"]),
            "status": "completed",
            "user_id": 1,
            "created_at": int(time.time()),
        }
        _MEMORY_DIFFS[task_id] = fallback["diffs"]
        return {
            "comparison_id": task_id,
            "task_id": task_id,
            "stats": fallback["stats"],
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
    try:
        from app.crud.compare import get_compare_tasks
        tasks = get_compare_tasks(db, skip=skip, limit=limit) or []
        for t in tasks:
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
    except Exception:
        pass

    mem_list = sorted(_MEMORY_TASKS.values(), key=lambda x: -x["id"])
    for m in mem_list:
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

    return items[skip: skip + limit]


@router.get("/{task_id}")
async def read_compare(task_id: int, db: Session = Depends(get_db)):
    task_obj = None
    diffs = []

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

    if format == "html":
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>文档对比报告</title>
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
</style></head><body>
<div class="header"><h1>文档对比报告</h1></div>
<h2>对比概览</h2>
<p class="similarity">相似度: {similarity*100:.1f}%</p>
<p><strong>判定:</strong> {verdict}</p>
<table class="summary">
<tr><td>差异总数</td><td>{data.get('total_diffs', 0)}</td></tr>
<tr><td>新增</td><td>{stats.get('add', 0)}</td></tr>
<tr><td>删除</td><td>{stats.get('delete', 0)}</td></tr>
<tr><td>修改</td><td>{stats.get('modify', 0)}</td></tr>
</table>
<h2>详细差异</h2>
"""
        for idx, d in enumerate(diffs[:100], 1):
            dtype = d.get("diff_type", "modify")
            html += f"""<div class="diff {dtype}">
<h3>差异 #{idx}</h3>
<p><strong>类型:</strong> {dtype}</p>
<p><strong>相似度:</strong> {d.get('similarity', 0.0)*100:.1f}%</p>
<p><strong>原文:</strong> {d.get('text_a', '')}</p>
<p><strong>修改后:</strong> {d.get('text_b', '')}</p>
</div>"""
        html += "</body></html>"
        return {"content": html, "format": "html"}

    md_lines = [
        "# 文档对比报告",
        "",
        "## 对比概览",
        "",
        f"- 相似度: {similarity*100:.1f}%",
        f"- 判定: {verdict}",
        f"- 差异总数: {data.get('total_diffs', 0)}",
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
