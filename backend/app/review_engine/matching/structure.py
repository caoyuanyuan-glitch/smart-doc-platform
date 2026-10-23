from __future__ import annotations

import re

from app.review_engine.matching.normalize import normalize_text


_ACTION_RE = re.compile(r"(点击|长按|按下|选择|插入|移除|click|press|select|insert|remove)\s*([^\s，。,]{1,24})", re.IGNORECASE)
_CONDITION_RE = re.compile(r"(如果|当|之后|before|after|when|if)\s*([^，。,.]{1,40})", re.IGNORECASE)


def extract_structure(text: str) -> dict:
    value = normalize_text(text)
    action_match = _ACTION_RE.search(value)
    condition_match = _CONDITION_RE.search(value)
    action = (action_match.group(1) if action_match else "").lower()
    obj = (action_match.group(2) if action_match else "").lower()
    condition = (condition_match.group(0) if condition_match else "").lower()
    return {
        "action": action,
        "object": obj,
        "condition": condition,
        "signature": f"{action}|{obj}|{condition}",
    }


def structures_compatible(left: str, right: str) -> bool:
    a = extract_structure(left)
    b = extract_structure(right)
    if a["action"] and b["action"] and a["action"] == b["action"] and a["object"] != b["object"] and a["object"] and b["object"]:
        return False
    if a["condition"] and b["condition"] and a["condition"] != b["condition"]:
        return False
    return True
