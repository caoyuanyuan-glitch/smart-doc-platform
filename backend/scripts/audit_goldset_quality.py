"""Gold Set 标注质量扫描器

目的：把评测套件引用的 baseline 里"低质量批注"扫出来，供标注员针对性补全。
      只有标注可信，严格口径 recall/precision 才能成为可辩护的 88% 度量。

检测项（每条批注）：
  - missing_page           缺页码（page 为空）
  - placeholder_author     作者为"待补"等占位
  - empty_selected_text    selected_text 为空
  - vague_selected_text    selected_text 是中文概念描述而非原文（如"商标相关表述""跨页重复句"）
  - empty_context          context 为空
  - missing_expected_rule  缺 expected_rule
  - suspicious_rule        expected_rule 带 [NEW] 等非确认标记

文档级：
  - placeholder_fn         FN（漏检项）区为占位（【待补】等）或缺失
  - no_fn_section          没有 FN 区（则 recall 分母不可知）

输出：
  --json-out   结构化扫描结果（可复算、可 diff）
  --md-out     标注员可直接填写的清单
  默认打印汇总到 stdout。

用法：
  cd backend
  python scripts/audit_goldset_quality.py \
      --config config/review-evaluation-suite.accuracy.json \
      --json-out /tmp/goldset_quality.json \
      --md-out /tmp/goldset_quality_checklist.md

注意：本脚本只读标注文件，不改任何 baseline，不依赖数据库/LLM。
"""

import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.review_engine.annotation_baseline import (  # noqa: E402
    HumanAnnotation,
    parse_human_annotation_markdown,
)

# 占位作者
PLACEHOLDER_AUTHORS = {"", "待补", "tbd", "todo", "n/a", "na", "-", "未知", "待定"}

# 中文概念描述特征：这些词出现在 selected_text 里，说明写的是"概念"而非文档原文
VAGUE_TERMS = [
    "相关表述", "相关描述", "重复句", "引导语", "错误表述", "不一致", "文件名",
    "相关说明", "此处", "某处", "相关内容", "写法", "相关文字", "相关内容",
    "表述", "描述", "占位", "示例文本", "待补", "具体内容", "等",
]
# 纯中文的 selected_text 才判为可疑（英文说明书原文不会是纯中文概念）
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")

# expected_rule 非确认标记
SUSPICIOUS_RULE_RE = re.compile(r"\[(NEW|TODO|TBD|DRAFT)\]", re.IGNORECASE)

# FN 占位
FN_PLACEHOLDER_RE = re.compile(r"【待补】|\[待补\]|待补|TBD|TODO|N/A", re.IGNORECASE)
FN_SECTION_RE = re.compile(r"漏检项|漏检|\bFN\b|false\s*negative", re.IGNORECASE)


def load_annotations(path: Path) -> list[HumanAnnotation]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return [HumanAnnotation(**item) for item in payload.get("annotations", [])]
    return parse_human_annotation_markdown(path)


def resolve_baseline(value: str) -> Path:
    p = Path(value)
    if p.is_absolute() and p.exists():
        return p
    if p.exists():
        return p
    candidate = ROOT / p
    return candidate if candidate.exists() else p


def vague_reason(selected_text: str) -> bool:
    """selected_text 是否像中文概念描述而非原文。"""
    text = (selected_text or "").strip()
    if not text:
        return False
    # 含拉丁字母的通常是原文片段，不判为概念描述
    if LATIN_RE.search(text):
        return False
    if not CJK_RE.search(text):
        return False
    return any(term in text for term in VAGUE_TERMS)


def check_annotation(item: HumanAnnotation, idx: int) -> dict:
    issues = []
    if not (item.page or "").strip():
        issues.append("missing_page")
    if (item.author or "").strip().lower() in PLACEHOLDER_AUTHORS:
        issues.append("placeholder_author")
    selected = (item.selected_text or "").strip()
    if not selected:
        issues.append("empty_selected_text")
    elif vague_reason(selected):
        issues.append("vague_selected_text")
    if not (item.context or "").strip():
        issues.append("empty_context")
    if not (item.expected_rule or "").strip():
        issues.append("missing_expected_rule")
    elif SUSPICIOUS_RULE_RE.search(item.expected_rule):
        issues.append("suspicious_rule")

    return {
        "index": idx,
        "file": item.file,
        "page": item.page,
        "author": item.author,
        "comment": item.comment,
        "selected_text": item.selected_text,
        "context": item.context,
        "expected_rule": item.expected_rule,
        "category": item.category,
        "layer": item.layer,
        "issues": issues,
        "quality": "ok" if not issues else "needs_fix",
    }


def check_document_placeholder(path: Path) -> dict:
    """文档级：FN 区是否存在、是否为占位。"""
    text = path.read_text(encoding="utf-8-sig")
    result = {"has_fn_section": False, "fn_placeholder": False}
    if not FN_SECTION_RE.search(text):
        result["no_fn_section"] = True
        return result
    result["has_fn_section"] = True
    # 截取 FN 段落做占位检测
    match = FN_SECTION_RE.search(text)
    tail = text[match.start():]
    result["fn_placeholder"] = bool(FN_PLACEHOLDER_RE.search(tail))
    return result


def scan(config_path: Path) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    docs = []
    for doc in config.get("documents", []):
        name = doc.get("name", "")
        baseline_value = doc.get("baseline", "")
        enforce = doc.get("enforce", True)
        path = resolve_baseline(baseline_value)
        if not path.exists():
            docs.append({
                "name": name,
                "enforce": enforce,
                "baseline": baseline_value,
                "error": "baseline_not_found",
                "annotations": [],
            })
            continue
        annotations = load_annotations(path)
        checked = [
            check_annotation(item, i) for i, item in enumerate(annotations, start=1)
        ]
        doc_check = check_document_placeholder(path)
        docs.append({
            "name": name,
            "enforce": enforce,
            "baseline": baseline_value,
            "resolved_path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            "annotation_count": len(checked),
            "doc_check": doc_check,
            "annotations": checked,
        })
    return {
        "config": str(config_path.relative_to(ROOT)) if config_path.is_relative_to(ROOT) else str(config_path),
        "documents": docs,
    }


def summarize(report: dict) -> dict:
    issue_counter: dict[str, int] = {}
    total_annotations = 0
    total_needs_fix = 0
    per_doc = []
    for doc in report["documents"]:
        if "error" in doc:
            per_doc.append({
                "name": doc["name"],
                "enforce": doc["enforce"],
                "error": doc["error"],
                "total": 0,
                "needs_fix": 0,
            })
            continue
        total = doc.get("annotation_count", 0)
        needs_fix = sum(1 for a in doc["annotations"] if a["quality"] == "needs_fix")
        total_annotations += total
        total_needs_fix += needs_fix
        for a in doc["annotations"]:
            for issue in a["issues"]:
                issue_counter[issue] = issue_counter.get(issue, 0) + 1
        per_doc.append({
            "name": doc["name"],
            "enforce": doc["enforce"],
            "total": total,
            "needs_fix": needs_fix,
            "fn_placeholder": doc.get("doc_check", {}).get("fn_placeholder", False),
            "no_fn_section": doc.get("doc_check", {}).get("no_fn_section", False),
        })
    return {
        "total_annotations": total_annotations,
        "total_needs_fix": total_needs_fix,
        "issue_counts": dict(sorted(issue_counter.items(), key=lambda kv: (-kv[1], kv[0]))),
        "per_document": per_doc,
    }


ISSUE_LABELS = {
    "missing_page": "缺页码",
    "placeholder_author": "作者占位",
    "empty_selected_text": "选中文本为空",
    "vague_selected_text": "选中文本是概念描述",
    "empty_context": "上下文为空",
    "missing_expected_rule": "缺期望规则",
    "suspicious_rule": "规则未确认",
}


def render_markdown(report: dict, summary: dict) -> str:
    lines = []
    lines.append("# Gold Set 标注补全清单")
    lines.append("")
    lines.append("> 由 `scripts/audit_goldset_quality.py` 生成。数字可复算，勿手工改统计。")
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    lines.append(f"- 批注总数：**{summary['total_annotations']}**")
    lines.append(f"- 需补全：**{summary['total_needs_fix']}**")
    lines.append("")
    lines.append("| 文档 | 强制 | 批注数 | 需补全 | FN占位 |")
    lines.append("|---|---|---|---|---|")
    for d in summary["per_document"]:
        if "error" in d:
            lines.append(f"| {d['name']} | {'是' if d['enforce'] else '否'} | - | - | 文件缺失: {d['error']} |")
            continue
        fn = "是" if (d["fn_placeholder"] or d["no_fn_section"]) else "否"
        lines.append(
            f"| {d['name']} | {'是' if d['enforce'] else '否'} | {d['total']} | {d['needs_fix']} | {fn} |"
        )
    lines.append("")
    lines.append("问题分布：" + "、".join(
        f"{ISSUE_LABELS.get(k, k)} {v} 条" for k, v in summary["issue_counts"].items()
    ))
    lines.append("")
    lines.append("---")
    lines.append("")

    for doc in report["documents"]:
        lines.append(f"## {doc['name']}")
        lines.append("")
        if "error" in doc:
            lines.append(f"> 基线文件未找到：`{doc['baseline']}`")
            lines.append("")
            continue
        lines.append(f"基线：`{doc['resolved_path']}` · 强制评测：{'是' if doc['enforce'] else '否'}")
        lines.append("")
        dc = doc.get("doc_check", {})
        if dc.get("no_fn_section"):
            lines.append("> ⚠ 未找到 FN（漏检项）区 —— recall 分母不可知，必须补一节漏检项。")
            lines.append("")
        elif dc.get("fn_placeholder"):
            lines.append("> ⚠ FN（漏检项）区仍是 `【待补】` 占位 —— 必须填真实漏检项。")
            lines.append("")
        needs = [a for a in doc["annotations"] if a["quality"] == "needs_fix"]
        if not needs:
            lines.append("本文档全部批注质量合格。")
            lines.append("")
            continue
        lines.append("| # | 期望规则 | 选中文本 | 作者 | 问题 | 待补页码 | 待补上下文 |")
        lines.append("|---|---|---|---|---|---|---|")
        for a in needs:
            labels = "、".join(ISSUE_LABELS.get(i, i) for i in a["issues"])
            selected = (a["selected_text"] or "").replace("|", "\\|").replace("\n", " ")
            rule = a["expected_rule"] or "—"
            author = a["author"] or "—"
            lines.append(
                f"| {a['index']} | {rule} | {selected} | {author} | {labels} | ____ | ____ |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="扫描 gold set 标注质量，产出补全清单")
    parser.add_argument(
        "--config",
        default="config/review-evaluation-suite.accuracy.json",
        help="评估套件配置路径（相对 backend/ 或绝对路径）",
    )
    parser.add_argument("--json-out", help="结构化扫描结果输出路径")
    parser.add_argument("--md-out", help="标注员填写清单输出路径")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute() and not config_path.exists():
        config_path = ROOT / config_path
    if not config_path.exists():
        print(f"[错误] 配置文件不存在: {config_path}", file=sys.stderr)
        return 2

    report = scan(config_path)
    summary = summarize(report)

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"report": report, "summary": summary}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[写出] {out}")
    if args.md_out:
        out = Path(args.md_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_markdown(report, summary), encoding="utf-8")
        print(f"[写出] {out}")

    print(f"\n批注总数: {summary['total_annotations']}  需补全: {summary['total_needs_fix']}")
    print("按文档:")
    for d in summary["per_document"]:
        if "error" in d:
            print(f"  - {d['name']}: 基线缺失 ({d['error']})")
        else:
            fn = " FN占位" if (d["fn_placeholder"] or d["no_fn_section"]) else ""
            print(f"  - {d['name']}: {d['needs_fix']}/{d['total']} 需补全{fn}")
    print("问题分布:")
    for k, v in summary["issue_counts"].items():
        print(f"  - {ISSUE_LABELS.get(k, k)}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
