import os
import tempfile
import time
import uuid
from io import BytesIO
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from PIL import Image

from app.crud.knowledge import get_file, get_folder_tree
from app.database import get_db
from app.utils.document_parser import parse_file
from app.utils.file_utils import read_file_safe

router = APIRouter()

DRAFT_CACHE: Dict[str, dict] = {}
DRAFT_CACHE_MAX = 20

STYLE_GUIDE_PATH = ("写作规范", "写作风格指南")
STYLE_GUIDE_MAX_CHARS = 1500  # 截断风格指南以避免 prompt 超长
TEMPLATE_MAX_CHARS = 2000
MODEL_IMAGE_MAX_EDGE = 700
MODEL_IMAGE_QUALITY = 65


class GenerateRequest(BaseModel):
    product_name: str
    product_model: str
    doc_type: str
    target_chapter: str


def _generate_fallback(product_name: str, product_model: str, doc_type: str, target_chapter: str):
    title = f"{product_name}（{product_model}）{doc_type} - {target_chapter}"
    sections = [
        {
            "title": f"{target_chapter} 概述",
            "level": 1,
            "content": f"本章介绍 {product_name}（型号：{product_model}）在{doc_type}中的相关说明。"
        },
        {
            "title": "产品特点",
            "level": 2,
            "content": f"- 型号 {product_model} 具备标准功能与接口。\n- 适用于典型{doc_type}场景。\n- 可在规定环境下稳定运行。"
        },
        {
            "title": "使用说明",
            "level": 2,
            "content": f"请按以下步骤操作 {product_name} {product_model}：\n1. 检查外观与配件。\n2. 按照指示完成接线或初始化。\n3. 参考详细章节完成配置。"
        },
        {
            "title": "注意事项",
            "level": 2,
            "content": "- 使用前请仔细阅读本章内容。\n- 保持设备干燥、避免剧烈震动。\n- 如有异常请联系客服。"
        }
    ]
    content = f"# {title}\n\n"
    for s in sections:
        prefix = "#" * s["level"]
        content += f"\n{prefix} {s['title']}\n\n{s['content']}\n"
    return {"content": content.strip(), "sections": sections}


def _image_steps_fallback(file_names: List[str], prompt: str):
    steps = []
    for index, file_name in enumerate(file_names, start=1):
        steps.append(f"步骤 {index}：根据 {file_name} 中显示的关键对象和状态，完成当前环节操作，并确认进入下一步前的界面或物料状态已经满足要求。")

    return {
        "summary": f"共接收 {len(file_names)} 张图片，已按图片顺序整理为一组连续操作说明。",
        "relation_summary": f"当前结果按上传顺序组织流程，并结合用户补充要求输出。{prompt if prompt else '未提供额外约束。'}",
        "steps": steps,
        "used_style_guide_name": "自动匹配未命中具体指南",
        "model": "fallback",
        "warning": "当前多模型图片分析链路未返回有效结果，结果来自本地兜底逻辑，不能作为正式操作说明。",
    }


def _prepare_model_image(raw: bytes, content_type: str) -> tuple[bytes, str]:
    try:
        with Image.open(BytesIO(raw)) as image:
            image = image.convert("RGB")
            image.thumbnail((MODEL_IMAGE_MAX_EDGE, MODEL_IMAGE_MAX_EDGE), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=MODEL_IMAGE_QUALITY, optimize=True)
            return buffer.getvalue(), "image/jpeg"
    except Exception:
        return raw, content_type


def _infer_guide_language(name: str) -> str:
    lowered = str(name or "").lower()
    if "中文" in lowered or "chinese" in lowered:
        return "zh"
    if "英文" in lowered or "english" in lowered:
        return "en"
    return "unknown"


def _detect_result_language(text: str) -> str:
    sample = str(text or "")
    if not sample.strip():
        return "unknown"
    chinese_count = sum(1 for ch in sample if "\u4e00" <= ch <= "\u9fff")
    english_count = sum(1 for ch in sample if ("a" <= ch.lower() <= "z"))
    if chinese_count > english_count:
        return "zh"
    if english_count > chinese_count:
        return "en"
    return "unknown"


def _resolve_used_style_guide_name(style_guide_bundle: Optional[dict], result: dict) -> str:
    explicit_name = str(result.get("used_style_guide_name") or "").strip()
    if explicit_name:
        return explicit_name
    if not style_guide_bundle or not style_guide_bundle.get("guides"):
        return ""

    guides = style_guide_bundle.get("guides") or []
    if style_guide_bundle.get("mode") == "selected":
        return str(guides[0].get("name") or "").strip()

    combined_text = "\n".join([
        str(result.get("summary") or ""),
        str(result.get("relation_summary") or ""),
        "\n".join(result.get("steps") or []),
    ])
    detected_language = _detect_result_language(combined_text)
    for guide in guides:
        if guide.get("language") == detected_language:
            return str(guide.get("name") or "").strip()

    return str(guides[0].get("name") or "").strip()


def _collect_style_guides(node: dict, current_path: List[str]) -> List[dict]:
    guides = []
    for file in node.get("files") or []:
        file_path = file.get("file_path")
        file_type = str(file.get("file_type") or "").lower()
        if not file_path or not os.path.exists(file_path):
            continue
        if file_type not in {"md", "markdown", "txt"}:
            continue
        guides.append({
            "id": file.get("id"),
            "name": file.get("name") or file.get("filename") or "风格指南",
            "file_path": file_path,
            "path": " / ".join([*current_path, file.get("name") or file.get("filename") or "风格指南"]),
        })

    for child in node.get("children") or []:
        child_name = child.get("name") or ""
        guides.extend(_collect_style_guides(child, [*current_path, child_name]))
    return guides


def _list_style_guide_candidates(db: Session) -> List[dict]:
    candidates: List[dict] = []

    def walk(nodes: List[dict], current_path: List[str]):
        for node in nodes or []:
            node_name = node.get("name") or ""
            next_path = [*current_path, node_name]
            if len(next_path) >= len(STYLE_GUIDE_PATH) and tuple(next_path[-len(STYLE_GUIDE_PATH):]) == STYLE_GUIDE_PATH:
                candidates.extend(_collect_style_guides(node, next_path))
                continue
            walk(node.get("children") or [], next_path)

    walk(get_folder_tree(db, None), [])
    return candidates


def _load_style_guide_bundle(db: Session, style_guide_id: Optional[int]) -> Optional[dict]:
    if style_guide_id:
        guide_file = get_file(db, style_guide_id)
        if not guide_file or not guide_file.file_path or not os.path.exists(guide_file.file_path):
            return None
        content = read_file_safe(guide_file.file_path).strip()
        if not content:
            return None
        if len(content) > STYLE_GUIDE_MAX_CHARS:
            content = content[:STYLE_GUIDE_MAX_CHARS] + "\n\n...（指南内容已截断以避免 prompt 超长）"
        guide_name = guide_file.name or guide_file.filename or "风格指南"
        return {
            "mode": "selected",
            "guides": [{
                "id": guide_file.id,
                "name": guide_name,
                "language": _infer_guide_language(guide_name),
                "content": content,
            }],
        }

    guides = []
    for item in _list_style_guide_candidates(db):
        try:
            content = read_file_safe(item["file_path"]).strip()
        except Exception:
            continue
        if not content:
            continue
        if len(content) > STYLE_GUIDE_MAX_CHARS:
            content = content[:STYLE_GUIDE_MAX_CHARS] + "\n\n...（指南内容已截断以避免 prompt 超长）"
        guides.append({
            "id": item["id"],
            "name": item["name"],
            "path": item["path"],
            "language": _infer_guide_language(item["name"]),
            "content": content,
        })

    if not guides:
        return None
    return {"mode": "auto", "guides": guides}


async def _load_template_reference(template_file: Optional[UploadFile]) -> Optional[dict]:
    if not template_file:
        return None

    raw = await template_file.read()
    if not raw:
        return None

    suffix = os.path.splitext(template_file.filename or "")[1] or ".txt"
    try:
        with tempfile.TemporaryDirectory(prefix="image-template-") as temp_dir:
            temp_path = os.path.join(temp_dir, f"template{suffix}")
            with open(temp_path, "wb") as handle:
                handle.write(raw)
            content = parse_file(temp_path).strip()
    except Exception:
        try:
            content = raw.decode("utf-8", errors="replace").strip()
        except Exception:
            return None

    if not content:
        return None

    return {
        "name": template_file.filename or "模板文件",
        "content": content[:TEMPLATE_MAX_CHARS],
    }


@router.post("/")
async def generate_content(request: GenerateRequest):
    try:
        from app.utils.ai_client import ai_client

        ai_result = ai_client.generate_content(
            request.product_name,
            request.product_model,
            request.doc_type,
            request.target_chapter,
        )

        content = ""
        sections = []
        if isinstance(ai_result, dict):
            content = ai_result.get("content") or ai_result.get("text") or ""
            sections = ai_result.get("sections") or []
        elif isinstance(ai_result, str):
            content = ai_result

        if not content:
            raise RuntimeError("empty ai result")

        if not sections:
            lines = [ln.strip() for ln in content.split("\n") if ln.strip()]
            for i, ln in enumerate(lines[:8]):
                sections.append({
                    "title": ln[:40],
                    "level": 1 if i == 0 else 2,
                    "content": ln[:200]
                })

        return {
            "product_name": request.product_name,
            "product_model": request.product_model,
            "doc_type": request.doc_type,
            "target_chapter": request.target_chapter,
            "content": content,
            "sections": sections,
        }
    except Exception:
        fb = _generate_fallback(
            request.product_name,
            request.product_model,
            request.doc_type,
            request.target_chapter,
        )
        return {
            "product_name": request.product_name,
            "product_model": request.product_model,
            "doc_type": request.doc_type,
            "target_chapter": request.target_chapter,
            "content": fb["content"],
            "sections": fb["sections"],
        }


@router.post("/image-steps")
async def generate_image_steps(
    files: List[UploadFile] = File(...),
    template_file: Optional[UploadFile] = File(None),
    prompt: str = Form(""),
    style_guide_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    started_at = time.monotonic()
    valid_images = []
    for index, file in enumerate(files, start=1):
        raw = await file.read()
        if not raw:
            continue
        content_type = file.content_type or "image/png"
        if not content_type.startswith("image/"):
            continue
        valid_images.append({
            "name": file.filename or f"image-{index}.png",
            "content_type": content_type,
            "raw": raw,
        })

    if not valid_images:
        raise HTTPException(status_code=400, detail="请上传至少一张有效图片")

    from app.utils.ai_client import ai_client

    print(f"[image-steps] request received, images={len(valid_images)}, template={'yes' if template_file and template_file.filename else 'no'}, style_guide_id={style_guide_id or 'auto'}")

    image_entries = []
    original_size = 0
    prepared_size = 0
    for item in valid_images:
        original_size += len(item["raw"])
        prepared_raw, prepared_type = _prepare_model_image(item["raw"], item["content_type"])
        prepared_size += len(prepared_raw)
        image_entries.append({
            "name": item["name"],
            "data_url": ai_client.build_image_data_url(prepared_raw, item["name"], prepared_type),
        })
    style_guide_bundle = _load_style_guide_bundle(db, style_guide_id) if style_guide_id else None
    template_reference = await _load_template_reference(template_file)

    try:
        print(f"[image-steps] prepared images, original={original_size}, prepared={prepared_size}")
        result = ai_client.analyze_images_to_steps(
            image_entries,
            user_prompt=prompt,
            style_guide_bundle=style_guide_bundle,
            template_reference=template_reference,
        )
        if not result or not result.get("steps"):
            raise RuntimeError("empty image analysis result")
        elapsed = time.monotonic() - started_at
        print(f"[image-steps] success, model={result.get('model')}, steps={len(result.get('steps') or [])}, elapsed={elapsed:.1f}s")
        draft_key = uuid.uuid4().hex
        DRAFT_CACHE[draft_key] = {
            "draft": {
                "summary": result.get("summary") or "",
                "relation_summary": result.get("relation_summary") or "",
                "steps": result.get("steps") or [],
            },
            "created_at": time.time(),
        }
        if len(DRAFT_CACHE) > DRAFT_CACHE_MAX:
            oldest = sorted(DRAFT_CACHE.keys(), key=lambda k: DRAFT_CACHE[k].get("created_at", 0))[0]
            del DRAFT_CACHE[oldest]
        return {
            "summary": result.get("summary") or "",
            "relation_summary": result.get("relation_summary") or "",
            "steps": result.get("steps") or [],
            "used_style_guide_name": _resolve_used_style_guide_name(style_guide_bundle, result),
            "model": result.get("model") or "kimi",
            "draft_key": draft_key,
            "warning": "",
        }
    except Exception as e:
        import traceback
        elapsed = time.monotonic() - started_at
        print(f"[image-steps] fallback: {e}, elapsed={elapsed:.1f}s")
        traceback.print_exc()
        fallback = _image_steps_fallback([item["name"] for item in valid_images], prompt)
        return fallback


@router.post("/refine-draft")
async def refine_draft(
    draft_key: str = Form(...),
    template_file: Optional[UploadFile] = File(None),
    prompt: str = Form(""),
    style_guide_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    entry = DRAFT_CACHE.get(draft_key)
    if not entry:
        raise HTTPException(status_code=404, detail="初稿已过期，请重新上传图片生成")

    draft = entry["draft"]
    if not draft.get("steps"):
        raise HTTPException(status_code=400, detail="缓存的初稿为空，请重新上传图片生成")

    style_guide_bundle = _load_style_guide_bundle(db, style_guide_id) if style_guide_id else None
    template_reference = await _load_template_reference(template_file)

    if not style_guide_bundle and not template_reference and not str(prompt or "").strip():
        return {
            "summary": draft["summary"],
            "relation_summary": draft["relation_summary"],
            "steps": draft["steps"],
            "used_style_guide_name": "",
            "model": "kimi-draft",
            "draft_key": draft_key,
            "warning": "",
        }

    from app.utils.ai_client import ai_client

    started_at = time.monotonic()
    refined = ai_client._refine_image_steps_text(
        draft,
        style_guide_bundle=style_guide_bundle,
        template_reference=template_reference,
        user_prompt=prompt,
        timeout=90,
    )

    if refined:
        entry["draft"] = {
            "summary": refined.get("summary") or draft.get("summary"),
            "relation_summary": refined.get("relation_summary") or draft.get("relation_summary"),
            "steps": refined.get("steps") or draft.get("steps"),
        }
        entry["created_at"] = time.time()
        elapsed = time.monotonic() - started_at
        print(f"[refine-draft] success, key={draft_key[:8]}..., model={refined.get('model')}, elapsed={elapsed:.1f}s")
        return {
            "summary": entry["draft"]["summary"],
            "relation_summary": entry["draft"]["relation_summary"],
            "steps": entry["draft"]["steps"],
            "used_style_guide_name": refined.get("used_style_guide_name") or "",
            "model": refined.get("model") or "kimi",
            "draft_key": draft_key,
            "warning": "",
        }

    elapsed = time.monotonic() - started_at
    print(f"[refine-draft] refine failed, returning cached draft, elapsed={elapsed:.1f}s")
    return {
        "summary": draft["summary"],
        "relation_summary": draft["relation_summary"],
        "steps": draft["steps"],
        "used_style_guide_name": "",
        "model": "kimi-draft",
        "draft_key": draft_key,
        "warning": "模板/风格指南改写未返回有效步骤，当前展示读图初稿，可更换模板后重试",
    }
