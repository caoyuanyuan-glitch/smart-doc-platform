import json

from app.review_engine.annotation_baseline import HumanAnnotation, classify_human_annotation, evaluate_against_annotations
from scripts import evaluate_review


def test_as_list_wraps_scalar_values():
    assert evaluate_review._as_list("baseline.md") == ["baseline.md"]
    assert evaluate_review._as_list(["a", "b"]) == ["a", "b"]


def test_evaluate_annotation_filters_supports_allowed_misses_and_false_positives():
    annotations = [
        HumanAnnotation(
            file="doc-a.md",
            page="1",
            annotation_type="批注",
            author="Tina",
            comment="建议优化表达",
            selected_text="原句",
            context="上下文",
            category="表达与句式",
            layer="ai_assisted",
            expected_rule="AI-STYLE-001",
        )
    ]

    kept, ignored = evaluate_review._evaluate_annotation_filters(annotations, ["AI-STYLE-001"], ["R029"])

    assert kept == []
    assert ignored == [
        {
            "file": "doc-a.md",
            "page": "1",
            "annotation_type": "批注",
            "author": "Tina",
            "comment": "建议优化表达",
            "selected_text": "原句",
            "context": "上下文",
            "category": "表达与句式",
            "layer": "ai_assisted",
            "expected_rule": "AI-STYLE-001",
        }
    ]


def test_annotation_classifier_prioritizes_chinese_typo_page_and_address_cases():
    assert classify_human_annotation('错别字，"线揽"应为"线缆"', '扫码枪 线揽 本表格', '') == (
        '术语拼写', 'deterministic', 'DET-TERM-SPELL-001'
    )
    assert classify_human_annotation('页码错误，后面又出现了24', '24', '') == (
        '页码异常', 'structural_consistency', 'STRUCT-PAGE-NUM-001'
    )
    assert classify_human_annotation('确认下吧，是否城南大道', '越南大道', '') == (
        '地址字段确认', 'ai_assisted', 'AI-ADDR-001'
    )


def test_evaluate_against_annotations_matches_page_address_and_check_rules():
    annotations = [
        HumanAnnotation('doc.pdf', '1', 'Square', 'Tina', '页码错误，后面又出现了24', '24', '', '页码异常', 'structural_consistency', 'STRUCT-PAGE-NUM-001'),
        HumanAnnotation('doc.pdf', '2', 'Square', 'Tina', '确认下吧，是否城南大道', '越南大道', '', '地址字段确认', 'ai_assisted', 'AI-ADDR-001'),
        HumanAnnotation('doc.pdf', '3', 'Square', 'Tina', '是登录，不是登陆', '登陆密码', '', '人工确认项', 'ai_assisted', 'AI-CHECK-001'),
    ]
    issues = [
        {'rule': 'CYY-CN-PAGE-001', 'category': '页码异常', 'original_text': '24', 'description': ''},
        {'rule': 'CYY-CN-ADDR-001', 'category': '人工确认项', 'original_text': '越南大道2号', 'description': ''},
        {'rule': 'CYY-CN-CONSIST-025', 'category': '术语一致性', 'original_text': '登陆密码信息', 'description': '登录，不是登陆'},
    ]

    result = evaluate_against_annotations(issues, annotations)

    assert result['matched'] == 3


def test_evaluate_against_annotations_matches_layout_and_image_cross_rules():
    annotations = [
        HumanAnnotation('doc.pdf', '58', 'Square', 'Tina', '调整列宽，让这里可以一行展示完整', '运输 境', '', '表格/版式', 'structural_consistency', 'STRUCT-LAYOUT-001'),
        HumanAnnotation('doc.pdf', '23', 'Square', 'Tina', '确认下这个步骤是否需要', '4. 点击【Install】开始安装系统。安装完成后，点击【Finish】完成安装。5. 在计算机桌面双击打开本系统。', '', '图片/对象缺失', 'ai_assisted', 'STRUCT-IMAGE-001'),
    ]
    issues = [
        {'rule': 'CYY-CN-CONSIST-019', 'category': '术语一致性', 'original_text': '储存环 境', 'description': '环境名称建议保持连写一致。'},
        {'rule': 'CYY-CN-LOGIC-007', 'category': '内容逻辑', 'original_text': '在MacOS 端安装本系统', 'description': 'MacOS 拖拽安装与 Windows 安装向导式按钮同时出现，流程逻辑存在冲突。'},
    ]

    result = evaluate_against_annotations(issues, annotations)

    assert result['matched'] == 2


def test_evaluate_against_annotations_reports_strict_and_loose_matches_separately():
    annotations = [
        HumanAnnotation('doc.pdf', '1', 'Square', 'Tina', '调整列宽，让这里可以一行展示完整', '运输 境', '', '表格/版式', 'structural_consistency', 'STRUCT-LAYOUT-001'),
    ]
    issues = [
        {'rule': 'CYY-CN-LAYOUT-002', 'category': '表格/版式', 'original_text': '其他表格内容', 'description': '检测到同类版式问题'},
    ]

    result = evaluate_against_annotations(issues, annotations)

    assert result['matched'] == 1
    assert result['strict_matched'] == 0
    assert result['match_rate'] == 1.0
    assert result['strict_match_rate'] == 0.0
    assert result['strict_misses'][0]['expected_rule'] == 'STRUCT-LAYOUT-001'


def test_evaluate_against_annotations_reports_precision_recall_and_f1():
    annotations = [
        HumanAnnotation('doc.pdf', '1', 'Square', 'Tina', '单位前面加空格', '24VDC，5A', '', '单位/空格', 'deterministic', 'DET-SPACE-001'),
        HumanAnnotation('doc.pdf', '2', 'Square', 'Tina', '错别字，链，不是连', '二连读长', '', '术语拼写', 'deterministic', 'DET-TERM-SPELL-001'),
    ]
    issues = [
        {'rule': 'CYY-CN-FMT-003', 'category': '数字与单位格式', 'original_text': '24VDC，5A', 'suggestion': '24 VDC，5 A', 'description': ''},
        {'rule': 'CYY-CN-SPELL-003', 'category': '术语拼写', 'original_text': '二连读长', 'suggestion': '二链读长', 'description': ''},
        {'rule': 'CYY-CN-CONSIST-999', 'category': '术语一致性', 'original_text': '额外问题', 'suggestion': '额外修正', 'description': ''},
    ]

    result = evaluate_against_annotations(issues, annotations)

    assert result['human_total'] == 2
    assert result['issue_total'] == 3
    assert result['recall'] == 1.0
    assert result['precision'] == 0.6667
    assert result['f1'] == 0.8
    assert result['matched_issue_count'] == 2
    assert result['unmatched_issue_count'] == 1
    assert result['unmatched_issues_by_category'] == {'术语一致性': 1}


def test_evaluate_against_annotations_matches_ocr_fragment_overlap_for_precision():
    annotations = [
        HumanAnnotation('doc.pdf', '27', 'Square', 'Tina', '错别字，链，不是连', '连读 者某', '', '术语拼写', 'deterministic', 'DET-TERM-SPELL-001'),
        HumanAnnotation('doc.pdf', '52', 'Square', 'Tina', '多余的字', '查的托 % 酒', '', '人工审核其他项', 'ai_assisted', 'AI-HUMAN-OTHER'),
    ]
    issues = [
        {'rule': 'CYY-CN-SPELL-003', 'category': '术语拼写', 'original_text': '二连读长', 'suggestion': '二链读长', 'description': '错别字'},
        {'rule': 'CYY-CN-GRAMMAR-007', 'category': '语法表达', 'original_text': '检查的托盘表面', 'suggestion': '检查托盘表面', 'description': '多余助词'},
    ]

    result = evaluate_against_annotations(issues, annotations)

    assert result['precision'] == 1.0
    assert result['matched_issue_count'] == 2


def test_evaluate_against_annotations_matches_issue_text_in_human_context_and_comment():
    annotations = [
        HumanAnnotation('doc.pdf', '15', 'Square', 'Tina', '与后面的大类重复', '大类、 表。', '', '重复内容', 'structural_consistency', 'STRUCT-DUP-001'),
        HumanAnnotation('doc.pdf', '23', 'Square', 'Tina', '删了', '程。 】可', '可点击【Browse】可选择目标安装目录。', '表达与句式', 'ai_assisted', 'AI-STYLE-001'),
        HumanAnnotation('doc.pdf', '78', 'Square', 'Tina', '（即，自增物料）', '料。', '', '人工确认项', 'ai_assisted', 'AI-CHECK-001'),
    ]
    issues = [
        {'rule': 'CYY-CN-DUP-002', 'category': '重复内容', 'original_text': '测试物料大类、试剂等大 类', 'suggestion': '测试物料大类、试剂等'},
        {'rule': 'CYY-CN-GRAMMAR-007', 'category': '表达与句式', 'original_text': '可点击【Browse】可选择', 'suggestion': '点击【Browse】可选择目标安装目录'},
        {'rule': 'CYY-CN-CONSIST-012', 'category': '术语一致性', 'original_text': '自增物料', 'suggestion': '明确“自增物料”的定义'},
    ]

    result = evaluate_against_annotations(issues, annotations)

    assert result['precision'] == 1.0
    assert result['matched_issue_count'] == 3


def test_batch_evaluate_from_config_preserves_suite_fields(tmp_path, monkeypatch):
    config = {
        "documents": [
            {
                "name": "doc-a",
                "review_id": 101,
                "standard_answers": ["baseline-a.md", "baseline-b.md"],
                "allowed_misses": ["AI-STYLE-001"],
                "explicit_false_positives": ["R029"],
            },
            {
                "name": "doc-b",
                "review_id": 202,
                "standard_answers": ["baseline-c.md"],
            },
        ],
        "thresholds": {
            "max_noop_rate": 0.1,
            "max_numeric_change_rate": 0.0,
            "max_protected_change_rate": 0.0,
            "min_high_value_rate": 0.2,
        },
    }
    config_path = tmp_path / "review-suite.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    seen = []

    def fake_evaluate_suite_document(doc_cfg, markers):
        seen.append(doc_cfg)
        return {
            "review_id": doc_cfg["review_id"],
            "total": 1,
            "noop_suggestions": 0,
            "numeric_changed": 0,
            "protected_meaning_changed": 0,
            "effectiveness": {
                "high_value_rate": 0.5,
                "high_value_items": [],
                "low_value_noise_items": [],
            },
            "marker_hits": {},
            "config": doc_cfg,
            "suite_filters": {},
        }

    monkeypatch.setattr(evaluate_review, "evaluate_suite_document", fake_evaluate_suite_document)

    result = evaluate_review.batch_evaluate_from_config(str(config_path), ["marker"])

    assert result["summary"] == {"total": 2, "passed": 2, "failed": 0, "regressions": 0}
    assert seen[0]["standard_answers"] == ["baseline-a.md", "baseline-b.md"]
    assert seen[0]["allowed_misses"] == ["AI-STYLE-001"]
    assert seen[0]["explicit_false_positives"] == ["R029"]
    assert result["results"][0]["config"]["standard_answers"] == ["baseline-a.md", "baseline-b.md"]
