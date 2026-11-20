from app.review_engine.dashboard_metrics import compute_quality_rates


def test_detection_rate_unset_without_manual_supplements():
    result = compute_quality_rates(
        platform_detected=12,
        manual_supplemented=0,
        false_positive_count=3,
        platform_reported=15,
    )

    assert result["detection_rate"] is None
    assert result["detection_rate_available"] is False
    assert result["false_positive_rate"] == 0.2


def test_detection_rate_uses_manual_supplements_as_misses():
    result = compute_quality_rates(
        platform_detected=8,
        manual_supplemented=2,
        false_positive_count=1,
        platform_reported=9,
    )

    assert result["detection_rate_available"] is True
    assert result["detection_rate"] == 0.8
    assert result["expected_issues"] == 10


def test_false_positive_rate_uses_unfiltered_platform_set():
    from types import SimpleNamespace
    from app.api import review as review_api

    issues = [
        SimpleNamespace(source="rule", status="false_positive", original_text="rule hit", suggestion="fix", audit_basis="规范", rule="R999"),
        SimpleNamespace(source="ai", status="confirmed", original_text="ai hit", suggestion="fix it", audit_basis="规范条款", rule="AI-001"),
    ]
    metrics = review_api._dashboard_quality_metrics(issues)
    visible = review_api._dashboard_visible_issues(issues)
    assert metrics["false_positive_count"] == 1
    assert metrics["false_positive_rate"] == 0.5
    assert [item.status for item in visible] == ["confirmed"]


def test_dashboard_issue_group_uses_real_categories():
    from types import SimpleNamespace
    from app.api import review as review_api

    assert review_api._dashboard_issue_group(SimpleNamespace(category="术语一致性", rule="TERM-001", description="")) == "术语"
    assert review_api._dashboard_issue_group(SimpleNamespace(category="标点符号", rule="DOC-PUNCT-001", description="")) == "格式与写法"
    assert review_api._dashboard_issue_group(SimpleNamespace(category="操作步骤语气", rule="DOC-PROC-001", description="不得添加请")) == "语法与表达"
    assert review_api._dashboard_issue_group(SimpleNamespace(category="图片/对象缺失", rule="PDF-VISUAL-001", description="")) == "图表与版式"
    assert review_api._dashboard_issue_group(SimpleNamespace(category="", rule="", description="")) == "其他"


def test_dashboard_issue_summary_merges_similar_wording():
    from types import SimpleNamespace
    from app.api import review as review_api

    term_a = review_api._dashboard_issue_distribution_label(SimpleNamespace(category="", rule="", description="同一术语全文统一"))
    term_b = review_api._dashboard_issue_distribution_label(SimpleNamespace(category="", rule="", description="同一概念全文统一，不混用"))
    assert term_a == term_b == "术语不统一"

    grammar_a = review_api._dashboard_issue_distribution_label(SimpleNamespace(category="", rule="", description="避免'不避免'类语法错误"))
    grammar_b = review_api._dashboard_issue_distribution_label(SimpleNamespace(category="", rule="", description="避免“不避免”类语法错误"))
    assert grammar_a == grammar_b == "避免「不避免」类语法"

    honorific = review_api._dashboard_issue_distribution_label(SimpleNamespace(
        category="操作步骤语气",
        rule="",
        description="操作步骤中不得添加“请”等敬语（除UI界面本身显示的提示外）",
    ))
    assert honorific == "操作步骤勿用敬语"

    assert review_api._dashboard_issue_distribution_label(SimpleNamespace(category="数字与单位格式", rule="CYY-CN-FMT-001", description="")) == "温度范围单位空格"
    assert review_api._dashboard_issue_distribution_label(SimpleNamespace(category="中英文混用", rule="CYY-CN-MIXED-008", description="")) == "中英文术语混用"
    assert review_api._dashboard_issue_distribution_label(SimpleNamespace(category="结构完整性", rule="CYY-CN-ROHS-001", description="")) == "有害物质表缺部件"
    assert review_api._dashboard_issue_distribution_label(SimpleNamespace(
        category="",
        rule="EXT-R020",
        description="错别字检查：避免现成误用为现场",
    ), {"EXT-R020": "错别字检查：避免现成误用为现场"}) == "错别字"
