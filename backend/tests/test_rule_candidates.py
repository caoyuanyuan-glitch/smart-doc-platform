import re
from pathlib import Path

from scripts.import_rule_candidates import CANDIDATE_XLSX, load_candidates


def test_rule_candidates_compile_and_skip_suppress():
    assert CANDIDATE_XLSX.is_file()
    candidates = load_candidates(CANDIDATE_XLSX)
    assert len(candidates) == 29
    nos = {item.rule_no for item in candidates}
    assert not any(no.startswith("HR-FP-SUPPRESS") for no in nos)
    for item in candidates:
        re.compile(item.regex)
        assert item.regex not in {"(?!)", "(?!x?x?)"}
