"""Helpers for knowledge-base QA card configuration."""

import json
import re
import uuid

from app.models.knowledge import Folder
from app.models.qa_card import QaCard, QaCardFolder
from app.utils.qa_knowledge_scope import AGENT_KB_ROOT_NAME

DEFAULT_ACCENT = "#1d4ed8"
DEFAULT_KICKER = "自定义"
ACCENT_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_SUGGESTIONS = 6
MAX_SUGGESTION_LENGTH = 120


def parse_suggestions(raw) -> list:
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            parsed = []
        items = parsed if isinstance(parsed, list) else []
    else:
        items = []
    result = []
    for item in items:
        text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def dump_suggestions(items) -> str:
    return json.dumps(parse_suggestions(items), ensure_ascii=False)


def load_folder_index(db):
    folders = db.query(Folder).all()
    by_id = {folder.id: folder for folder in folders}
    children = {}
    for folder in folders:
        children.setdefault(folder.parent_id, []).append(folder.id)
    return by_id, children


def agent_folder_ids(db, by_id=None) -> set:
    by_id = by_id or load_folder_index(db)[0]
    result = set()
    for folder in by_id.values():
        current = folder
        seen = set()
        while current is not None:
            folder_id = getattr(current, "id", None)
            if folder_id is not None:
                if folder_id in seen:
                    break
                seen.add(folder_id)
            if (getattr(current, "name", None) or "") == AGENT_KB_ROOT_NAME:
                result.add(folder.id)
                break
            current = by_id.get(getattr(current, "parent_id", None))
    return result


def expand_folder_ids(db, root_ids, allowed_ids=None) -> list:
    by_id, children = load_folder_index(db)
    blocked = agent_folder_ids(db, by_id)
    allowed = set(allowed_ids) if allowed_ids is not None else None
    result = set()
    seen = set()
    stack = [int(folder_id) for folder_id in root_ids or [] if folder_id is not None]
    while stack:
        folder_id = stack.pop()
        if folder_id in seen:
            continue
        seen.add(folder_id)
        if folder_id in blocked:
            continue
        if allowed is None or folder_id in allowed:
            if folder_id in by_id:
                result.add(folder_id)
        for child_id in children.get(folder_id, []):
            stack.append(child_id)
    return sorted(result)


def card_to_dict(card: QaCard, folder_ids=None) -> dict:
    ids = folder_ids
    if ids is None:
        ids = [row.folder_id for row in card.folders]
    return {
        "id": card.id,
        "key": card.key,
        "kicker": card.kicker or DEFAULT_KICKER,
        "title": card.title,
        "description": card.description or "",
        "accent": card.accent or DEFAULT_ACCENT,
        "suggestions": parse_suggestions(card.suggestions_json),
        "home_visible": bool(card.home_visible),
        "sort_order": int(card.sort_order or 0),
        "folder_ids": sorted({int(folder_id) for folder_id in ids if folder_id is not None}),
    }


def normalize_suggestions(value, errors: list):
    items = parse_suggestions(value)
    cleaned = []
    seen = set()
    for item in items:
        text = item.strip()
        if not text or text in seen:
            continue
        if len(text) > MAX_SUGGESTION_LENGTH:
            errors.append(f"推荐问题单条不能超过 {MAX_SUGGESTION_LENGTH} 个字符")
            return []
        seen.add(text)
        cleaned.append(text)
    if len(cleaned) > MAX_SUGGESTIONS:
        errors.append(f"推荐问题最多 {MAX_SUGGESTIONS} 条")
        return []
    return cleaned


def normalize_folder_ids(db, value, errors: list):
    if not isinstance(value, (list, tuple, set)):
        errors.append("请选择知识库文件夹")
        return []
    ids = []
    seen = set()
    for item in value:
        try:
            folder_id = int(item)
        except (TypeError, ValueError):
            continue
        if folder_id <= 0 or folder_id in seen:
            continue
        seen.add(folder_id)
        ids.append(folder_id)
    if not ids:
        errors.append("请至少选择一个知识库文件夹")
        return []
    folders = db.query(Folder).filter(Folder.id.in_(ids)).all()
    folder_map = {folder.id: folder for folder in folders}
    missing = [folder_id for folder_id in ids if folder_id not in folder_map]
    if missing:
        errors.append("部分知识库文件夹不存在，请刷新后重试")
        return []
    blocked = agent_folder_ids(db)
    if any(folder_id in blocked for folder_id in ids):
        errors.append("「AI agent知识库」不支持作为问答卡片范围")
        return []
    return ids


def normalize_card_payload(db, payload: dict, card: QaCard = None) -> dict:
    errors = []
    title = str(payload.get("title", "") or "").strip()
    if not title:
        errors.append("请填写卡片标题")
    elif len(title) > 30:
        errors.append("卡片标题不能超过 30 个字符")

    kicker = str(payload.get("kicker", "") or "").strip() or DEFAULT_KICKER
    if len(kicker) > 12:
        errors.append("分类标签不能超过 12 个字符")

    description = str(payload.get("description", "") or "").strip()
    if len(description) > 120:
        errors.append("卡片说明不能超过 120 个字符")

    accent = str(payload.get("accent", "") or "").strip() or DEFAULT_ACCENT
    if not ACCENT_PATTERN.fullmatch(accent):
        errors.append("主题色需为 #RRGGBB 格式")

    suggestions = normalize_suggestions(payload.get("suggestions"), errors)
    folder_ids = normalize_folder_ids(db, payload.get("folder_ids"), errors)

    home_visible = payload.get("home_visible", True)
    if not isinstance(home_visible, bool):
        home_visible = str(home_visible).strip().lower() not in {"0", "false", "no", "off"}

    sort_order = payload.get("sort_order")
    if sort_order in (None, ""):
        sort_order = card.sort_order if card is not None else None
    else:
        try:
            sort_order = int(sort_order)
        except (TypeError, ValueError):
            errors.append("排序值需为整数")
            sort_order = card.sort_order if card is not None else None

    if errors:
        raise ValueError("；".join(errors))

    return {
        "title": title,
        "kicker": kicker,
        "description": description,
        "accent": accent,
        "suggestions": suggestions,
        "folder_ids": folder_ids,
        "home_visible": home_visible,
        "sort_order": sort_order,
    }


def replace_card_folders(db, card: QaCard, folder_ids):
    db.query(QaCardFolder).filter(QaCardFolder.card_id == card.id).delete(synchronize_session=False)
    seen = set()
    for folder_id in folder_ids or []:
        folder_id = int(folder_id)
        if folder_id in seen:
            continue
        seen.add(folder_id)
        db.add(QaCardFolder(card_id=card.id, folder_id=folder_id))


def next_sort_order(db) -> int:
    max_order = db.query(QaCard).order_by(QaCard.sort_order.desc()).first()
    return int(max_order.sort_order or 0) + 10 if max_order else 10


def build_card_key() -> str:
    return f"card-{uuid.uuid4().hex[:12]}"
