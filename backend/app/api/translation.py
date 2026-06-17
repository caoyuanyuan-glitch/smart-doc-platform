from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import os
import zipfile
import tempfile
import sys
import xml.etree.ElementTree as ET
import lxml.etree as ET_LXML
import re

from app.database import get_db
from app.schemas.translation import TranslationRequest, TranslationResponse, MemoryEntry, MemoryEntryOut, TranslationDocOut
from app.crud.document import get_document, get_documents
from app.crud.review import get_reviews
from app.crud.memory import (
    create_memory_entry, get_memory_entries, get_memory_entry,
    delete_memory_entry, search_memory
)
from app.models.translation_doc import TranslationDoc
from app.utils.document_parser import parse_file
from app.utils.ai_client import ai_client

router = APIRouter()

UPLOAD_DIR = "./static/uploads/translation"
TRANSLATION_OUTPUT_DIR = "./static/translations"


def translate_with_ai(content: str, model: str, source_lang: str, target_lang: str) -> str:
    lang_names = {
        "zh": "中文", "en": "英文", "ja": "日文", "ko": "韩文",
        "fr": "法文", "de": "德文", "es": "西班牙文", "ru": "俄文"
    }
    src_name = lang_names.get(source_lang, source_lang)
    tgt_name = lang_names.get(target_lang, target_lang)

    prompt = f"""你是一个专业的技术文档翻译引擎。请将以下{src_name}文本翻译为{tgt_name}。

翻译规则：
1. 必须严格将原文内容翻译为{tgt_name}，输出必须是纯{tgt_name}文本，不得包含{src_name}
2. 保持原文的段落结构、编号、列表格式完全不变
3. 使用专业准确的技术术语
4. 只输出翻译后的{tgt_name}结果，不要添加任何解释、注释或原始文本

原文：
{content[:8000]}"""
    messages = [{"role": "user", "content": prompt}]

    if model == "deepseek":
        result = ai_client.call_deepseek(messages, max_tokens=4096)
        if result is None:
            result = ai_client.call_qwen(messages, max_tokens=4096)
    else:
        result = ai_client.call_qwen(messages, max_tokens=4096)
        if result is None:
            result = ai_client.call_deepseek(messages, max_tokens=4096)

    if result is None:
        raise HTTPException(
            status_code=500,
            detail="AI翻译引擎不可用，请检查 QWEN (DASHSCOPE_API_KEY) 或 DeepSeek (DEEPSEEK_API_KEY) 的 API Key 是否已配置"
        )

    return result


def translate_with_memory(content: str, source_lang: str, target_lang: str,
                          db: Session) -> tuple:
    memory_result = search_memory(db, content, source_lang, target_lang)
    if memory_result:
        return memory_result, True
    return None, False


@router.post("/translate", response_model=TranslationResponse)
async def translate_text(req: TranslationRequest, db: Session = Depends(get_db)):
    translated = None
    from_memory = False
    from_ai = False
    engine = req.engine

    if engine in ["memory", "hybrid"]:
        result, hit = translate_with_memory(req.content, req.source_lang, req.target_lang, db)
        if hit:
            translated = result
            from_memory = True
            if engine == "memory":
                return TranslationResponse(
                    original=req.content,
                    translated=translated,
                    engine_used="memory",
                    from_memory=True,
                    from_ai=False
                )

    if engine in ["ai", "hybrid"] and not translated:
        translated = translate_with_ai(req.content, req.model, req.source_lang, req.target_lang)
        from_ai = True

        if engine == "hybrid":
            create_memory_entry(
                db=db,
                source_text=req.content,
                translated_text=translated,
                source_lang=req.source_lang,
                target_lang=req.target_lang
            )

    if not translated:
        raise HTTPException(status_code=500, detail="翻译失败，AI和记忆库引擎均未返回结果")

    return TranslationResponse(
        original=req.content,
        translated=translated,
        engine_used=engine,
        from_memory=from_memory,
        from_ai=from_ai
    )


@router.post("/translate/file")
async def translate_file(
    file: UploadFile = File(...),
    engine: str = Form("hybrid"),
    model: str = Form("qwen"),
    source_lang: str = Form("zh"),
    target_lang: str = Form("en"),
    db: Session = Depends(get_db)
):
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR, exist_ok=True)

    filename = file.filename
    file_path = os.path.join(UPLOAD_DIR, filename)

    try:
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    ext = os.path.splitext(filename)[1].lower()

    if not os.path.exists(TRANSLATION_OUTPUT_DIR):
        os.makedirs(TRANSLATION_OUTPUT_DIR, exist_ok=True)

    base_name = os.path.splitext(filename)[0]
    translated_filename = _translate_filename(base_name, source_lang, target_lang)
    output_filename = f"{translated_filename}{ext}"
    output_path = os.path.join(TRANSLATION_OUTPUT_DIR, output_filename)

    all_original_parts = []
    all_translated_parts = []

    def _do_translate(text: str) -> str:
        result = None
        if engine in ["memory", "hybrid"]:
            r, hit = translate_with_memory(text, source_lang, target_lang, db)
            if hit:
                result = r
        if engine in ["ai", "hybrid"] and not result:
            result = translate_with_ai(text, model, source_lang, target_lang)
        if not result:
            raise HTTPException(status_code=500, detail="翻译失败")
        return result

    def _translate_dita_xml(fpath: str) -> str:
        with open(fpath, "rb") as f:
            raw_bytes = f.read()
        raw_str = raw_bytes.decode("utf-8")

        ns_decls = re.findall(r'xmlns:(\w+)="([^"]*)"', raw_str)
        for prefix, uri in ns_decls:
            if prefix:
                ET_LXML.register_namespace(prefix, uri)

        parser = ET_LXML.XMLParser(remove_blank_text=False, strip_cdata=False)
        tree = ET_LXML.parse(fpath, parser)
        root = tree.getroot()

        def _translate_element(elem):
            if elem.text and elem.text.strip():
                orig = elem.text
                stripped = orig.strip()
                translated = _do_translate(stripped)
                elem.text = orig.replace(stripped, translated, 1)
                all_original_parts.append(stripped)
                all_translated_parts.append(translated)

            for child in elem:
                _translate_element(child)

            if elem.tail and elem.tail.strip():
                orig = elem.tail
                stripped = orig.strip()
                translated = _do_translate(stripped)
                elem.tail = orig.replace(stripped, translated, 1)
                all_original_parts.append(stripped)
                all_translated_parts.append(translated)

        _translate_element(root)

        doctype = tree.docinfo.doctype
        result_bytes = ET_LXML.tostring(
            tree,
            xml_declaration=True,
            encoding="UTF-8",
            doctype=doctype,
            pretty_print=False,
        )
        return result_bytes.decode("utf-8")

    def _translate_xlf_xml(fpath: str) -> str:
        tree = ET.parse(fpath)
        root_xliff = tree.getroot()
        xliff_ns = "urn:oasis:names:tc:xliff:document:1.2"
        ET.register_namespace("", xliff_ns)

        for trans_unit in root_xliff.iter(f"{{{xliff_ns}}}trans-unit"):
            source_el = trans_unit.find(f"{{{xliff_ns}}}source")
            if source_el is None:
                continue

            target_parts = []
            text_segments = []

            if source_el.text and source_el.text.strip():
                seg = source_el.text.strip()
                text_segments.append(seg)
                target_parts.append(_do_translate(seg))

            for child in list(source_el):
                child_tail = child.tail
                child.tail = None
                tag_str = ET.tostring(child, encoding="unicode").strip()
                child.tail = child_tail
                target_parts.append(tag_str)
                if child_tail and child_tail.strip():
                    seg = child_tail.strip()
                    text_segments.append(seg)
                    target_parts.append(_do_translate(seg))

            if not target_parts:
                continue

            target_content = "".join(target_parts)
            target_el = trans_unit.find(f"{{{xliff_ns}}}target")
            target_str = f"<target>{target_content}</target>"
            try:
                target_fragment = ET.fromstring(target_str)
            except Exception:
                continue
            if target_el is not None:
                trans_unit.remove(target_el)
            trans_unit.append(target_fragment)
            target_fragment.set("state", "translated")

            all_original_parts.append(" ".join(text_segments))
            all_translated_parts.append(target_content)

        return ET.tostring(root_xliff, encoding="unicode")

    def _translate_pptx_xml(fpath: str) -> bytes:
        """Translate text in PPTX slides, preserving all formatting and non-text content."""
        import io as pptx_io
        pptx_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"

        in_buf = pptx_io.BytesIO()
        with open(fpath, "rb") as f:
            in_buf.write(f.read())
        in_buf.seek(0)

        pptx_original = []
        pptx_translated = []

        out_buf = pptx_io.BytesIO()
        with zipfile.ZipFile(in_buf, 'r') as z_in:
            with zipfile.ZipFile(out_buf, 'w', zipfile.ZIP_DEFLATED) as z_out:
                for zinfo in z_in.infolist():
                    raw = z_in.read(zinfo)
                    name = zinfo.filename
                    if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                        slide_xml = raw.decode("utf-8")
                        root = ET.fromstring(slide_xml)
                        for t_elem in root.iter(f"{{{pptx_ns}}}t"):
                            if t_elem.text and t_elem.text.strip():
                                original_text = t_elem.text.strip()
                                translated = _do_translate(original_text)
                                pptx_original.append(original_text)
                                pptx_translated.append(translated)
                                t_elem.text = translated
                                xml_space = t_elem.get("{http://www.w3.org/XML/1998/namespace}space")
                                if xml_space != "preserve" and translated.strip() == translated:
                                    pass
                        new_xml = ET.tostring(root, encoding="unicode")
                        if not new_xml.startswith("<?xml"):
                            new_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + new_xml
                        raw = new_xml.encode("utf-8")
                    z_out.writestr(zinfo, raw)
        out_buf.seek(0)

        all_original_parts.append("\n".join(pptx_original))
        all_translated_parts.append("\n".join(pptx_translated))

        return out_buf.read()

    try:
        if ext == ".zip":
            with tempfile.TemporaryDirectory() as tmpdir:
                translated_files = []

                with zipfile.ZipFile(file_path, 'r') as zf:
                    for zinfo in zf.infolist():
                        if zinfo.is_dir():
                            continue
                        zip_name = zinfo.filename

                        safe_fname = f"_tmp_{len(translated_files)}{os.path.splitext(zip_name)[1]}"
                        safe_fpath = os.path.join(tmpdir, safe_fname)

                        try:
                            with open(safe_fpath, "wb") as sf:
                                sf.write(zf.read(zinfo))
                        except Exception:
                            continue

                        _, name_ext = os.path.splitext(zip_name)
                        ext_lower = name_ext.lower()

                        if ext_lower == ".dita":
                            try:
                                translated_content = _translate_dita_xml(safe_fpath)
                            except Exception:
                                continue
                        elif ext_lower == ".xlf":
                            try:
                                translated_content = _translate_xlf_xml(safe_fpath)
                            except Exception:
                                continue
                        elif ext_lower == ".pptx":
                            try:
                                translated_content = _translate_pptx_xml(safe_fpath)
                            except Exception:
                                continue
                        else:
                            try:
                                file_content = parse_file(safe_fpath)
                                if not file_content.strip():
                                    continue
                            except Exception:
                                continue
                            translated_content = _do_translate(file_content)
                            all_original_parts.append(file_content)
                            all_translated_parts.append(translated_content)

                        dir_part, name_part = os.path.split(zip_name)
                        name_base = os.path.splitext(name_part)[0]
                        new_name = _translate_filename(name_base, source_lang, target_lang)
                        new_rel = os.path.join(dir_part, f"{new_name}{name_ext}") if dir_part else f"{new_name}{name_ext}"

                        translated_files.append((new_rel, translated_content))

                        if os.path.exists(safe_fpath):
                            os.remove(safe_fpath)

                if not translated_files:
                    raise HTTPException(status_code=400, detail="ZIP包中未找到可翻译的文件")

                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as out_zf:
                    for rel_path, content in translated_files:
                        if isinstance(content, bytes):
                            out_zf.writestr(rel_path, content)
                        else:
                            out_zf.writestr(rel_path, content.encode("utf-8"))

        elif ext == ".dita":
            translated_xml = _translate_dita_xml(file_path)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(translated_xml)

        elif ext == ".xlf":
            translated_xml = _translate_xlf_xml(file_path)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(translated_xml)

        elif ext == ".pptx":
            translated_bytes = _translate_pptx_xml(file_path)
            with open(output_path, "wb") as f:
                f.write(translated_bytes)

        else:
            content = parse_file(file_path)
            if not content.strip():
                raise HTTPException(status_code=400, detail="无法从文件中提取文本内容")

            translated = _do_translate(content)
            all_original_parts.append(content)
            all_translated_parts.append(translated)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(translated)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件处理失败: {str(e)}")

    original_content = "\n\n".join(all_original_parts)
    translated_content = "\n\n".join(all_translated_parts)

    doc = TranslationDoc(
        filename=filename,
        file_type=ext.replace(".", ""),
        source_lang=source_lang,
        target_lang=target_lang,
        engine=engine,
        model=model if engine != "memory" else "memory",
        original_content=original_content[:8000],
        translated_content=translated_content[:8000],
        translated_filename=output_filename,
        original_preview=original_content[:500] + "..." if len(original_content) > 500 else original_content,
        translated_preview=translated_content[:500] + "..." if len(translated_content) > 500 else translated_content
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "message": "翻译完成",
        "doc_id": doc.id,
        "original_filename": filename,
        "translated_filename": output_filename,
        "download_url": f"/api/translation/download/{doc.id}"
    }


def _translate_filename(filename: str, source_lang: str, target_lang: str) -> str:
    if source_lang == target_lang:
        return filename

    lang_names = {
        "zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
        "fr": "French", "de": "German", "es": "Spanish", "ru": "Russian"
    }
    src_name = lang_names.get(source_lang, source_lang)
    tgt_name = lang_names.get(target_lang, target_lang)

    prompt = f'Translate this filename from {src_name} to {tgt_name}. Output ONLY the translated filename, no other text: "{filename}"'
    messages = [{"role": "user", "content": prompt}]
    result = ai_client._call_model(messages, max_tokens=500)

    if result:
        translated = result.strip().strip('"').strip("'").replace("/", "_").replace("\\", "_").replace(":", "_")
        if translated and translated != filename:
            return translated

    return filename


@router.get("/download/{doc_id}")
async def download_translated_file(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(TranslationDoc).filter(TranslationDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Translation doc not found")

    output_filename = doc.translated_filename
    if not output_filename:
        ext = os.path.splitext(doc.filename)[1].lower()
        output_filename = f"{os.path.splitext(doc.filename)[0]}_translated{ext}"

    output_path = os.path.join(TRANSLATION_OUTPUT_DIR, output_filename)

    if os.path.exists(output_path):
        media_type = "application/octet-stream"
        if output_filename.endswith(".zip"):
            media_type = "application/zip"
        elif output_filename.endswith(".xlf"):
            media_type = "application/xliff+xml"
        return FileResponse(
            path=output_path,
            filename=output_filename,
            media_type=media_type
        )

    raise HTTPException(status_code=404, detail="文件不存在")


@router.get("/reviewed-docs")
async def get_reviewed_documents(db: Session = Depends(get_db)):
    reviews = get_reviews(db)
    reviewed_doc_ids = set()
    for review in reviews:
        if review.status == "completed":
            reviewed_doc_ids.add(review.document_id)

    documents = get_documents(db, limit=500)
    result = []
    for doc in documents:
        if doc.id in reviewed_doc_ids:
            result.append({
                "id": doc.id,
                "filename": doc.filename,
                "file_type": doc.file_type,
                "preview": doc.preview,
                "created_at": doc.created_at.isoformat() if doc.created_at else None
            })

    return result


@router.get("/memory", response_model=list[MemoryEntryOut])
async def list_memory_entries(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    keyword: str = Query(None),
    db: Session = Depends(get_db)
):
    return get_memory_entries(db, skip=skip, limit=limit, keyword=keyword)


@router.post("/memory", response_model=MemoryEntryOut)
async def add_memory_entry(entry: MemoryEntry, db: Session = Depends(get_db)):
    return create_memory_entry(
        db=db,
        source_text=entry.source_text,
        translated_text=entry.translated_text,
        source_lang=entry.source_lang,
        target_lang=entry.target_lang,
        tags=entry.tags
    )


@router.delete("/memory/{entry_id}")
async def remove_memory_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = delete_memory_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return {"message": "Memory entry deleted successfully"}


@router.get("/docs", response_model=list[TranslationDocOut])
async def list_translation_docs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db)
):
    docs = db.query(TranslationDoc).order_by(TranslationDoc.created_at.desc()).offset(skip).limit(limit).all()
    return docs


@router.get("/docs/{doc_id}", response_model=TranslationDocOut)
async def get_translation_doc(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(TranslationDoc).filter(TranslationDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Translation doc not found")
    return doc


@router.delete("/docs/{doc_id}")
async def delete_translation_doc(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(TranslationDoc).filter(TranslationDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Translation doc not found")
    db.delete(doc)
    db.commit()
    return {"message": "Translation doc deleted successfully"}
