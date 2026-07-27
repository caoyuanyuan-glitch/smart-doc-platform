"""
仪器文档智能润色规则引擎

纯规则引擎，不依赖 LLM。用于：
1. AI 润色前的确定性预处理（术语替换、专有名词保护、标点规范化）
2. AI 润色后的回退保护（检查专有名词是否丢失）
3. 作为 V2 Skill 的 conservative 回退策略

来源：仪器文档智能润色系统最终版
"""
import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


class PolishConfig:
    L2_THRESHOLD = 0.85
    L3_THRESHOLD = 0.90
    TYPE_MATCH_MIN = 0.40
    MIN_CLAUSE_LEN = 4


@dataclass
class MatchResult:
    original: str
    replacement: str
    level: str
    confidence: float
    reason: str = ""


class InstrumentPolishEngine:
    """仪器文档规则引擎主入口。

    对外暴露两个核心方法：
    - pre_polish(text): AI 前预处理，返回处理后的文本
    - post_protect(original, polished): AI 后保护检查，返回是否需要回退
    """

    # 内置术语替换表（AI 润色前先行替换，不受 LLM 幻觉影响）
    TERM_DICT = {
        "样品": "样本",
        "机器": "仪器",
        "推板": "载台",
        "枪头": "吸头",
        "移液枪": "移液器",
        "机械手": "机械臂",
        "八连管": "八联管",
        "试验台": "实验台",
        "枪盒": "吸头盒",
    }

    # 专用名词保护模式（按长度降序匹配，避免短模式先吞掉长名词的一部分）
    PROPER_NOUN_PATTERNS = [
        r'[A-Z][A-Za-z]*[-]\d+[A-Za-z\d]*',        # DNBelab-D4RS, Agilent-7890
        r'[A-Z]{2,}[-/][A-Z\d]+',                    # FID-TCD, GB/T (先匹配带连字符的)
        r'[A-Z][A-Za-z]*\d+[A-Za-z\d]*',             # D4RS, T20 (避免裸数字开头的)
        r'\d+\.?\d*\s*(?:℃|°C|K|nm|μm|mm|cm|m|mg|g|kg|mL|L|Hz|kHz|MHz|GHz|V|A|Ω|Pa|bar)',  # 数值+单位
    ]

    # 排除的短通用缩写（不保护，让它们正常参与空格和术语处理）
    _EXCLUDE_ACRONYMS = {"PCR", "DNA", "RNA", "CPU", "GPU", "API", "URL", "HTTP", "HTTPS", "FTP", "SSH",
                         "SQL", "JSON", "XML", "HTML", "CSS", "PDF", "CSV", "USB", "LAN", "WAN", "MAC"}

    @staticmethod
    def extract_proper_nouns(text: str) -> List[str]:
        nouns = []
        for pattern in InstrumentPolishEngine.PROPER_NOUN_PATTERNS:
            nouns.extend(re.findall(pattern, text))
        return list(set(nouns))

    @staticmethod
    def check_nouns_lost(original: str, polished: str) -> Tuple[bool, List[str]]:
        """检查润色结果是否丢失了原文的专有名词"""
        original_nouns = set(InstrumentPolishEngine.extract_proper_nouns(original))
        polished_nouns = set(InstrumentPolishEngine.extract_proper_nouns(polished))
        lost = original_nouns - polished_nouns
        return len(lost) > 0, list(lost)

    @staticmethod
    def pre_polish(text: str, extra_terms: Optional[Dict[str, str]] = None) -> str:
        """
        AI 润色前的确定性预处理：
        1. 专有名词占位保护
        2. 术语替换
        3. 标点规范化
        4. 恢复专有名词
        """
        if not text or not text.strip():
            return text

        terms = dict(InstrumentPolishEngine.TERM_DICT)
        if extra_terms:
            terms.update(extra_terms)

        # Step 1: 保护专有名词
        protected = []
        counter = [0]

        def _protect(m):
            word = m.group(0)
            # 跳过通用缩写
            if word in InstrumentPolishEngine._EXCLUDE_ACRONYMS:
                return word
            idx = counter[0]
            counter[0] += 1
            protected.append(word)
            return f"__PROPER_{idx}__"

        for pattern in InstrumentPolishEngine.PROPER_NOUN_PATTERNS:
            text = re.sub(pattern, _protect, text)

        # Step 2: 术语替换
        for old, new in terms.items():
            if old in text:
                text = text.replace(old, new)

        # Step 3: 标点规范化
        text = InstrumentPolishEngine._normalize_punctuation(text)

        # Step 4: 中英文间加空格
        text = re.sub(r'([\u4e00-\u9fa5])([A-Za-z])', r'\1 \2', text)
        text = re.sub(r'([A-Za-z])([\u4e00-\u9fa5])', r'\1 \2', text)

        # Step 5: 数字与单位间加空格（角度、百分比除外）
        text = re.sub(r'(\d)([a-zA-Z℃°]+)', r'\1 \2', text)
        text = re.sub(r'(\d)\s+(℃|°|%)', r'\1\2', text)

        # Step 6: 恢复专有名词
        for i, name in enumerate(protected):
            text = text.replace(f"__PROPER_{i}__", name)

        return text

    @staticmethod
    def _normalize_punctuation(text: str) -> str:
        """标点规范化"""
        # 连续重复标点去重（兼容中英文逗号）
        text = re.sub(r'，{2,}', '，', text)
        text = re.sub(r',{2,}', '，', text)          # ASCII 双逗号 → 单个中文逗号
        text = re.sub(r'。{2,}', '。', text)
        text = re.sub(r'、{2,}', '、', text)
        # 中英文间逗号统一为中文逗号
        text = re.sub(r'(?<=[\u4e00-\u9fa5A-Z\d])[，,](?=[\u4e00-\u9fa5A-Z\d])', '，', text)
        # 英文大写字母间用顿号
        text = re.sub(r'([A-Z])[，,](?=[A-Z])', r'\1、', text)
        # 数字间逗号改顿号
        text = re.sub(r'(\d)[，,](?=\d)', r'\1、', text)
        # 句尾逗号改句号（但保留已有句号）
        text = re.sub(r'，$', '。', text)
        # 逗号+句号清理
        text = re.sub(r'，。', '。', text)
        # 删除多余空格
        text = re.sub(r' {2,}', ' ', text)

        return text

    @staticmethod
    def post_protect(original: str, polished: str) -> Dict:
        """
        AI 润色后的回退保护。
        返回: { "safe": bool, "reason": str, "suggested": str }
        """
        if not polished or polished == original:
            return {"safe": True, "reason": "", "suggested": polished}

        lost, lost_nouns = InstrumentPolishEngine.check_nouns_lost(original, polished)
        if lost:
            return {
                "safe": False,
                "reason": f"AI 润色丢失专有名词: {', '.join(lost_nouns)}",
                "suggested": original  # 回退原文
            }

        return {"safe": True, "reason": "", "suggested": polished}

    @staticmethod
    def polish_term_only(text: str, extra_terms: Optional[Dict[str, str]] = None) -> str:
        """仅执行术语替换 + 标点规范化（不做句式改写），用于保守回退策略"""
        return InstrumentPolishEngine.pre_polish(text, extra_terms)


# 导出全局单例
instrument_polish_engine = InstrumentPolishEngine()
