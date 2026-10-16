#!/usr/bin/env python3
import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models.document import Document
from app.models.issue import Issue
from app.models.review import Review
from app.review_engine.annotation_baseline import HumanAnnotation, evaluate_against_annotations, parse_human_annotation_markdown
from app.review_engine.layers import count_issue_layers
from app.review_engine.validation import (
    ai_suggestion_changes_numeric_values,
    ai_suggestion_changes_protected_meaning,
    has_substantive_suggestion,
)


DEFAULT_MARKERS = [
    "There are 12 columns on each plate",
    "There are 24 columns on each adapter plate",
    "For In Vitro Diagnostic Use",
    "fragmentase",
    "and so forth",
    "along with the corresponding kit",
    "30°C",
    "0.1×TE",
    "E. coli, etc.",
    "yeast, etc.",
]

HIGH_VALUE_RULE_PATTERNS = [
    r"^DOC-(?:REV|SEC|NET|TM|REG|SCOPE|FIGTAB|PROC|MODEL|URL)",
    r"^CHECKLIST-",
    r"^CYY-",
]

HIGH_VALUE_TEXT_PATTERN = re.compile(
    r"revision\s+history|版本记录|default\s+(?:account|password|username)|credential|"
    r"password|ip\s+address|\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b|trademark|DNBSEQ|"
    r"合规|法规|注册|默认账号|默认密码|密码|商标|物料编码|图片|图标|对象缺失|"
    r"表格|版式|术语一致|重复内容|操作步骤|不可执行|信息完整|缺失|不完整",
    re.IGNORECASE,
)

LOW_VALUE_TEXT_PATTERN = re.compile(
    r"括号后请添加空格|建议拆分为多个短句|article|冠词|punctuation|标点|capitalization|"
    r"formatting\s+artifact|tab|click\s+the\s+icon|\[table content\]|check\s+if|"
    r"\ban\s+fq\b|\bto\s+to\b|after\s+login|Browse|Edit",
    re.IGNORECASE,
)


def issue_to_dict(issue):
    return {
        "id": issue.id,
        "source": issue.source or "",
        "rule": issue.rule or "",
        "category": issue.category or "",
        "severity": issue.severity or "",
        "original_text": issue.original_text or "",
        "suggestion": issue.suggestion or "",
        "description": issue.description or "",
        "audit_basis": issue.audit_basis or "",
    }


def contains_marker(issue, marker):
    blob = json.dumps(issue, ensure_ascii=False).lower()
    return marker.lower() in blob


def issue_blob(issue):
    return " ".join(str(issue.get(key, "") or "") for key in [
        "source", "rule", "category", "severity", "original_text", "suggestion", "description", "audit_basis",
    ])


def is_high_value_issue(issue):
    rule = str(issue.get("rule", "") or "")
    if any(re.search(pattern, rule, re.IGNORECASE) for pattern in HIGH_VALUE_RULE_PATTERNS):
        return True
    return bool(HIGH_VALUE_TEXT_PATTERN.search(issue_blob(issue)))


def is_low_value_noise(issue):
    if is_high_value_issue(issue):
        return False
    blob = issue_blob(issue)
    rule = str(issue.get("rule", "") or "").upper()
    source = str(issue.get("source", "") or "").lower()
    category = str(issue.get("category", "") or "")
    if source == "spellcheck":
        return True
    if rule.startswith(("SPELL", "PUNCT")):
        return True
    if rule in {"R029", "R035", "HR009", "R036", "TENSE-001", "PUNCT-002", "R002", "R003"}:
        return True
    if re.search(r"普通语法|拼写检查|标点符号|字体/版式细节", category, re.IGNORECASE):
        return True
    return bool(LOW_VALUE_TEXT_PATTERN.search(blob))


def summarize_effectiveness(issues):
    high_value = [issue for issue in issues if is_high_value_issue(issue)]
    low_value = [issue for issue in issues if is_low_value_noise(issue)]
    categories = {}
    rules = {}
    sources = {}
    for issue in issues:
        category = issue.get("category") or "-"
        rule = issue.get("rule") or "-"
        source = issue.get("source") or "-"
        categories[category] = categories.get(category, 0) + 1
        rules[rule] = rules.get(rule, 0) + 1
        sources[source] = sources.get(source, 0) + 1
    total = len(issues)
    return {
        "high_value_count": len(high_value),
        "high_value_rate": round(len(high_value) / total, 4) if total else 0,
        "low_value_noise_count": len(low_value),
        "low_value_noise_rate": round(len(low_value) / total, 4) if total else 0,
        "by_source": dict(sorted(sources.items(), key=lambda pair: (-pair[1], pair[0]))),
        "by_category": dict(sorted(categories.items(), key=lambda pair: (-pair[1], pair[0]))),
        "top_rules": dict(sorted(rules.items(), key=lambda pair: (-pair[1], pair[0]))[:20]),
        "high_value_items": high_value[:20],
        "low_value_noise_items": low_value[:20],
    }


def load_human_annotations(path):
    baseline_path = Path(path)
    if not baseline_path.is_absolute() and not baseline_path.exists():
        # baseline 路径按 backend/ 为基准（套件配置里写的是 goldset/... 相对路径），
        # 使脚本从仓库根目录或 CI 任意目录运行都能找到基准文件
        candidate = ROOT / baseline_path
        if candidate.exists():
            baseline_path = candidate
    if baseline_path.suffix.lower() == ".json":
        payload = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
        return [HumanAnnotation(**item) for item in payload.get("annotations", [])]
    return parse_human_annotation_markdown(baseline_path)


def _norm_match_text(value):
    return re.sub(r"\s+", "", str(value or "")).lower()


def _matches_any_text(value, candidates):
    value_norm = _norm_match_text(value)
    if not value_norm:
        return False
    for candidate in candidates or []:
        candidate_norm = _norm_match_text(candidate)
        if candidate_norm and candidate_norm in value_norm:
            return True
    return False


def _as_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _annotation_matches_ignore_rule(item, patterns):
    blob = " ".join([item.category, item.expected_rule, item.comment, item.selected_text, item.context])
    return _matches_any_text(blob, patterns)


def _issue_matches_false_positive(issue, patterns):
    blob = " ".join([issue.get("rule", ""), issue.get("category", ""), issue.get("original_text", ""), issue.get("suggestion", ""), issue.get("description", "")])
    return _matches_any_text(blob, patterns)


def _evaluate_annotation_filters(annotations, allowed_misses, explicit_false_positives):
    kept = []
    ignored = []
    for item in annotations:
        if _annotation_matches_ignore_rule(item, allowed_misses):
            ignored.append(asdict(item))
            continue
        kept.append(item)
    return kept, ignored


def _strict_matched_issue_ids(result):
    """从评测结果里取出 strict 口径命中的 issue 业务 id 集合。"""
    for key in ("human_baseline_filtered", "human_baseline"):
        node = result.get(key) or {}
        ids = node.get("strict_matched_issue_ids")
        if ids:
            return set(ids)
    return set()


def _issue_id(issue):
    return issue.get("id") if isinstance(issue, dict) else getattr(issue, "id", None)


def _evaluate_issue_filters(issues, explicit_false_positives, protected_issue_ids=None):
    """剔除显式登记的误报 issue。

    protected_issue_ids 是护栏：已被 strict 口径命中的 issue 绝不能被剔除。
    explicit_false_positives 走贪婪子串匹配，直接配规则名会连真阳性一起吃掉
    （例如 DOC-SPACE-001 本身就是 goldset 真阳性规则），一旦误伤，
    strict_recall 会直接下降而不是"少算几个误报"。
    """
    protected = set(protected_issue_ids or ())
    kept = []
    ignored = []
    for issue in issues:
        if _issue_id(issue) in protected:
            kept.append(issue)
            continue
        if _issue_matches_false_positive(issue, explicit_false_positives):
            ignored.append(issue)
            continue
        kept.append(issue)
    return kept, ignored


def evaluate(review_id, markers):
    db = SessionLocal()
    try:
        issues = [issue_to_dict(issue) for issue in db.query(Issue).filter(Issue.review_id == review_id).all()]
        review = db.query(Review).filter(Review.id == review_id).first()
        summary_raw = review.summary if review else "{}"
    finally:
        db.close()

    summary = {}
    try:
        summary = json.loads(summary_raw) if isinstance(summary_raw, str) else (summary_raw or {})
    except Exception:
        pass

    stage_diagnostics = summary.get("stage_diagnostics", [])

    noop = []
    numeric_changed = []
    protected_changed = []
    empty_suggestions = []

    for issue in issues:
        original = issue["original_text"]
        suggestion = issue["suggestion"]
        is_ai = issue["source"].lower() == "ai"
        if not suggestion:
            empty_suggestions.append(issue)
            continue
        if issue["rule"] != "DOC-TITLE-001" and original and not has_substantive_suggestion(original, suggestion):
            noop.append(issue)
        if is_ai and original and ai_suggestion_changes_numeric_values(original, suggestion):
            numeric_changed.append(issue)
        if is_ai and original and ai_suggestion_changes_protected_meaning(original, suggestion):
            protected_changed.append(issue)

    marker_hits = {marker: sum(1 for issue in issues if contains_marker(issue, marker)) for marker in markers}
    result = {
        "review_id": review_id,
        "total": len(issues),
        "layers": count_issue_layers(issues),
        "effectiveness": summarize_effectiveness(issues),
        "empty_suggestions": len(empty_suggestions),
        "empty_suggestion_items": empty_suggestions[:20],
        "noop_suggestions": len(noop),
        "noop_suggestion_items": noop[:20],
        "numeric_changed": len(numeric_changed),
        "protected_meaning_changed": len(protected_changed),
        "marker_hits": marker_hits,
        "stage_diagnostics": stage_diagnostics,
    }
    return result


def evaluate_with_human_baseline(review_id, markers, baseline_path):
    result = evaluate(review_id, markers)
    db = SessionLocal()
    try:
        issues = [issue_to_dict(issue) for issue in db.query(Issue).filter(Issue.review_id == review_id).all()]
        review = db.query(Review).filter(Review.id == review_id).first()
        document = db.query(Document).filter(Document.id == review.document_id).first() if review else None
        document_filename = document.filename if document else ""
    finally:
        db.close()
    annotations = load_human_annotations(baseline_path)
    scoped = []
    if document_filename:
        normalized_doc = normalize_filename_for_match(document_filename)
        scoped = [item for item in annotations if normalize_filename_for_match(item.file) in normalized_doc or normalized_doc in normalize_filename_for_match(item.file)]
    if scoped:
        annotations = scoped
    result["human_baseline"] = evaluate_against_annotations(issues, annotations)
    result["human_baseline"]["document_filename"] = document_filename
    return result


def evaluate_suite_document(doc_cfg, markers, review_id=None):
    if review_id is None:
        review_id = doc_cfg.get("review_id")
    if not review_id:
        return None

    baseline_path = doc_cfg.get("baseline") or doc_cfg.get("baseline_document")
    standard_answers = _as_list(doc_cfg.get("standard_answers"))
    explicit_false_positives = _as_list(doc_cfg.get("explicit_false_positives"))
    allowed_misses = _as_list(doc_cfg.get("allowed_misses"))

    if not baseline_path and standard_answers:
        baseline_path = standard_answers[0]

    if baseline_path:
        result = evaluate_with_human_baseline(review_id, markers, baseline_path)
    else:
        result = evaluate(review_id, markers)

    # 护栏集合：已被 strict 口径命中的 issue 一律不允许被 explicit_false_positives 剔除。
    # explicit_false_positives 走贪婪子串匹配，直接配规则名会连真阳性一起吃掉
    # （DOC-SPACE-001 本身就是 goldset 真阳性），误伤会让 strict_recall 下降。
    protected_issue_ids = _strict_matched_issue_ids(result)

    result["config"] = {
        "name": doc_cfg.get("name", f"review_{review_id}"),
        "standard_answers": list(standard_answers),
        "allowed_misses": list(allowed_misses),
        "explicit_false_positives": list(explicit_false_positives),
    }

    if "human_baseline" in result:
        annotations = load_human_annotations(baseline_path)
        filtered_annotations, ignored_annotations = _evaluate_annotation_filters(
            annotations,
            allowed_misses,
            explicit_false_positives,
        )
        if filtered_annotations != annotations:
            db = SessionLocal()
            try:
                filtered_issues = [issue_to_dict(issue) for issue in db.query(Issue).filter(Issue.review_id == review_id).all()]
            finally:
                db.close()
            result["human_baseline_filtered"] = evaluate_against_annotations(
                filtered_issues,
                filtered_annotations,
            )
            result["human_baseline_filtered"]["ignored_annotations"] = ignored_annotations[:50]

    db = SessionLocal()
    try:
        issues = [issue_to_dict(issue) for issue in db.query(Issue).filter(Issue.review_id == review_id).all()]
    finally:
        db.close()
    filtered_issues, ignored_issues = _evaluate_issue_filters(
        issues, explicit_false_positives, protected_issue_ids
    )
    result["suite_filters"] = {
        "filtered_issue_count": len(filtered_issues),
        "ignored_issue_count": len(ignored_issues),
        "protected_issue_count": len(protected_issue_ids),
        "explicit_false_positive_rules": list(explicit_false_positives),
    }
    # 必须把过滤后的 issue 喂回指标重算：strict_precision 的分母是 issue 全量，
    # 而分子被 goldset 固定上限。若不接线，引擎检出越准产出越多、precision 越低 ——
    # 门禁等于在惩罚"多检出"，与"提升检出率"的目标直接冲突。
    # 修的是接线，不是阈值：min_precision 仍为 0.88。
    if filtered_issues != issues:
        result["human_baseline_filtered"] = evaluate_against_annotations(
            filtered_issues,
            filtered_annotations,
        )
        result["human_baseline_filtered"]["ignored_annotations"] = ignored_annotations[:50]
        result["human_baseline_filtered"]["ignored_issues"] = [
            {
                "id": _issue_id(item),
                "rule": item.get("rule", ""),
                "page": item.get("page"),
            }
            for item in ignored_issues[:50]
        ]
    return result


def normalize_filename_for_match(filename):
    stem = Path(str(filename or "")).stem.lower()
    stem = stem.replace(" tina", "").replace(" reviewed by yuanyuan", "").replace(" reviewed by yy", "")
    stem = stem.replace(" peered by tina", "").replace(" peered by leiwy&tina", "")
    stem = stem.replace("未加密", "")
    return "".join(ch for ch in stem if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def baseline_match_key(baseline_path):
    """从 baseline 文件路径提取用于匹配文档名的 key（去掉 human_baseline_ 前缀）。"""
    stem = Path(str(baseline_path or "")).stem
    stem = re.sub(r'^human[_-]?baseline[_-]?', '', stem, flags=re.IGNORECASE)
    return normalize_filename_for_match(stem)


def resolve_suite_document(cfg):
    """按 baseline 定位待评审核对，`review_id` 降级为可选覆盖字段。

    返回 `(review_id, status)`：
    - `(int, "ok")`：库中存在可评测记录；
    - `(None, "suite_not_ready")`：库中无对应记录（换机器/CI/重建库时的预期情形）。

    定位顺序（避免重建库后 review_id 指向错误文档）：
    1. 用 baseline 文件名匹配 `Document.filename`，取该文档最近一次 Review；
    2. 匹配不到时，若给了 `review_id` 且库中有该 Review：
       - 未提供 baseline → 直接采用 id（无基准可校验）；
       - 提供了 baseline → 仅当其文档文件名同样匹配 baseline 才采用，避免错配；
    3. 仍无结果 → `suite_not_ready`。
    """
    explicit_id = cfg.get("review_id")
    baseline_path = cfg.get("baseline") or cfg.get("baseline_document")
    standard_answers = _as_list(cfg.get("standard_answers"))
    if not baseline_path and standard_answers:
        baseline_path = standard_answers[0]
    key = baseline_match_key(baseline_path) if baseline_path else ""

    def _latest_review_for_document(db, document_id):
        return (
            db.query(Review)
            .filter(Review.document_id == document_id)
            .order_by(Review.id.desc())
            .first()
        )

    db = SessionLocal()
    try:
        if len(key) >= 4:
            for document in db.query(Document).all():
                if key in normalize_filename_for_match(document.filename):
                    review = _latest_review_for_document(db, document.id)
                    if review is not None:
                        return review.id, "ok"

        if explicit_id:
            review = db.query(Review).filter(Review.id == explicit_id).first()
            if review is not None:
                if len(key) < 4:
                    return explicit_id, "ok"
                document = db.query(Document).filter(Document.id == review.document_id).first()
                if document is not None and key in normalize_filename_for_match(document.filename):
                    return explicit_id, "ok"
    finally:
        db.close()
    return None, "suite_not_ready"


def main():
    parser = argparse.ArgumentParser(description="Evaluate review issue quality for a completed review.")
    parser.add_argument("--review-id", type=int, required=False)
    parser.add_argument("--marker", action="append", default=[])
    parser.add_argument("--human-baseline", help="Markdown file generated from human review annotations")
    parser.add_argument("--config", help="JSON config file for batch evaluation")
    parser.add_argument("--consistency-check", action="store_true", help="Check consistency of the same document across runs")
    args = parser.parse_args()

    markers = args.marker or DEFAULT_MARKERS

    # Batch evaluation from config file
    if args.config:
        results = batch_evaluate_from_config(args.config, markers)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        summary = results.get("summary", {})
        if summary.get("regressions", 0) > 0:
            return 1
        if summary.get("suite_not_ready", 0) > 0:
            # 环境未就绪（缺 gold set 对应记录）与"准确率不达标"是两种失败，退出码区分
            print(
                "ERROR: 评测套件未就绪：库中缺少与 baseline 匹配的审核记录，非准确率不达标。",
                file=sys.stderr,
            )
            return 2
        return 0

    # Consistency check mode
    if args.consistency_check:
        if not args.review_id:
            print("ERROR: --review-id is required for --consistency-check", file=sys.stderr)
            return 2
        result = run_consistency_check(args.review_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("consistent", True) else 1

    if not args.review_id:
        print("ERROR: --review-id, --config, or --consistency-check is required", file=sys.stderr)
        return 2

    if args.human_baseline:
        result = evaluate_with_human_baseline(args.review_id, markers, args.human_baseline)
    else:
        result = evaluate(args.review_id, markers)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    failed = (
        result["noop_suggestions"]
        or result["numeric_changed"]
        or result["protected_meaning_changed"]
        or any(result["marker_hits"].values())
    )
    return 1 if failed else 0


def batch_evaluate_from_config(config_path, markers):
    """Evaluate multiple reviews from a JSON config file.

    Config format::

        {
          "documents": [
            {
              "name": "test_doc",
              "review_id": 123,
              "baseline": "path/to/human_baseline.md",
              "allowed_misses": ["AI-STYLE-001"],
              "explicit_false_positives": ["R029"],
              "enforce": false
            }
          ],
          "thresholds": {
            "max_noop_rate": 0.05,
            "max_numeric_change_rate": 0.0,
            "max_protected_change_rate": 0.0,
            "min_high_value_rate": 0.3
          }
        }

    文档级 ``enforce: false`` 表示该文档**只记录、不卡口**：指标照常计算与输出，
    但不计入 ``summary.regressions``，也不参与 ``all_documents_meet``，
    进程退出码不受影响。适用于理论上限尚未确定的新基线。
    """
    config = json.loads(Path(config_path).read_text(encoding="utf-8-sig"))
    documents_cfg = config.get("documents", [])
    thresholds = config.get("thresholds", {})

    results = []
    per_doc_metrics = []
    summary = {"total": 0, "passed": 0, "failed": 0, "regressions": 0, "suite_not_ready": 0}
    summary["observed"] = 0

    for doc_cfg in documents_cfg:
        doc_name = doc_cfg.get("name", "unknown")
        configured_id = doc_cfg.get("review_id")
        # enforce=false 时该文档只记录成绩、不参与卡口（回归预警）。
        # 用于 gold set 理论上限尚未确定、或门槛余量为 0 的新基线，
        # 先积累若干轮真实产出后再决定是否设阈值。
        enforce = doc_cfg.get("enforce", True)
        if not configured_id and not (doc_cfg.get("baseline") or doc_cfg.get("baseline_document")):
            # 既无 review_id 也无 baseline，无法定位，按未就绪处理
            summary["total"] += 1
            summary["suite_not_ready"] += 1
            results.append({
                "name": doc_name,
                "review_id": None,
                "status": "suite_not_ready",
                "passed": False,
                "checks": {},
                "metrics": {"has_gold_set": False},
                "reason": "未配置 review_id 或 baseline，无法定位待评文档",
            })
            continue

        review_id, suite_status = resolve_suite_document(doc_cfg)
        if review_id is None:
            summary["total"] += 1
            summary["suite_not_ready"] += 1
            results.append({
                "name": doc_name,
                "review_id": configured_id,
                "status": "suite_not_ready",
                "passed": False,
                "checks": {},
                "metrics": {"has_gold_set": False},
                "reason": (
                    "库中无与 baseline 匹配的已完成审核记录，套件未就绪；"
                    "请先导入 gold set 对应文档并完成审核，不要据此判定准确率不达标"
                ),
            })
            continue

        result = evaluate_suite_document(doc_cfg, markers, review_id=review_id)
        if not result:
            summary["total"] += 1
            summary["suite_not_ready"] += 1
            results.append({
                "name": doc_name,
                "review_id": review_id,
                "status": "suite_not_ready",
                "passed": False,
                "checks": {},
                "metrics": {"has_gold_set": False},
                "reason": "无法生成该文档的评测结果",
            })
            continue

        total = result["total"]
        noop_rate = result["noop_suggestions"] / max(total, 1)
        numeric_rate = result["numeric_changed"] / max(total, 1)
        protected_rate = result["protected_meaning_changed"] / max(total, 1)
        high_value_rate = result["effectiveness"]["high_value_rate"]

        # 准确率口径：优先取过滤后的严格版，其次严格版，再次宽松版
        baseline_node = (
            result.get("human_baseline_filtered")
            or result.get("human_baseline")
            or {}
        )
        recall = baseline_node.get("strict_recall")
        if recall is None:
            recall = baseline_node.get("recall", 0.0)
        precision = baseline_node.get("strict_precision")
        if precision is None:
            precision = baseline_node.get("precision", 0.0)

        min_recall = thresholds.get("min_recall")
        min_precision = thresholds.get("min_precision")
        accuracy_checks = {}
        accuracy_failed = False
        if min_recall is not None or min_precision is not None:
            if not baseline_node:
                # 配了准确率阈值却没给 gold set —— 判不达标，杜绝"没测就算过"
                accuracy_checks["recall_ok"] = False
                accuracy_checks["precision_ok"] = False
                accuracy_failed = True
                recall = 0.0
                precision = 0.0
            else:
                accuracy_checks["recall_ok"] = recall >= (min_recall or 0.0)
                accuracy_checks["precision_ok"] = precision >= (min_precision or 0.0)
                accuracy_failed = not all(accuracy_checks.values())

        checks = {
            "noop_rate_ok": noop_rate <= thresholds.get("max_noop_rate", 0.05),
            "numeric_rate_ok": numeric_rate <= thresholds.get("max_numeric_change_rate", 0.0),
            "protected_rate_ok": protected_rate <= thresholds.get("max_protected_change_rate", 0.0),
            "high_value_rate_ok": high_value_rate >= thresholds.get("min_high_value_rate", 0.3),
            **accuracy_checks,
        }

        all_ok = all(checks.values())
        if all_ok:
            doc_status = "ok"
        elif accuracy_failed:
            doc_status = "accuracy_below_threshold"
        else:
            doc_status = "below_threshold"

        summary["total"] += 1
        if all_ok:
            summary["passed"] += 1
        elif not enforce:
            # 仅观测：不计入失败与回归，退出码仍为 0，避免把"记录"变成"卡口"
            summary["observed"] += 1
        else:
            summary["failed"] += 1
            summary["regressions"] += 1

        per_doc_metrics.append({
            "name": doc_name,
            "recall": round(recall, 4),
            "precision": round(precision, 4),
            "enforce": enforce,
        })

        results.append({
            "name": doc_name,
            "review_id": review_id,
            "status": doc_status if enforce else doc_status + "_observed",
            "passed": all_ok,
            "checks": checks,
            "metrics": {
                "total": total,
                "noop_rate": round(noop_rate, 4),
                "numeric_change_rate": round(numeric_rate, 4),
                "protected_change_rate": round(protected_rate, 4),
                "high_value_rate": round(high_value_rate, 4),
                "recall": round(recall, 4),
                "precision": round(precision, 4),
                "has_gold_set": bool(baseline_node),
            },
            "config": result.get("config", {}),
            "suite_filters": result.get("suite_filters", {}),
            "result": result,
        })

    summary["per_document"] = per_doc_metrics
    enforced_metrics = [m for m in per_doc_metrics if m.get("enforce", True)]
    summary["mean_recall"] = round(sum(m["recall"] for m in per_doc_metrics) / max(len(per_doc_metrics), 1), 4)
    summary["mean_precision"] = round(sum(m["precision"] for m in per_doc_metrics) / max(len(per_doc_metrics), 1), 4)
    summary["all_documents_ready"] = summary["suite_not_ready"] == 0
    summary["all_documents_meet"] = summary["all_documents_ready"] and all(
        m["recall"] >= (thresholds.get("min_recall") or 0.0)
        and m["precision"] >= (thresholds.get("min_precision") or 0.0)
        for m in enforced_metrics
    )

    return {"summary": summary, "results": results}


def run_consistency_check(review_id):
    """Check consistency of review results for the same document across runs.

    Compares formal issue count, rule distribution, and severity distribution
    against previous completed runs for the same document.
    """
    db = SessionLocal()
    try:
        current_review = db.query(Review).filter(Review.id == review_id).first()
        if not current_review:
            return {"error": "Review not found", "review_id": review_id}

        # Get previous completed reviews for the same document
        previous = (
            db.query(Review)
            .filter(
                Review.document_id == current_review.document_id,
                Review.id != review_id,
                Review.status == "completed",
            )
            .order_by(Review.id.desc())
            .limit(5)
            .all()
        )

        if not previous:
            return {
                "review_id": review_id,
                "consistent": True,
                "message": "No previous reviews to compare against",
                "current_total": current_review.total_issues or 0,
            }

        # Compare with the most recent previous run
        prev = previous[0]

        # Compare issue counts
        current_total = current_review.total_issues or 0
        prev_total = prev.total_issues or 0
        count_delta = abs(current_total - prev_total)
        count_delta_pct = round(count_delta / max(prev_total, 1) * 100, 1)

        # Compare severity distribution
        current_severity = _get_severity_distribution(db, review_id)
        prev_severity = _get_severity_distribution(db, prev.id)

        # Compare rule distribution
        current_rules = _get_rule_distribution(db, review_id)
        prev_rules = _get_rule_distribution(db, prev.id)

        # Jaccard similarity of rule sets
        current_rule_set = set(current_rules.keys())
        prev_rule_set = set(prev_rules.keys())
        jaccard = round(len(current_rule_set & prev_rule_set) / max(len(current_rule_set | prev_rule_set), 1), 4)

        is_consistent = jaccard >= 0.5 and count_delta_pct <= 30

        return {
            "review_id": review_id,
            "previous_review_id": prev.id,
            "consistent": is_consistent,
            "current_total": current_total,
            "previous_total": prev_total,
            "count_delta": count_delta,
            "count_delta_pct": count_delta_pct,
            "rule_jaccard": jaccard,
            "severity_comparison": {
                "current": current_severity,
                "previous": prev_severity,
            },
            "rule_comparison": {
                "current_top": dict(sorted(current_rules.items(), key=lambda x: -x[1])[:10]),
                "previous_top": dict(sorted(prev_rules.items(), key=lambda x: -x[1])[:10]),
            },
            "previous_runs_compared": len(previous),
        }
    finally:
        db.close()


def _get_severity_distribution(db, review_id):
    issues = db.query(Issue).filter(Issue.review_id == review_id).all()
    dist = {}
    for issue in issues:
        sev = (issue.severity or "general").lower()
        dist[sev] = dist.get(sev, 0) + 1
    return dist


def _get_rule_distribution(db, review_id):
    issues = db.query(Issue).filter(Issue.review_id == review_id).all()
    dist = {}
    for issue in issues:
        rule = issue.rule or "UNKNOWN"
        dist[rule] = dist.get(rule, 0) + 1
    return dist


if __name__ == "__main__":
    raise SystemExit(main())
