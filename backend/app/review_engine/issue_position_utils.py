"""共享的 issue 位置/上下文工具（从 unit_spacing/cn_typo/learned_patch 三份逐字相同的拷贝提取）。

工程债治理：三份 _encode_position / _page_at 实现完全一致；_context 仅默认半径不同
（unit_spacing/cn_typo=60，learned_patch=70），这里保留参数默认值由调用方显式传入。
不改变任何行为；原模块改为 re-export，保持现有 import 路径兼容。
"""

from __future__ import annotations

import json
import re


def encode_position(start: int, end: int, **meta) -> str:
    payload = {"start": start, "end": end, "area": meta.pop("area", "正文")}
    payload.update({key: value for key, value in meta.items() if value not in (None, "", [], {})})
    return json.dumps(payload, ensure_ascii=False)


def page_at(text: str, offset: int) -> int:
    return text[: max(0, offset)].count("\f") + 1


def build_context(text: str, start: int, end: int, radius: int = 60) -> str:
    return re.sub(r"\s+", " ", text[max(0, start - radius):min(len(text), end + radius)]).strip()
