"""错别字字典。"""

# 内嵌默认错别字词典，优先覆盖实验/仪器/文档润色高频误写。
INSTRUMENT_TYPO_DICT = {
    "按装": "安装",
    "安裝": "安装",
    "按排": "安排",
    "交户": "交互",
    "移液其": "移液器",
    "移液抢": "移液器",
    "离心管驾": "离心管架",
    "震荡器": "振荡器",
    "制备卡下册": "制备卡下侧",
}


def get_default_typo_dict() -> dict:
    return {key: value for key, value in INSTRUMENT_TYPO_DICT.items() if key and value and key != value}
