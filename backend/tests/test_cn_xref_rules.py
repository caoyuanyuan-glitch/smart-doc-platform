from app.review_engine.cn_xref_rules import (
    CN_XREF_ENGINE_ID,
    iter_cn_local_xref_hits,
    parse_reference_number,
)
from app.review_engine.reference_index import check_references


def test_parse_reference_number_normalizes_compound_forms():
    assert parse_reference_number("3") == (3,)
    assert parse_reference_number("3-1") == (3, 1)
    assert parse_reference_number("3.1") == (3, 1)
    assert parse_reference_number("3．1") == (3, 1)
    assert parse_reference_number("3–1") == (3, 1)
    assert parse_reference_number("3—1") == (3, 1)


def _rules(text):
    return [item[3] for item in iter_cn_local_xref_hits(text, text)]


def test_as_shown_matches_plain_and_compound_captions():
    assert _rules("如图3所示\n图3 标题") == []
    assert _rules("如图3-1所示\n图3-1 标题") == []
    assert _rules("如图 3-1 所示\n图3—1 标题") == []
    assert _rules("如表3.1所示\n表3．1 标题") == []
    assert _rules("如Figure 3所示\nFigure 3 Title") == []


def test_as_shown_reports_nearby_mismatch_only():
    hits = list(iter_cn_local_xref_hits("如图3所示\n图4 标题", "如图3所示\n图4 标题"))
    assert len(hits) == 1
    assert hits[0][3] == "CYY-CN-REF-006"
    assert _rules("如图3所示\n无图标题") == []


def test_reference_index_compound_ids_share_parser():
    text = "如图3-1所示，完成装载。\n图 3—1 装载界面\n"
    assert check_references(text) == []
    missing = check_references("如图3-1所示，完成装载。\n")
    assert missing
    assert missing[0]["reference_id"] == "3-1"
    assert missing[0]["status"] != "confirmed"


def test_unparsed_and_visual_only_stay_blocked():
    visual = check_references("See Figure 2.", visual_targets={"figure": ["2"]}, parsed=True)
    assert visual[0]["status"] == "blocked"
    assert visual[0]["target_status"] == "target_visual_only"
    unparsed = check_references("See Figure 2.", parsed=False)
    assert unparsed[0]["status"] == "blocked"
    assert unparsed[0]["target_status"] == "target_not_parsed"


def test_engine_id_is_stable():
    assert CN_XREF_ENGINE_ID == "cn_xref_v2"
