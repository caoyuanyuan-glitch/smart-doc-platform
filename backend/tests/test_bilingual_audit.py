"""四层双语审核管道的回归测试。锁定受控文件实测发现的全部误报。"""

from app.review_engine.bilingual_audit import (
    _segment_signature,
    align_blocks,
    apply_gates,
    deterministic_compare,
    run_bilingual_audit,
    segment_text,
)

CN = """图 1 安全信息
请勿将设备暴露在潮湿环境中。
操作前请佩戴防护装备。
图 2 试剂与耗材
1 玻璃染色缸 用于样本预处理。
加入 200 μL 样本，室温孵育 15 分钟。
"""

EN = """Figure 1 Safety information
Keep the device away from moisture.
Wear protective equipment before operation.
Do not swallow any reagent. Seek immediate medical care if swallowing occurs.
Figure 2 Reagents and consumables
1 KimWipes Kimtech, Cat. No.: 34155 for cleaning.
Add 20 μL of sample and incubate at room temperature for 15 min.
"""


def test_segment_text_separates_structure_labels():
    blocks = segment_text(CN)
    assert [b["key"] for b in blocks] == ["fig:1", "fig:2"]
    # 列表号「1 玻璃染色缸」的编号必须剥离，正文保留
    assert any("玻璃染色缸" in s["text"] and s["text"].startswith("玻璃染色缸") for s in blocks[1]["segments"])


def test_segment_signature_normalizes_units_and_ignores_hyphen_words():
    sig = _segment_signature("孵育 15 分钟，self-check 后加入 200 μL")
    assert "15min" in sig
    assert "200μl" in sig
    assert "self-check" not in sig and "SELF-CHECK" not in sig


def test_align_blocks_pairs_by_position_not_signature():
    aligned = align_blocks(segment_text(CN), segment_text(EN))
    assert len(aligned) == 2
    # fig:1 英文多一句（吞咽警告），不应强行配对
    assert len(aligned[0]["unmatched_en"]) >= 1


def test_deterministic_compare_catches_value_and_catalog():
    aligned = align_blocks(segment_text(CN), segment_text(EN))
    rows = deterministic_compare(aligned, CN, EN)
    kinds = {r["kind"] for r in rows}
    assert "bilingual_value" in kinds  # 200 μL / 20 μL
    assert any("200μl" in r["conclusion"] for r in rows)


def test_deterministic_compare_catches_missing_negation_warning():
    aligned = align_blocks(segment_text(CN), segment_text(EN))
    rows = deterministic_compare(aligned, CN, EN)
    safety = [r for r in rows if r["kind"] == "bilingual_safety"]
    assert len(safety) == 1
    assert safety[0]["level"] == "P0"
    assert "swallow" in safety[0]["evidence"] or "Do not" in safety[0]["evidence"]


def test_apply_gates_dedups_and_drops_version_specific():
    from app.review_engine.bilingual_audit import _make_row
    rows = [
        _make_row(kind="pair", level="P1", name="X", conclusion="英文线缆长度 for overseas use，中文无",
                  zh_evidence="-", en_evidence="3 m", zh_line=0, en_line=0, anchor="全文"),
        _make_row(kind="value", level="P1", name="Y", conclusion="数值不一致",
                  zh_evidence="200μl", en_evidence="20μl", zh_line=1, en_line=1, anchor="fig:2"),
        _make_row(kind="value", level="P1", name="Y", conclusion="数值不一致",
                  zh_evidence="200μl", en_evidence="20μl", zh_line=1, en_line=1, anchor="fig:2"),
    ]
    kept = apply_gates(rows, CN, EN)
    assert len(kept) == 1
    assert kept[0]["parameter_name"] == "Y"


def test_semantic_layer_is_optional_no_llm_no_token():
    result = run_bilingual_audit({"filename": "cn.md", "text": CN}, [{"filename": "en.md", "text": EN}])
    assert result["layer_stats"]["aligned_blocks"] == 2
    assert result["layer_stats"]["semantic"] == 0
    assert result["layer_stats"]["final"] >= 1


def test_semantic_llm_is_used_when_injected():
    calls = []

    def fake_llm(messages):
        calls.append(messages)
        return '{"verdict":"有问题","issues":[{"type":"translation_error","severity":"中","zh_evidence":"样本管","en_evidence":"needle","reason":"对象错"}]}'

    # 证据不在句对里 -> 必须被证据校验丢弃
    result = run_bilingual_audit(
        {"filename": "cn.md", "text": CN}, [{"filename": "en.md", "text": EN}],
        llm=fake_llm, max_pairs=2,
    )
    assert calls  # LLM 被调用
    assert result["layer_stats"]["semantic"] == 0  # 编造证据被丢弃


def test_same_language_pair_does_not_run():
    result = run_bilingual_audit({"filename": "a", "text": CN}, [{"filename": "b", "text": CN}])
    assert result["layer_stats"]["final"] == 1
    assert "未识别到中英配对" in result["rows"][0]["conclusion"]


def test_unit_conversion_equivalence():
    from app.review_engine.bilingual_audit import _segment_signature
    assert _segment_signature("静置 60 分钟") == _segment_signature("keep for 1 h")
    assert _segment_signature("500 μL 缓冲液") == _segment_signature("0.5 mL buffer")
