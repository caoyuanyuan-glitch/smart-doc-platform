"""F7：页级 issue 上限由 LAYOUT_LIMIT 与 PAGE_BUDGET 共同支配。"""

from types import SimpleNamespace

import pytest

from app.api import review as review_api


@pytest.mark.parametrize(
    "limit, layout, budget, expected",
    [
        (24, 48, 0, 48),
        (6, 48, 0, 48),
        (6, 12, 0, 12),
        (6, 6, 0, 6),
        (6, 6, 6, 6),
        (24, 48, 8, 8),
    ],
)
def test_visual_page_limit_is_dominated_by_layout_and_budget(
    monkeypatch, limit, layout, budget, expected
):
    document = SimpleNamespace(file_type="pdf", filename="demo.pdf")
    pages = []
    for index in range(1, 61):
        pages.append({
            "page_number": index,
            "reasons": ["table_layout", "dense_table_or_layout"],
            "char_start": index * 10,
            "char_end": index * 10 + 5,
            "text_preview": "Revision History Version Date column width table header",
            "table_blocks": 4,
        })
    suspicious_pages = {
        "enabled": True,
        "candidate_count": 60,
        "page_count": 60,
        "candidates": pages,
    }
    monkeypatch.setattr(review_api, "_review_pdf_visual_verify_enabled", lambda: True)
    monkeypatch.setattr(review_api, "_review_pdf_visual_verify_limit", lambda: limit)
    monkeypatch.setattr(review_api, "_review_pdf_visual_verify_layout_limit", lambda: layout)
    monkeypatch.setattr(review_api, "_review_pdf_visual_verify_page_budget", lambda: budget)
    monkeypatch.setattr(review_api, "_visual_provider_available", lambda name: False)
    monkeypatch.setattr(review_api, "_should_promote_page_candidate_without_visual", lambda cand: True)
    monkeypatch.setattr(review_api, "set_progress", lambda *args, **kwargs: None)

    filtered, diagnostics = review_api._apply_pdf_visual_verification(
        123, document, "dummy", [], suspicious_pages
    )
    visual = [item for item in filtered if item.get("rule") == "PDF-VISUAL-001"]
    assert diagnostics["page_candidate_count"] == expected
    assert diagnostics["page_issue_count"] == expected
    assert len(visual) == expected
