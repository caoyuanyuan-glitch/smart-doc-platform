"""Per-user folder grants for the knowledge base."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.knowledge import Folder, UserKnowledgeGrant
from app.models.user import User
from app.utils.qa_knowledge_scope import is_agent_kb_folder, is_user_visible_folder

ACTION_READ = "read"
ACTION_PREVIEW = "preview"
ACTION_DOWNLOAD = "download"
ACTION_EDIT = "edit"
ACTION_DELETE = "delete"

ALL_ACTIONS = (ACTION_READ, ACTION_PREVIEW, ACTION_DOWNLOAD, ACTION_EDIT, ACTION_DELETE)
ACTION_LABELS = {
    ACTION_READ: "只读",
    ACTION_PREVIEW: "预览",
    ACTION_DOWNLOAD: "下载",
    ACTION_EDIT: "编辑",
    ACTION_DELETE: "删除",
}
IMPLIES = {
    ACTION_READ: frozenset({ACTION_READ}),
    ACTION_PREVIEW: frozenset({ACTION_READ, ACTION_PREVIEW}),
    ACTION_DOWNLOAD: frozenset({ACTION_READ, ACTION_PREVIEW, ACTION_DOWNLOAD}),
    ACTION_EDIT: frozenset({ACTION_READ, ACTION_PREVIEW, ACTION_DOWNLOAD, ACTION_EDIT}),
    ACTION_DELETE: frozenset(ALL_ACTIONS),
}
BASELINE_ACTIONS = frozenset({ACTION_READ, ACTION_PREVIEW})
ADMIN_ACTIONS = frozenset(ALL_ACTIONS)


def is_admin(user) -> bool:
    return getattr(user, "role", None) == "admin"


def normalize_actions(actions) -> set:
    result = set()
    for action in actions or []:
        key = str(action or "").strip()
        if key in IMPLIES:
            result |= set(IMPLIES[key])
    return result


def serialize_actions(actions) -> str:
    normalized = normalize_actions(actions)
    return ",".join(action for action in ALL_ACTIONS if action in normalized)


def parse_actions(raw) -> set:
    if not raw:
        return set()
    if isinstance(raw, (list, tuple, set, frozenset)):
        return normalize_actions(raw)
    return normalize_actions(str(raw).split(","))


def folder_chain_ids(folder, folder_by_id=None) -> list:
    ids = []
    current = folder
    seen = set()
    while current is not None:
        folder_id = getattr(current, "id", None)
        if folder_id is None or folder_id in seen:
            break
        seen.add(folder_id)
        ids.append(folder_id)
        parent = getattr(current, "parent", None)
        parent_id = getattr(current, "parent_id", None)
        if parent is None and folder_by_id and parent_id:
            parent = folder_by_id.get(parent_id)
        current = parent
    return ids


def load_folder_index(db: Session) -> dict:
    return {folder.id: folder for folder in db.query(Folder).all()}


def load_user_grant_map(db: Session, user_id: int) -> dict:
    rows = db.query(UserKnowledgeGrant).filter(UserKnowledgeGrant.user_id == user_id).all()
    return {row.folder_id: parse_actions(row.actions) for row in rows if parse_actions(row.actions)}


def effective_folder_actions(db: Session, folder, user, grant_map=None, folder_by_id=None) -> set:
    if is_admin(user):
        return set(ADMIN_ACTIONS)
    if folder is None:
        return set()
    if grant_map is None:
        grant_map = load_user_grant_map(db, getattr(user, "id", None))
    for folder_id in folder_chain_ids(folder, folder_by_id):
        if folder_id in grant_map:
            return set(grant_map[folder_id])
    if is_user_visible_folder(folder):
        return set(BASELINE_ACTIONS)
    return set()


def visible_folder_actions(db: Session, user) -> dict:
    folder_by_id = load_folder_index(db)
    if is_admin(user):
        return {folder_id: set(ADMIN_ACTIONS) for folder_id in folder_by_id}
    grant_map = load_user_grant_map(db, getattr(user, "id", None))
    visible = {}
    for folder in folder_by_id.values():
        actions = effective_folder_actions(
            db, folder, user, grant_map=grant_map, folder_by_id=folder_by_id
        )
        if actions:
            visible[folder.id] = actions
    for folder_id, actions in list(visible.items()):
        if not actions:
            continue
        current = folder_by_id.get(folder_id)
        while current is not None and current.parent_id:
            parent_id = current.parent_id
            if parent_id not in visible:
                visible[parent_id] = set()
            current = folder_by_id.get(parent_id)
    return visible


def resolve_qa_scope(db: Session, user, requested_ids=None) -> list:
    """Resolve QA folder scope to folders the user can read.

    Requested parent folders are expanded recursively, then intersected with
    readable folders. Ungranted siblings are never included.
    """
    folder_by_id = load_folder_index(db)
    children = {}
    for folder in folder_by_id.values():
        children.setdefault(folder.parent_id, []).append(folder.id)

    visible = visible_folder_actions(db, user)
    allowed = {
        folder_id
        for folder_id, actions in visible.items()
        if ACTION_READ in actions
        and folder_id in folder_by_id
        and not is_agent_kb_folder(folder_by_id[folder_id])
    }
    if not requested_ids:
        return sorted(allowed)

    scope = set()
    seen = set()
    stack = []
    for raw in requested_ids:
        try:
            folder_id = int(raw)
        except (TypeError, ValueError):
            continue
        if folder_id in folder_by_id:
            stack.append(folder_id)

    while stack:
        folder_id = stack.pop()
        if folder_id in seen:
            continue
        seen.add(folder_id)
        if folder_id in allowed:
            scope.add(folder_id)
        for child_id in children.get(folder_id, []):
            stack.append(child_id)
    return sorted(scope)


def filter_tree_nodes(nodes, visible_actions: dict) -> list:
    result = []
    for node in nodes or []:
        children = filter_tree_nodes(node.get("children") or [], visible_actions)
        folder_id = node.get("id")
        if folder_id not in visible_actions and not children:
            continue
        if folder_id in visible_actions:
            actions = sorted(visible_actions[folder_id])
        else:
            actions = [ACTION_READ] if children else []
        copied = dict(node)
        copied["children"] = children
        copied["actions"] = actions
        if ACTION_READ not in actions:
            copied["files"] = []
        result.append(copied)
    return result


def list_folder_grant_items(db: Session, folder_id: int) -> list:
    users = (
        db.query(User)
        .filter(User.role != "admin", User.status == "active")
        .order_by(User.id.asc())
        .all()
    )
    rows = db.query(UserKnowledgeGrant).filter(UserKnowledgeGrant.folder_id == folder_id).all()
    grant_map = {row.user_id: sorted(parse_actions(row.actions)) for row in rows}
    items = []
    for user in users:
        items.append({
            "user_id": user.id,
            "username": user.username,
            "display_name": user.display_name or user.username,
            "actions": grant_map.get(user.id, []),
        })
    return items


def replace_folder_grants(db: Session, folder_id: int, grants, granted_by: int) -> list:
    payload = []
    seen = set()
    for item in grants or []:
        user_id = int(item.get("user_id") or 0)
        if user_id <= 0 or user_id in seen:
            continue
        seen.add(user_id)
        actions = serialize_actions(item.get("actions") or [])
        payload.append((user_id, actions))

    users = db.query(User).filter(User.id.in_([user_id for user_id, _ in payload])).all() if payload else []
    user_map = {user.id: user for user in users}
    db.query(UserKnowledgeGrant).filter(UserKnowledgeGrant.folder_id == folder_id).delete()
    saved = []
    now = datetime.utcnow()
    for user_id, actions in payload:
        user = user_map.get(user_id)
        if user is None or user.role == "admin" or user.status != "active":
            continue
        if not actions:
            continue
        row = UserKnowledgeGrant(
            user_id=user_id,
            folder_id=folder_id,
            actions=actions,
            granted_by=granted_by,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        saved.append({"user_id": user_id, "actions": actions.split(",") if actions else []})
    db.commit()
    return saved


def folder_grant_tree(db: Session, grant_map=None) -> list:
    grant_map = grant_map or {}
    folders = db.query(Folder).order_by(Folder.id.asc()).all()
    nodes = {}
    for folder in folders:
        nodes[folder.id] = {
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
            "actions": sorted(grant_map.get(folder.id) or []),
            "children": [],
        }
    roots = []
    for folder in folders:
        node = nodes[folder.id]
        parent_id = folder.parent_id
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


def list_user_grant_tree(db: Session, user_id: int) -> list:
    return folder_grant_tree(db, load_user_grant_map(db, user_id))


def replace_user_grants(db: Session, user_id: int, grants, granted_by: int) -> list:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or user.role == "admin":
        db.query(UserKnowledgeGrant).filter(UserKnowledgeGrant.user_id == user_id).delete()
        db.commit()
        return []

    folder_ids = {folder.id for folder in db.query(Folder).all()}
    payload = []
    seen = set()
    for item in grants or []:
        folder_id = int(item.get("folder_id") or 0)
        if folder_id <= 0 or folder_id in seen or folder_id not in folder_ids:
            continue
        seen.add(folder_id)
        actions = serialize_actions(item.get("actions") or [])
        if actions:
            payload.append((folder_id, actions))

    db.query(UserKnowledgeGrant).filter(UserKnowledgeGrant.user_id == user_id).delete()
    saved = []
    now = datetime.utcnow()
    for folder_id, actions in payload:
        row = UserKnowledgeGrant(
            user_id=user_id,
            folder_id=folder_id,
            actions=actions,
            granted_by=granted_by,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        saved.append({"folder_id": folder_id, "actions": actions.split(",") if actions else []})
    db.commit()
    return saved
BASELINE_ACTIONS = frozenset({ACTION_READ, ACTION_PREVIEW})
