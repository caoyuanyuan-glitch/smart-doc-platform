"""Shared goldset scoring helpers for G99 channel reports."""
from __future__ import annotations

import json
from pathlib import Path


BACKEND = Path("/workspace/backend")
GOLD = BACKEND / "goldset" / "human_baseline_DNBSEQ-G99RS&DNBSEQ-G99ARSSystemGuide(StandardMPS2.0)_V9.0_R01Lijuan.json"


def load_annotations(gold_path: Path | None = None):
    from app.review_engine.annotation_baseline import HumanAnnotation

    path = gold_path or GOLD
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return [HumanAnnotation(**item) for item in data.get("annotations", [])]


def issue_row_to_dict(issue) -> dict:
    if isinstance(issue, dict):
        return issue
    return {
        "id": getattr(issue, "id", None),
        "source": getattr(issue, "source", "") or "",
        "rule": getattr(issue, "rule", "") or "",
        "category": getattr(issue, "category", "") or "",
        "severity": getattr(issue, "severity", "") or "",
        "original_text": getattr(issue, "original_text", "") or "",
        "suggestion": getattr(issue, "suggestion", "") or "",
        "description": getattr(issue, "description", "") or "",
        "audit_basis": getattr(issue, "audit_basis", "") or "",
        "context": getattr(issue, "context", "") or "",
        "chapter": getattr(issue, "chapter", "") or "",
        "position": getattr(issue, "position", "") or "",
        "confidence": getattr(issue, "confidence", 0) or 0,
    }


def split_channels(issues: list[dict]) -> dict[str, list[dict]]:
    visual = []
    ai = []
    rules = []
    for item in issues:
        rule = str(item.get("rule") or "")
        source = str(item.get("source") or "").lower()
        if rule == "PDF-VISUAL-001":
            visual.append(item)
        elif source in {"ai", "ai_assisted", "llm"}:
            ai.append(item)
        else:
            rules.append(item)
    return {
        "规则通道": rules,
        "AI深度通道": ai,
        "PDF视觉通道": visual,
        "规则+视觉": rules + visual,
        "完整主流程": list(issues),
    }


def compact_eval(res: dict) -> dict:
    return {
        "issue_total": res.get("issue_total"),
        "human_total": res.get("human_total"),
        "strict_matched": res.get("strict_matched"),
        "strict_recall": res.get("strict_recall"),
        "strict_precision": res.get("strict_precision"),
        "recall": res.get("recall"),
        "precision": res.get("precision"),
        "matched": res.get("matched"),
    }


def score_channels(issues: list[dict], annotations) -> dict:
    from app.review_engine.annotation_baseline import evaluate_against_annotations

    payload = {}
    for name, subset in split_channels(issues).items():
        payload[name] = compact_eval(evaluate_against_annotations(subset, annotations))
    return payload
