from types import SimpleNamespace

from app.utils.qa_knowledge_scope import (
    AGENT_KB_ROOT_NAME,
    is_agent_kb_folder,
    user_root_folder_ids,
    folder_path_names,
)


def test_agent_root_is_excluded():
    folder = SimpleNamespace(id=1, name=AGENT_KB_ROOT_NAME, parent=None)
    assert is_agent_kb_folder(folder) is True


def test_nested_agent_skill_is_excluded():
    root = SimpleNamespace(id=1, name=AGENT_KB_ROOT_NAME, parent=None)
    skill = SimpleNamespace(id=2, name="AI skill", parent=root)
    memory = SimpleNamespace(id=3, name="润色", parent=skill)
    assert is_agent_kb_folder(skill) is True
    assert is_agent_kb_folder(memory) is True


def test_user_writing_folder_is_kept():
    root = SimpleNamespace(id=10, name="写作规范", parent=None)
    child = SimpleNamespace(id=11, name="写作风格指南", parent=root)
    assert is_agent_kb_folder(root) is False
    assert is_agent_kb_folder(child) is False


def test_user_root_folder_ids_skip_agent_kb():
    writing = SimpleNamespace(id=10, name="写作规范", parent=None)
    resources = SimpleNamespace(id=20, name="资源库", parent=None)
    agent = SimpleNamespace(id=30, name=AGENT_KB_ROOT_NAME, parent=None)
    assert user_root_folder_ids([writing, resources, agent]) == [10, 20]


def test_folder_path_names_joins_ancestors():
    root = SimpleNamespace(id=10, name="资源库", parent=None)
    child = SimpleNamespace(id=11, name="文件资料", parent=root)
    assert folder_path_names(child) == "资源库/文件资料"
