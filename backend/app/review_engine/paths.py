"""Path bounds for review-module file access."""

from __future__ import annotations

from pathlib import Path


class ReviewPathError(ValueError):
    pass


def resolve_review_file_path(root, filename) -> Path:
    root_path = Path(root).resolve()
    name = Path(str(filename or "")).name
    if not name or name in {".", ".."}:
        raise ReviewPathError("empty or invalid review filename")
    candidate = (root_path / name).resolve()
    if not str(candidate).startswith(str(root_path)):
        raise ReviewPathError("review file path is outside the allowed root")
    return candidate
