"""Knowledge-base scope helpers for general QA retrieval."""

AGENT_KB_ROOT_NAME = "AI agent知识库"


def is_agent_kb_folder(folder) -> bool:
    """Return True if the folder is the AI agent knowledge root or one of its descendants."""
    current = folder
    seen = set()
    while current is not None:
        folder_id = getattr(current, "id", None)
        if folder_id is not None:
            if folder_id in seen:
                break
            seen.add(folder_id)
        name = getattr(current, "name", None) or ""
        if name == AGENT_KB_ROOT_NAME:
            return True
        current = getattr(current, "parent", None)
    return False


def user_root_folder_ids(folders) -> list:
    """Keep top-level folders that belong to user-facing knowledge."""
    ids = []
    for folder in folders or []:
        if is_agent_kb_folder(folder):
            continue
        folder_id = getattr(folder, "id", None)
        if folder_id is not None:
            ids.append(folder_id)
    return ids


def folder_path_names(folder) -> str:
    """Return parent-to-child folder names joined by /."""
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
        current = getattr(current, "parent", None)
    parts.reverse()
    return "/".join(parts)
