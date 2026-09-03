from app.review_engine.language_segments import classify_text_language, segment_text_by_language


def test_segment_chinese_paragraph_stays_zh():
    segments = segment_text_by_language("使用 DNBSEQ 测序仪完成测序。")
    assert segments
    assert all(item["language"] == "zh-CN" for item in segments)


def test_segment_english_paragraph_stays_en():
    segments = segment_text_by_language("Please record the sample ID.")
    assert segments
    assert all(item["language"] == "en-US" for item in segments)


def test_mixed_sentence_splits_chinese_phrase():
    text = "Please record the sample ID after 文库定量."
    segments = segment_text_by_language(text)
    languages = {item["language"] for item in segments}
    assert "zh-CN" in languages
    assert "en-US" in languages
    chinese = next(item for item in segments if "文库定量" in item["text"])
    assert chinese["language"] == "zh-CN"
    assert text[chinese["start"]:chinese["end"]] == chinese["text"]


def test_classify_masks_product_names():
    assert classify_text_language("使用 DNBSEQ-G99RS 完成测序") == "zh-CN"
