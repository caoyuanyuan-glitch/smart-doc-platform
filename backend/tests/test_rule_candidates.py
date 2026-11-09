import re

from scripts.import_rule_candidates import CANDIDATE_XLSX, load_candidates


def test_rule_candidates_compile_and_skip_suppress():
    assert CANDIDATE_XLSX.is_file()
    candidates, skipped = load_candidates(CANDIDATE_XLSX)
    assert len(candidates) == 20
    nos = {item.rule_no for item in candidates}
    assert not any(no.startswith("HR-FP-SUPPRESS") for no in nos)
    for item in candidates:
        re.compile(item.regex)
        assert item.regex not in {"(?!)", "(?!x?x?)"}
    assert "HR-STRUCT-DITA-001" in nos
    assert "HR-DOC-PAGE-001" in nos


def test_import_skips_false_positive_lex_rules():
    candidates, skipped = load_candidates(CANDIDATE_XLSX)
    skipped_text = "\n".join(skipped)
    assert len(skipped) == 9
    for token in ["\\bName\\b", "\\bReport\\b", "\\bplace\\b", "\\byour\\b", "Pool"]:
        assert token in skipped_text
    word_hits = [line for line in skipped if "纯英文单词命中停用词" in line]
    comment_hits = [line for line in skipped if "建议栏是审核评论而非替换写法" in line]
    assert len(word_hits) == 5
    assert len(comment_hits) == 4
    for no in ["HR-A5-LEX-017", "HR-A5-LEX-018", "HR-A5-LEX-030", "HR-A5-LEX-033"]:
        assert any(line.startswith(no + ":") for line in comment_hits)
    assert any("HR-A5-LEX-022" in line for line in word_hits)
    nos = {item.rule_no for item in candidates}
    assert "HR-STRUCT-DITA-001" in nos
    assert "HR-DOC-PAGE-001" in nos
