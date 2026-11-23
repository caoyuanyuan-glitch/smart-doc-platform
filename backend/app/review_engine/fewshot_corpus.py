"""few-shot 审校判例语料：加载 + 选择 + prompt 区块构建。

数据源：assets/rule_corpus_fewshot.jsonl —— 168 条真实人工审核批注
（64 个 label_code 族，每条含 comment / anchor / suggestion / label_name）。

用途：注入审核 AI 的 system prompt（build_audit_prompt_payload），
校准「什么样的问题值得报告」与人工批注的措辞颗粒度。

选择策略（build_fewshot_block，相关门控）：
仅当判例的上下文锚文本（>=6 字符）真实命中当前节选时注入；无命中不注入，
绝大多数 chunk 的 prompt 不受影响（T7 R01 回归实证：无差别兜底会回退 recall）。

失败语义：文件缺失/损坏一律返回空区块，不阻断审核主流程。
"""
import json
from functools import lru_cache
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_FEWSHOT_FILE = _ASSETS_DIR / "rule_corpus_fewshot.jsonl"

# anchor 短于该长度时不做命中匹配（PDF 残片噪声大）
_ANCHOR_MIN_LEN = 6
# 命中判例配额
_MATCH_LIMIT = 4
# comment 长度甜区：过短无信息量，过长挤占 token 预算
_COMMENT_MIN_LEN = 3
_COMMENT_MAX_LEN = 90
_BLOCK_CHAR_BUDGET = 2400

_CN_HEADER = (
    "审校判例（资深审核员在同类文档上的真实批注，仅用于校准问题报告的颗粒度"
    "与措辞风格：判例展示的是「什么样的问题值得报告、批注写多简短」；判例出自"
    "其他文档，严禁照抄进输出，也不得因问题形似判例而放宽证据要求）："
)
_EN_HEADER = (
    "CALIBRATION EXAMPLES (real annotations by a senior reviewer on similar "
    "documents. They calibrate the granularity and phrasing of reportable "
    "issues — how short a genuine review comment looks. They come from OTHER "
    "documents: never copy them into your output, and never relax the "
    "evidence requirements because an issue resembles an example):"
)


@lru_cache(maxsize=1)
def load_fewshot_examples():
    """加载判例语料，返回 tuple[dict]；文件缺失/损坏返回空元组。"""
    rows = []
    if not _FEWSHOT_FILE.exists():
        return ()
    try:
        with open(_FEWSHOT_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not row.get("label_code") or not row.get("comment"):
                    continue
                rows.append(row)
    except OSError:
        return ()
    return tuple(rows)


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def select_fewshot_examples(excerpt_text, match_limit=None):
    """按相关性选择判例：仅 anchor 真实命中当前节选时注入（相关门控）。

    设计依据（2026-11-23 T7 R01 回归实证）：无差别兜底（每个 chunk 注入
    6 条任意判例）造成样式漂移与泛化噪声，宽松 recall 85.4%→78.0%；
    改为命中门控——无命中即返回空，绝大多数 chunk 的 prompt 不受影响。
    """
    match_limit = _MATCH_LIMIT if match_limit is None else match_limit
    rows = load_fewshot_examples()
    if not rows:
        return []

    text = (excerpt_text or "").lower()
    picked = []
    seen_labels = set()

    for row in rows:
        if len(picked) >= match_limit:
            break
        label = row.get("label_code") or ""
        if label in seen_labels or label.startswith("Z"):
            continue  # Z 族为元批注（指代其他批注/定位失效/未识别），无教学价值
        anchor = (row.get("anchor") or "").strip()
        if len(anchor) < _ANCHOR_MIN_LEN or anchor.lower() not in text:
            continue
        comment = (row.get("comment") or "").strip()
        if not (_COMMENT_MIN_LEN <= len(comment) <= _COMMENT_MAX_LEN):
            continue
        seen_labels.add(label)
        picked.append({**row, "matched": True})

    return picked


def _format_example(index, row):
    label = row.get("label_name") or row.get("label_code") or ""
    comment = _truncate(row.get("comment"), 100)
    anchor = _truncate(row.get("anchor"), 60)
    line = f"{index}. [{label}] {_truncate(comment, 100)}"
    if anchor:
        line += f"｜位置上下文：{anchor}"
    return line


def build_fewshot_block(excerpt_text, language="cn"):
    """构建注入 system prompt 的判例区块；无可用判例时返回空串。"""
    examples = select_fewshot_examples(excerpt_text)
    if not examples:
        return ""
    is_english = language in ("en", "both")
    header = _EN_HEADER if is_english else _CN_HEADER
    lines = [header]
    used = 0
    for index, row in enumerate(examples, 1):
        line = _format_example(index, row)
        if used + len(line) > _BLOCK_CHAR_BUDGET:
            break
        lines.append(line)
        used += len(line)
    if len(lines) <= 1:
        return ""
    lines.append("")
    return "\n".join(lines)
