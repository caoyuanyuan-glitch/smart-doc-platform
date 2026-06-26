from fastapi import APIRouter, HTTPException, File, UploadFile
from typing import List
import os
import time
import json

router = APIRouter()

UPLOAD_DIR = "./static/uploads"


def _ensure_upload_dir():
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/")
async def compare_params(
    files: List[UploadFile] = File(...),
):
    _ensure_upload_dir()

    if not files or len(files) < 2:
        raise HTTPException(status_code=400, detail="至少需要上传2个文档进行参数对比")

    saved_paths = []
    saved_names = []
    ts = int(time.time() * 1000)

    for i, f in enumerate(files):
        path = os.path.join(UPLOAD_DIR, f"{ts}_{i}_{f.filename}")
        try:
            with open(path, "wb") as buffer:
                buffer.write(await f.read())
            saved_paths.append(path)
            saved_names.append(f.filename)
        except Exception:
            for p in saved_paths:
                try:
                    os.remove(p)
                except Exception:
                    pass
            raise HTTPException(status_code=500, detail="文件上传失败")

    try:
        from app.utils.param_compare import run_param_compare, extract_params, _extract_raw_text

        ref_path = saved_paths[0]
        ref_name = saved_names[0]
        all_results = []
        tasks_saved = []

        for i in range(1, len(saved_paths)):
            cmp_path = saved_paths[i]
            cmp_name = saved_names[i]

            pair_result = run_param_compare(ref_path, cmp_path)
            pair_result["file_a"] = ref_name
            pair_result["file_b"] = cmp_name
            pair_result["pair_index"] = i

            raw_ref = _extract_raw_text(ref_path)
            raw_cmp = _extract_raw_text(cmp_path)
            pair_result["extracted_text_a"] = raw_ref[:3000] if raw_ref else ""
            pair_result["extracted_text_b"] = raw_cmp[:3000] if raw_cmp else ""

            all_results.append(pair_result)

            _save_param_task_to_db(
                file_a_name=ref_name,
                file_b_name=cmp_name,
                group_id=ts,
                file_names=json.dumps(saved_names, ensure_ascii=False),
                pair_result=pair_result,
            )

        return {
            "file_count": len(files),
            "file_names": saved_names,
            "results": all_results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"参数对比失败: {str(e)}")
    finally:
        for p in saved_paths:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


def _save_param_task_to_db(file_a_name, file_b_name, group_id, file_names, pair_result):
    """将参数对比结果保存到 CompareTask 表，以便在历史任务中查看"""
    try:
        from app.database import SessionLocal
        from app.models.compare_task import CompareTask

        results = pair_result.get("results", [])
        matched = [r for r in results if r["match"] in ("一致", "不一致")]
        only_a = [r for r in results if r["match"] == "仅A有"]
        only_b = [r for r in results if r["match"] == "仅B有"]

        match_count = pair_result.get("match_count", 0)
        diff_count = pair_result.get("diff_count", 0)
        total = pair_result.get("total", 0)
        similarity = match_count / total if total > 0 else 0.0

        if similarity >= 0.95:
            verdict = "参数基本一致（>=95%）"
        elif similarity >= 0.80:
            verdict = "参数存在差异（80% ~ 95%）"
        else:
            verdict = "参数差异较大（<80%）"

        db = SessionLocal()
        try:
            task = CompareTask(
                task_type="param",
                file_a_name=file_a_name,
                file_b_name=file_b_name,
                file_names=file_names,
                group_id=group_id,
                similarity=similarity,
                verdict=verdict,
                total_diffs=diff_count + len(only_a) + len(only_b),
                diff_stats=json.dumps({
                    "match": match_count,
                    "diff": diff_count,
                    "only_a": len(only_a),
                    "only_b": len(only_b),
                    "params_a": pair_result.get("params_a_count", 0),
                    "params_b": pair_result.get("params_b_count", 0),
                }),
                status="completed",
                user_id=1,
                exact_match=match_count,
                n_a=pair_result.get("params_a_count", 0),
                n_b=pair_result.get("params_b_count", 0),
                matched_pairs=json.dumps(matched, ensure_ascii=False),
                only_a=json.dumps(only_a, ensure_ascii=False),
                only_b=json.dumps(only_b, ensure_ascii=False),
            )
            db.add(task)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[param_compare] Failed to save task to DB: {e}")
