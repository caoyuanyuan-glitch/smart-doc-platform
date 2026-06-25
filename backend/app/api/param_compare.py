from fastapi import APIRouter, HTTPException, File, UploadFile
import os
import time

router = APIRouter()

UPLOAD_DIR = "./static/uploads"


def _ensure_upload_dir():
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/")
async def compare_params(
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...),
):
    _ensure_upload_dir()

    file_a_path = os.path.join(UPLOAD_DIR, f"{int(time.time() * 1000)}_{file_a.filename}")
    file_b_path = os.path.join(UPLOAD_DIR, f"{int(time.time() * 1000)}_{file_b.filename}")

    try:
        with open(file_a_path, "wb") as buffer:
            buffer.write(await file_a.read())
        with open(file_b_path, "wb") as buffer:
            buffer.write(await file_b.read())
    except Exception:
        _cleanup(file_a_path, file_b_path)
        raise HTTPException(status_code=500, detail="文件上传失败")

    try:
        from app.utils.param_compare import run_param_compare, extract_params, _extract_raw_text

        result = run_param_compare(file_a_path, file_b_path)

        raw_a = _extract_raw_text(file_a_path)
        raw_b = _extract_raw_text(file_b_path)

        result["extracted_text_a"] = raw_a[:3000] if raw_a else ""
        result["extracted_text_b"] = raw_b[:3000] if raw_b else ""

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"参数对比失败: {str(e)}")
    finally:
        _cleanup(file_a_path, file_b_path)


def _cleanup(path_a, path_b):
    for p in (path_a, path_b):
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
