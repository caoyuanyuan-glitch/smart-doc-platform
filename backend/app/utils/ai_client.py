import os
import re
import json
import httpx
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def _is_valid_key(val):
    return bool(val) and val and "your-" not in val.lower()


class AIClient:
    def __init__(self):
        self.default_provider = os.getenv("DEFAULT_MODEL_PROVIDER", "qwen")
        self.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
        self.qwen_model = os.getenv("QWEN_MODEL", "qwen-max")
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

        self.arkclaw_api_key = os.getenv("ARKCLAW_API_KEY")
        self.arkclaw_base_url = os.getenv("ARKCLAW_BASE_URL", "https://api.arkclaw.com/v1")
        self.arkclaw_model = os.getenv("ARKCLAW_MODEL", "arkclaw-chat")

        timeout = httpx.Timeout(30.0, read=120.0)
        self.qwen_client = OpenAI(
            api_key=self.dashscope_api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=timeout,
        ) if _is_valid_key(self.dashscope_api_key) else None

        self.deepseek_client = OpenAI(
            api_key=self.deepseek_api_key,
            base_url="https://api.deepseek.com/v1",
            timeout=timeout,
        ) if _is_valid_key(self.deepseek_api_key) else None

        self.arkclaw_client = OpenAI(
            api_key=self.arkclaw_api_key,
            base_url=self.arkclaw_base_url,
            timeout=timeout,
        ) if _is_valid_key(self.arkclaw_api_key) else None

    # ------------------------------------------------------------------
    # 基础 chat 接口
    # ------------------------------------------------------------------
    def call_qwen(self, messages, max_tokens=2048, temperature=0.3):
        if not self.qwen_client:
            return None
        try:
            response = self.qwen_client.chat.completions.create(
                model=self.qwen_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Qwen调用失败: {str(e)}")
            return None

    def call_deepseek(self, messages, max_tokens=2048, temperature=0.3):
        if not self.deepseek_client:
            return None
        try:
            response = self.deepseek_client.chat.completions.create(
                model=self.deepseek_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"DeepSeek调用失败: {str(e)}")
            return None

    def call_arkclaw(self, messages, max_tokens=2048, temperature=0.3):
        if not self.arkclaw_client:
            return None
        try:
            response = self.arkclaw_client.chat.completions.create(
                model=self.arkclaw_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"ArkClaw调用失败: {str(e)}")
            return None

    def chat(self, messages, max_tokens=2048, fallback=True, temperature=0.3):
        """
        首选: arkclaw (如果配置了)
        其次: DEFAULT_MODEL_PROVIDER
        最后: 其他可用提供者 fallback
        """
        tried = set()
        # ArkClaw 优先
        if self.arkclaw_client is not None:
            tried.add("arkclaw")
            result = self.call_arkclaw(messages, max_tokens, temperature)
            if result is not None:
                return result

        order = []
        if self.default_provider == "qwen":
            order = [("qwen", self.call_qwen), ("deepseek", self.call_deepseek)]
        elif self.default_provider == "deepseek":
            order = [("deepseek", self.call_deepseek), ("qwen", self.call_qwen)]
        else:
            order = [("qwen", self.call_qwen), ("deepseek", self.call_deepseek)]

        for name, fn in order:
            if name in tried:
                continue
            tried.add(name)
            # 只有配置了 key 才调用 (client 非 None 时)
            result = fn(messages, max_tokens, temperature)
            if result is not None:
                return result
            if not fallback:
                return None
        return None

    # ------------------------------------------------------------------
    # 文档审核: 使用 ArkClaw 为主模型, 输出结构化问题
    # ------------------------------------------------------------------
    def audit_document(self, content, language=None):
        lang_desc = "中文" if language == "cn" else "英文" if language == "en" else "中英文混合"

        prompt = f"""你是一名资深技术文档审核专家。请对以下{lang_desc}技术文档进行严格、精准的审核，只报真正存在的问题。

审核目标：
1) 拼写 / 用词错误 (包括缩写、大小写、术语一致性)
2) 标点符号误用 (中英文标点混放、省略号、引号等)
3) 语法与句式错误 (主谓不一致、时态错误、残缺句)
4) 格式与排版问题 (标题层级、列表、段落缩进等)
5) 事实性 / 逻辑错误 (前后矛盾、数值错误、步骤缺失)

请遵循以下原则（非常重要）：
- 只对确定的错误报警；不要对正常用法（如英文公司名中的 "Ltd."、"Co."、"P.R."、缩写点号）误报。
- 相同 / 相似问题请合并成一条，不要重复列出。
- 每条问题给出简短、具体的修改建议。
- 给出原文片段 original_text 与上下文 context。
- 提供问题所在的章节标题（能定位的章节）。
- 输出严格的 JSON，不要加任何额外解释或 markdown 代码块。

文档内容（最多 5000 字符）：
{content[:5000]}

请严格按以下 JSON 格式输出：
{{
  "issues": [
    {{
      "severity": "fatal|serious|general|suggestion",
      "category": "分类（如：拼写/标点/语法/格式/术语/逻辑）",
      "rule": "规则描述",
      "chapter": "章节标题或位置",
      "original_text": "原文片段",
      "context": "上下文（±50字符）",
      "suggestion": "修改建议",
      "description": "问题描述（一句话）",
      "audit_basis": "审核依据（如：MGI技术文档风格指南/通用语法规则）",
      "confidence": 70
    }}
  ]
}}

再次提醒：
- severity 只能是 fatal/serious/general/suggestion 之一。
- 只报告明确的错误，宁缺毋滥。
- 相同问题合并，不要重复。
- 英文缩写中的点号（如 Ltd., Co., Inc., P.R.）是合法写法，不要误报。
- 纯 JSON 输出，不要 ```json 包裹。"""

        messages = [{"role": "user", "content": prompt}]
        # 审核使用较低温度以保证一致性
        result = self.chat(messages, max_tokens=4096, temperature=0.2)

        try:
            if result and result.strip().startswith("```"):
                # 去除可能的 markdown 代码块包裹
                result = re.sub(r"^```[a-zA-Z]*\n?", "", result.strip())
                result = re.sub(r"\n?```$", "", result.strip())
            return json.loads(result)
        except Exception as e:
            print(f"解析审核结果失败: {e}")
            # 尝试从文本中提取 JSON 对象
            if result:
                m = re.search(r"\{[\s\S]*\}", result)
                if m:
                    try:
                        return json.loads(m.group(0))
                    except Exception:
                        pass
            return {"issues": []}

    # ------------------------------------------------------------------
    # 规则审核的二次验证 (ArkClaw 过滤误报)
    # 输入: [{original_text, context, rule, category, ...}] 候选问题
    # 输出: 过滤后的列表 (仅保留确定为错误的项)
    # ------------------------------------------------------------------
    def filter_rule_false_positives(self, candidate_issues, document_language):
        if not candidate_issues:
            return []

        lang_desc = "中文" if document_language == "cn" else "英文" if document_language == "en" else "中英文混合"

        # 最多送入 50 条进行验证 (降低 token 成本)
        capped = candidate_issues[:50]
        sample_text = "\n".join([
            f"[{idx+1}] 规则: {c.get('rule','')} | 原文: {c.get('original_text','')} | 上下文: {(c.get('context','') or '')[:120]}"
            for idx, c in enumerate(capped)
        ])

        prompt = f"""请作为{lang_desc}技术文档审核专家，判断以下规则匹配出的候选问题是否是真正的错误。

判断原则（非常重要）：
1. 英文公司名 / 专有名词中的点号（如 "Ltd."、"Co."、"Inc."、"P.R."、"U.S.A."）是合法写法，不算错误。
2. 常见缩写（"e.g."、"i.e."、"etc."）合法。
3. 正常的英文句号后空一格不算问题。
4. 只把确定为错误的项标记为 valid=true。
5. 如果原文片段本身不构成问题（只是正则误匹配），标记为 valid=false。

输入候选问题（每条一行，编号从 1 开始）：
{sample_text}

请严格输出 JSON，数组长度必须为 {len(capped)}，每项为 {{"index": 编号, "valid": true|false, "reason": "简短理由"}}。只输出 JSON，不要额外文字。"""

        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, max_tokens=3000, temperature=0.1)
        if not result:
            # 无 AI 可用时，保守返回全部 (由调用方进一步去重)
            return candidate_issues

        try:
            text = result.strip()
            if text.startswith("```"):
                text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            data = json.loads(text)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                data = data["items"]
            valid_indices = set()
            for item in data:
                if isinstance(item, dict) and item.get("valid") is True:
                    valid_indices.add(int(item.get("index", 0)))
        except Exception as e:
            print(f"过滤误报失败: {e}")
            return candidate_issues

        filtered = []
        for idx, issue in enumerate(capped):
            if (idx + 1) in valid_indices:
                filtered.append(issue)
        # 超出 50 条的部分，保留但不去重（后续流程会再按内容合并）
        if len(candidate_issues) > len(capped):
            filtered.extend(candidate_issues[len(capped):])
        return filtered

    # ------------------------------------------------------------------
    # 润色 / 问答 / 生成 保持向后兼容
    # ------------------------------------------------------------------
    def polish_text(self, text):
        prompt = f"""请对以下文本进行专业润色，优化表达和句式：

原文：
{text}

润色要求：
1. 保持原意不变
2. 优化句式结构，使表达更流畅自然
3. 修正语法和用词问题
4. 提升专业性和可读性

请以JSON格式输出：
{{
  "original": "原文",
  "polished": "润色后内容"
}}"""
        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, max_tokens=2048, temperature=0.5)
        try:
            return json.loads(result)
        except Exception:
            return {"original": text, "polished": text}

    def qa_answer(self, question, context):
        prompt = f"""基于以下文档内容回答问题：

文档内容：
{context[:8000]}

问题：{question}

请按照以下要求回答：
1. 回答必须基于提供的文档内容，禁止编造信息
2. 如果文档中没有相关信息，请明确说明"文档中未找到相关信息"
3. 回答请附带引用来源（章节名或段落位置）
4. 保持回答简洁明了

请以JSON格式输出：
{{
  "answer": "回答内容",
  "sources": ["来源1", "来源2"]
}}"""
        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, max_tokens=2048, temperature=0.3)
        try:
            return json.loads(result)
        except Exception:
            return {"answer": "文档中未找到相关信息", "sources": []}

    def generate_content(self, product_name, product_model, doc_type, target_chapter):
        prompt = f"""请根据以下参数生成技术文档内容：

产品名称：{product_name}
产品型号：{product_model}
文档类型：{doc_type}
目标章节：{target_chapter}

要求：
1. 内容必须符合对应文档类型的规范
2. 使用专业术语
3. 结构清晰，逻辑严谨
4. 输出DITA格式或纯文本格式

请直接输出生成的内容。"""
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, max_tokens=4096, temperature=0.6) or ""

    def general_answer(self, question):
        prompt = f"""请回答以下问题：

问题：{question}

请以JSON格式输出：
{{
  "answer": "回答内容",
  "sources": []
}}"""
        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, max_tokens=2048, temperature=0.5)
        try:
            return json.loads(result)
        except Exception:
            return {"answer": result or "无法回答该问题", "sources": []}


ai_client = AIClient()
