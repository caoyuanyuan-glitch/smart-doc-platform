import os
import json
import re
import httpx
import time
from openai import OpenAI
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# 完整审核规则（从review_rules模块导入）
from app.api.review_rules import (
    build_system_prompt,
    get_all_rules,
    ENGLISH_CORRECT_SPELLINGS,
    BRITISH_AMERICAN_SPELLINGS
)

ANTHROPIC_VERSION = "2023-06-01"


def _is_valid_key(val):
    return bool(val) and val and "your-" not in val.lower()


def _strip_code_fence(text):
    if not text:
        return ""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


class AIClient:
    def __init__(self):
        self.default_provider = os.getenv("DEFAULT_MODEL_PROVIDER", "kimi")
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

        self.arkclaw_api_key = os.getenv("ARKCLAW_API_KEY")
        self.arkclaw_base_url = os.getenv("ARKCLAW_BASE_URL", "https://api.arkclaw.com/v1")
        self.arkclaw_model = os.getenv("ARKCLAW_MODEL", "arkclaw-chat")

        # Kimi (Moonshot AI) 配置
        self.kimi_api_key = os.getenv("KIMI_API_KEY")
        self.kimi_base_url = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
        self.kimi_model = os.getenv("KIMI_MODEL", "moonshot-v1-8k")

        timeout = httpx.Timeout(30.0, read=180.0)

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

        # Kimi 客户端初始化
        self.kimi_client = OpenAI(
            api_key=self.kimi_api_key,
            base_url=self.kimi_base_url,
            timeout=timeout,
        ) if _is_valid_key(self.kimi_api_key) else None
        if self.kimi_client:
            print(f"[AI] Kimi (Moonshot) 已连接, base_url={self.kimi_base_url}, model={self.kimi_model}")

        # Proxy 回退客户端（使用 OpenAI 兼容接口）
        self.proxy_client = OpenAI(
            api_key=self.dashscope_api_key or os.getenv("OPENAI_API_KEY"),
            base_url=self.anthropic_base_url,
            timeout=timeout,
        )
        if self.proxy_client:
            print(f"[AI] Proxy 回退已配置, base_url={self.anthropic_base_url}, model={self.anthropic_model}")

    @property
    def has_any_client(self):
        return self.kimi_client is not None or self.arkclaw_client is not None or self.deepseek_client is not None

    # ------------------------------------------------------------------
    # 基础 chat 接口
    # ------------------------------------------------------------------
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

    def call_kimi(self, messages, max_tokens=2048, temperature=0.3):
        if not self.kimi_client:
            return None
        try:
            response = self.kimi_client.chat.completions.create(
                model=self.kimi_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Kimi调用失败: {str(e)}")
            return None

    def chat(self, messages, max_tokens=2048, fallback=True, temperature=0.3):
        # 优先级: Kimi > DeepSeek > ArkClaw
        providers = []
        if self.kimi_client:
            providers.append(('Kimi', self.kimi_client, self.kimi_model))
        if self.deepseek_client:
            providers.append(('DeepSeek', self.deepseek_client, self.deepseek_model))
        if self.arkclaw_client:
            providers.append(('ArkClaw', self.arkclaw_client, self.arkclaw_model))

        if not providers:
            return None

        max_retries = 3
        retry_delay = 2

        for name, client, model in providers:
            for attempt in range(1, max_retries + 1):
                try:
                    response = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    return response.choices[0].message.content
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str and attempt < max_retries:
                        print(f"[AI] {name} 引擎繁忙 (429), 等待 {retry_delay}s 后重试... (第 {attempt}/{max_retries} 次)")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    print(f"[AI] {name} 调用失败: {error_str[:100]}")
                    break  # 非 429 或重试耗尽，切换下一个 provider

            # 当前 provider 全部失败，尝试下一个
            if not fallback:
                return None

        return None

    @staticmethod
    def _extract_json(result, default):
        if not result:
            return default
        try:
            return json.loads(_strip_code_fence(result))
        except Exception:
            try:
                m = re.search(r"\{[\s\S]*\}", result)
                if m:
                    return json.loads(m.group(0))
            except Exception:
                pass
        return default

    @staticmethod
    def _normalize_confidence(value, default=0):
        try:
            confidence = float(value)
            if confidence <= 1:
                confidence *= 100
            confidence = int(round(confidence))
        except Exception:
            confidence = default
        return max(0, min(100, confidence))

    @staticmethod
    def _normalize_severity(value, confidence=0):
        text = str(value or "").strip().lower()
        mapping = {
            "fatal": "fatal",
            "serious": "serious",
            "general": "general",
            "suggestion": "suggestion",
            "error": "serious",
            "warning": "general",
            "info": "suggestion",
        }
        severity = mapping.get(text, "general")
        if confidence < 70 and severity != "suggestion":
            return "suggestion"
        return severity

    @staticmethod
    def _clean_text(value, limit=500):
        text = str(value or "").strip()
        text = re.sub(r"\s+", " ", text)
        return text[:limit]

    def normalize_audit_issues(self, issues, content, source="ai", min_confidence=70):
        normalized = []
        if not isinstance(issues, list):
            return normalized

        # 去重：记录已报告的错误内容
        reported_errors = set()

        for item in issues:
            if not isinstance(item, dict):
                continue

            original_text = self._clean_text(item.get("original_text") or item.get("original"), 200)
            context = self._clean_text(item.get("context"), 500)
            suggestion = self._clean_text(item.get("suggestion") or item.get("expected"), 300)
            description = self._clean_text(item.get("description") or item.get("rule_description"), 300)
            chapter = self._clean_text(item.get("chapter") or item.get("section") or item.get("location"), 120)
            category = self._clean_text(item.get("category") or item.get("type"), 80) or "其他"
            rule = self._clean_text(item.get("rule") or item.get("rule_id"), 80) or ("AI" if source == "ai" else "")
            audit_basis = self._clean_text(item.get("audit_basis") or item.get("basis"), 200)
            confidence = self._normalize_confidence(item.get("confidence"), 0)
            severity = self._normalize_severity(item.get("severity"), confidence)

            if confidence < min_confidence:
                continue
            if not description and not suggestion:
                continue
            if len(description) < 4 and len(suggestion) < 2:
                continue

            # 去重逻辑：同一错误内容在同一文档中只报告第一次
            error_key = original_text.lower().strip()
            if error_key in reported_errors:
                continue
            if error_key:
                reported_errors.add(error_key)

            if original_text:
                if len(original_text) == 1 and not re.search(r"[\u4e00-\u9fffA-Za-z]", original_text):
                    continue
                if content and original_text not in content and context and original_text not in context:
                    continue
            elif source == "ai":
                continue

            if context and len(context) < len(original_text) and original_text:
                context = original_text

            normalized.append({
                "severity": severity,
                "category": category,
                "rule": rule,
                "chapter": chapter,
                "original_text": original_text,
                "context": context,
                "suggestion": suggestion,
                "description": description,
                "audit_basis": audit_basis,
                "confidence": confidence,
                "source": source,
                "position": self._clean_text(item.get("position"), 80),
            })

        return normalized

    # ------------------------------------------------------------------
    # 文档润色
    # ------------------------------------------------------------------
    @staticmethod
    def _strip_examples_from_guide(guide_text):
        """剔除句式清单表格中的"示例"列，仅保留"句式模板"列。"""
        lines = guide_text.split('\n')
        result = []
        for line in lines:
            s = line.strip()
            if s.startswith('|') and s.endswith('|'):
                parts = s.split('|')
                if len(parts) >= 4:
                    result.append('|' + parts[1] + '|' + parts[2] + '|')
                    continue
            result.append(line)
        return '\n'.join(result)

    def polish_text(self, text, style_guide=None, terminology=None):
        system = """你是一位严格的中文技术文档校对员。按以下优先级逐句处理待审核文本：

处理优先级（从高到低）：
1. 句式匹配：将每句与句式清单逐句比对并改写，优先匹配句式模板
2. 术语替换：将非标准术语替换为标准术语（术语库强制规则）
3. 风格规范：按写作风格指南中的禁用词、标点、格式规范修正
4. 其他规则：被动语态、双重否定、句子长度等微调

句式清单每行含三列：序号 | 句式模板 | 示例。
- 句式模板定义句式骨架（如"将...拨至【...】位置"）
- 示例展示该模板在真实文档中的用法，供你理解语境

句式匹配规则：
1. 对原句中每个"..."位置，确认原句自己提供了什么词，就用什么词
2. 对原句中模板外的部分（如操作对象、参数），完全保留原句自己的内容
3. 示例仅用于学习句式和动词选择，不得用于填充原句缺失的内容

强制规则：
- 原句写的是"开关"，输出必须是"开关"，不得改成示例里的"电源按钮"
- 原句写的是"开"，输出必须是"开"，不得改成示例里的"ON"
- 原句写的是"制备卡"，输出必须是"制备卡"，不得改成示例里的"样本制备卡"
- 原句没有提到的设备名、试剂名、步骤名，一律不得添加

输出：直接输出改写后的完整文本，无需解释。"""

        if terminology:
            term_lines = []
            for non_std, std in terminology.items():
                if non_std and std and non_std != std:
                    term_lines.append(f'  - "{non_std}" 必须替换为 "{std}"')
            if term_lines:
                term_section = "\n术语库强制替换规则（最高优先级）：\n" + "\n".join(term_lines) + "\n"
                system += term_section

        user_prompt = f"请润色以下文本：\n\n{text}"

        if style_guide:
            user_prompt = f"""句式清单如下。请严格逐句改写待审核文本。

关键：句式学模板，内容留原文。示例只能帮你理解模板怎么用，不能用来替换原文中的词。

===== 句式清单开始 =====
{style_guide}
===== 句式清单结束 =====

===== 待审核文本开始 =====
{text}
===== 待审核文本结束 =====

逐句改写，每句保留原文的具体名称和参数。"""

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
    # 文档审核 (AI 驱动的拼写/语法/风格检查)
    # ------------------------------------------------------------------
    def audit_document(self, content, language=None):
        lang = language or "en"
        is_english = lang in ("en", "both")

        # 使用完整的System Prompt模板（包含所有审核规则）
        base_system_prompt = build_system_prompt()

        if is_english:
            system_prompt = f"""You are a senior reviewer for regulated English technical documents in medical devices, IVD, and research instruments.

{base_system_prompt}

IMPORTANT REMINDERS:
- Report only issues with EXPLICIT textual evidence from the document.
- The following are VALID English words (do NOT flag as spelling errors):
  {', '.join(ENGLISH_CORRECT_SPELLINGS[:50])}...
- British/American spellings: {', '.join(f'{k}→{v}' for k, v in list(BRITISH_AMERICAN_SPELLINGS.items())[:5])}...
- Product names, company names, model numbers, and technical abbreviations are VALID unless context proves an error."""

            user_prompt = f"""Please review the following English technical document.

Document excerpt:
{content[:20000]}

Output ONLY strict JSON:
{{
  "issues": [
    {{
      "severity": "serious|general|suggestion",
      "type": "Spelling|Grammar|Punctuation|Terminology|Units|Compliance|Format",
      "location": "section or line",
      "original": "exact text from excerpt",
      "expected": "correct form",
      "rule": "which rule is violated"
    }}
  ],
  "summary": {{
    "total": number,
    "serious": number,
    "general": number,
    "suggestion": number
  }}
}}

Return empty issues array if no high-confidence issues found."""
        else:
            system_prompt = f"""{base_system_prompt}

重要提醒：
- 只报告有明确文本证据的问题。
- 产品名、公司名、型号、技术缩写词，除非上下文明确显示错误，默认视为正确。
- 对于结构完整性、法规完整性问题，只有当前节选里存在直接证据时才报告。"""

            user_prompt = f"""请审核下面这段中文技术文档。

文档内容：
{content[:20000]}

输出要求：
1. 按JSON格式输出审核结果
2. 只报告有明确文本证据的真实问题
3. 不要报告可选的风格偏好问题
4. 去重：同一错误在同一文档中只报告第一次出现

输出严格JSON：
{{
  "issues": [
    {{
      "type": "拼写|语法|标点|术语|单位|合规|格式",
      "severity": "serious|general|suggestion",
      "location": "章节名或行号",
      "original": "原文内容",
      "expected": "正确写法",
      "rule": "违反的具体规则"
    }}
  ],
  "summary": {{
    "total": 数量,
    "serious": 严重数量,
    "general": 一般数量,
    "suggestion": 建议数量
  }}
}}

如果没有高置信度问题，返回空数组。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        result = self.chat(messages, max_tokens=4096, temperature=0.2)
        if not result:
            return {"issues": []}

        data = self._extract_json(result, {"issues": []})
        issues = self.normalize_audit_issues(data.get("issues", []), content, source="ai", min_confidence=75)
        return {"issues": issues}

    # ------------------------------------------------------------------
    # 规则审核的二次验证 (ArkClaw 过滤误报)
    # ------------------------------------------------------------------
    def filter_rule_false_positives(self, candidate_issues, document_language):
        if not candidate_issues:
            return []

        is_english = document_language in ("en", "both")
        filtered = []
        chunk_size = 20

        for start in range(0, len(candidate_issues), chunk_size):
            chunk = candidate_issues[start:start + chunk_size]
            if is_english:
                sample_text = "\n".join([
                    f"[{idx+1}] Rule: {c.get('rule','')} | Category: {c.get('category','')} | Text: {c.get('original_text','')} | Context: {(c.get('context','') or '')[:160]}"
                    for idx, c in enumerate(chunk)
                ])

                prompt = f"""You are validating candidate issues found by rules in an English regulated technical document.

Candidate issues:
{sample_text}

Validation principles:
- Keep only clear, text-supported violations.
- Treat company names, product names, model names, technical abbreviations, addresses, URLs, email addresses, and legal names as valid unless the context proves an error.
- If context is insufficient, mark invalid.
- If the item is only a style preference or uncertain inference, mark invalid.

Return strict JSON only:
{{
  "items": [
    {{"index": 1, "valid": true, "confidence": 92, "reason": "short reason"}}
  ]
}}

Only keep items with clear evidence."""
            else:
                sample_text = "\n".join([
                    f"[{idx+1}] 规则: {c.get('rule','')} | 分类: {c.get('category','')} | 原文: {c.get('original_text','')} | 上下文: {(c.get('context','') or '')[:160]}"
                    for idx, c in enumerate(chunk)
                ])
                prompt = f"""请验证以下规则命中的候选问题，判断哪些是真实问题。

候选问题：
{sample_text}

判断原则：
- 只保留有明确文本证据的问题。
- 公司名、产品名、型号、地址、网址、邮箱、专有术语、中英混排专有名词默认视为正确，除非上下文明确显示错误。
- 证据不足、依赖更多上下文、属于可选风格偏好的项，判定为无效。

请严格输出 JSON：
{{
  "items": [
    {{"index": 1, "valid": true, "confidence": 92, "reason": "简短理由"}}
  ]
}}

只有确定为真实问题的项才返回 valid=true。"""

            messages = [{"role": "user", "content": prompt}]
            result = self.chat(messages, max_tokens=2500, temperature=0.1)
            if not result:
                filtered.extend(chunk)
                continue

            data = self._extract_json(result, {"items": []})
            items = data.get("items", []) if isinstance(data, dict) else []
            try:
                valid_map = {
                    int(item.get("index", 0)): self._normalize_confidence(item.get("confidence"), 0)
                    for item in items
                    if isinstance(item, dict) and item.get("valid") is True
                }
            except Exception as e:
                print(f"[AI] 过滤误报失败: {e}")
                filtered.extend(chunk)
                continue

            for idx, issue in enumerate(chunk, 1):
                confidence = valid_map.get(idx, 0)
                if confidence >= 75:
                    issue["confidence"] = max(self._normalize_confidence(issue.get("confidence"), 0), confidence)
                    filtered.append(issue)

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
