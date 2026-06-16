import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

class AIClient:
    def __init__(self):
        self.default_provider = os.getenv("DEFAULT_MODEL_PROVIDER", "qwen")
        self.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
        self.qwen_model = os.getenv("QWEN_MODEL", "qwen-max")
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        
        # 自动识别火山引擎方舟 API Key
        VOLC_ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"
        if self.dashscope_api_key and self.dashscope_api_key.startswith("ark-"):
            self.qwen_client = OpenAI(
                api_key=self.dashscope_api_key,
                base_url=VOLC_ARK_BASE
            )
            print(f"[AI] 火山引擎方舟已连接, base_url={VOLC_ARK_BASE}, model={self.qwen_model}")
        elif self.dashscope_api_key:
            self.qwen_client = OpenAI(
                api_key=self.dashscope_api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
        else:
            self.qwen_client = None
        
        self.deepseek_client = OpenAI(
            api_key=self.deepseek_api_key,
            base_url="https://api.deepseek.com/v1"
        ) if self.deepseek_api_key else None

    def call_qwen(self, messages, max_tokens=2048):
        if not self.qwen_client:
            return None
        try:
            response = self.qwen_client.chat.completions.create(
                model=self.qwen_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Qwen调用失败: {str(e)}")
            return None

    def call_deepseek(self, messages, max_tokens=2048):
        if not self.deepseek_client:
            return None
        try:
            response = self.deepseek_client.chat.completions.create(
                model=self.deepseek_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"DeepSeek调用失败: {str(e)}")
            return None

    def chat(self, messages, max_tokens=2048, fallback=True):
        result = None
        
        if self.default_provider == "qwen":
            result = self.call_qwen(messages, max_tokens)
            if result is None and fallback:
                result = self.call_deepseek(messages, max_tokens)
        else:
            result = self.call_deepseek(messages, max_tokens)
            if result is None and fallback:
                result = self.call_qwen(messages, max_tokens)
        
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

    def polish_text(self, text, style_guide=None):
        system = """你是一位资深的技术文档编辑，负责对中国政府/企业公文和技术文档进行专业润色。
你需要同时做到以下五点：
1. 修正语法错误、错别字、标点不当
2. 删除空洞套话（如"众所周知""不言而喻"），换成具体事实
3. 将口语化表达转为正式书面语（如"搞""弄""做"等动词替换为精确动词）
4. 拆分超过80字的超长句，合并相邻的破碎短句
5. 保持原意不变，不添加原文没有的信息

严禁事项：
- 不要改变数据、日期、人名、地名
- 不要替换专业术语（除非明显错误）
- 不要添加任何解释性内容"""

        user_prompt = f"请润色以下文本：\n\n{text}"
        
        if style_guide:
            user_prompt = f"请根据以下风格指南润色文本：\n{style_guide}\n\n待润色内容：\n{text}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt}
        ]
        result = self.chat(messages, max_tokens=4096)
        
        if not result:
            return {"original": text, "polished": text}
        
        # 尝试解析 JSON，失败则直接使用返回文本
        try:
            parsed = json.loads(result)
            if isinstance(parsed, dict) and "polished" in parsed:
                return parsed
        except:
            pass
        
        # 如果不是 JSON，直接作为润色结果
        return {"original": text, "polished": result.strip()}

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
