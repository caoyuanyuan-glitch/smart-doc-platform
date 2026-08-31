"""DOCX/PDF pairing contract for dual-input review."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import re


MODE_DOCX_PDF = "docx+pdf"
MODE_DOCX_ONLY = "docx"
MODE_PDF_ONLY = "pdf"
MODE_CONVERTED = "converted_docx"


@dataclass
class PairingResult:
    input_mode: str
    pairing_status: str
    pairing_confidence: int
    content_source_file_id: int | None = None
    visual_source_file_id: int | None = None
    source_format: str = "docx"
    message: str = ""
    needs_user_confirm: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _stem(name: str) -> str:
    stem = Path(str(name or "")).stem.lower()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", stem)


def resolve_input_pairing(
    content_doc,
    visual_doc=None,
    *,
    explicit: bool = False,
    same_user: bool = True,
    same_task: bool = True,
) -> PairingResult:
    content_type = str(getattr(content_doc, "file_type", "") or "").lower()
    content_id = getattr(content_doc, "id", None)
    if visual_doc is None:
        if content_type == "pdf":
            return PairingResult(
                input_mode="C",
                pairing_status="pdf_only",
                pairing_confidence=100,
                content_source_file_id=content_id,
                visual_source_file_id=content_id,
                source_format="pdf",
                message="未提供 DOCX，使用 PDF 文本层与视觉层联合解析。",
            )
        return PairingResult(
            input_mode="B",
            pairing_status="docx_only",
            pairing_confidence=100,
            content_source_file_id=content_id,
            source_format="docx",
            message="未提供 PDF，未完成最终版式复核。",
        )

    visual_id = getattr(visual_doc, "id", None)
    if explicit:
        return PairingResult(
            input_mode="A",
            pairing_status="paired",
            pairing_confidence=100,
            content_source_file_id=content_id,
            visual_source_file_id=visual_id,
            source_format=MODE_DOCX_PDF,
        )

    if not same_user or not same_task:
        return PairingResult(
            input_mode="A",
            pairing_status="unpaired",
            pairing_confidence=0,
            content_source_file_id=content_id,
            visual_source_file_id=visual_id,
            source_format="docx",
            message="配对校验失败，请确认 PDF 是否属于本次审核。",
            needs_user_confirm=True,
        )

    content_name = str(getattr(content_doc, "filename", "") or "")
    visual_name = str(getattr(visual_doc, "filename", "") or "")
    stem_ok = bool(_stem(content_name) and _stem(content_name) == _stem(visual_name))
    confidence = 80 if stem_ok else 30
    if not stem_ok:
        return PairingResult(
            input_mode="A",
            pairing_status="unpaired",
            pairing_confidence=confidence,
            content_source_file_id=content_id,
            visual_source_file_id=visual_id,
            source_format="docx",
            message="文件名主干不一致，未静默合并，请确认配对。",
            needs_user_confirm=True,
        )
    return PairingResult(
        input_mode="A",
        pairing_status="paired",
        pairing_confidence=confidence,
        content_source_file_id=content_id,
        visual_source_file_id=visual_id,
        source_format=MODE_DOCX_PDF,
    )
