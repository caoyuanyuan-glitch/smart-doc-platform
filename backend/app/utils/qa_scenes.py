"""Knowledge-base QA scene catalog and file inventory.

Keep QA_SCENES.paths aligned with frontend/src/views/QA.vue SCENE_CARDS.
"""

from app.models.knowledge import Folder, KnowledgeFile
from app.utils.qa_knowledge_scope import AGENT_KB_ROOT_NAME


QA_SCENES = [
    {
        "key": "style",
        "kicker": "写作规范",
        "title": "查规范与自检",
        "paths": [
            ["写作规范", "写作风格指南"],
            ["写作规范", "常见错误清单"],
            ["写作规范", "技术文档审核规则库"],
            ["写作规范", "说明书自检checklist"],
            ["写作规范", "审核依据汇总"],
        ],
    },
    {
        "key": "phrase",
        "kicker": "句式与记忆",
        "title": "找句式和译法",
        "paths": [
            ["写作规范", "句式清单"],
            ["资源库", "记忆库"],
        ],
    },
    {
        "key": "term",
        "kicker": "术语库",
        "title": "查术语",
        "paths": [["资源库", "术语库"]],
    },
    {
        "key": "files",
        "kicker": "文件资料",
        "title": "找文件资料",
        "paths": [["资源库", "文件资料"]],
    },
]


def _folder_index(folders):
    by_id = {}
    children = {}
    for folder in folders or []:
        by_id[folder.id] = folder
        children.setdefault(folder.parent_id, []).append(folder)
    return by_id, children


def _is_agent_folder(folder, by_id):
    current = folder
    seen = set()
    while current is not None:
        folder_id = getattr(current, "id", None)
        if folder_id is not None:
            if folder_id in seen:
                break
            seen.add(folder_id)
        if (getattr(current, "name", None) or "") == AGENT_KB_ROOT_NAME:
            return True
        parent_id = getattr(current, "parent_id", None)
        current = by_id.get(parent_id) if parent_id is not None else None
    return False


def _folder_path(folder, by_id):
    parts = []
    current = folder
    seen = set()
    while current is not None:
        folder_id = getattr(current, "id", None)
        if folder_id is not None:
            if folder_id in seen:
                break
            seen.add(folder_id)
        name = getattr(current, "name", None) or ""
        if name:
            parts.append(name)
        parent_id = getattr(current, "parent_id", None)
        current = by_id.get(parent_id) if parent_id is not None else None
    parts.reverse()
    return "/".join(parts)


def resolve_folder_by_path(children, path):
    parent_id = None
    node = None
    for name in path or []:
        node = next((item for item in children.get(parent_id, []) if item.name == name), None)
        if node is None:
            return None
        parent_id = node.id
    return node


def descendant_folder_ids(folder_id, children):
    ids = []
    stack = [folder_id]
    seen = set()
    while stack:
        current_id = stack.pop()
        if current_id in seen:
            continue
        seen.add(current_id)
        ids.append(current_id)
        for child in children.get(current_id, []):
            stack.append(child.id)
    return ids


def build_scene_inventory(db):
    folders = db.query(Folder).all()
    by_id, children = _folder_index(folders)
    files_by_folder = {}
    for item in db.query(KnowledgeFile).all():
        files_by_folder.setdefault(item.folder_id, []).append(item)

    scenes = []
    for scene in QA_SCENES:
        missing_paths = []
        folder_ids = []
        for path in scene["paths"]:
            folder = resolve_folder_by_path(children, path)
            if folder is None or _is_agent_folder(folder, by_id):
                missing_paths.append("/".join(path))
                continue
            for folder_id in descendant_folder_ids(folder.id, children):
                descendant = by_id.get(folder_id)
                if descendant is None or _is_agent_folder(descendant, by_id):
                    continue
                folder_ids.append(folder_id)

        folder_ids = list(dict.fromkeys(folder_ids))
        files = []
        seen = set()
        for folder_id in folder_ids:
            folder = by_id.get(folder_id)
            folder_path = _folder_path(folder, by_id) if folder else ""
            for item in files_by_folder.get(folder_id, []):
                if item.id in seen:
                    continue
                seen.add(item.id)
                files.append({
                    "id": item.id,
                    "name": item.name,
                    "folder_id": item.folder_id,
                    "folder_path": folder_path,
                    "file_type": item.file_type or "",
                    "updated_at": item.updated_at,
                })

        files.sort(key=lambda row: (row.get("folder_path") or "", row.get("name") or "", row.get("id") or 0))
        scenes.append({
            "key": scene["key"],
            "kicker": scene["kicker"],
            "title": scene["title"],
            "folder_count": len(folder_ids),
            "file_count": len(files),
            "missing_paths": missing_paths,
            "files": files,
        })
    return scenes
