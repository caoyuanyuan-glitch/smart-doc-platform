import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_VERSION = "2023-06-01"


class AIClient:
    def __init__(self):
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        self.model = os.getenv("QWEN_MODEL", "monkeycode-pro/qwen3.6-plus")
        self.base_url = os.getenv("QWEN_BASE_URL", "https://proxy.monkeycode-ai.com/v1")
        self.http_client = httpx.Client(verify=False, timeout=120)

    def _call_model(self, messages, max_tokens=2048, temperature=0.3):
        system_msg = None
        user_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                user_messages.append(msg)

        body = {
            "model": self.model,
            "messages": user_messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        if system_msg:
            body["system"] = system_msg

        try:
            response = self.http_client.post(
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": ANTHROPIC_VERSION
                },
                json=body
            )

            if response.status_code != 200:
                print(f"模型调用失败 [{response.status_code}]: {response.text[:200]}")
                return None

            data = response.json()

            text_parts = []
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))

            return "".join(text_parts) if text_parts else None

        except Exception as e:
            print(f"模型调用异常: {str(e)}")
            return None

    def call_qwen(self, messages, max_tokens=2048):
        return self._call_model(messages, max_tokens)

    def call_deepseek(self, messages, max_tokens=2048):
        return self._call_model(messages, max_tokens)

    def chat(self, messages, max_tokens=2048, fallback=True):
        result = self._call_model(messages, max_tokens)
        if result is None and fallback:
            result = self._call_model(messages, max_tokens)
        return result

    def audit_document(self, content):
        prompt = f"""
请对以下技术文档进行智能审核，识别潜在问题并提供修改建议：

文档内容：
{content[:5000]}

请按照以下JSON格式输出审核结果：
{{
  "issues": [
    {{
      "severity": "fatal|serious|general|suggestion",
      "category": "分类",
      "rule": "匹配规则",
      "chapter": "章节位置",
      "original_text": "原文片段",
      "context": "上下文",
      "suggestion": "修改建议",
      "description": "问题描述",
      "audit_basis": "审核依据",
      "confidence": 0-100
    }}
  ]
}}

注意：
1. severity分为四级：fatal(致命), serious(严重), general(一般), suggestion(建议)
2. category包括：字词、句子、标点、段落、逻辑、拼写、句式、语法
3. 请尽可能多地发现问题，置信度表示你对该问题的确定程度
"""
        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, max_tokens=4096)

        try:
            return json.loads(result)
        except:
            return {"issues": []}

    def polish_text(self, text):
        prompt = f"""
请对以下文本进行专业润色，优化表达和句式：

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
}}
"""
        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, max_tokens=2048)

        try:
            return json.loads(result)
        except:
            return {"original": text, "polished": text}

    def qa_answer(self, question, context):
        prompt = f"""
基于以下文档内容回答问题：

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
}}
"""
        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, max_tokens=2048)

        try:
            return json.loads(result)
        except:
            return {"answer": "文档中未找到相关信息", "sources": []}

    def generate_content(self, product_name, product_model, doc_type, target_chapter):
        prompt = f"""
请根据以下参数生成技术文档内容：

产品名称：{product_name}
产品型号：{product_model}
文档类型：{doc_type}（中文IVD/中文RUO/英文IVDR/英文RUO+CE）
目标章节：{target_chapter}

要求：
1. 内容必须符合对应文档类型的规范
2. 使用专业术语
3. 结构清晰，逻辑严谨
4. 输出DITA格式或纯文本格式

请直接输出生成的内容。
"""
        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, max_tokens=4096)

        return result or ""

    def general_answer(self, question):
        prompt = f"""
请回答以下问题：

问题：{question}

请按照以下要求回答：
1. 基于你的专业知识给出准确回答
2. 保持回答简洁明了
3. 如果涉及技术文档相关内容，请提供专业建议

请以JSON格式输出：
{{
  "answer": "回答内容",
  "sources": []
}}
"""
        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, max_tokens=2048)

        try:
            return json.loads(result)
        except:
            return {"answer": result or "无法回答该问题", "sources": []}


ai_client = AIClient()
