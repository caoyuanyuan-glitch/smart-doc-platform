"""人工审核意见 → 抽象问题模式清单（安全激活）

设计原则（重要）：
  - 只输出"问题模式/检测要点"这类抽象描述，**不输出任何具体文档的意见原文**
    （如"步骤3之后跳到步骤5"）。原因：把旧文档的具体错误塞进新文档审核 prompt，
    模型会照搬臆造 —— 这正是 commit 42733b2 `fix(review): reduce false positives`
    和测试 test_load_cyy_human_review_basis_sections_omits_comment_details 守护的行为。
  - 本模块产出的 section 使用独立 label/tags，与既有"CYY人工审核经验基线"section 分离，
    不破坏现有测试与行为。
  - 通过 REVIEW_HUMAN_PATTERN_BASIS=0 可整体关闭。

数据来源：.monkeycode/docs/cyy-human-review-baseline.json（603 条人工批注的结构化摘要）。
未来扩展到 3323 条时，只需替换数据文件，本模块无需改动。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# __file__ = <repo>/backend/app/review_engine/human_review_patterns.py
# parents[0]=review_engine, [1]=app, [2]=backend, [3]=<repo>
REPO_ROOT = Path(__file__).resolve().parents[3]
BASELINE_PATH = REPO_ROOT / ".monkeycode" / "docs" / "cyy-human-review-baseline.json"

# 每个类别对应的"抽象检测要点"。刻意不含任何具体文档的错误文本。
# 描述的是"这类问题长什么样、该在什么条件下报"，供模型理解审核偏好。
CATEGORY_PATTERNS: dict[str, str] = {
    "单位/空格": "数字与单位、倍率符号之间是否保留半角空格（如数字+℃/mL/μL/min 连写）；同类表述全文是否空格一致。",
    "表达与句式": "句子是否通顺、是否有成分残缺或叠用（如“按照……按要求”）；是否存在口语化、歧义或与上下文不一致的表达。",
    "人工审核其他项": "通读上下文，判断是否存在影响理解或交付的异常；仅在有明确文本证据时报告，不凭样例臆造。",
    "步骤结构": "步骤编号是否连续、是否有跳号或合并；操作引导句与步骤层级是否一致；步骤是否可执行。",
    "重复内容": "同一句或同一信息是否跨页/跨段重复出现；语义是否重复（如“超过……以上”）。",
    "术语一致性": "同一概念全文用词与大小写是否统一（含 Barcode/DualBarcode 等）；术语首次出现是否有解释。",
    "表格/版式": "表格表头是否跨页重复、列宽是否足够、边框/竖线是否多余或缺失、单元格内容是否出界。",
    "官网地址": "封底官网地址、邮箱、电话是否与手册语言对应（中文/英文手册各自的正确地址）。",
    "人工确认项": "涉及版本、参数、账号、法规归属等需人工确认的表述，标记为待确认而非直接定性为错误。",
    "图片/对象缺失": "图片是否丢失或未正确链接；图题与图编号是否连续、与正文引用是否对应。",
    "中文残留": "英文手册中是否混入未翻译的中文；中文手册中是否有异常的外文残留。",
    "版本记录": "版本记录表的日期是否填写、版本是否与正文/文件名一致、修订描述是否完整。",
    "字体/版式细节": "字号、上下角标、公式、字形是否与全文体例一致。",
    "标点符号": "中英文标点是否混用（半角/全角）、句号/逗号/冒号/括号是否缺失或多余、括号是否配对。",
    "分页与标题边界": "标题是否与正文分页割裂、表头是否跨页重复、内容是否被不当地拆到下一页。",
    "主题结构": "页眉主题、附录等结构性标题是否与文档层级一致。",
    "商标声明": "商标声明页的标注形式是否合规；正文商标名不要求重复加 ®（声明页已标注即合规）。",
    "货号写法": "货号是否符合“940-XXXXXX-XX”三段式等既定格式；全文格式是否统一。",
    "法规/注册确认": "涉及标准清单、认证范围、法规适用的表述是否需要人工确认，不自行定性。",
    "表图编号": "表号、图号是否连续无缺号无重号，正文交叉引用是否命中目标。",
    "结构完整性": "结构组成章节是否覆盖主要部件；是否存在只提子件不提主体的情况。",
    "操作步骤语气": "操作步骤是否使用一致的祈使句语气。",
    "标题大小写": "标题大小写全文是否一致。",
    "物料编码": "物料编码格式是否符合规范。",
    "符号规范": "乘号、范围符号等是否使用规范字符。",
    "范围/数值格式": "数值范围写法是否统一、符号是否规范。",
    "适用范围/硬件配置": "适用范围与硬件配置项是否与实物一致、是否遗漏关键配置。",
    "公司主体表述": "公司主体名称、母子公司表述是否全文一致。",
    "索引一致性": "索引词条页码是否与正文实际页码对应（注意印刷页与物理页偏移）。",
    "页码异常": "全局页码是否连续、是否有重复或错误页码。",
    "地址字段确认": "公司地址等字段是否与已确认的标准表述一致。",
}

# 无具体错误文本的兜底提示
FALLBACK_PATTERN = "检查该类问题是否有明确的文本或版面证据；仅在证据充分时报告。"


def _enabled() -> bool:
    return os.getenv("REVIEW_HUMAN_PATTERN_BASIS", "1").strip().lower() not in {
        "0", "false", "no", "off"
    }


def load_pattern_sections() -> list[dict]:
    """产出抽象问题模式 section；关闭时返回空列表。"""
    if not _enabled():
        return []
    if not BASELINE_PATH.exists():
        return []
    try:
        payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    by_category = (payload.get("summary") or {}).get("by_category") or {}
    if not by_category:
        return []

    lines = [
        "【人工审核意见 · 抽象问题模式清单】",
        "以下为历史人工审核高频关注的问题模式，仅用于理解审核偏好。",
        "注意：这些是抽象模式，不含任何具体文档的错误内容；只在新文档有明确证据时报告对应问题，不得照搬历史样例。",
    ]
    for category, count in sorted(by_category.items(), key=lambda kv: (-int(kv[1] or 0), kv[0])):
        pattern = CATEGORY_PATTERNS.get(category, FALLBACK_PATTERN)
        lines.append(f"- {category}（历史出现 {count} 次）：{pattern}")

    return [{
        "label": "人工审核意见-抽象问题模式清单",
        "text": "\n".join(lines),
        "priority": 4,
        "language": "both",
        "basis_type": "human_pattern",
        "tags": ["human-review", "pattern", "abstract"],
    }]
