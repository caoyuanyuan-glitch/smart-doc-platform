from app.review_engine.pdf_layout_signals import collect_pdf_layout_signals, layout_candidate_score


def test_collect_pdf_layout_signals_counts_thick_drawings(tmp_path):
    import fitz

    path = tmp_path / "thick.pdf"
    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    page.draw_rect(fitz.Rect(40, 40, 360, 360), width=4)
    page.draw_line(fitz.Point(40, 200), fitz.Point(360, 200), width=4)
    doc.save(path)
    doc.close()

    signals = collect_pdf_layout_signals(path)
    assert 1 in signals
    assert signals[1]["drawing_line_count"] >= 1
    assert signals[1]["thick_line_ratio"] > 0


def test_layout_candidate_score_ranks_crowding_first():
    low = {
        "page_number": 10,
        "reasons": ["table_layout"],
        "table_blocks": 1,
        "layout_signals": {"crowding_score": 0.1, "thick_line_ratio": 0.9, "image_offset_ratio": 0.0},
    }
    high = {
        "page_number": 90,
        "reasons": ["table_layout"],
        "table_blocks": 1,
        "layout_signals": {"crowding_score": 0.9, "thick_line_ratio": 0.1, "image_offset_ratio": 0.0},
    }
    assert layout_candidate_score(high) > layout_candidate_score(low)


def test_layout_candidate_score_ranks_dense_table_above_crowding():
    crowded = {
        "page_number": 13,
        "reasons": ["crowded_lines"],
        "table_blocks": 0,
        "layout_signals": {"crowding_score": 0.95, "thick_line_ratio": 0.0, "image_offset_ratio": 0.0},
    }
    dense = {
        "page_number": 69,
        "reasons": ["dense_table_or_layout", "table_layout"],
        "table_blocks": 8,
        "layout_signals": {"crowding_score": 0.0, "thick_line_ratio": 0.03, "image_offset_ratio": 0.0},
    }
    assert layout_candidate_score(dense) > layout_candidate_score(crowded)
