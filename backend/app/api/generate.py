from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter()


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
