import contextvars
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session
from jose import JWTError, jwt

from app.api.auth import ALGORITHM, SECRET_KEY
from app.database import SessionLocal
from app.models.knowledge import Folder, KnowledgeFile, KnowledgeFileCall

logger = logging.getLogger(__name__)

MODULE_POLISH = "polish"
MODULE_QA = "qa"
MODULE_TRANSLATION = "translation"
MODULE_LABELS = {
    MODULE_POLISH: "智能润色",
    MODULE_QA: "智能问答",
    MODULE_TRANSLATION: "AI翻译",
}
VALID_MODULES = set(MODULE_LABELS)
BEIJING_TZ = timezone(timedelta(hours=8))
_usage_actor = contextvars.ContextVar("knowledge_usage_actor", default=None)

_request_calls = contextvars.ContextVar("knowledge_usage_request_calls", default=None)


def _normalize_duration_ms(duration_ms) -> int:
    return max(1, int(round(float(duration_ms or 0))))


def set_usage_actor(user) -> contextvars.Token:
    username = ""
    user_id = None
    if user is not None:
        user_id = getattr(user, "id", None)
        username = str(getattr(user, "username", "") or "").strip()
    return _usage_actor.set({
        "user_id": user_id,
        "username": username or "guest",
    })


def reset_usage_actor(token: contextvars.Token) -> None:
    try:
        _usage_actor.reset(token)
    except ValueError:
        _usage_actor.set(None)


def bind_usage_actor_from_authorization(authorization: str | None) -> None:
    username = "guest"
    header = str(authorization or "").strip()
    if header.lower().startswith("bearer "):
        token = header.split(" ", 1)[1].strip()
        if token:
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                username = str(payload.get("sub") or "").strip() or "guest"
            except JWTError:
                username = "guest"
    _usage_actor.set({"user_id": None, "username": username})
    _request_calls.set({})


def install_knowledge_usage_middleware(app) -> None:
    @app.middleware("http")
    async def bind_knowledge_usage_actor_middleware(request, call_next):
        bind_usage_actor_from_authorization(request.headers.get("authorization"))
        try:
            return await call_next(request)
        finally:
            _usage_actor.set(None)
            _request_calls.set(None)


def _actor_payload(user=None) -> dict:
    if user is not None:
        username = str(getattr(user, "username", "") or "").strip() or "guest"
        return {"user_id": getattr(user, "id", None), "username": username}
    return _usage_actor.get() or {"user_id": None, "username": "guest"}


def record_knowledge_file_call(file_id, module: str, duration_ms: int = 0, user=None) -> None:
    if not file_id or module not in VALID_MODULES:
        return
    actor = _actor_payload(user)
    duration_ms = _normalize_duration_ms(duration_ms)
    call_key = (int(file_id), module)
    try:
        db = SessionLocal()
        try:
            seen = _request_calls.get()
            existing_id = seen.get(call_key) if isinstance(seen, dict) else None
            if existing_id:
                row = db.query(KnowledgeFileCall).filter(KnowledgeFileCall.id == existing_id).first()
                if row:
                    row.duration_ms = int(row.duration_ms or 0) + duration_ms
                    db.commit()
                    return
            row = KnowledgeFileCall(
                file_id=int(file_id),
                module=module,
                user_id=actor.get("user_id"),
                username=(actor.get("username") or "guest")[:64],
                duration_ms=duration_ms,
            )
            db.add(row)
            db.flush()
            if isinstance(seen, dict):
                seen[call_key] = row.id
            db.commit()
        finally:
            db.close()
    except Exception:
        logger.exception("failed to record knowledge file call file_id=%s module=%s", file_id, module)


def record_timed_call(file_id, module: str, fn, *args, user=None, **kwargs):
    started = time.perf_counter()
    try:
        return fn(*args, **kwargs)
    finally:
        duration_ms = _normalize_duration_ms((time.perf_counter() - started) * 1000)
        record_knowledge_file_call(file_id, module, duration_ms, user=user)


def to_beijing_iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BEIJING_TZ).isoformat(timespec="seconds")


def parse_beijing_day_range(start: Optional[str], end: Optional[str]):
    start_dt = None
    end_dt = None
    if start:
        start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ).astimezone(timezone.utc).replace(tzinfo=None)
    if end:
        end_dt = datetime.strptime(end, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=BEIJING_TZ
        ).astimezone(timezone.utc).replace(tzinfo=None)
    return start_dt, end_dt


def _folder_path(folder_id, folder_map: dict) -> str:
    names = []
    seen = set()
    current_id = folder_id
    while current_id and current_id not in seen:
        seen.add(current_id)
        folder = folder_map.get(current_id)
        if folder is None:
            break
        names.append(folder.name)
        current_id = folder.parent_id
    names.reverse()
    return " / ".join(names)


def _apply_call_filters(query, module=None, start=None, end=None):
    if module:
        query = query.filter(KnowledgeFileCall.module == module)
    if start:
        query = query.filter(KnowledgeFileCall.created_at >= start)
    if end:
        query = query.filter(KnowledgeFileCall.created_at <= end)
    return query


def query_usage_summary(db: Session, module=None, start=None, end=None, keyword=None):
    query = db.query(
        KnowledgeFileCall.file_id,
        func.count(KnowledgeFileCall.id).label("call_count"),
        func.coalesce(func.sum(KnowledgeFileCall.duration_ms), 0).label("total_duration_ms"),
        func.count(distinct(KnowledgeFileCall.username)).label("account_count"),
        func.max(KnowledgeFileCall.created_at).label("last_called_at"),
        func.group_concat(KnowledgeFileCall.module).label("modules_raw"),
    )
    query = _apply_call_filters(query, module, start, end)
    if keyword:
        like = "%" + keyword.strip() + "%"
        query = query.join(KnowledgeFile, KnowledgeFile.id == KnowledgeFileCall.file_id).filter(
            KnowledgeFile.name.like(like)
        )
    rows = query.group_by(KnowledgeFileCall.file_id).order_by(func.count(KnowledgeFileCall.id).desc()).all()

    file_ids = [row.file_id for row in rows]
    files = {}
    if file_ids:
        files = {item.id: item for item in db.query(KnowledgeFile).filter(KnowledgeFile.id.in_(file_ids)).all()}
    folder_map = {item.id: item for item in db.query(Folder).all()}

    items = []
    total_calls = 0
    total_duration = 0
    for row in rows:
        knowledge_file = files.get(row.file_id)
        modules = []
        for name in str(row.modules_raw or "").split(","):
            if name and name not in modules and name in MODULE_LABELS:
                modules.append(name)
        call_count = int(row.call_count or 0)
        duration_ms = int(row.total_duration_ms or 0)
        total_calls += call_count
        total_duration += duration_ms
        items.append({
            "file_id": row.file_id,
            "file_name": knowledge_file.name if knowledge_file else "已删除文件",
            "folder_path": _folder_path(knowledge_file.folder_id, folder_map) if knowledge_file else "",
            "call_count": call_count,
            "total_duration_ms": duration_ms,
            "avg_duration_ms": int(duration_ms / call_count) if call_count else 0,
            "modules": modules,
            "module_labels": [MODULE_LABELS[name] for name in modules],
            "account_count": int(row.account_count or 0),
            "last_called_at": to_beijing_iso(row.last_called_at),
        })

    module_query = db.query(
        KnowledgeFileCall.module,
        func.count(KnowledgeFileCall.id).label("call_count"),
        func.count(distinct(KnowledgeFileCall.file_id)).label("file_count"),
    )
    module_query = _apply_call_filters(module_query, module, start, end)
    if keyword:
        like = "%" + keyword.strip() + "%"
        module_query = module_query.join(KnowledgeFile, KnowledgeFile.id == KnowledgeFileCall.file_id).filter(
            KnowledgeFile.name.like(like)
        )
    module_rows = {row.module: row for row in module_query.group_by(KnowledgeFileCall.module).all()}
    module_stats = []
    for name, label in MODULE_LABELS.items():
        module_row = module_rows.get(name)
        module_stats.append({
            "module": name,
            "module_label": label,
            "call_count": int(module_row.call_count or 0) if module_row else 0,
            "file_count": int(module_row.file_count or 0) if module_row else 0,
        })
    module_stats.sort(key=lambda item: (-item["call_count"], item["module_label"]))

    return {
        "file_count": len(items),
        "total_calls": total_calls,
        "total_duration_ms": total_duration,
        "module_stats": module_stats,
        "items": items,
    }


def query_usage_details(db: Session, file_id: int, module=None, start=None, end=None, offset: int = 0, limit: int = 50):
    query = db.query(KnowledgeFileCall).filter(KnowledgeFileCall.file_id == file_id)
    query = _apply_call_filters(query, module, start, end)
    total = query.count()
    rows = query.order_by(KnowledgeFileCall.created_at.desc()).offset(offset).limit(limit).all()
    knowledge_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == file_id).first()
    folder_map = {item.id: item for item in db.query(Folder).all()}
    return {
        "file_id": file_id,
        "file_name": knowledge_file.name if knowledge_file else "已删除文件",
        "folder_path": _folder_path(knowledge_file.folder_id, folder_map) if knowledge_file else "",
        "total": total,
        "items": [
            {
                "id": row.id,
                "created_at": to_beijing_iso(row.created_at),
                "module": row.module,
                "module_label": MODULE_LABELS.get(row.module, row.module),
                "username": row.username or "guest",
                "duration_ms": int(row.duration_ms or 0),
            }
            for row in rows
        ],
    }
