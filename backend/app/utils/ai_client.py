import os
import json
import re
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

        # ArkClaw: 大模型审核主引擎
        self.arkclaw_api_key = os.getenv("ARKCLAW_API_KEY")
        self.arkclaw_base_url = os.getenv("ARKCLAW_BASE_URL", "https://api.arkclaw.com/v1")
        self.arkclaw_model = os.getenv("ARKCLAW_MODEL", "arkclaw-chat")

        # 自动识别火山引擎方舟 API Key
        VOLC_ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"
        if _is_valid_key(self.dashscope_api_key) and self.dashscope_api_key.startswith("ark-"):
            self.qwen_client = OpenAI(
                api_key=self.dashscope_api_key,
                base_url=VOLC_ARK_BASE
            )
            print(f"[AI] 火山引擎方舟已连接, base_url={VOLC_ARK_BASE}, model={self.qwen_model}")
        elif _is_valid_key(self.dashscope_api_key):
            self.qwen_client = OpenAI(
                api_key=self.dashscope_api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
        else:
            self.qwen_client = None

        self.deepseek_client = OpenAI(
            api_key=self.deepseek_api_key,
            base_url="https://api.deepseek.com/v1"
        ) if _is_valid_key(self.deepseek_api_key) else None

        self.arkclaw_client = OpenAI(
            api_key=self.arkclaw_api_key,
            base_url=self.arkclaw_base_url,
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
                temperature=temperature
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
                temperature=temperature
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
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"ArkClaw调用失败: {str(e)}")
            return None

    def chat(self, messages, max_tokens=2048, fallback=True, temperature=0.3):
        result = None

        if self.default_provider == "arkclaw":
            result = self.call_arkclaw(messages, max_tokens, temperature)
            if result is None and fallback:
                result = self.call_qwen(messages, max_tokens, temperature)
            if result is None and fallback:
                result = self.call_deepseek(messages, max_tokens, temperature)
        elif self.default_provider == "qwen":
            result = self.call_qwen(messages, max_tokens, temperature)
            if result is None and fallback:
                result = self.call_deepseek(messages, max_tokens, temperature)
            if result is None and fallback:
                result = self.call_arkclaw(messages, max_tokens, temperature)
        else:
            result = self.call_deepseek(messages, max_tokens, temperature)
            if result is None and fallback:
                result = self.call_qwen(messages, max_tokens, temperature)
            if result is None and fallback:
                result = self.call_arkclaw(messages, max_tokens, temperature)

        return result

    # ------------------------------------------------------------------
    # 文档润色
    # ------------------------------------------------------------------
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
        
        try:
            parsed = json.loads(result)
            if isinstance(parsed, dict) and "polished" in parsed:
                return parsed
        except:
            pass
        
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

请以JSON格式输出：
{{
  "answer": "你的回答",
  "source": "引用来源"
}}
"""
        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, max_tokens=2048)
        
        try:
            return json.loads(result)
        except:
            return {"answer": result or "文档中未找到相关信息", "source": ""}

    def generate_document(self, topic, doc_type, template_text="", requirements=""):
        prompt = f"""
根据以下要求生成技术文档：

主题：{topic}
文档类型：{doc_type}

{"参考模板：" + template_text[:3000] if template_text else ""}

{"特殊要求：" + requirements if requirements else ""}

请生成一份专业的技术文档。对于中文技术文档，重点检查：
1. 术语解释 
2. 使用流程

输出格式：JSON
{{
  "title": "文档标题",
  "content": "文档内容（Markdown格式）",
  "sections": ["章节1", "章节2", ...],
  "word_count": 字数
}}
"""
        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, max_tokens=4096)
        
        try:
            return json.loads(result)
        except:
            return {"title": topic, "content": result or "", "sections": [], "word_count": 0}

    def generate_qa_pairs(self, content, count=3):
        prompt = f"""
根据以下文档内容生成{count}个问答对：

文档内容：
{content[:6000]}

要求：
1. 问题应该涵盖文档中的不同方面（概念解释、关键参数、操作步骤等）
2. 答案应该准确、简洁，引用源文相关段落

请以JSON数组格式输出：
[
  {{"question": "问题1", "answer": "答案1", "category": "类别"}},
  {{"question": "问题2", "answer": "答案2", "category": "类别"}}
]
"""
        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, max_tokens=2048)
        
        try:
            return json.loads(result)
        except:
            return []

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
        for idx, issue in enumerate(capped, 1):
            if idx in valid_indices:
                filtered.append(issue)

        # 如果有超过 50 条未处理的，直接保留
        if len(candidate_issues) > len(capped):
            filtered.extend(candidate_issues[len(capped):])

        return filtered

    # ------------------------------------------------------------------
    # 对比分析结果的 AI 二次验证
    # ------------------------------------------------------------------
    def verify_comparison_result(self, diffs, doc_a_lang, doc_b_lang):
        if not diffs:
            return diffs

        lang_a = "中文" if doc_a_lang == "cn" else "英文" if doc_a_lang == "en" else "中英文混合"
        lang_b = "中文" if doc_b_lang == "cn" else "英文" if doc_b_lang == "en" else "中英文混合"

        capped = diffs[:30]
        sample_text = "\n".join([
            f"[{idx+1}] 类型: {d.get('type','')} | 文档A: {d.get('text_a','')[:80]} | 文档B: {d.get('text_b','')[:80]}"
            for idx, d in enumerate(capped)
        ])

        prompt = f"""请作为技术文档对比分析专家，验证以下文档对比结果是否为真实差异。

文档 A 语言: {lang_a}
文档 B 语言: {lang_b}

输入候选差异 (每条一行):
{sample_text}

请严格输出 JSON，数组长度必须为 {len(capped)}，每项为 {{"index": 编号, "valid": true|false, "reason": "简短理由"}}。只输出 JSON，不要额外文字。"""

        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, max_tokens=3000, temperature=0.1)
        if not result:
            return diffs

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
            print(f"对比验证失败: {e}")
            return diffs

        verified = []
        for idx, diff in enumerate(capped, 1):
            if idx in valid_indices:
                verified.append(diff)

        if len(diffs) > len(capped):
            verified.extend(diffs[len(capped):])

        return verified

    # ------------------------------------------------------------------
    # 文档审核
    # ------------------------------------------------------------------
    def review_document(self, content, rules_text="", audit_basis="", document_language="cn"):
        lang_desc = "中文" if document_language == "cn" else "英文" if document_language == "en" else "中英文混合"
        prompt = f"""
请作为{lang_desc}技术文档审核专家，审核以下文档：

文档内容：
{content[:8000]}

{"{'审核规则：' + rules_text[:3000] if rules_text else ''}"}
{"{'审核依据：' + audit_basis[:3000] if audit_basis else ''}"}

请从以下维度进行审核：
1. 内容完整性
2. 术语准确性
3. 格式规范性
4. 逻辑清晰度

请以JSON格式输出：
{{
  "score": 综合评分(0-100),
  "summary": "总体评价",
  "issues": [
    {{
      "severity": "严重程度(error/warning/info)",
      "category": "问题类别",
      "description": "问题描述",
      "location": "问题位置",
      "suggestion": "修改建议"
    }}
  ]
}}
"""
        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, max_tokens=4096)
        
        try:
            return json.loads(result)
        except:
            return {"score": 0, "summary": "审核失败", "issues": []}


ai_client = AIClient()
