"""错别字字典。"""

INSTRUMENT_TYPO_DICT = {
    "移液其": "移液器",
    "按装": "安装",
    "移液抢": "移液器",
    "离心管驾": "离心管架",
    "震荡器": "振荡器",
    "制备卡下册": "制备卡下侧",
}


def get_default_typo_dict() -> dict:
    return {key: value for key, value in INSTRUMENT_TYPO_DICT.items() if key and value and key != value}
