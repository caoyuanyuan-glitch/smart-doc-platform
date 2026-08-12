import json
import os
import tempfile
import time
import uuid
from io import BytesIO
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from PIL import Image

from app.api.auth import get_current_active_user
from app.crud.knowledge import get_file, get_folder_tree
from app.database import get_db
from app.utils.document_parser import parse_file
from app.utils.file_utils import read_file_safe
from app.utils.template_profiler import build_template_profile, retrieve_for_intent, MAX_TEMPLATE_SIZE_BYTES
from app.utils.template_job_manager import create_job, launch_job, get_job

router = APIRouter(dependencies=[Depends(get_current_active_user)])

DRAFT_CACHE: Dict[str, dict] = {}
DRAFT_CACHE_MAX = 20

STYLE_GUIDE_PATH = ("写作规范", "写作风格指南")
TERMINOLOGY_PATH = ("资源库", "术语库")
STYLE_GUIDE_MAX_CHARS = 1500  # 截断风格指南以避免 prompt 超长
TERMINOLOGY_MAX_CHARS = 3000
TEMPLATE_MAX_CHARS = 2000
MODEL_IMAGE_MAX_EDGE = 700
MODEL_IMAGE_QUALITY = 65

INTENT_INSTRUCTIONS = {
    "product_appearance": "生成意图：产品外观描述。重点描述产品整体外观、结构组成、可见部件、布局关系、颜色材质和可识别标识。",
    "operation_steps": "生成意图：操作步骤说明。重点从图片中识别连续操作步骤，输出可执行动作、点击对象、输入内容和页面跳转结果。",
    "interface_manual": "生成意图：界面功能说明。重点说明界面区域、功能入口、控件用途、状态提示和用户可执行操作。",
    "custom": "生成意图：自定义。优先遵循用户在补充要求中说明的生成目标。",
}

OUTPUT_FORMAT_INSTRUCTIONS = {
    "plain_text": "输出格式：纯文本。使用自然段组织内容，避免强制编号。",
    "numbered_steps": "输出格式：带编号步骤。按 1、2、3 的顺序输出步骤，每条步骤表达一个清晰动作或说明点。",
}

LANGUAGE_STYLE_INSTRUCTIONS = {
    "formal_technical": "语言风格：正式技术文档。使用规范、客观、可直接进入说明书的表达。",
    "concise": "语言风格：简要说明。使用简洁句式，保留关键信息，减少背景铺垫。",
}

# ── Leading Words (锚定预训练概念，提升可预测性) ──
LW_STEP = "步骤"        # 触发：操作序列、执行顺序
LW_DETAIL = "细化"      # 触发：展开说明、增加细节
LW_PARAM = "参数"       # 触发：数值条件、技术指标
LW_NOTICE = "须知"      # 触发：注意事项、使用提示
LW_WARN = "警示"        # 触发：风险识别、安全提示
LW_FAULT = "排查"       # 触发：异常检查、恢复操作
LW_CUSTOM = "指令"      # 触发：用户自定义要求

CONTINUATION_INTENT_INSTRUCTIONS = {
    "next_step": f"[{LW_STEP}] 仅写下一步操作。① 只能描述紧随其后的一个动作，包含操作对象、具体动作和预期结果 ② 禁止补充参数、注意事项、安全警告或故障处理 ③ 禁止编写编号步骤链 ④ 仅输出一段话，不写标题或序号",
    "expand_detail": f"[{LW_DETAIL}] 仅细化现有描述。① 对原文中的关键术语、机制、流程做展开说明 ② 禁止跳转到参数表、安全警告或故障处理 ③ 仅输出一段说明文，与原文主题完全一致",
    "supplement_parameters": f"[{LW_PARAM}] 仅补充参数。① 输出与当前操作相关的技术参数：数值范围、阈值、工作条件、规格要求 ② 格式可用「参数名：取值」或短句描述 ③ 禁止写操作步骤、注意事项、安全警告或故障排查 ④ 不写标题，直接列参数",
    "supplement_notices": f"[{LW_NOTICE}] 仅写注意事项。① 输出操作前/中/后需留意的要点（前置条件、操作细节、常见疏忽） ② 每条以短句开头，语气为温和提醒，非警告 ③ 禁止输出安全警示（含风险后果）、操作步骤或故障排查 ④ 建议用无编号短句，语气平实",
    "safety_warning": f"[{LW_WARN}] 仅写安全警告。① 识别当前操作的风险点，每条包含「风险场景 + 可能后果 + 规避动作」② 语气严肃、带警示性 ③ 禁止输出普通注意事项（不含风险后果）、操作步骤、参数或故障排查 ④ 不写标题，直接列警示内容",
    "troubleshooting": f"[{LW_FAULT}] 仅写故障处理。① 围绕当前操作场景补充异常现象、检查项和恢复动作 ② 每条包含「异常标志 + 检查步骤 + 恢复动作」③ 禁止输出操作步骤、参数说明、注意事项或安全警告 ④ 不写标题，直接列排查项",
    "custom": f"[{LW_CUSTOM}] 严格遵循用户提供的自定义续写要求，不添加要求以外的内容。",
}

CONTINUATION_LENGTH_INSTRUCTIONS = {
    "auto": "[续写长度] 自动。根据意图类型和上文上下文自行判断（1 句 ~ 1 段均可），以语义完整为原则，完成后立即停止。",
    "short": "[续写长度] 简短（严格控制）。\n"
             "① 只允许输出 1-2 个完整句子，正文总计不超过 80 个中文字符\n"
             "② 写完 1-2 句后必须立即停止，严禁补充第三句或任何额外说明\n"
             "③ 不要写序号、标题、项目符号",
    "detailed": "[续写长度] 详细（严格控制）。\n"
                "① 输出 1 个完整自然段，正文总计 150-350 个中文字符\n"
                "② 该自然段由 4-10 个句子组成，围绕同一主题展开\n"
                "③ 写完一个完整段落后必须立即停止，严禁继续写第二段\n"
                "④ 不要写序号、标题、项目符号",
}


class GenerateRequest(BaseModel):
    product_name: str
    product_model: str
    doc_type: str
    target_chapter: str


class ContinueTextRequest(BaseModel):
    source_text: str
    chapter_title: str = ""
    intent: str = "next_step"
    custom_intent: str = ""
    length: str = "auto"
    keep_terminology: bool = True
    keep_sentence_style: bool = True
    regenerate_seq: int = 0


def _generate_fallback(product_name: str, product_model: str, doc_type: str, target_chapter: str):
    title = f"{product_name}（{product_model}）{doc_type} - {target_chapter}"
    sections = [
        {
            "title": f"{target_chapter} 概述",
            "level": 1,
            "content": f"本章介绍 {product_name}（型号：{product_model}）在{doc_type}中的相关说明。"
        },
        {
            "title": "产品特点",
            "level": 2,
            "content": f"- 型号 {product_model} 具备标准功能与接口。\n- 适用于典型{doc_type}场景。\n- 可在规定环境下稳定运行。"
        },
        {
            "title": "使用说明",
            "level": 2,
            "content": f"请按以下步骤操作 {product_name} {product_model}：\n1. 检查外观与配件。\n2. 按照指示完成接线或初始化。\n3. 参考详细章节完成配置。"
        },
        {
            "title": "注意事项",
            "level": 2,
            "content": "- 使用前请仔细阅读本章内容。\n- 保持设备干燥、避免剧烈震动。\n- 如有异常请联系客服。"
        }
    ]
    content = f"# {title}\n\n"
    for s in sections:
        prefix = "#" * s["level"]
        content += f"\n{prefix} {s['title']}\n\n{s['content']}\n"
    return {"content": content.strip(), "sections": sections}


def _image_steps_fallback(file_names: List[str], prompt: str):
    steps = []
    for index, file_name in enumerate(file_names, start=1):
        steps.append(f"步骤 {index}：根据 {file_name} 中显示的关键对象和状态，完成当前环节操作，并确认进入下一步前的界面或物料状态已经满足要求。")

    return {
        "summary": f"共接收 {len(file_names)} 张图片，已按图片顺序整理为一组连续操作说明。",
        "relation_summary": f"当前结果按上传顺序组织流程，并结合用户补充要求输出。{prompt if prompt else '未提供额外约束。'}",
        "steps": steps,
        "used_style_guide_name": "自动匹配未命中具体指南",
        "model": "fallback",
        "warning": "当前多模型图片分析链路未返回有效结果，结果来自本地兜底逻辑，不能作为正式操作说明。",
    }


def _prepare_model_image(raw: bytes, content_type: str) -> tuple[bytes, str]:
    try:
        with Image.open(BytesIO(raw)) as image:
            image = image.convert("RGB")
            image.thumbnail((MODEL_IMAGE_MAX_EDGE, MODEL_IMAGE_MAX_EDGE), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=MODEL_IMAGE_QUALITY, optimize=True)
            return buffer.getvalue(), "image/jpeg"
    except Exception:
        return raw, content_type


def _infer_guide_language(name: str) -> str:
    lowered = str(name or "").lower()
    if "中文" in lowered or "chinese" in lowered:
        return "zh"
    if "英文" in lowered or "english" in lowered:
        return "en"
    return "unknown"


def _detect_result_language(text: str) -> str:
    sample = str(text or "")
    if not sample.strip():
        return "unknown"
    chinese_count = sum(1 for ch in sample if "\u4e00" <= ch <= "\u9fff")
    english_count = sum(1 for ch in sample if ("a" <= ch.lower() <= "z"))
    if chinese_count > english_count:
        return "zh"
    if english_count > chinese_count:
        return "en"
    return "unknown"


def _resolve_used_style_guide_name(style_guide_bundle: Optional[dict], result: dict) -> str:
    explicit_name = str(result.get("used_style_guide_name") or "").strip()
    if explicit_name:
        return explicit_name
    if not style_guide_bundle or not style_guide_bundle.get("guides"):
        return ""

    guides = style_guide_bundle.get("guides") or []
    if style_guide_bundle.get("mode") == "selected":
        return str(guides[0].get("name") or "").strip()

    combined_text = "\n".join([
        str(result.get("summary") or ""),
        str(result.get("relation_summary") or ""),
        "\n".join(result.get("steps") or []),
    ])
    detected_language = _detect_result_language(combined_text)
    for guide in guides:
        if guide.get("language") == detected_language:
            return str(guide.get("name") or "").strip()

    return str(guides[0].get("name") or "").strip()


def _collect_style_guides(node: dict, current_path: List[str]) -> List[dict]:
    guides = []
    for file in node.get("files") or []:
        file_path = file.get("file_path")
        file_type = str(file.get("file_type") or "").lower()
        if not file_path or not os.path.exists(file_path):
            continue
        if file_type not in {"md", "markdown", "txt"}:
            continue
        guides.append({
            "id": file.get("id"),
            "name": file.get("name") or file.get("filename") or "风格指南",
            "file_path": file_path,
            "path": " / ".join([*current_path, file.get("name") or file.get("filename") or "风格指南"]),
        })

    for child in node.get("children") or []:
        child_name = child.get("name") or ""
        guides.extend(_collect_style_guides(child, [*current_path, child_name]))
    return guides


def _collect_terminology_files(node: dict, current_path: List[str]) -> List[dict]:
    files = []
    for file in node.get("files") or []:
        file_path = file.get("file_path")
        if not file_path or not os.path.exists(file_path):
            continue
        files.append({
            "id": file.get("id"),
            "name": file.get("name") or file.get("filename") or "术语库文件",
            "file_path": file_path,
            "path": " / ".join([*current_path, file.get("name") or file.get("filename") or "术语库文件"]),
        })

    for child in node.get("children") or []:
        child_name = child.get("name") or ""
        files.extend(_collect_terminology_files(child, [*current_path, child_name]))
    return files


def _list_style_guide_candidates(db: Session) -> List[dict]:
    candidates: List[dict] = []

    def walk(nodes: List[dict], current_path: List[str]):
        for node in nodes or []:
            node_name = node.get("name") or ""
            next_path = [*current_path, node_name]
            if len(next_path) >= len(STYLE_GUIDE_PATH) and tuple(next_path[-len(STYLE_GUIDE_PATH):]) == STYLE_GUIDE_PATH:
                candidates.extend(_collect_style_guides(node, next_path))
                continue
            walk(node.get("children") or [], next_path)

    walk(get_folder_tree(db, None), [])
    return candidates


def _list_terminology_candidates(db: Session) -> List[dict]:
    candidates: List[dict] = []

    def walk(nodes: List[dict], current_path: List[str]):
        for node in nodes or []:
            node_name = node.get("name") or ""
            next_path = [*current_path, node_name]
            if len(next_path) >= len(TERMINOLOGY_PATH) and tuple(next_path[-len(TERMINOLOGY_PATH):]) == TERMINOLOGY_PATH:
                candidates.extend(_collect_terminology_files(node, next_path))
                continue
            walk(node.get("children") or [], next_path)

    walk(get_folder_tree(db, None), [])
    return candidates


def _read_reference_file(path: str) -> str:
    try:
        return parse_file(path).strip()
    except Exception:
        try:
            return read_file_safe(path).strip()
        except Exception:
            return ""


def _load_terminology_reference(db: Session, enabled: bool) -> Optional[dict]:
    if not enabled:
        return None

    chunks = []
    used_files = []
    remaining = TERMINOLOGY_MAX_CHARS
    for item in _list_terminology_candidates(db):
        content = _read_reference_file(item["file_path"])
        if not content:
            continue
        block = f"文件：{item['path']}\n{content}"
        if len(block) > remaining:
            block = block[:remaining]
        chunks.append(block)
        used_files.append(item["path"])
        remaining -= len(block)
        if remaining <= 0:
            break

    if not chunks:
        return None

    return {
        "files": used_files,
        "content": "\n\n".join(chunks),
    }


def _parse_terminology_pairs(content: str) -> dict:
    terms = {}
    for raw_line in str(content or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "---" in line:
            continue
        if "|" in line:
            cells = [cell.strip() for cell in line.strip("|").split("|") if cell.strip()]
        elif "\t" in line:
            cells = [cell.strip() for cell in line.split("\t") if cell.strip()]
        elif "," in line:
            cells = [cell.strip() for cell in line.split(",") if cell.strip()]
        else:
            continue
        if len(cells) < 2:
            continue
        lowered = " ".join(cells[:3]).lower()
        if any(token in lowered for token in ["非标准", "标准", "source", "target", "term"]):
            continue
        source, target = cells[0], cells[1]
        if source and target and source != target and len(source) <= 80 and len(target) <= 80:
            terms[source] = target
    return terms


def _apply_terminology_to_text(text: str, terminology_reference: Optional[dict]) -> str:
    """将术语库映射应用到单段文本，替换非标准术语为标准术语。"""
    if not terminology_reference:
        return text
    terms = _parse_terminology_pairs(terminology_reference.get("content") or "")
    if not terms:
        return text
    updated = str(text or "")
    for source, target in terms.items():
        updated = updated.replace(source, target)
    return updated


def _compute_quality_score(source_text: str, continuation: str, intent: str) -> dict:
    """
    综合质量评分（0-100），覆盖所有续写意图：
    - AI 腔扣分（slop-scan）
    - 风格一致性（voice-audit）
    - 内容长度合理性
    - 语义相关性（与原文的词汇重叠度）
    - 结构合理性（按意图检查输出格式）
    """
    import re

    score = 100
    issues = []

    # ── 1. AI 腔检测扣分 ──
    slop_findings = _slop_scan(continuation)
    if slop_findings:
        deduction = min(30, len(slop_findings) * 5)
        score -= deduction
        issues.append(f"检测到 {len(slop_findings)} 处 AI 腔表达")

    # ── 2. 风格一致性 ──
    va = _voice_audit(source_text, continuation)
    style_score = va["score"]
    if style_score < 60:
        score -= 20
        issues.append("风格与原文偏差较大")
    elif style_score < 80:
        score -= 10
        issues.append("风格与原文有一定偏差")

    # ── 3. 内容长度合理性 ──
    cont_len = len(continuation.strip())
    if cont_len < 10:
        score -= 40
        issues.append("续写内容过短")
    elif cont_len < 30:
        score -= 20
        issues.append("续写内容偏短")
    elif cont_len > 500:
        score -= 15
        issues.append("续写内容偏长，可能不够精炼")

    # ── 4. 语义相关性（词汇重叠度）──
    src_chars = set(source_text)
    cont_chars = set(continuation)
    if src_chars and cont_chars:
        overlap = len(src_chars & cont_chars) / max(len(src_chars), 1)
        if overlap < 0.15 and cont_len > 20:
            score -= 15
            issues.append("续写内容与原文关联度较低，可能存在跑题")

    score = max(0, min(100, round(score)))
    passed = score >= 70

    return {
        "score": score,
        "passed": passed,
        "threshold": 70,
        "issues": issues,
        "slop_count": len(slop_findings),
        "style_score": style_score,
        "length": cont_len,
    }


def _apply_terminology_reference(result: dict, terminology_reference: Optional[dict]) -> dict:
    if not terminology_reference:
        return result
    terms = _parse_terminology_pairs(terminology_reference.get("content") or "")
    if not terms:
        return result

    def replace_terms(text: str) -> str:
        updated = str(text or "")
        for source, target in terms.items():
            updated = updated.replace(source, target)
        return updated

    next_result = dict(result)
    next_result["summary"] = replace_terms(next_result.get("summary") or "")
    next_result["relation_summary"] = replace_terms(next_result.get("relation_summary") or "")
    next_result["steps"] = [replace_terms(step) for step in (next_result.get("steps") or [])]
    return next_result


def _build_image_generation_prompt(
    prompt: str,
    generation_intent: str,
    custom_intent: str,
    output_format: str,
    language_style: str,
    terminology_reference: Optional[dict],
) -> str:
    parts = [
        INTENT_INSTRUCTIONS.get(generation_intent) or INTENT_INSTRUCTIONS["operation_steps"],
        OUTPUT_FORMAT_INSTRUCTIONS.get(output_format) or OUTPUT_FORMAT_INSTRUCTIONS["numbered_steps"],
        LANGUAGE_STYLE_INSTRUCTIONS.get(language_style) or LANGUAGE_STYLE_INSTRUCTIONS["formal_technical"],
    ]
    if generation_intent == "custom" and custom_intent.strip():
        parts.append(f"自定义生成意图：{custom_intent.strip()}")
    if terminology_reference:
        parts.append(
            "术语标准：使用知识库资源库/术语库文件中的术语。系统会在读图后对生成结果执行术语标准化。\n"
            f"已关联术语库文件：{'; '.join(terminology_reference.get('files') or [])}"
        )
    if prompt.strip():
        parts.append(f"用户补充要求：{prompt.strip()}")
    return "\n\n".join(parts)


# ── SLOP-SCAN: AI 腔检测模式 (famulare writing-assistant-skills) ──
# 检测续写结果中的通用/空洞/AI 腔语言，返回标记列表
SLOP_SCAN_PATTERNS = {
    "generic_opening": ("通用开头", r"^(首先|第一步|开始之前|需要注意的是|值得一提的是)"),
    "vague_intensifier": ("模糊修饰", r"(非常|十分|相当|极其|特别|很重要|值得注意的是|需要注意的是)"),
    "corporate_filler": ("企业套话", r"( seamlessly| seamlessly| robust| robust| transformative| transformative| unlock| harness| leverage| delve| underscore)"),
    "motivational_filler": ("鸡汤式填充", r"(确保.*成功|为.*保驾护航|助力.*发展|实现.*目标|提升.*体验)"),
    "fake_symmetry": ("虚假对称", r"(不仅.*而且.*还|一方面.*另一方面|既要.*又要.*还要)"),
    "stakes_narration": ("意义宣告", r"(这是.*的关键|这一点非常重要|.*的意义在于|.*至关重要)"),
    "meta_conclusion": ("元结论", r"(综上所述|总之|总而言之|由此可见|因此.*可以得出)"),
    "low_info_coda": ("低信息收尾", r"(希望以上内容.*有帮助|如有疑问.*请联系|.*请随时.*我们)"),
    "over_broad_tail": ("过度泛化", r"(在.*领域|对于.*行业|从.*角度来看|.*具有重要意义)"),
    "absolute_quantifier": ("绝对化表述", r"(唯一|绝对|完全|彻底|始终|永远|必然|肯定)"),
    "abstract_noun": ("抽象名词堆砌", r"(实现.*的|完成.*的|进行.*的|开展.*的|推进.*的)"),
    "citation_wave": ("无引用文献波", r"(研究表明|实践证明|数据显示|经验表明|长期以来)"),
    "passive_voice": ("过度被动", r"被.*所.*"),
    "empty_transition": ("空转接", r"(此外|另外|除此之外|与此同时|不仅如此)"),
}


def _slop_scan(text: str) -> list:
    """扫描文本中的 AI 腔（slop），返回检测到的模式列表。"""
    import re
    findings = []
    for key, (label, pattern) in SLOP_SCAN_PATTERNS.items():
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        for m in matches:
            # 获取匹配上下文（前后各10字）
            start = max(0, m.start() - 10)
            end = min(len(text), m.end() + 10)
            context = text[start:end]
            findings.append({
                "type": key,
                "label": label,
                "matched": m.group(0),
                "context": context,
                "position": m.start(),
            })
    # 按位置排序
    findings.sort(key=lambda x: x["position"])
    return findings


def _voice_audit(source_text: str, continuation: str) -> dict:
    """
    风格一致性审计（voice-audit）：对比原文与续写的风格特征。
    返回风格一致性评分和观察点。
    """
    import re

    def extract_features(text: str) -> dict:
        # 句子长度特征
        sentences = re.split(r'[。！？\n]', text)
        sentence_lengths = [len(s.strip()) for s in sentences if s.strip()]
        avg_len = sum(sentence_lengths) / len(sentence_lengths) if sentence_lengths else 0

        # 标点特征
        comma_density = text.count('，') / max(len(text), 1)
        semicolon_count = text.count('；')

        # 人称特征
        first_person = text.count('我') + text.count('我们')
        second_person = text.count('你') + text.count('您')

        # 祈使句特征（技术文档常见）
        imperative = len(re.findall(r'^[请|将|把|按|确认|检查|点击|输入|选择]', text, re.MULTILINE))

        # 数字/编号密度
        number_density = len(re.findall(r'\d+', text)) / max(len(text), 1)

        return {
            "avg_sentence_length": round(avg_len, 1),
            "comma_density": round(comma_density * 100, 2),
            "semicolon_count": semicolon_count,
            "first_person": first_person,
            "second_person": second_person,
            "imperative_count": imperative,
            "number_density": round(number_density * 100, 2),
        }

    src = extract_features(source_text)
    cont = extract_features(continuation)

    # 计算一致性偏差（越小越一致）
    deviations = {
        "sentence_length": abs(src["avg_sentence_length"] - cont["avg_sentence_length"]),
        "comma_density": abs(src["comma_density"] - cont["comma_density"]),
        "number_density": abs(src["number_density"] - cont["number_density"]),
    }

    # 综合一致性评分 (0-100, 100=完全一致)
    # 句子长度偏差每 5 字扣 5 分，逗号密度每 1% 扣 5 分，数字密度每 1% 扣 3 分
    score = 100
    score -= min(25, deviations["sentence_length"] / 5 * 5)
    score -= min(25, deviations["comma_density"] * 5)
    score -= min(20, deviations["number_density"] * 3)

    # 祈使句一致性奖励（技术文档应保持祈使语气）
    if src["imperative_count"] > 0 and cont["imperative_count"] > 0:
        score += 5
    elif src["imperative_count"] > 0 and cont["imperative_count"] == 0:
        score -= 10  # 原文有祈使句，续写却没有 = 风格漂移

    score = max(0, min(100, round(score)))

    observations = []
    if deviations["sentence_length"] > 10:
        observations.append(f"句子长度偏差较大（原文 {src['avg_sentence_length']} 字/句 vs 续写 {cont['avg_sentence_length']} 字/句）")
    if deviations["comma_density"] > 2:
        observations.append("逗号使用密度与原文不一致")
    if src["imperative_count"] > 0 and cont["imperative_count"] == 0:
        observations.append("原文使用祈使语气，续写未保持")
    if cont["first_person"] > src["first_person"]:
        observations.append("续写出现第一人称，原文未使用或较少")

    return {
        "score": score,
        "source_features": src,
        "continuation_features": cont,
        "deviations": {k: round(v, 2) for k, v in deviations.items()},
        "observations": observations,
        "status": "consistent" if score >= 80 else "drift" if score >= 60 else "significant_drift",
    }


def _build_continuation_prompt(
    request: ContinueTextRequest,
    terminology_reference: Optional[dict],
    style_guide_bundle: Optional[dict],
    template_profile: Optional[dict] = None,
) -> str:
    """
    构建续写 prompt —— 应用 mattpocock Skill 原则：
    - 正向表述（Positives）替代否定/禁止
    - Leading Words 锚定行为
    - 明确的完成标准（Completion Criterion）
    - 删除 no-op（不支付 token 给默认就遵守的指令）
    """
    parts = [
        "[角色] 技术文档续写助手。",
        "[任务] 基于现有技术文档片段，生成可直接插入说明书的后续内容。",
        "[铁律] 以下四条是每次续写都必须严格遵守的硬性规则，优先级高于其他任何指令：\n"
        "① 不编造事实 — 不得杜撰不存在的功能、参数、操作步骤或安全风险，不确定的内容宁可省略也不要臆造；\n"
        "② 不重复已有内容 — 不得复述、改写或仅在措辞上微调用户提供的现有内容，续写必须是原文之后的增量信息；\n"
        "③ 只输出有价值内容 — 拒绝废话、套话、口水话（如'请按照说明书操作''注意安全''相关信息请参见下文'等无信息量的句子），每一句都必须对读者有实际帮助；\n"
        "④ 技术文档风格 — 用词准确、句式简洁、逻辑严密，避免口语化、情绪化表达，不使用感叹号、表情符号或营销性语言。",
        CONTINUATION_INTENT_INSTRUCTIONS.get(request.intent) or CONTINUATION_INTENT_INSTRUCTIONS["next_step"],
        CONTINUATION_LENGTH_INSTRUCTIONS.get(request.length) or CONTINUATION_LENGTH_INSTRUCTIONS["short"],
        "[输出标准] 只输出新增续写文本，不重复原文。",
    ]

    if request.intent == "next_step":
        parts.append("[完成标准] ① 只输出一个后续动作的描述，包含操作对象、动作、预期结果 ② 必须与上文语义连贯 ③ 禁止补充参数、注意事项、警告、故障排查等其他类型内容 ④ 不写序号或标题")
    elif request.intent == "supplement_parameters":
        parts.append("[完成标准] ① 仅输出参数值、范围、阈值、规格，使用「参数名：取值」或短句 ② 禁止操作步骤、注意事项、警告、故障排查 ③ 不写标题，不写解释性文字 ④ 直接列参数")
    elif request.intent == "supplement_notices":
        parts.append("[完成标准] ① 仅输出温和提醒类注意事项，不涉及风险后果 ② 禁止安全警告、操作步骤、参数、故障排查 ③ 语气平实、提醒而非警示 ④ 不写标题")
    elif request.intent == "safety_warning":
        parts.append("[完成标准] ① 仅输出含风险场景 + 后果 + 规避动作的安全警告 ② 禁止普通注意事项、操作步骤、参数、故障排查 ③ 语气严肃、带警示性 ④ 不写标题")
    elif request.intent == "troubleshooting":
        parts.append("[完成标准] ① 仅输出含异常标志 + 检查步骤 + 恢复动作的故障排查项 ② 禁止操作步骤、参数、注意事项、安全警告 ③ 不写标题")
    elif request.intent == "expand_detail":
        parts.append("[完成标准] ① 仅细化原文已有的术语、机制或流程 ② 禁止跳转到其他意图类型（步骤/参数/注意/警告/排查）③ 与原文主题完全一致 ④ 一段说明文，不写标题")
    else:
        parts.append("[完成标准] 输出内容必须满足：① 与上文语义连贯 ② 不含标题/解释/JSON/Markdown 代码块 ③ 仅基于上下文合理推断，不引入外部假设。")

    if request.intent == "custom" and request.custom_intent.strip():
        parts.append(f"[自定义指令] {request.custom_intent.strip()}")

    if terminology_reference:
        terminology_pairs = _parse_terminology_pairs(terminology_reference.get("content") or "")
        terminology_lines = [
            f"- {source} -> {target}"
            for source, target in list(terminology_pairs.items())[:80]
        ]
        if terminology_lines:
            parts.append(
                "[术语锚定] 优先使用以下标准术语：\n"
                + "\n".join(terminology_lines)
            )

    if style_guide_bundle and style_guide_bundle.get("guides"):
        guide_blocks = []
        for guide in (style_guide_bundle.get("guides") or [])[:2]:
            guide_blocks.append(f"{guide.get('name') or '未命名'}\n{guide.get('content') or ''}")
        parts.append(
            "[风格锚定] 匹配以下句式手册的表达习惯：\n"
            + "\n\n".join(guide_blocks)
        )

    if request.chapter_title.strip():
        parts.append(f"[当前章节]\n{request.chapter_title.strip()}")

    if template_profile:
        profile = template_profile.get("document_profile") or {}
        examples = template_profile.get("example_bank") or {}

        # 检索相关片段（按 intent + chapter_title + source_text 做 query）
        query_text = f"{request.chapter_title} {request.source_text[:80]}"
        retrieved = retrieve_for_intent(
            template_profile, intent=request.intent,
            query=query_text, max_chars=1200,
        )

        tpl_blocks: List[str] = []

        style_lines = []
        ws = str(profile.get("writing_style") or "").strip()
        fs = str(profile.get("format_spec") or "").strip()
        gl = profile.get("glossary") or []
        ty = profile.get("typical_sentences") or []
        fo = profile.get("forbidden_expressions") or []
        if ws:
            style_lines.append(f"写作风格：{ws}")
        if fs:
            style_lines.append(f"格式规范：{fs}")
        if gl:
            gl_str = "；".join(
                f"{g.get('term','')}={g.get('def','')}" if isinstance(g, dict) else str(g)
                for g in gl[:12]
            )
            style_lines.append(f"术语表：{gl_str}")
        if ty:
            style_lines.append("典型句式：" + " / ".join(str(t) for t in ty[:6]))
        if fo:
            style_lines.append("禁用表达：" + " / ".join(str(f) for f in fo[:6]))

        if style_lines:
            tpl_blocks.append(
                f"[模板风格锚定 · {template_profile.get('name','')}] "
                "请按如下风格特征和术语表来写续写内容，但不要复述模板：\n"
                + "\n".join(f"· {line}" for line in style_lines)
            )

        # 意图匹配的样例
        intent_examples = examples.get(request.intent) or []
        if intent_examples:
            label = {
                "next_step": "操作步骤写法",
                "expand_detail": "详细说明写法",
                "supplement_parameters": "参数写法",
                "supplement_notices": "注意事项写法",
                "safety_warning": "安全警告写法",
                "troubleshooting": "故障处理写法",
                "custom": "通用写法",
            }.get(request.intent, "写法")
            tpl_blocks.append(
                f"[模板样例 · {label}] 以下是模板中同类型写法的原文摘录，"
                "续写请参考其措辞和句式，不要照搬：\n"
                + "\n".join(f"- {e}" for e in intent_examples[:5])
            )

        # 检索到的相关片段
        if retrieved:
            snippet_lines = []
            for item in retrieved:
                title = item.get("title", "")
                content = item.get("content", "")
                snippet_lines.append(
                    f"【片段：{title}】\n{content}" if title else content
                )
            tpl_blocks.append(
                f"[模板检索片段 · {request.intent}] 以下是模板中与"
                "本意图相关的章节片段，请参考写法，不要复述原文：\n"
                + "\n\n".join(snippet_lines)
            )

        if tpl_blocks:
            parts.append("\n\n".join(tpl_blocks))
        else:
            preview = template_profile.get("full_text_preview") or ""
            if preview:
                parts.append(
                    f"[参考模板 · {template_profile.get('name','')}] "
                    "模板自动分析暂未命中意图相关片段，请参考模板整体写法：\n"
                    f"{preview[:600]}"
                )

    parts.append(f"[现有内容]\n{request.source_text.strip()}")

    # [输出边界硬约束] —— 放在 prompt 末尾，让模型最后看到最强的长度锚定
    if request.length == "short":
        parts.append(
            "[输出边界硬约束] 你现在必须输出续写内容。"
            "规则如下：\n"
            "① 最多写 2 句，每句控制在 30-50 字以内，总字数不超过 80 字\n"
            "② 写完 1-2 句完整意思后，立即停止输出，不要加任何后续文字\n"
            "③ 严禁输出解释、说明、标题、序号或额外段落\n"
            "⚠️ 一旦达到 2 句或 80 字上限，必须停笔，不要贪多"
        )
    elif request.length == "detailed":
        parts.append(
            "[输出边界硬约束] 你现在必须输出续写内容。"
            "规则如下：\n"
            "① 写 1 个完整自然段（4-10 句，总字数 150-350 字）\n"
            "② 自然段写完（语义完整、有明确结尾）后立即停止输出\n"
            "③ 严禁输出第二段、标题、序号、项目符号或额外补充说明\n"
            "⚠️ 段内写完即停，不要继续往下写"
        )
    else:
        parts.append(
            "[输出边界硬约束] 你现在必须输出续写内容。"
            "根据上文和意图自行判断长度，但必须在语义完整后立即停止，不要贪多。"
        )

    return "\n\n".join(parts)


def _resolve_continuation_max_tokens(length: str, intent: str = "") -> int:
    if length == "short":
        return 192
    if length == "detailed":
        return 768
    if length == "auto":
        if intent in ("supplement_parameters", "supplement_notices", "safety_warning", "troubleshooting"):
            return 768
        if intent == "next_step":
            return 256
        return 512
    return 384


def _clean_continuation_text(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            cleaned = parsed.get("continuation") or parsed.get("content") or parsed.get("text") or cleaned
    except Exception:
        pass
    for prefix in ("续写：", "续写内容：", "continuation:", "content:"):
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix):].strip()
            break
    return cleaned.strip().strip('"\',，,')


def _ensure_step_format(text: str) -> str:
    """
    将输出文本强制转换为编号步骤格式。
    - 如果已经是步骤格式（行首有编号），直接规范化编号
    - 否则按句号/换行切分为独立动作，重新编号
    - 如果只有 1 个步骤，尝试按逗号拆分为多个子步骤
    """
    import re

    cleaned = str(text or "").strip()
    if not cleaned:
        return cleaned

    # 检测是否已经是步骤格式
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    number_pattern = re.compile(r'^[\d]+[.)、]\s*')

    # 如果所有非空行都以编号开头 → 只是需要规范化编号
    if lines and all(number_pattern.match(line) for line in lines):
        content_lines = [number_pattern.sub('', line).strip() for line in lines]
        # 如果只有 1 步且内容包含逗号，尝试拆分为子步骤
        if len(content_lines) == 1:
            sub_steps = _split_single_step(content_lines[0])
            if len(sub_steps) > 1:
                cleaned = "\n".join(sub_steps)
                lines = sub_steps

        renumbered = []
        for i, line in enumerate(lines, 1):
            content = number_pattern.sub('', line).strip()
            renumbered.append(f"{i}. {content}")
        return "\n".join(renumbered)

    # 否则：按中文句号、分号、换行切分为独立子句，重新编号
    clauses = []
    for line in lines:
        line = number_pattern.sub('', line).strip()
        sub_clauses = re.split(r'[。；;]\s*', line)
        for clause in sub_clauses:
            clause = clause.strip(' 　')
            if clause and len(clause) >= 2:
                if not clause[-1] in '。！？！.':
                    clause += '。'
                clauses.append(clause)

    if not clauses:
        return cleaned

    # 如果只有 1 个子句，尝试进一步拆分
    if len(clauses) == 1:
        raw = clauses[0].rstrip('。！？！.')
        sub_steps = _split_single_step(raw)
        if len(sub_steps) > 1:
            steps = []
            for i, s in enumerate(sub_steps, 1):
                steps.append(f"{i}. {s}")
            return "\n".join(steps)

    steps = []
    for i, clause in enumerate(clauses, 1):
        steps.append(f"{i}. {clause}")

    return "\n".join(steps)


def _split_single_step(text: str) -> list:
    """
    将单个长步骤按逗号、顿号拆分为多个子步骤。
    返回拆分后的子步骤列表（不含编号）。
    """
    import re
    raw = str(text or "").strip().rstrip('。！？！.')
    if not raw:
        return [text]

    # 按中文逗号、顿号、英文逗号拆分，但保留完整短语
    # 启发式：如果文本较长（>20字）且包含逗号，尝试拆分
    if len(raw) < 15:
        return [text]

    # 按逗号拆分，过滤太短的片段并重新组合
    parts = re.split(r'[，,、]\s*', raw)
    if len(parts) < 2:
        return [text]

    # 过滤掉太短的部分（<3字），并将其合并到前一部分
    merged = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) < 3 and merged:
            merged[-1] = merged[-1].rstrip('。') + '，' + part
        else:
            merged.append(part)

    if len(merged) < 2:
        return [text]

    # 为每个子句补回句号
    result = []
    for part in merged:
        if not part[-1] in '。！？！.':
            part += '。'
        result.append(part)

    return result


def _continuation_fallback(request: ContinueTextRequest) -> str:
    if request.intent == "next_step":
        return "完成当前操作后，在控制面板点击确认按钮，等待系统响应并观察界面状态变化。"
    if request.intent == "expand_detail":
        return "该步骤的执行效果受样本初始状态、环境温湿度及设备校准精度共同影响，操作前需确保各项前置条件满足说明书规定。"
    if request.intent == "supplement_parameters":
        return "工作电压：DC 12V ± 5%\n环境温度：15 ℃ ~ 30 ℃\n相对湿度：≤ 75%\n样本容量：0.5 mL ~ 2.0 mL\n运行时长：约 45 分钟"
    if request.intent == "supplement_notices":
        return "操作前请核对样本编号与录入信息是否一致。\n运行过程中请勿触碰设备外壳。\n更换耗材后请注意及时关闭舱门。\n操作完成后建议对工作台进行清洁。"
    if request.intent == "safety_warning":
        return "⚠️ 舱门未完全关闭即启动设备，可能导致样本飞溅或运动部件外露，务必确认锁定后再执行。\n⚠️ 长时间连续运行会使设备过热，建议每 4 小时停机休息 10 分钟。\n⚠️ 请勿将磁性物品靠近控制主板，可能影响传感器读数准确性。"
    if request.intent == "troubleshooting":
        return "异常标志：设备启动后界面无响应 → 检查电源插头是否插紧，重新上电重试。\n异常标志：槽盖关闭后系统仍提示未锁定 → 检查槽盖传感器是否被异物遮挡，清理后再次关闭。\n异常标志：实验中途暂停 → 查看样本是否偏离采样位，复位后点击继续按钮。"
    if request.intent == "custom" and request.custom_intent.strip():
        return f"（兜底续写）{request.custom_intent.strip()}：请确认操作对象就位后，按界面提示完成后续步骤。"
    return "请确认当前操作对象已正确就位，然后点击界面中的开始按钮启动处理流程。系统进入下一步后，按照页面提示继续完成后续操作。"


def _load_style_guide_bundle(db: Session, style_guide_id: Optional[int]) -> Optional[dict]:
    if style_guide_id:
        guide_file = get_file(db, style_guide_id)
        if not guide_file or not guide_file.file_path or not os.path.exists(guide_file.file_path):
            return None
        content = read_file_safe(guide_file.file_path).strip()
        if not content:
            return None
        if len(content) > STYLE_GUIDE_MAX_CHARS:
            content = content[:STYLE_GUIDE_MAX_CHARS] + "\n\n...（指南内容已截断以避免 prompt 超长）"
        guide_name = guide_file.name or guide_file.filename or "风格指南"
        return {
            "mode": "selected",
            "guides": [{
                "id": guide_file.id,
                "name": guide_name,
                "language": _infer_guide_language(guide_name),
                "content": content,
            }],
        }

    guides = []
    for item in _list_style_guide_candidates(db):
        try:
            content = read_file_safe(item["file_path"]).strip()
        except Exception:
            continue
        if not content:
            continue
        if len(content) > STYLE_GUIDE_MAX_CHARS:
            content = content[:STYLE_GUIDE_MAX_CHARS] + "\n\n...（指南内容已截断以避免 prompt 超长）"
        guides.append({
            "id": item["id"],
            "name": item["name"],
            "path": item["path"],
            "language": _infer_guide_language(item["name"]),
            "content": content,
        })

    if not guides:
        return None
    return {"mode": "auto", "guides": guides}


async def _load_template_reference(template_file: Optional[UploadFile]) -> Optional[dict]:
    if not template_file:
        return None

    raw = await template_file.read()
    if not raw:
        return None

    suffix = os.path.splitext(template_file.filename or "")[1] or ".txt"
    try:
        with tempfile.TemporaryDirectory(prefix="image-template-") as temp_dir:
            temp_path = os.path.join(temp_dir, f"template{suffix}")
            with open(temp_path, "wb") as handle:
                handle.write(raw)
            raw_content = parse_file(temp_path).strip()
    except Exception:
        try:
            raw_content = raw.decode("utf-8", errors="replace").strip()
        except Exception:
            return None

    if not raw_content:
        return None

    content = raw_content[:TEMPLATE_MAX_CHARS]
    debug_content = content

    if "\f" in content:
        pages = content.split("\f")
        debug_parts = []
        for idx, page_text in enumerate(pages, start=1):
            page_clean = page_text.strip()
            if not page_clean:
                continue
            preview = page_clean[:20].replace("\n", " ")
            debug_parts.append(f"\n--- 第 {idx} 页 ---\n前 20 字预览：{preview}\n\n{page_clean}")
        if debug_parts:
            debug_content = "\n".join(debug_parts)
    else:
        paragraphs = [p for p in content.split("\n\n") if p.strip()]
        if len(paragraphs) > 1:
            debug_parts = []
            for idx, para in enumerate(paragraphs, start=1):
                para_clean = para.strip()
                preview = para_clean[:20].replace("\n", " ")
                debug_parts.append(f"\n--- 第 {idx} 段 ---\n首 20 字：{preview}\n\n{para_clean}")
            debug_content = "\n".join(debug_parts)

    return {
        "name": template_file.filename or "模板文件",
        "content": content,
        "debug_content": debug_content,
    }


@router.post("/")
async def generate_content(request: GenerateRequest):
    try:
        from app.utils.ai_client import ai_client

        ai_result = ai_client.generate_content(
            request.product_name,
            request.product_model,
            request.doc_type,
            request.target_chapter,
        )

        content = ""
        sections = []
        if isinstance(ai_result, dict):
            content = ai_result.get("content") or ai_result.get("text") or ""
            sections = ai_result.get("sections") or []
        elif isinstance(ai_result, str):
            content = ai_result

        if not content:
            raise RuntimeError("empty ai result")

        if not sections:
            lines = [ln.strip() for ln in content.split("\n") if ln.strip()]
            for i, ln in enumerate(lines[:8]):
                sections.append({
                    "title": ln[:40],
                    "level": 1 if i == 0 else 2,
                    "content": ln[:200]
                })

        return {
            "product_name": request.product_name,
            "product_model": request.product_model,
            "doc_type": request.doc_type,
            "target_chapter": request.target_chapter,
            "content": content,
            "sections": sections,
        }
    except Exception:
        fb = _generate_fallback(
            request.product_name,
            request.product_model,
            request.doc_type,
            request.target_chapter,
        )
        return {
            "product_name": request.product_name,
            "product_model": request.product_model,
            "doc_type": request.doc_type,
            "target_chapter": request.target_chapter,
            "content": fb["content"],
            "sections": fb["sections"],
        }


# ────────── 模板异步分析（卡点 1-A）──────────────────────────

@router.post("/template-analyze")
async def template_analyze(
    template_file: UploadFile = File(...),
):
    """提交模板文件，后台异步分析。立即返回 job_id。"""
    raw = await template_file.read()
    filename = template_file.filename or "未命名模板"

    try:
        job = create_job(filename, raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    launch_job(job.job_id, raw)
    return job.to_public_dict()


@router.get("/template-status")
async def template_status(job_id: str):
    """查询 job 当前进度。"""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"job_id 不存在或已过期：{job_id}")
    return job.to_public_dict()


# ────────── 智能续写 ────────────────────────────────────────────

@router.post("/continue-text")
async def continue_text(
    source_text: str = Form(...),
    chapter_title: str = Form(""),
    intent: str = Form("next_step"),
    custom_intent: str = Form(""),
    length: str = Form("auto"),
    keep_terminology: bool = Form(True),
    keep_sentence_style: bool = Form(True),
    regenerate_seq: int = Form(0),
    template_file: Optional[UploadFile] = File(None),
    template_job_id: str = Form(""),
    db: Session = Depends(get_db),
):
    source_text = source_text.strip()
    chapter_title = chapter_title.strip()
    if not source_text:
        raise HTTPException(status_code=400, detail="请填写现有内容")
    if len(source_text) > 6000:
        raise HTTPException(status_code=400, detail="现有内容过长，请控制在 6000 字以内")
    if intent == "custom" and not custom_intent.strip():
        raise HTTPException(status_code=400, detail="请填写自定义续写要求")

    request = ContinueTextRequest(
        source_text=source_text,
        chapter_title=chapter_title,
        intent=intent,
        custom_intent=custom_intent,
        length=length,
        keep_terminology=keep_terminology,
        keep_sentence_style=keep_sentence_style,
        regenerate_seq=regenerate_seq,
    )

    terminology_reference = _load_terminology_reference(db, keep_terminology)
    style_guide_bundle = _load_style_guide_bundle(db, None) if keep_sentence_style else None

    template_profile = None
    if template_job_id:
        job = get_job(template_job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"模板分析任务不存在或已过期")
        if job.status == "analyzing":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "TEMPLATE_ANALYZING",
                    "job_id": job.job_id,
                    "step": job.step,
                    "step_label": job.step_label,
                },
            )
        if job.status == "failed":
            raise HTTPException(status_code=400, detail=f"模板分析失败：{job.error or '未知错误'}")
        template_profile = job.profile
    elif template_file:
        try:
            raw = await template_file.read()
            if raw:
                try:
                    template_profile = build_template_profile(
                        template_file.filename or "模板文件", raw
                    )
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            print(f"[continue-text] template_profile build failed: {e}")
            template_profile = None

    prompt = _build_continuation_prompt(
        request, terminology_reference, style_guide_bundle, template_profile=template_profile
    )

    base_temperature = 0.25
    if regenerate_seq > 0:
        import random
        temperature = min(0.75, base_temperature + regenerate_seq * 0.1)
        angle_hint = random.choice([
            "请从另一个具体动作切入",
            "请换一个表述方式重写",
            "请补充更具体的操作细节",
            "请从不同角度描述",
            "请使用不同的动词",
        ])
        prompt = f"{prompt}\n\n[重写提示 #{regenerate_seq}] {angle_hint}，与之前结果保持不同。"
    else:
        temperature = base_temperature

    try:
        from app.utils.ai_client import ai_client

        max_attempts = 2
        best_result = None
        best_quality = {"score": 0, "passed": False}

        for attempt in range(max_attempts):
            result = ai_client.chat([
                {"role": "system", "content": "[任务] 输出新增续写文本，不重复上文。"},
                {"role": "user", "content": prompt},
            ], max_tokens=_resolve_continuation_max_tokens(length, request.intent),
               temperature=temperature + attempt * 0.15, kimi_thinking="disabled")
            continuation = _clean_continuation_text(result)
            if not continuation:
                continue

            # ── 后处理：术语库强制对齐 ──
            if terminology_reference:
                continuation = _apply_terminology_to_text(continuation, terminology_reference)

            # ── 质量评分 ──
            quality = _compute_quality_score(source_text, continuation, intent)

            if quality["score"] > best_quality["score"]:
                best_quality = quality
                best_result = continuation

            if quality["passed"]:
                break

        if not best_result:
            raise RuntimeError("empty continuation")

        # ── 最终审计（仅记录，不暴露给 UI）──
        slop_findings = _slop_scan(best_result)
        voice_audit = _voice_audit(source_text, best_result)

        return {
            "source_text": source_text,
            "continuation": best_result,
            "used_terminology_files": terminology_reference.get("files") if terminology_reference else [],
            "used_style_guide_name": _resolve_used_style_guide_name(style_guide_bundle, {"steps": [best_result]}) if style_guide_bundle else "",
            "template_name": template_profile.get("name") if template_profile else "",
            "model": "kimi",
            "warning": "",
            "audit": {
                "slop_scan": {
                    "findings_count": len(slop_findings),
                    "findings": slop_findings,
                    "passed": len(slop_findings) == 0,
                },
                "voice_audit": voice_audit,
                "quality_score": best_quality["score"],
                "quality_passed": best_quality["passed"],
                "quality_issues": best_quality.get("issues", []),
            },
        }
    except Exception as e:
        print(f"[continue-text] fallback: {e}")
        fallback_text = _continuation_fallback(request)
        if terminology_reference:
            fallback_text = _apply_terminology_to_text(fallback_text, terminology_reference)
        return {
            "source_text": source_text,
            "continuation": fallback_text,
            "used_terminology_files": terminology_reference.get("files") if terminology_reference else [],
            "used_style_guide_name": _resolve_used_style_guide_name(style_guide_bundle, {"steps": []}) if style_guide_bundle else "",
            "model": "fallback",
            "warning": "当前 AI 续写链路未返回有效结果，已展示本地示例续写。",
            "audit": {
                "slop_scan": {"findings_count": 0, "findings": [], "passed": True},
                "voice_audit": {
                    "score": 0,
                    "status": "fallback",
                    "observations": ["当前为兜底续写，未执行风格审计"],
                },
                "quality_score": 0,
                "quality_passed": False,
                "quality_issues": ["当前为兜底续写"],
            },
        }


@router.post("/image-steps")
async def generate_image_steps(
    files: List[UploadFile] = File(...),
    template_file: Optional[UploadFile] = File(None),
    prompt: str = Form(""),
    generation_intent: str = Form("operation_steps"),
    custom_intent: str = Form(""),
    output_format: str = Form("numbered_steps"),
    language_style: str = Form("formal_technical"),
    use_terminology: bool = Form(False),
    style_guide_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    started_at = time.monotonic()
    valid_images = []
    for index, file in enumerate(files, start=1):
        raw = await file.read()
        if not raw:
            continue
        content_type = file.content_type or "image/png"
        if not content_type.startswith("image/"):
            continue
        valid_images.append({
            "name": file.filename or f"image-{index}.png",
            "content_type": content_type,
            "raw": raw,
        })

    if not valid_images:
        raise HTTPException(status_code=400, detail="请上传至少一张有效图片")

    from app.utils.ai_client import ai_client

    print(f"[image-steps] request received, images={len(valid_images)}, intent={generation_intent}, output_format={output_format}, terminology={use_terminology}")

    image_entries = []
    original_size = 0
    prepared_size = 0
    for item in valid_images:
        original_size += len(item["raw"])
        prepared_raw, prepared_type = _prepare_model_image(item["raw"], item["content_type"])
        prepared_size += len(prepared_raw)
        image_entries.append({
            "name": item["name"],
            "data_url": ai_client.build_image_data_url(prepared_raw, item["name"], prepared_type),
        })
    style_guide_bundle = _load_style_guide_bundle(db, style_guide_id) if style_guide_id else None
    template_reference = await _load_template_reference(template_file)
    terminology_reference = _load_terminology_reference(db, use_terminology)
    enhanced_prompt = _build_image_generation_prompt(
        prompt=prompt,
        generation_intent=generation_intent,
        custom_intent=custom_intent,
        output_format=output_format,
        language_style=language_style,
        terminology_reference=terminology_reference,
    )

    try:
        print(f"[image-steps] prepared images, original={original_size}, prepared={prepared_size}")
        result = ai_client.analyze_images_to_steps(
            image_entries,
            user_prompt=enhanced_prompt,
            style_guide_bundle=style_guide_bundle,
            template_reference=template_reference,
        )
        if not result or not result.get("steps"):
            raise RuntimeError("empty image analysis result")
        result = _apply_terminology_reference(result, terminology_reference)
        elapsed = time.monotonic() - started_at
        print(f"[image-steps] success, model={result.get('model')}, steps={len(result.get('steps') or [])}, elapsed={elapsed:.1f}s")
        draft_key = uuid.uuid4().hex
        DRAFT_CACHE[draft_key] = {
            "draft": {
                "summary": result.get("summary") or "",
                "relation_summary": result.get("relation_summary") or "",
                "steps": result.get("steps") or [],
            },
            "created_at": time.time(),
        }
        if len(DRAFT_CACHE) > DRAFT_CACHE_MAX:
            oldest = sorted(DRAFT_CACHE.keys(), key=lambda k: DRAFT_CACHE[k].get("created_at", 0))[0]
            del DRAFT_CACHE[oldest]
        return {
            "summary": result.get("summary") or "",
            "relation_summary": result.get("relation_summary") or "",
            "steps": result.get("steps") or [],
            "used_style_guide_name": _resolve_used_style_guide_name(style_guide_bundle, result),
            "used_terminology_files": terminology_reference.get("files") if terminology_reference else [],
            "model": result.get("model") or "kimi",
            "draft_key": draft_key,
            "warning": "",
            "draft_raw": result.get("draft_raw") or "",
            "refined_raw": result.get("refined_raw") or "",
            "draft_prompt": result.get("draft_prompt") or "",
            "refined_prompt": result.get("refined_prompt") or "",
            "template_name": template_reference.get("name") if template_reference else "",
            "template_content": template_reference.get("content") if template_reference else "",
            "template_debug_content": template_reference.get("debug_content") if template_reference else "",
        }
    except Exception as e:
        import traceback
        elapsed = time.monotonic() - started_at
        print(f"[image-steps] fallback: {e}, elapsed={elapsed:.1f}s")
        traceback.print_exc()
        fallback = _image_steps_fallback([item["name"] for item in valid_images], enhanced_prompt)
        return fallback


@router.post("/refine-draft")
async def refine_draft(
    draft_key: str = Form(...),
    template_file: Optional[UploadFile] = File(None),
    prompt: str = Form(""),
    style_guide_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    entry = DRAFT_CACHE.get(draft_key)
    if not entry:
        raise HTTPException(status_code=404, detail="初稿已过期，请重新上传图片生成")

    draft = entry["draft"]
    if not draft.get("steps"):
        raise HTTPException(status_code=400, detail="缓存的初稿为空，请重新上传图片生成")

    style_guide_bundle = _load_style_guide_bundle(db, style_guide_id) if style_guide_id else None
    template_reference = await _load_template_reference(template_file)

    if not style_guide_bundle and not template_reference and not str(prompt or "").strip():
        return {
            "summary": draft["summary"],
            "relation_summary": draft["relation_summary"],
            "steps": draft["steps"],
            "used_style_guide_name": "",
            "model": "kimi-draft",
            "draft_key": draft_key,
            "warning": "",
        }

    from app.utils.ai_client import ai_client

    started_at = time.monotonic()
    refined = ai_client._refine_image_steps_text(
        draft,
        style_guide_bundle=style_guide_bundle,
        template_reference=template_reference,
        user_prompt=prompt,
        timeout=90,
    )

    if refined:
        entry["draft"] = {
            "summary": refined.get("summary") or draft.get("summary"),
            "relation_summary": refined.get("relation_summary") or draft.get("relation_summary"),
            "steps": refined.get("steps") or draft.get("steps"),
        }
        entry["created_at"] = time.time()
        elapsed = time.monotonic() - started_at
        print(f"[refine-draft] success, key={draft_key[:8]}..., model={refined.get('model')}, elapsed={elapsed:.1f}s")
        return {
            "summary": entry["draft"]["summary"],
            "relation_summary": entry["draft"]["relation_summary"],
            "steps": entry["draft"]["steps"],
            "used_style_guide_name": refined.get("used_style_guide_name") or "",
            "model": refined.get("model") or "kimi",
            "draft_key": draft_key,
            "warning": "",
        }

    elapsed = time.monotonic() - started_at
    print(f"[refine-draft] refine failed, returning cached draft, elapsed={elapsed:.1f}s")
    return {
        "summary": draft["summary"],
        "relation_summary": draft["relation_summary"],
        "steps": draft["steps"],
        "used_style_guide_name": "",
        "model": "kimi-draft",
        "draft_key": draft_key,
        "warning": "模板/风格指南改写未返回有效步骤，当前展示读图初稿，可更换模板后重试",
    }
