import json
import os
import re
import xml.etree.ElementTree as ET


EDITABLE_SUFFIXES = (".dita", ".ditamap", ".xml")
SKIP_NAMES = {"metadata.xml"}

_LI_OR_ENTRY_TEXT = re.compile(
    r"(<(li|entry)(?:\s[^>]*)?>)(\s*)([^<]+?)(\s*)(</\2>)",
    re.DOTALL,
)
_ROOT_OPEN_TAG = re.compile(
    r"(<(?:topic|concept|task|reference|bookmap)\b[^>]*?)(/?>)",
    re.IGNORECASE,
)


def _is_well_formed_xml(text):
    body = re.sub(r"<!DOCTYPE[^>]*>", "", text or "", count=1, flags=re.IGNORECASE)
    try:
        ET.fromstring(body.encode("utf-8"))
        return True
    except Exception:
        return False


def wrap_bare_li_and_entry(xml_text):
    def _repl(match):
        inner = match.group(4).strip()
        if not inner:
            return match.group(0)
        return f"{match.group(1)}{match.group(3)}<p>{inner}</p>{match.group(5)}{match.group(6)}"

    return _LI_OR_ENTRY_TEXT.sub(_repl, xml_text)


def infer_imesofttype(filename):
    stem = os.path.splitext(os.path.basename(filename or ""))[0].upper()
    if stem.startswith("CTT"):
        return "sCoverTopic"
    if stem.startswith("CTO"):
        return "chapterTopic"
    return "sDitaTopic"


def ensure_imesofttype(xml_text, filename):
    if "cms:imesofttype=" in (xml_text or ""):
        return xml_text
    itype = infer_imesofttype(filename)

    def _repl(match):
        return f'{match.group(1)} cms:imesofttype="{itype}"{match.group(2)}'

    updated, count = _ROOT_OPEN_TAG.subn(_repl, xml_text, count=1)
    return updated if count else xml_text


def iter_editable_files(output_dir):
    for dirpath, _, files in os.walk(output_dir):
        for name in files:
            if name in SKIP_NAMES:
                continue
            if name.lower().endswith(EDITABLE_SUFFIXES):
                yield os.path.join(dirpath, name)


def apply_hygiene(xml_text, filename):
    updated = ensure_imesofttype(xml_text, filename)
    updated = wrap_bare_li_and_entry(updated)
    if updated != xml_text and not _is_well_formed_xml(updated):
        return xml_text
    return updated


def apply_exact_patches(xml_text, patches):
    updated = xml_text
    applied = 0
    for patch in patches or []:
        find = str(patch.get("find") or "")
        replace = patch.get("replace")
        if not find or replace is None:
            continue
        if updated.count(find) != 1:
            continue
        candidate = updated.replace(find, str(replace), 1)
        if not _is_well_formed_xml(candidate):
            continue
        updated = candidate
        applied += 1
    return updated, applied


def _extract_json_object(raw):
    text = (raw or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start_obj = text.find("{")
        start_arr = text.find("[")
        if start_obj == -1 and start_arr == -1:
            return None
        if start_arr == -1 or (start_obj != -1 and start_obj < start_arr):
            text = text[start_obj:]
        else:
            text = text[start_arr:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        end = max(text.rfind("}"), text.rfind("]"))
        if end > 0:
            try:
                return json.loads(text[: end + 1])
            except json.JSONDecodeError:
                return None
        return None


def _relative_path(output_dir, path):
    return os.path.relpath(path, output_dir).replace("\\", "/")


def _build_catalog(files):
    lines = []
    for rel, content in files.items():
        title_match = re.search(r"<title[^>]*>(.*?)</title>", content, re.DOTALL)
        title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else ""
        has_type = "cms:imesofttype=" in content
        lines.append(f"{rel}\ttitle={title}\timesofttype={'yes' if has_type else 'no'}\tchars={len(content)}")
    return "\n".join(lines)


def _select_files_for_prompt(files, feedback, limit_chars=24000):
    feedback_l = (feedback or "").lower()
    ranked = []
    for rel, content in files.items():
        score = 0
        base = os.path.basename(rel).lower()
        if base in feedback_l or os.path.splitext(base)[0] in feedback_l:
            score += 5
        title_match = re.search(r"<title[^>]*>(.*?)</title>", content, re.DOTALL)
        title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else ""
        if title and title.lower() in feedback_l:
            score += 5
        if rel.lower().endswith(".ditamap"):
            score += 3
        if "cms:imesofttype=" not in content:
            score += 1
        ranked.append((score, rel))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = {}
    used = 0
    for score, rel in ranked:
        if score <= 0 and selected:
            continue
        content = files[rel]
        if used + len(content) > limit_chars and selected:
            continue
        selected[rel] = content
        used += len(content)
        if used >= limit_chars:
            break
    if not selected:
        for rel, content in files.items():
            selected[rel] = content
            used += len(content)
            if used >= limit_chars:
                break
    return selected


def _normalize_patch_list(payload):
    if payload is None:
        return []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("patches") or payload.get("edits") or []
    else:
        return []
    patches = []
    for item in items:
        if not isinstance(item, dict):
            continue
        file_name = str(item.get("file") or item.get("path") or "").replace("\\", "/").lstrip("./")
        find = item.get("find") or item.get("old") or item.get("from")
        replace = item.get("replace") if "replace" in item else item.get("new", item.get("to"))
        if file_name and find is not None and replace is not None:
            patches.append({"file": file_name, "find": str(find), "replace": str(replace)})
    return patches


def request_ai_patches(files, feedback, chat_fn):
    if not chat_fn:
        return []
    selected = _select_files_for_prompt(files, feedback)
    user_content = (
        "用户反馈：\n"
        f"{feedback.strip()}\n\n"
        "当前转换包文件目录：\n"
        f"{_build_catalog(files)}\n\n"
        "需要修改的文件原文：\n"
    )
    for rel, content in selected.items():
        user_content += f"\n----- FILE {rel} -----\n{content}\n"
    messages = [
        {
            "role": "system",
            "content": (
                "你在修订一份给 IME 导入的 DITA 转换包。"
                "只根据用户反馈做最小修改。"
                "封面用 sCoverTopic，章级用 chapterTopic，其余用 sDitaTopic。"
                "不要编造新的 cms:number / 文件名。"
                "只输出 JSON，格式："
                '{"patches":[{"file":"相对路径","find":"原文中唯一片段","replace":"替换后的片段"}]}。'
                "find 必须是目标文件中恰好出现一次的原文。"
                "没有需要改的地方就输出 {\"patches\":[]}。"
            ),
        },
        {"role": "user", "content": user_content},
    ]
    raw = chat_fn(messages, max_tokens=4000, temperature=0, request_label="convert.feedback")
    return _normalize_patch_list(_extract_json_object(raw))


def apply_convert_feedback(output_dir, feedback, chat_fn=None):
    """Apply user feedback onto an unzipped DITA conversion package.

    Returns a summary dict: files_touched, hygiene_files, ai_patches, notes.
    """
    feedback = (feedback or "").strip()
    if not feedback:
        raise ValueError("反馈不能为空")
    if not os.path.isdir(output_dir):
        raise ValueError("转换包目录不存在")

    files = {}
    for abs_path in iter_editable_files(output_dir):
        rel = _relative_path(output_dir, abs_path)
        with open(abs_path, "r", encoding="utf-8", errors="ignore") as handle:
            files[rel] = handle.read()

    if not files:
        raise ValueError("转换包中没有可修改的 DITA 文件")

    hygiene_files = []
    updated = {}
    for rel, content in files.items():
        cleaned = apply_hygiene(content, rel)
        if cleaned != content:
            hygiene_files.append(rel)
        updated[rel] = cleaned

    ai_patches = request_ai_patches(updated, feedback, chat_fn)
    patches_by_file = {}
    for patch in ai_patches:
        patches_by_file.setdefault(patch["file"], []).append(patch)

    applied_patches = 0
    ai_files = []
    for rel, content in list(updated.items()):
        file_patches = patches_by_file.get(rel) or patches_by_file.get(os.path.basename(rel)) or []
        if not file_patches:
            continue
        patched, count = apply_exact_patches(content, file_patches)
        if count:
            updated[rel] = patched
            applied_patches += count
            ai_files.append(rel)

    touched = []
    for rel, content in updated.items():
        if content == files[rel]:
            continue
        abs_path = os.path.join(output_dir, rel)
        with open(abs_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        touched.append(rel)

    notes = []
    if hygiene_files:
        notes.append(f"已补齐 {len(hygiene_files)} 个文件的 IME 必要标记（imesofttype / 列表与单元格 p）")
    if applied_patches:
        notes.append(f"已按反馈应用 {applied_patches} 处精确替换")
    elif chat_fn:
        notes.append("模型未给出可安全应用的精确替换，已保留卫生检查结果")
    elif not hygiene_files:
        notes.append("未改动文件：当前环境没有可用模型，且反馈未命中可自动修复项")

    if not touched:
        raise ValueError("未能根据反馈改动转换包，请写得更具体，例如文件名、缺的属性或要替换的原文")

    return {
        "files_touched": touched,
        "hygiene_files": hygiene_files,
        "ai_patches": applied_patches,
        "notes": notes,
    }
