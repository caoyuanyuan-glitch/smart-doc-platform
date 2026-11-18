from scripts.run_rule_family_regression import _doc_no


def test_doc_no_join_uses_normalized_sample_no():
    """样本 doc 带 -NN 版本后缀时，join 必须按归一化后的文档号比对。"""
    assert _doc_no("H-020-001235-00") == "H-020-001235"
    assert _doc_no("H-020-001235-00") == _doc_no("xxx H-020-001235 yyy.pdf")
    assert _doc_no("H020-000008") == "H-020-000008"
    assert _doc_no("H020-000008") == _doc_no("H-020-000008-00 DNBSEQ.pdf")
