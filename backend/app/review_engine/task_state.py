"""Per-review_id isolation for temporary review-task state."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any


current_review_id: ContextVar[int | None] = ContextVar("current_review_id", default=None)

_TASK_STATE: dict[str, Any] = {}


def _key(review_id, slot: str) -> str:
    return f"{review_id}:{slot}"


def set_current_review_id(review_id) -> None:
    try:
        current_review_id.set(int(review_id))
    except (TypeError, ValueError):
        current_review_id.set(None)


def get_current_review_id(default=None):
    value = current_review_id.get()
    return default if value is None else value


def set_task_value(review_id, slot: str, value: Any) -> None:
    if review_id is None:
        return
    _TASK_STATE[_key(review_id, slot)] = value


def get_task_value(review_id, slot: str, default=None):
    if review_id is None:
        return default
    return _TASK_STATE.get(_key(review_id, slot), default)


def clear_task_state(review_id) -> None:
    if review_id is None:
        return
    prefix = f"{review_id}:"
    for key in list(_TASK_STATE):
        if key.startswith(prefix):
            _TASK_STATE.pop(key, None)


def snapshot_task_state(review_id) -> dict:
    prefix = f"{review_id}:"
    return {key[len(prefix):]: value for key, value in _TASK_STATE.items() if key.startswith(prefix)}
