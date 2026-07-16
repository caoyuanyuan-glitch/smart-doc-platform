import json
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
TERMINOLOGY_PATH = ("资源库", "术语库")
STYLE_GUIDE_MAX_CHARS = 1500  # 截断风格指南以避免 prompt 超长
TERMINOLOGY_MAX_CHARS = 3000
TEMPLATE_MAX_CHARS = 2000
MODEL_IMAGE_MAX_EDGE = 700
MODEL_IMAGE_QUALITY = 65

INTENT_INSTRUCTIONS = {
    "product_appearance": "生成意图：产品外观描述。重点描述产品整体外观、结构组成、可见部件、布局关系、颜色材质和可识别标识。",
    "operation_steps": "生成意图：操作步骤说明。重点从图片中识别连续操作步骤，输出可执行动作、点击对象、输入内容和页面跳转结果。",
    "interface_manual": "生成意图：界面功能说明。重点说明界面区域、功能入口、控件用途、状态提示和用户可执行操作。",
    "custom": "生成意图：自定义。优先遵循用户在补充要求中说明的生成目标。",
}

OUTPUT_FORMAT_INSTRUCTIONS = {
    "plain_text": "输出格式：纯文本。使用自然段组织内容，避免强制编号。",
    "numbered_steps": "输出格式：带编号步骤。按 1、2、3 的顺序输出步骤，每条步骤表达一个清晰动作或说明点。",
}

LANGUAGE_STYLE_INSTRUCTIONS = {
    "formal_technical": "语言风格：正式技术文档。使用规范、客观、可直接进入说明书的表达。",
    "concise": "语言风格：简要说明。使用简洁句式，保留关键信息，减少背景铺垫。",
}

CONTINUATION_INTENT_INSTRUCTIONS = {
    "next_step": "续写意图：续写下一步操作。基于上下文推断下一步可执行动作，重点写清操作对象、动作和结果。",
    "expand_detail": "续写意图：扩写详细说明。补充参数条件、确认动作、注意事项或状态变化，避免偏离原文主题。",
    "safety_warning": "续写意图：补充安全警告。识别当前操作中的风险点，输出必要警示和规避措施。",
    "troubleshooting": "续写意图：补充故障处理。基于当前操作步骤补充异常现象、检查项和恢复操作。",
    "custom": "续写意图：自定义。严格遵循用户提供的自定义续写要求。",
}

CONTINUATION_LENGTH_INSTRUCTIONS = {
    "short": "续写长度：简短，输出 1-2 句。",
    "detailed": "续写长度：详细，输出 1 个自然段。",
}


class GenerateRequest(BaseModel):
    product_name: str
    product_model: str
    doc_type: str
    target_chapter: str


class ContinueTextRequest(BaseModel):
    source_text: str
    intent: str = "next_step"
    custom_intent: str = ""
    length: str = "short"
    keep_terminology: bool = True
    keep_sentence_style: bool = True


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


def _collect_terminology_files(node: dict, current_path: List[str]) -> List[dict]:
    files = []
    for file in node.get("files") or []:
        file_path = file.get("file_path")
        if not file_path or not os.path.exists(file_path):
            continue
        files.append({
            "id": file.get("id"),
            "name": file.get("name") or file.get("filename") or "术语库文件",
            "file_path": file_path,
            "path": " / ".join([*current_path, file.get("name") or file.get("filename") or "术语库文件"]),
        })

    for child in node.get("children") or []:
        child_name = child.get("name") or ""
        files.extend(_collect_terminology_files(child, [*current_path, child_name]))
    return files


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


def _list_terminology_candidates(db: Session) -> List[dict]:
    candidates: List[dict] = []

    def walk(nodes: List[dict], current_path: List[str]):
        for node in nodes or []:
            node_name = node.get("name") or ""
            next_path = [*current_path, node_name]
            if len(next_path) >= len(TERMINOLOGY_PATH) and tuple(next_path[-len(TERMINOLOGY_PATH):]) == TERMINOLOGY_PATH:
                candidates.extend(_collect_terminology_files(node, next_path))
                continue
            walk(node.get("children") or [], next_path)

    walk(get_folder_tree(db, None), [])
    return candidates


def _read_reference_file(path: str) -> str:
    try:
        return parse_file(path).strip()
    except Exception:
        try:
            return read_file_safe(path).strip()
        except Exception:
            return ""


def _load_terminology_reference(db: Session, enabled: bool) -> Optional[dict]:
    if not enabled:
        return None

    chunks = []
    used_files = []
    remaining = TERMINOLOGY_MAX_CHARS
    for item in _list_terminology_candidates(db):
        content = _read_reference_file(item["file_path"])
        if not content:
            continue
        block = f"文件：{item['path']}\n{content}"
        if len(block) > remaining:
            block = block[:remaining]
        chunks.append(block)
        used_files.append(item["path"])
        remaining -= len(block)
        if remaining <= 0:
            break

    if not chunks:
        return None

    return {
        "files": used_files,
        "content": "\n\n".join(chunks),
    }


def _parse_terminology_pairs(content: str) -> dict:
    terms = {}
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "---" in line:
            continue
        if "|" in line:
            cells = [cell.strip() for cell in line.strip("|").split("|") if cell.strip()]
        elif "\t" in line:
            cells = [cell.strip() for cell in line.split("\t") if cell.strip()]
        elif "," in line:
            cells = [cell.strip() for cell in line.split(",") if cell.strip()]
        else:
            continue
        if len(cells) < 2:
            continue
        lowered = " ".join(cells[:3]).lower()
        if any(token in lowered for token in ["非标准", "标准", "source", "target", "term"]):
            continue
        source, target = cells[0], cells[1]
        if source and target and source != target and len(source) <= 80 and len(target) <= 80:
            terms[source] = target
    return terms


def _apply_terminology_reference(result: dict, terminology_reference: Optional[dict]) -> dict:
    if not terminology_reference:
        return result
    terms = _parse_terminology_pairs(terminology_reference.get("content") or "")
    if not terms:
        return result

    def replace_terms(text: str) -> str:
        updated = str(text or "")
        for source, target in terms.items():
            updated = updated.replace(source, target)
        return updated

    next_result = dict(result)
    next_result["summary"] = replace_terms(next_result.get("summary") or "")
    next_result["relation_summary"] = replace_terms(next_result.get("relation_summary") or "")
    next_result["steps"] = [replace_terms(step) for step in (next_result.get("steps") or [])]
    return next_result


def _build_image_generation_prompt(
    prompt: str,
    generation_intent: str,
    custom_intent: str,
    output_format: str,
    language_style: str,
    terminology_reference: Optional[dict],
) -> str:
    parts = [
        INTENT_INSTRUCTIONS.get(generation_intent) or INTENT_INSTRUCTIONS["operation_steps"],
        OUTPUT_FORMAT_INSTRUCTIONS.get(output_format) or OUTPUT_FORMAT_INSTRUCTIONS["numbered_steps"],
        LANGUAGE_STYLE_INSTRUCTIONS.get(language_style) or LANGUAGE_STYLE_INSTRUCTIONS["formal_technical"],
    ]
    if generation_intent == "custom" and custom_intent.strip():
        parts.append(f"自定义生成意图：{custom_intent.strip()}")
    if terminology_reference:
        parts.append(
            "术语标准：使用知识库资源库/术语库文件中的术语。系统会在读图后对生成结果执行术语标准化。\n"
            f"已关联术语库文件：{'; '.join(terminology_reference.get('files') or [])}"
        )
    if prompt.strip():
        parts.append(f"用户补充要求：{prompt.strip()}")
    return "\n\n".join(parts)


def _build_continuation_prompt(
    request: ContinueTextRequest,
    terminology_reference: Optional[dict],
    style_guide_bundle: Optional[dict],
) -> str:
    parts = [
        "你是技术文档智能续写助手。任务是根据现有内容片段续写后续内容，输出可直接插入说明书或操作文档的文本。",
        CONTINUATION_INTENT_INSTRUCTIONS.get(request.intent) or CONTINUATION_INTENT_INSTRUCTIONS["next_step"],
        CONTINUATION_LENGTH_INSTRUCTIONS.get(request.length) or CONTINUATION_LENGTH_INSTRUCTIONS["short"],
        "续写规则：只输出新增续写内容，不重复原文，不输出标题、解释、JSON、Markdown 代码块或字段名。",
        "语义规则：基于上下文推断合理下一步，不编造具体型号、数值、界面按钮名称或耗材名称。",
    ]
    if request.intent == "custom" and request.custom_intent.strip():
        parts.append(f"自定义续写要求：{request.custom_intent.strip()}")
    if terminology_reference:
        terminology_pairs = _parse_terminology_pairs(terminology_reference.get("content") or "")
        terminology_lines = [
            f"- {source} -> {target}"
            for source, target in list(terminology_pairs.items())[:80]
        ]
        parts.append(
            "术语一致性：优先使用知识库资源库/术语库文件中的标准术语。\n"
            f"已关联术语库文件：{'; '.join(terminology_reference.get('files') or [])}\n"
            + ("术语对照：\n" + "\n".join(terminology_lines) if terminology_lines else "术语对照：未解析到可用术语对")
        )
    if style_guide_bundle and style_guide_bundle.get("guides"):
        guide_blocks = []
        for guide in (style_guide_bundle.get("guides") or [])[:2]:
            guide_blocks.append(f"句式手册：{guide.get('name') or '未命名'}\n{guide.get('content') or ''}")
        parts.append(
            "句式风格：匹配句式手册中的推荐模板、动词选择和技术文档表达习惯。\n"
            + "\n\n".join(guide_blocks)
        )
    parts.append(f"现有内容：\n{request.source_text.strip()}")
    return "\n\n".join(parts)


def _resolve_continuation_max_tokens(length: str) -> int:
    if length == "short":
        return 384
    if length == "detailed":
        return 1024
    return 512


def _clean_continuation_text(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            cleaned = parsed.get("continuation") or parsed.get("content") or parsed.get("text") or cleaned
    except Exception:
        pass
    for prefix in ("续写：", "续写内容：", "continuation:", "content:"):
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix):].strip()
            break
    return cleaned.strip().strip('"\',，,')


def _continuation_fallback(request: ContinueTextRequest) -> str:
    if request.intent == "safety_warning":
        return "请确认相关部件已正确放置并保持稳定，避免因安装不到位导致处理失败。操作过程中如发现异常提示，应停止当前流程并按故障处理说明进行检查。"
    if request.intent == "troubleshooting":
        return "若系统未进入下一步，请检查样本位置、槽盖状态和界面提示信息。确认条件满足后，重新执行当前操作并观察系统反馈。"
    if request.intent == "expand_detail":
        return "执行该操作前，应确认样本、耗材和设备状态均满足使用要求。完成操作后，观察界面状态变化，并根据提示继续后续流程。"
    return "请确认当前操作对象已正确就位，然后点击界面中的开始按钮启动处理流程。系统进入下一步后，按照页面提示继续完成后续操作。"


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


@router.post("/continue-text")
async def continue_text(request: ContinueTextRequest, db: Session = Depends(get_db)):
    source_text = request.source_text.strip()
    if not source_text:
        raise HTTPException(status_code=400, detail="请填写现有内容")
    if len(source_text) > 6000:
        raise HTTPException(status_code=400, detail="现有内容过长，请控制在 6000 字以内")
    if request.intent == "custom" and not request.custom_intent.strip():
        raise HTTPException(status_code=400, detail="请填写自定义续写要求")

    terminology_reference = _load_terminology_reference(db, request.keep_terminology)
    style_guide_bundle = _load_style_guide_bundle(db, None) if request.keep_sentence_style else None
    prompt = _build_continuation_prompt(request, terminology_reference, style_guide_bundle)

    try:
        from app.utils.ai_client import ai_client

        result = ai_client.chat([
            {"role": "system", "content": "你只输出新增续写文本。"},
            {"role": "user", "content": prompt},
        ], max_tokens=_resolve_continuation_max_tokens(request.length), temperature=0.25, kimi_thinking="disabled")
        continuation = _clean_continuation_text(result)
        if not continuation:
            raise RuntimeError("empty continuation")
        return {
            "source_text": source_text,
            "continuation": continuation,
            "used_terminology_files": terminology_reference.get("files") if terminology_reference else [],
            "used_style_guide_name": _resolve_used_style_guide_name(style_guide_bundle, {"steps": [continuation]}) if style_guide_bundle else "",
            "model": "kimi",
            "warning": "",
        }
    except Exception as e:
        print(f"[continue-text] fallback: {e}")
        return {
            "source_text": source_text,
            "continuation": _continuation_fallback(request),
            "used_terminology_files": terminology_reference.get("files") if terminology_reference else [],
            "used_style_guide_name": _resolve_used_style_guide_name(style_guide_bundle, {"steps": []}) if style_guide_bundle else "",
            "model": "fallback",
            "warning": "当前 AI 续写链路未返回有效结果，已展示本地示例续写。",
        }


@router.post("/image-steps")
async def generate_image_steps(
    files: List[UploadFile] = File(...),
    template_file: Optional[UploadFile] = File(None),
    prompt: str = Form(""),
    generation_intent: str = Form("operation_steps"),
    custom_intent: str = Form(""),
    output_format: str = Form("numbered_steps"),
    language_style: str = Form("formal_technical"),
    use_terminology: bool = Form(False),
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

    print(f"[image-steps] request received, images={len(valid_images)}, intent={generation_intent}, output_format={output_format}, terminology={use_terminology}")

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
    terminology_reference = _load_terminology_reference(db, use_terminology)
    enhanced_prompt = _build_image_generation_prompt(
        prompt=prompt,
        generation_intent=generation_intent,
        custom_intent=custom_intent,
        output_format=output_format,
        language_style=language_style,
        terminology_reference=terminology_reference,
    )

    try:
        print(f"[image-steps] prepared images, original={original_size}, prepared={prepared_size}")
        result = ai_client.analyze_images_to_steps(
            image_entries,
            user_prompt=enhanced_prompt,
            style_guide_bundle=style_guide_bundle,
            template_reference=template_reference,
        )
        if not result or not result.get("steps"):
            raise RuntimeError("empty image analysis result")
        result = _apply_terminology_reference(result, terminology_reference)
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
            "used_terminology_files": terminology_reference.get("files") if terminology_reference else [],
            "model": result.get("model") or "kimi",
            "draft_key": draft_key,
            "warning": "",
        }
    except Exception as e:
        import traceback
        elapsed = time.monotonic() - started_at
        print(f"[image-steps] fallback: {e}, elapsed={elapsed:.1f}s")
        traceback.print_exc()
        fallback = _image_steps_fallback([item["name"] for item in valid_images], enhanced_prompt)
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
