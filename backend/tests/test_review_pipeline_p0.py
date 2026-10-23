"""P0/P1 审核召回链路回归：截断解除、页码通道、视觉 category、降级留痕。"""

import json
from types import SimpleNamespace

from app.api import review as review_api
from app.review_engine.annotation_baseline import (
    HumanAnnotation,
    _issue_blob,
    _matches_annotation_strictly,
    _matches_expected_rule,
    evaluate_against_annotations,
)


def _annotation(**kwargs):
    payload = {
        "file": "doc.pdf",
        "page": "1",
        "annotation_type": "Highlight",
        "author": "reviewer",
        "comment": "comment",
        "selected_text": "selected",
        "context": "context text here",
        "category": "术语拼写",
        "layer": "deterministic",
        "expected_rule": "DET-TERM-SPELL-001",
    }
    payload.update(kwargs)
    return HumanAnnotation(**payload)


def _issue(**kwargs):
    payload = {
        "id": 1,
        "source": "rule",
        "rule": "SPELL-TRANS",
        "category": "拼写错误",
        "severity": "general",
        "original_text": "Ilde",
        "suggestion": "Idle",
        "description": "spelling",
        "audit_basis": "规范",
        "context": "Status: Ilde",
    }
    payload.update(kwargs)
    return payload


def test_t1_page_metadata_keeps_all_pages(monkeypatch):
    document = SimpleNamespace(file_type="pdf", filename="g99.pdf")
    monkeypatch.setattr(review_api, "_get_document_upload_path", lambda document: None)
    content = "\n\f\n".join(f"page {index} body text" for index in range(1, 245))

    metadata = review_api._extract_pdf_page_metadata(document, content)

    assert metadata["page_count"] == 244
    assert len(metadata["pages"]) == 244
    assert metadata["pages"][-1]["page_number"] == 244


def test_t2_suspicious_candidates_are_not_capped_at_30():
    pages = []
    for index in range(1, 189):
        pages.append({
            "page_number": index,
            "text_preview": f"Table {index} layout | col | col",
            "footer_preview": [],
            "block_counts": {"table": 2},
            "table_like_line_count": 3,
            "line_count": 50,
            "char_start": index * 10,
            "char_end": index * 10 + 5,
        })

    result = review_api._collect_pdf_suspicious_pages({
        "enabled": True,
        "pages": pages,
        "page_count": 188,
    })

    assert result["candidate_count"] == 188
    assert len(result["candidates"]) == 188


def test_t3_pdf_limit_keeps_tail_pages_and_records_unscanned_range():
    assert review_api._review_content_limit("pdf") == 500000

    pages = [f"page-{index}-" + ("x" * 40) for index in range(1, 6)]
    content = "\n\f\n".join(pages)
    kept, info = review_api._truncate_content_at_page_boundary(content, 90)

    assert info["truncated"] is True
    assert "\f" not in kept or kept.count("\f") < content.count("\f")
    assert info["unscanned_page_start"] is not None
    assert info["unscanned_page_end"] == 5
    assert info["kept_pages"] < 5
    assert kept in content or content.startswith(kept.split("\n\f\n")[0])
    assert "page-5-" not in kept


def test_t4_offsets_use_production_content_not_extract_pdf(monkeypatch):
    document = SimpleNamespace(file_type="pdf", filename="demo.pdf")
    production = "AAA\n\f\nBBB\n\f\nCCC"
    monkeypatch.setattr(review_api, "_get_document_upload_path", lambda document: review_api.PROJECT_ROOT / "backend")
    monkeypatch.setattr(
        review_api,
        "extract_pdf",
        lambda path: {
            "page_texts": ["AAAA" * 80, "BBBB" * 80, "CCCC" * 80],
            "blocks": [],
        },
    )

    metadata = review_api._extract_pdf_page_metadata(document, production)
    pages = review_api._split_content_pages(production)
    offsets = review_api._page_offsets_from_pages(production)

    assert metadata["page_count"] == 3
    for index, (start, end) in enumerate(offsets):
        assert metadata["pages"][index]["char_start"] == start
        assert metadata["pages"][index]["char_end"] == end
        assert metadata["pages"][index]["char_count"] == len(pages[index])


def test_t5_english_layout_candidate_can_be_promoted():
    candidate = {
        "page_number": 3,
        "reasons": ["table_layout", "dense_table_or_layout"],
        "text_preview": "Revision History Version Date column width table header",
    }
    assert review_api._should_promote_page_candidate_without_visual(candidate) is True


def test_t6_visual_category_prefers_layout_over_figure_and_footer():
    assert review_api._page_visual_issue_category(
        ["dense_table_or_layout", "figure_table_numbering", "table_layout"]
    ) == "表格/版式"
    assert review_api._page_visual_issue_category(
        ["figure_table_numbering", "footer_or_page_number", "table_layout"]
    ) == "表格/版式"


def test_t7_visual_category_keeps_figure_only_as_numbering():
    assert review_api._page_visual_issue_category(["figure_table_numbering"]) == "图表编号"


def test_t8_page_channel_does_not_drop_ref_style_text_hits():
    annotations = []
    issues = []
    samples = [
        ("74", 12, "Make DNB reaction mixture 1 on Page 66:"),
        ("77", 19, "Make DNB reaction mixture 1 on Page 69."),
        ("78", 21, "Table 39 on Page 71."),
        ("80", 25, "Make DNB reaction mixture 1 on Page 73"),
        ("84", 30, "Make DNB reaction mixture 1 on Page 76 as V"),
        ("87", 40, "Make DNB reaction mixture 1 on Page 79 as V"),
    ]
    for index, (ann_page, issue_page, selected) in enumerate(samples, start=1):
        annotations.append(_annotation(
            page=ann_page,
            comment="取消交叉引用，改成 the table below",
            selected_text=selected,
            context=f"shown in {selected}",
            category="交叉引用",
            expected_rule="DET-MATERIAL-001",
        ))
        issues.append(_issue(
            id=index,
            rule="REF-STYLE",
            category="交叉引用",
            original_text=selected,
            suggestion="the table below",
            description="交叉引用写法不规范",
            position=json.dumps({"page_number": issue_page}),
        ))

    result = evaluate_against_annotations(issues, annotations)
    assert result["strict_matched"] == 6


def test_t9_same_page_layout_issue_strict_hits_p69():
    annotation = _annotation(
        page="69",
        comment="检查下样式，太挤了",
        selected_text="s\nT",
        context="Tips The manu actual du Reagents or mucos protective",
        category="表格/版式",
        expected_rule="STRUCT-LAYOUT-001",
    )
    issue = _issue(
        rule="PDF-VISUAL-001",
        category="表格/版式",
        original_text="unrelated visual preview without selected tokens",
        description="PDF 页级渲染复核确认疑点",
        position=json.dumps({"page_number": 69}),
    )

    # F6b: 页级 issue 禁止走页码通道，同页不能当成文本命中
    assert _matches_annotation_strictly(annotation, issue, _issue_blob(issue)) is False
    result = evaluate_against_annotations([issue], [annotation])
    assert result["strict_matched"] == 0


def test_t10_page_anchor_is_or_not_and():
    annotation = _annotation(
        page="74",
        comment="取消交叉引用，改成 the table below",
        selected_text="Make DNB reaction mixture 1 on Page 66:",
        context="Making DNBs Perform the following steps Make DNB reaction mixture 1 on Page 66:",
        category="交叉引用",
        expected_rule="DET-MATERIAL-001",
    )
    issue = _issue(
        rule="REF-STYLE",
        category="交叉引用",
        original_text="Make DNB reaction mixture 1 on Page 66:",
        suggestion="the table below",
        position=json.dumps({"page_number": 12}),
    )

    assert _matches_annotation_strictly(annotation, issue, _issue_blob(issue)) is True


def test_t11_spell_trans_family_is_accepted():
    item = _annotation(
        page="31",
        comment="拼写错误，应该是 Idle",
        selected_text="Ilde",
        context="Status: Ilde",
        expected_rule="DET-TERM-SPELL-001",
    )
    for rule in ("SPELL-TRANS", "SPELL-INS", "SPELL-SPLIT"):
        issue = _issue(rule=rule, category="拼写错误", original_text="", description="")
        assert _matches_expected_rule(item, issue, _issue_blob(issue)) is True


def test_t12_injective_matching_still_pairs_one_issue_to_one_annotation():
    annotations = [
        _annotation(
            page="69",
            comment="检查下样式，太挤了",
            selected_text="s\nT",
            context="Tips The manu actual du",
            category="表格/版式",
            expected_rule="STRUCT-LAYOUT-001",
        ),
        _annotation(
            page="69",
            comment="粗线条",
            selected_text="",
            context="SE100 2.0 8.0 0.5 PE150 3.0 14.0 0.5",
            category="表格/版式",
            expected_rule="STRUCT-LAYOUT-001",
        ),
    ]
    issue = _issue(
        rule="PDF-VISUAL-001",
        category="表格/版式",
        original_text="unrelated visual preview",
        position=json.dumps({"page_number": 69}),
    )

    result = evaluate_against_annotations([issue], annotations)
    assert result["strict_matched"] == 0
    assert result["strict_matched_issue_count"] == 0


def test_t13_provider_unavailable_emits_manual_review_issue(monkeypatch):
    document = SimpleNamespace(file_type="pdf", filename="demo.pdf")
    suspicious_pages = {
        "enabled": True,
        "candidate_count": 1,
        "page_count": 10,
        "candidates": [{
            "page_number": 3,
            "reasons": ["table_layout", "dense_table_or_layout"],
            "char_start": 20,
            "char_end": 80,
            "text_preview": "Revision History Version Date column width table header",
            "table_blocks": 4,
        }],
    }
    monkeypatch.setattr(review_api, "_review_pdf_visual_verify_enabled", lambda: True)
    monkeypatch.setattr(review_api, "_review_pdf_visual_verify_limit", lambda: 24)
    monkeypatch.setattr(review_api, "_visual_provider_available", lambda name: False)
    monkeypatch.setattr(review_api, "set_progress", lambda *args, **kwargs: None)

    filtered, diagnostics = review_api._apply_pdf_visual_verification(
        123, document, "dummy", [], suspicious_pages
    )

    assert diagnostics["reason"] == "provider_unavailable"
    assert diagnostics["page_issue_count"] > 0
    assert any(item.get("rule") == "PDF-VISUAL-001" for item in filtered)
    assert any(item.get("category") == "表格/版式" for item in filtered)


def test_t14_page_backfill_coverage_and_no_conflict():
    pages = [f"page-{index}-content" for index in range(1, 11)]
    content = "\n\f\n".join(pages)
    offsets = review_api._page_offsets_from_pages(content)

    issues = []
    for index, (start, end) in enumerate(offsets, start=1):
        if index <= 3:
            issues.append({
                "original_text": f"known-{index}",
                "position": json.dumps({"start": start, "end": end, "page_number": index}),
            })
        else:
            issues.append({
                "original_text": f"need-fill-{index}",
                "position": json.dumps({"start": start, "end": end}),
            })

    filled = review_api._backfill_issue_page_numbers(issues, content)
    assert filled == 7

    with_page = 0
    for index, issue in enumerate(issues, start=1):
        meta = json.loads(issue["position"])
        assert int(meta["page_number"]) == index
        with_page += 1
    assert with_page / len(issues) >= 0.7


def test_t15_geometry_reasons_map_to_layout_category():
    assert review_api._page_visual_issue_category(["crowded_lines"]) == "表格/版式"
    assert review_api._page_visual_issue_category(["thick_rules"]) == "表格/版式"
    assert review_api._page_visual_issue_category(["image_off_center"]) == "表格/版式"


def test_t16_english_celsius_extra_space_rule():
    issues = review_api._run_manual_engineering_audit(
        "Store the cartridge at 4 ℃ overnight. Keep it at 35 ℃.",
        "pdf",
    )
    space_issues = [item for item in issues if item.get("rule") == "DOC-SPACE-006"]
    originals = {item.get("original_text") for item in space_issues}
    assert "4 ℃" in originals
    assert "35 ℃" in originals
    annotation = _annotation(
        page="82",
        comment="多余空格了吗？全文关注",
        selected_text="℃",
        context="Remove the lid. Store at 4 ℃ overnight.",
        category="单位/空格",
        expected_rule="DET-SPACE-001",
    )
    issue = space_issues[0]
    issue["position"] = json.dumps({"page_number": 82})
    assert _matches_expected_rule(annotation, issue, _issue_blob(issue)) is True
    assert _matches_annotation_strictly(annotation, issue, _issue_blob(issue)) is True


def test_r3_celsius_skips_chinese_local_context():
    mixed = "保存温度 95 ℃，Store the cartridge at 4 ℃ overnight."
    mixed_issues = review_api._run_manual_engineering_audit(mixed, "pdf")
    mixed_space = {item.get("original_text") for item in mixed_issues if item.get("rule") == "DOC-SPACE-006"}
    assert "95 ℃" not in mixed_space
    assert "4 ℃" in mixed_space

    chinese = "试剂应在 95 ℃ 水浴中加热 5 分钟，随后置于 25 ℃。"
    chinese_issues = review_api._run_manual_engineering_audit(chinese, "pdf")
    chinese_space = [item for item in chinese_issues if item.get("rule") == "DOC-SPACE-006"]
    assert chinese_space == []

    english = "Incubate at 95 ℃ for 5 min, then keep at 25 ℃ and 4 ℃."
    english_issues = review_api._run_manual_engineering_audit(english, "pdf")
    english_space = {item.get("original_text") for item in english_issues if item.get("rule") == "DOC-SPACE-006"}
    assert {"95 ℃", "25 ℃", "4 ℃"} <= english_space


def test_t17_visual_selection_fills_high_layout_score_pages():
    candidates = []
    for page in range(1, 21):
        candidates.append({
            "page_number": page,
            "reasons": ["table_layout"],
            "table_blocks": 1,
            "layout_signals": {
                "crowding_score": 0.95 if page == 17 else 0.05,
                "thick_line_ratio": 0.8 if page == 17 else 0.0,
                "image_offset_ratio": 0.0,
            },
        })
    picked = review_api._select_visual_page_candidates(candidates, 6, 20)
    pages = {int(item["page_number"]) for item in picked}
    assert 17 in pages
    assert len(picked) == 6


def test_t18_layout_visual_limit_defaults_to_6():
    assert review_api._review_pdf_visual_verify_limit() == 6
    assert review_api._review_pdf_visual_verify_layout_limit() == 6


def test_t19_visual_selection_keeps_same_bucket_table_pages():
    gold = {69, 70, 76, 79, 90, 158, 213}
    candidates = []
    for page in range(1, 245):
        if page in gold:
            reasons = ["dense_table_or_layout", "table_layout"] if page in {69, 70, 158, 213} else ["table_layout"]
            table_blocks = {69: 8, 70: 7, 158: 5, 213: 5, 90: 3, 76: 2, 79: 2}[page]
        else:
            reasons = ["crowded_lines"]
            table_blocks = 0
        candidates.append({
            "page_number": page,
            "reasons": reasons,
            "table_blocks": table_blocks,
            "layout_signals": {
                "crowding_score": 0.9 if page not in gold else 0.0,
                "thick_line_ratio": 0.0,
                "image_offset_ratio": 0.0,
                "drawing_line_count": 80 if page in gold else 4,
            },
        })
    picked = review_api._select_visual_page_candidates(candidates, 48, 244)
    pages = {int(item["page_number"]) for item in picked}
    assert gold <= pages
    assert len(picked) == 48


def test_t20_caption_block_marks_figure_numbering():
    result = review_api._collect_pdf_suspicious_pages({
        "enabled": True,
        "page_count": 1,
        "pages": [{
            "page_number": 159,
            "text_preview": "Device maintenance Sequencer maintenance",
            "footer_preview": [],
            "block_counts": {"caption": 1, "body": 13},
            "table_like_line_count": 0,
            "line_count": 30,
            "char_start": 10,
            "char_end": 20,
            "layout_signals": {},
        }],
    })
    assert result["candidate_count"] == 1
    assert "figure_table_numbering" in result["candidates"][0]["reasons"]


def test_t21_page_backfill_enables_space_anchor():
    content = "\f".join(["page one text", "Store at 4 ℃ overnight and keep 35 ℃."])
    issues = review_api._run_manual_engineering_audit(content, "pdf")
    space_issues = [item for item in issues if item.get("rule") == "DOC-SPACE-006"]
    assert space_issues
    filled = review_api._backfill_issue_page_numbers(space_issues, content)
    assert filled >= 1
    annotation = _annotation(
        page="2",
        comment="多余空格了吗？全文关注",
        selected_text="℃",
        context="Store at 4 ℃ overnight.",
        category="单位/空格",
        expected_rule="DET-SPACE-001",
    )
    assert any(
        _matches_annotation_strictly(annotation, item, _issue_blob(item))
        for item in space_issues
    )


def test_t22_uncertain_layout_page_emits_manual_review(monkeypatch):
    document = SimpleNamespace(file_type="pdf", filename="demo.pdf")
    dummy_path = SimpleNamespace()
    dummy_path.exists = lambda: True
    suspicious_pages = {
        "enabled": True,
        "candidate_count": 1,
        "page_count": 220,
        "candidates": [{
            "page_number": 213,
            "reasons": ["table_layout", "dense_table_or_layout", "image_off_center"],
            "char_start": 20,
            "char_end": 80,
            "text_preview": "software screenshot not centered",
            "table_blocks": 1,
        }],
    }
    monkeypatch.setattr(review_api, "_review_pdf_visual_verify_enabled", lambda: True)
    monkeypatch.setattr(review_api, "_review_pdf_visual_verify_limit", lambda: 24)
    monkeypatch.setattr(review_api, "_visual_provider_available", lambda name: True)
    monkeypatch.setattr("app.review_engine.visual.visual_provider_chain", lambda: ["deepseek"])
    monkeypatch.setattr(review_api, "_get_document_upload_path", lambda document: dummy_path)
    monkeypatch.setattr(review_api, "_render_pdf_page_png_bytes", lambda *args, **kwargs: b"png")
    monkeypatch.setattr(
        review_api,
        "_verify_review_issue_visually",
        lambda *args, **kwargs: {
            "decision": "uncertain",
            "reason": "cannot exclude off-center image",
            "confidence": 40,
            "visual_status": "skipped",
        },
    )
    monkeypatch.setattr(review_api, "set_progress", lambda *args, **kwargs: None)

    filtered, diagnostics = review_api._apply_pdf_visual_verification(
        123, document, "dummy", [], suspicious_pages
    )

    assert diagnostics["uncertain_count"] == 1
    visual_issues = [item for item in filtered if item.get("rule") == "PDF-VISUAL-001"]
    assert visual_issues
    assert visual_issues[0]["category"] == "表格/版式"
    assert int(visual_issues[0].get("confidence") or 0) < 85


def test_t23_pipeline_keeps_space_issues_on_different_pages():
    from app.review_engine.pipeline import select_review_issues

    issues = []
    for page, start in ((82, 100), (88, 500)):
        issues.append({
            "source": "rule",
            "rule": "DOC-SPACE-006",
            "category": "空格与排版",
            "severity": "general",
            "original_text": "4 ℃",
            "suggestion": "4℃",
            "description": "英文文档使用 ℃ 时，数值与单位之间的空格属于多余空格",
            "confidence": 92,
            "chapter": "Storage",
            "position": json.dumps({"start": start, "end": start + 4, "page_number": page}),
        })
    selected = select_review_issues(issues)
    pages = set()
    for item in selected:
        mapping = item if isinstance(item, dict) else item
        position = mapping.get("position") if isinstance(mapping, dict) else None
        if position is None:
            position = getattr(mapping, "position", "")
        payload = json.loads(position) if isinstance(position, str) else (position or {})
        pages.add(int(payload.get("page_number") or 0))
    assert pages == {82, 88}
    deduped = review_api.dedupe_issues_by_original(issues)
    deduped_pages = set()
    for item in deduped:
        payload = json.loads(item["position"])
        deduped_pages.add(int(payload.get("page_number") or 0))
    assert deduped_pages == {82, 88}


def test_split_content_pages_mixed_separators():
    text = "page1\n\f\npage2\fpage3\n\f\npage4"
    pages = review_api._split_content_pages(text)
    assert pages == ["page1", "page2", "page3", "page4"]
    offsets = review_api._page_offsets_from_pages(text)
    assert len(offsets) == 4
    assert offsets[0] == (0, text.index("page1") + len("page1"))
    assert offsets[-1][1] == len(text)


def test_page_issue_whitelist_survives_select():
    from app.review_engine.pipeline import is_noise, select_review_issues

    categories = ["表格/版式", "目录一致性", "页脚异常", "图表编号", "页面复核"]
    for category in categories:
        for confidence in (72, 88, 92):
            issue = {
                "rule": "PDF-VISUAL-001",
                "category": category,
                "severity": "general",
                "confidence": confidence,
                "source": "rule",
                "original_text": f"page preview {category}",
                "suggestion": "请人工复核该页版式、页脚、图表编号或目录一致性",
                "description": "PDF 页级渲染复核确认疑点，原因: layout",
                "audit_basis": "PDF 页级渲染复核",
                "context": "page preview",
            }
            assert is_noise(issue) is False
            assert select_review_issues([issue])

    blocked = [
        {"rule": "STRUCT-LAYOUT-001", "category": "表格/版式", "confidence": 90},
        {"rule": "DET-TYPO-001", "category": "字体/版式细节", "confidence": 90},
        {"rule": "EXT-R015", "category": "表格/版式", "confidence": 90},
        {"rule": "EXT-R017", "category": "表格/版式", "confidence": 90},
        {"rule": "EXT-R018", "category": "表格/版式", "confidence": 90},
        {"rule": "CYY-CN-LAYOUT-001", "category": "表格/版式", "confidence": 70},
    ]
    for item in blocked:
        issue = {
            "severity": "general",
            "source": "rule",
            "original_text": "layout noise",
            "suggestion": "fix layout",
            "description": "visual layout noise",
            **item,
        }
        assert is_noise(issue) is True
        assert select_review_issues([issue]) == []


def test_page_issue_meta_flags():
    candidate = {
        "page_number": 2,
        "char_start": 10,
        "char_end": 40,
        "text_preview": "Revision History table",
        "reasons": ["table_layout"],
    }
    issue = review_api._build_pdf_page_visual_issue(
        candidate,
        {"decision": "confirm", "reason": "layout issue", "confidence": 88, "source": "ai"},
    )
    assert issue["needs_human_review"] is True
    assert issue["page_number"] == 2
    meta = review_api._decode_issue_position(issue["position"])
    assert meta.get("needs_human_review") is True
    assert int(meta.get("page_number") or 0) == 2

    manual = review_api._build_pdf_page_manual_review_issue(candidate, "visual_model_unavailable")
    assert manual["needs_human_review"] is True
    assert manual["page_number"] == 2
    manual_meta = review_api._decode_issue_position(manual["position"])
    assert manual_meta.get("needs_human_review") is True
    assert int(manual_meta.get("page_number") or 0) == 2


def test_report_issue_dict_projects_page_meta():
    with_meta = {
        "rule": "PDF-VISUAL-001",
        "position": json.dumps({"start": 10, "end": 40, "page_number": 2, "needs_human_review": True}),
    }
    payload = review_api._report_issue_to_dict(with_meta)
    assert payload["page_number"] == 2
    assert payload["needs_human_review"] is True

    no_meta = {"rule": "DOC-SPACE-006", "position": json.dumps({"start": 10, "end": 20})}
    payload = review_api._report_issue_to_dict(no_meta)
    assert payload["page_number"] is None
    assert payload["needs_human_review"] is False

    old = {"rule": "DOC-SPACE-006", "position": "100-120"}
    payload = review_api._report_issue_to_dict(old)
    assert payload["page_number"] is None
    assert payload["needs_human_review"] is False

    top_only = {
        "rule": "PDF-VISUAL-001",
        "needs_human_review": True,
        "position": json.dumps({"start": 10, "end": 40}),
    }
    payload = review_api._report_issue_to_dict(top_only)
    assert payload["needs_human_review"] is True


def test_visual_issue_location_and_chapter_use_meta_page():
    content = "Chapter 1 Overview\nAAA\n\f\nChapter 2 Overview\nBBB"
    issue = review_api._build_pdf_page_visual_issue(
        {
            "page_number": 2,
            "char_start": 0,
            "char_end": 3,
            "text_preview": "Chapter 2 Overview BBB",
            "reasons": ["table_layout"],
        },
        {"decision": "confirm", "reason": "layout", "confidence": 88},
    )
    assert review_api._report_resolve_chapter(issue, content) == "第2页"
    location = review_api._format_issue_location(issue, content)
    assert "第2页" in location


def test_html_report_renders_needs_human_review_badge():
    content = "Revision History table\nAAA\n\f\nChapter 2 Overview\nBBB"
    review = SimpleNamespace(id=7, document_id=1, created_at=None, completed_at=None)
    doc = SimpleNamespace(filename="demo.pdf", file_type="pdf", content=content)
    flagged = review_api._build_pdf_page_visual_issue(
        {
            "page_number": 1,
            "char_start": 0,
            "char_end": 22,
            "text_preview": "Revision History table",
            "reasons": ["table_layout"],
        },
        {"decision": "confirm", "reason": "layout issue", "confidence": 90, "source": "ai"},
    )
    ordinary = {
        "severity": "general",
        "category": "术语一致性",
        "rule": "TERM-001",
        "chapter": "1.1",
        "original_text": "Chapter 2 Overview",
        "context": "Chapter 2 Overview BBB",
        "suggestion": "keep wording",
        "description": "ordinary term issue",
        "audit_basis": "术语规范",
        "confidence": 92,
        "source": "rule",
        "status": "pending",
        "position": json.dumps({"start": content.find("Chapter 2 Overview"), "end": content.find("Chapter 2 Overview") + 18}),
    }
    html = review_api._generate_review_html_content(review, doc, [flagged, ordinary])
    assert "badge-manual" in html
    assert "需人工复核" in html
    assert html.count("需人工复核") == 1
