"""悬浮 Agent · 意图编排（A 方案）

职责：识别用户一句话想用哪个模块，抽取参数，然后
1) 需要上传文件/长流程的模块（审核、对比、转换）→ 返回 navigate 动作，前端跳转落地页并预填参数；
2) 短文本可直接出结果的模块（润色、生成）→ 复用 ai_client 现有方法直接返回；
3) 通用问答/寒暄 → 用 ai_client.chat 直接作答，并引导到对应模块。

设计约束：
- 不重写任何现有模块逻辑，仅复用 ai_client 与既有前端路由。
- AI 分类不可用时降级到关键词匹配，保证功能不中断。
- 所有端点沿用现有鉴权（get_current_active_user）。
"""

import json
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import get_current_active_user
from app.schemas.user import UserOut
from app.utils.ai_client import ai_client

router = APIRouter()

# 平台模块清单：name/path 与前端 router 保持一致，供分类提示与能力查询复用
AGENT_MODULES: List[Dict[str, Any]] = [
    {
        "key": "review",
        "name": "文档审核",
        "path": "/review",
        "needs_file": True,
        "desc": "上传文档，按规则库匹配问题并生成审核报告",
        "keywords": ["审核", "审报告", "检查文档", "校对", "审一下", "rule review", "review"],
    },
    {
        "key": "polish",
        "name": "智能润色",
        "path": "/polish",
        "needs_file": False,
        "desc": "润色一段文本，给出修改前后对比",
        "keywords": ["润色", "改写", "优化表达", "润色一下", "polish", "rewrite"],
    },
    {
        "key": "qa",
        "name": "智能问答",
        "path": "/qa",
        "needs_file": False,
        "desc": "基于知识库或说明书进行问答",
        "keywords": ["问答", "提问", "问问", "咨询", "知识库", "说明书里", "什么是", "怎么设置", "qa"],
    },
    {
        "key": "generate",
        "name": "内容生成",
        "path": "/generate/image-descriptions",
        "needs_file": False,
        "desc": "按主题和文档类型生成技术文档",
        "keywords": ["生成", "写一篇", "起草", "新建文档", "generate", "draft"],
    },
    {
        "key": "compare",
        "name": "文档对比",
        "path": "/compare",
        "needs_file": True,
        "desc": "对比两份文档，高亮差异",
        "keywords": ["对比", "比较", "差异", "版本区别", "compare", "diff"],
    },
    {
        "key": "convert",
        "name": "格式转换",
        "path": "/convert",
        "needs_file": True,
        "desc": "将文档转换为 DITA / Markdown 等格式",
        "keywords": ["转换", "转成", "格式转换", "dita", "markdown", "convert"],
    },
]

MODULE_BY_KEY = {m["key"]: m for m in AGENT_MODULES}
VALID_KEYS = set(MODULE_BY_KEY.keys()) | {"chat"}

_NAVIGATE_REPLY = {
    "review": "已为你打开「文档审核」。上传文档后即可按规则库生成审核报告。",
    "compare": "已为你打开「文档对比」。选择两份文档即可查看差异高亮。",
    "convert": "已为你打开「格式转换」。选择文档和目标格式即可开始转换。",
    "polish": "已为你打开「智能润色」。可以粘贴文本，也可以直接在这里发给我润色。",
    "qa": "已为你打开「智能问答」。可基于知识库或说明书提问。",
    "generate": "已为你打开「内容生成」。填写主题与文档类型即可生成。",
}

_CAPABILITY_INTRO = (
    "我可以帮你使用平台里的六个模块：文档审核、智能润色、智能问答、内容生成、文档对比、格式转换。\n"
    "你可以直接说「帮我润色这段话：……」「生成一篇测序仪操作指南」，"
    "或者说「审核这份文档」——需要文件的任务我会带你到对应页面。"
)


class AgentChatInput(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = None


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """从模型输出中稳健解析第一个 JSON 对象。"""
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    # 优先整体解析
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # 退而求其次：截取第一个 { ... } 片段
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(cleaned[start:end + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return None


def _keyword_intent(message: str) -> str:
    low = (message or "").lower()
    scores = {key: 0 for key in MODULE_BY_KEY}
    for key, module in MODULE_BY_KEY.items():
        for kw in module["keywords"]:
            if kw.lower() in low:
                scores[key] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "chat"


def _classify(message: str, history: Optional[List[Dict[str, str]]]) -> Dict[str, Any]:
    """用 AI 识别意图并抽取参数；失败时降级到关键词。"""
    module_lines = "\n".join(
        f"- {m['key']}: {m['name']}（{m['desc']}）" for m in AGENT_MODULES
    )
    history_lines = ""
    if history:
        recent = history[-6:]
        history_lines = "\n历史对话（仅用于理解指代）：\n" + "\n".join(
            f"{h.get('role', 'user')}: {h.get('content', '')}" for h in recent
        )
    prompt = f"""你是智能技术文档平台的意图分类器。判断用户这句话想用哪个模块，并抽取参数。

可选模块：
{module_lines}
- chat: 寒暄、平台能力咨询、或不属于以上任何模块

只输出 JSON，不要任何解释文字，格式：
{{"intent": "模块key或chat", "text": "要润色的原文（无则空字符串）", "topic": "要生成的主题（无则空字符串）", "doc_type": "文档类型（无则空字符串）", "question": "用户问题（无则空字符串）"}}
{history_lines}
用户这句话：{message}"""

    fallback_text = message or ""
    fallback = {
        "intent": _keyword_intent(message),
        "text": "",
        "topic": "",
        "doc_type": "",
        "question": fallback_text,
    }

    try:
        raw = ai_client.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=512,
            temperature=0.0,
            request_label="agent.intent",
            timeout=20,
        )
        obj = _extract_json(raw)
        if not obj:
            return fallback
        intent = str(obj.get("intent", "")).strip().lower()
        if intent not in VALID_KEYS:
            return fallback
        return {
            "intent": intent,
            "text": str(obj.get("text") or "").strip(),
            "topic": str(obj.get("topic") or "").strip(),
            "doc_type": str(obj.get("doc_type") or "").strip(),
            "question": str(obj.get("question") or "").strip(),
        }
    except Exception:
        return fallback


def _answer_general(question: str) -> str:
    try:
        return ai_client.chat(
            [
                {"role": "system", "content": f"你是智能技术文档平台的助手，熟悉文档审核、润色、问答、生成、对比、格式转换六类任务。回答简洁、专业、中文。\n{_CAPABILITY_INTRO}"},
                {"role": "user", "content": question},
            ],
            max_tokens=1024,
            request_label="agent.chat",
        ) or "抱歉，我暂时无法回答，请稍后重试。"
    except Exception:
        return "模型服务暂时不可用，你可以直接点击左侧菜单使用对应模块。"


def _suggestions(intent: str) -> List[str]:
    if intent == "chat" or intent not in MODULE_BY_KEY:
        return ["帮我润色一段文本", "生成一篇文档", "审核这份文档"]
    return ["继续", "返回能力说明", "换个模块"]


def _dispatch(intent: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """根据意图分发：返回 reply + 可选 action。"""
    module = MODULE_BY_KEY.get(intent)

    # 需要文件的模块 → 跳转落地页
    if module and module["needs_file"]:
        return {
            "intent": intent,
            "module_name": module["name"],
            "reply": _NAVIGATE_REPLY.get(intent, f"已为你打开「{module['name']}」。"),
            "action": {"type": "navigate", "path": module["path"], "params": {}},
            "suggestions": _suggestions(intent),
        }

    # 润色：有原文则直接出结果
    if intent == "polish":
        text = (params.get("text") or "").strip()
        if text:
            try:
                result = ai_client.polish_text(text, request_label="agent.polish")
                polished = result.get("polished", text) if isinstance(result, dict) else str(result)
                return {
                    "intent": intent,
                    "module_name": "智能润色",
                    "reply": f"润色结果：\n\n{polished}\n\n（完整对比与规则说明请前往「智能润色」页面）",
                    "action": {"type": "navigate", "path": MODULE_BY_KEY["polish"]["path"], "params": {"text": text}},
                    "suggestions": _suggestions(intent),
                }
            except Exception:
                pass
        return {
            "intent": intent,
            "module_name": "智能润色",
            "reply": _NAVIGATE_REPLY["polish"],
            "action": {"type": "navigate", "path": MODULE_BY_KEY["polish"]["path"], "params": {}},
            "suggestions": _suggestions(intent),
        }

    # 生成：有主题则直接出结果
    if intent == "generate":
        topic = (params.get("topic") or "").strip()
        if topic:
            try:
                result = ai_client.generate_document(
                    topic,
                    params.get("doc_type") or "使用说明书",
                )
                content = result.get("content", "") if isinstance(result, dict) else str(result)
                title = result.get("title", topic) if isinstance(result, dict) else topic
                if content:
                    return {
                        "intent": intent,
                        "module_name": "内容生成",
                        "reply": f"已生成《{title}》：\n\n{content[:1500]}\n\n（完整文档请前往「内容生成」页面）",
                        "action": {"type": "navigate", "path": MODULE_BY_KEY["generate"]["path"], "params": {}},
                        "suggestions": _suggestions(intent),
                    }
            except Exception:
                pass
        return {
            "intent": intent,
            "module_name": "内容生成",
            "reply": _NAVIGATE_REPLY["generate"],
            "action": {"type": "navigate", "path": MODULE_BY_KEY["generate"]["path"], "params": {}},
            "suggestions": _suggestions(intent),
        }

    # 问答：直接通用作答 + 引导到知识库问答页
    if intent == "qa":
        question = (params.get("question") or "").strip()
        answer = _answer_general(question) if question else _CAPABILITY_INTRO
        return {
            "intent": intent,
            "module_name": "智能问答",
            "reply": f"{answer}\n\n（以上为通用回答；如需基于知识库的精确问答，请前往「智能问答」页面）",
            "action": {"type": "navigate", "path": MODULE_BY_KEY["qa"]["path"], "params": {"question": question}},
            "suggestions": _suggestions(intent),
        }

    # 寒暄 / 能力咨询
    message = (params.get("question") or "").strip()
    reply = _answer_general(message) if message else _CAPABILITY_INTRO
    return {
        "intent": "chat",
        "module_name": None,
        "reply": reply,
        "action": {"type": "none", "path": None, "params": {}},
        "suggestions": _suggestions("chat"),
    }


@router.get("/capabilities")
async def agent_capabilities(_: UserOut = Depends(get_current_active_user)):
    return {
        "modules": [
            {"key": m["key"], "name": m["name"], "path": m["path"], "desc": m["desc"], "needs_file": m["needs_file"]}
            for m in AGENT_MODULES
        ],
        "intro": _CAPABILITY_INTRO,
    }


@router.post("/chat")
async def agent_chat(body: AgentChatInput, _: UserOut = Depends(get_current_active_user)):
    message = (body.message or "").strip()
    if not message:
        return {
            "intent": "chat",
            "module_name": None,
            "reply": "请输入你想做的事，比如「帮我润色这段话」或「审核文档」。",
            "action": {"type": "none", "path": None, "params": {}},
            "suggestions": _suggestions("chat"),
        }
    classified = _classify(message, body.history)
    intent = classified["intent"]
    return _dispatch(intent, classified)
