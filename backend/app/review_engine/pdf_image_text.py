# -*- coding: utf-8 -*-
"""图内文字提取通路（OCR 发现通道）。

背景（2026-11-24 园园裁定）：截图/流程图/界面图内的文字不在 PDF 文本层，
规则与 AI 都看不到（T7RS R02 的 Workpace 拼写、流程图内"面:"均因此漏报），
这类文字应可识别。

通路设计（key 后补即启用，无需改代码）：
  1. 挑页：只处理「图片型页面」——页面含图片且图片面积占比达标
     （REVIEW_PDF_IMAGE_TEXT_MIN_RATIO，默认 0.05），按占比降序取前
     REVIEW_PDF_IMAGE_TEXT_PAGE_LIMIT 页（默认 12）控制 token 成本；
  2. 渲染：fitz 按 REVIEW_PDF_VISUAL_VERIFY_SCALE 渲染 PNG；
  3. 提取：ai_client.extract_page_text_from_image（qwen/kimi VL，按
     REVIEW_VISUAL_PROVIDERS 链回退；无 key 时 status=unavailable 零成本降级）；
  4. diff：VLM 输出逐行与该页文本层比对（NFKC+去空白归一化），只保留
     「图内独有行」——正文已有的行丢弃，避免规则重复报；
  5. 拼接：返回 augment 文本块（带页码标记），由 review.py 追加到 content
     尾部，规则层（拼写近形词/半角标点/单位间距）与 AI 层共用同一上下文。

开关：REVIEW_PDF_IMAGE_TEXT_EXTRACT（默认 1=开；无视觉 key 时自然降级）。
"""
from __future__ import annotations

import os
import re
import unicodedata
from typing import Any

import fitz


def _env_flag(name: str, default: str = "1") -> bool:
    return str(os.getenv(name, default) or "").strip().lower() in {"1", "true", "yes", "on"}


def _norm_line(line: str) -> str:
    text = unicodedata.normalize("NFKC", str(line or ""))
    return re.sub(r"\s+", "", text).lower()


def _image_area_ratio(page: "fitz.Page") -> float:
    page_area = abs(page.rect) or 1.0
    total = 0.0
    try:
        for info in page.get_image_info():
            bbox = info.get("bbox")
            if not bbox:
                continue
            rect = fitz.Rect(bbox) & page.rect
            total += abs(rect)
    except Exception:
        return 0.0
    return min(total / page_area, 1.0)


def select_image_pages(doc: "fitz.Document", *, limit: int, min_ratio: float) -> list[int]:
    """挑「图片型页面」：图片面积占比达标的页，按占比降序，取前 limit 页。"""
    scored: list[tuple[float, int]] = []
    for pno, page in enumerate(doc, start=1):
        try:
            ratio = _image_area_ratio(page)
        except Exception:
            continue
        if ratio >= min_ratio:
            scored.append((ratio, pno))
    scored.sort(reverse=True)
    return [pno for _, pno in scored[: max(0, limit)]]


def _diff_image_only_lines(vlm_text: str, page_text: str) -> list[str]:
    """VLM 提取行 vs 该页文本层：只保留图内独有行。

    匹配口径：VLM 行归一化后是文本层任一行的子串 → 视为正文重复丢弃
    （VLM 常把一个视觉行拆成几段，整行精确匹配会漏）。
    """
    text_layer_norms = [
        _norm_line(l) for l in (page_text or "").splitlines() if _norm_line(l)
    ]
    kept: list[str] = []
    seen: set[str] = set()
    for raw in str(vlm_text or "").splitlines():
        line = raw.strip()
        norm = _norm_line(line)
        if len(norm) < 2:  # 单字符噪声（页码碎片、装饰符号）丢弃
            continue
        if norm in seen:
            continue
        if any(norm in t or t in norm for t in text_layer_norms):
            continue  # 与文本层互为子串 = 正文已有
        seen.add(norm)
        kept.append(line)
    return kept


def augment_pdf_image_text(pdf_path: str, *, review_id: int | None = None) -> tuple[str, dict]:
    """主入口：返回 (augment_text, diagnostics)。

    augment_text 为空串时表示未启用/无可用视觉 provider/无图内独有文字，
    调用方直接跳过拼接。
    """
    diagnostics: dict[str, Any] = {
        "enabled": False,
        "status": "disabled",
        "pages_selected": [],
        "pages_extracted": [],
        "image_only_lines": 0,
    }
    if not _env_flag("REVIEW_PDF_IMAGE_TEXT_EXTRACT"):
        return "", diagnostics
    diagnostics["enabled"] = True

    from app.utils.ai_client import ai_client  # 延迟导入，避免循环依赖

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        diagnostics["status"] = f"open_failed:{exc}"
        return "", diagnostics

    limit = int(os.getenv("REVIEW_PDF_IMAGE_TEXT_PAGE_LIMIT", "12") or 12)
    # 0.15 时 R02 只选 3 页（22%/19%/16%），小截图页全漏；降到 0.05 覆盖
    # 绝大多数含图页（R02 含图 >1% 共 11 页，0.05 覆盖 9 页）
    min_ratio = float(os.getenv("REVIEW_PDF_IMAGE_TEXT_MIN_RATIO", "0.05") or 0.05)
    scale = float(os.getenv("REVIEW_PDF_VISUAL_VERIFY_SCALE", "1.8") or 1.8)
    try:
        pages = select_image_pages(doc, limit=limit, min_ratio=min_ratio)
        diagnostics["pages_selected"] = pages
        if not pages:
            diagnostics["status"] = "no_image_pages"
            return "", diagnostics

        sections: list[str] = []
        for pno in pages:
            page = doc[pno - 1]
            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
                png = pix.tobytes("png")
            except Exception as exc:
                print(f"[视觉] 页面渲染失败 p{pno}: {exc}", flush=True)
                continue
            result = ai_client.extract_page_text_from_image(png, page_number=pno, review_id=review_id)
            if result.get("status") != "ok":
                diagnostics["status"] = str(result.get("reason") or result.get("status"))
                # provider 整体不可用（无 key）时不必再试后续页
                if str(result.get("status")) == "unavailable":
                    return "", diagnostics
                continue
            try:
                page_text = page.get_text("text")
            except Exception:
                page_text = ""
            image_only = _diff_image_only_lines(result.get("text", ""), page_text)
            if image_only:
                diagnostics["pages_extracted"].append(pno)
                diagnostics["image_only_lines"] += len(image_only)
                sections.append(
                    f"【第 {pno} 页 图片内文字（OCR 提取，仅供文字本身检查）】\n"
                    + "\n".join(image_only)
                )
        diagnostics["status"] = "ok" if sections else "no_image_only_text"
        return "\n\n".join(sections), diagnostics
    finally:
        doc.close()
