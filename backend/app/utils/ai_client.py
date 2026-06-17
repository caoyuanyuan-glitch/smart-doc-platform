import os
import json
import re
import httpx
import time
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

        # Kimi (Moonshot AI) 配置
        self.kimi_api_key = os.getenv("KIMI_API_KEY")
        self.kimi_base_url = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
        self.kimi_model = os.getenv("KIMI_MODEL", "moonshot-v1-8k")

        timeout = httpx.Timeout(30.0, read=180.0)

        VOLC_ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"
        if _is_valid_key(self.dashscope_api_key) and self.dashscope_api_key.startswith("ark-"):
            self.qwen_client = OpenAI(
                api_key=self.dashscope_api_key,
                base_url=VOLC_ARK_BASE,
                timeout=timeout,
            )
            print(f"[AI] 火山引擎方舟已连接, base_url={VOLC_ARK_BASE}, model={self.qwen_model}")
        elif _is_valid_key(self.dashscope_api_key):
            self.qwen_client = OpenAI(
                api_key=self.dashscope_api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                timeout=timeout,
            )
        else:
            self.qwen_client = None

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

    @property
    def has_any_client(self):
        return self.kimi_client is not None or self.arkclaw_client is not None or self.qwen_client is not None or self.deepseek_client is not None

    def get_primary_client(self):
        # Kimi 优先级最高
        if self.kimi_client is not None:
            return self.kimi_client, self.kimi_model
        if self.arkclaw_client is not None:
            return self.arkclaw_client, self.arkclaw_model
        if self.deepseek_client is not None:
            return self.deepseek_client, self.deepseek_model
        if self.qwen_client is not None:
            return self.qwen_client, self.qwen_model
        return None, None

    def chat(self, messages, max_tokens=2048, fallback=True, temperature=0.3):
        client, model = self.get_primary_client()
        if client is None:
            return None
        
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
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
                if "429" in error_str and attempt < max_retries - 1:
                    print(f"[AI] 引擎繁忙 (429), 等待 {retry_delay}s 后重试... (第 {attempt+1}/{max_retries} 次)")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                print(f"[AI] chat 失败: {error_str[:100]}")
                return None

    def audit_document(self, content, language=None):
        lang = language or "en"
        is_english = lang in ("en", "both")

        if is_english:
            system_prompt = "You are an expert technical document reviewer with 15+ years of experience in medical/technical writing, quality assurance, and technical communication in English. You specialize in reviewing product manuals, user guides, and technical specifications for medical devices and scientific instruments. Think of yourself as Microsoft Word's proofreader combined with a technical writing expert."
            user_prompt = f"""Please perform a COMPREHENSIVE proofreading and grammar check of this English technical document, similar to Microsoft Word's spell check and grammar check functionality. Find EVERY issue that a professional proofreader would catch.

DOCUMENT TYPE: User Manual for a medical/technical device
DOCUMENT EXCERPT (first 20000 chars):
{content[:20000]}

THIS REVIEW IS SIMILAR TO MICROSOFT WORD PROOFREADING - IDENTIFY:

1. SPELLING ERRORS (like Word's red underline):
   - Typos and misspelled words
   - Common confusable words: your/you're, their/there/they're, its/it's, affect/effect, etc.
   - Words that should be hyphenated or combined
   - Common misspellings like: "accomodate" (should be "accommodate"), "occured" (should be "occurred"), "seperate" (should be "separate"), "recomend" (should be "recommend"), "untill" (should be "until"), "goverment" (should be "government")

2. GRAMMAR ERRORS (like Word's blue/green underline):
   - Subject-verb disagreement: "The data shows..." vs "The data show..."
   - Wrong tense usage: "yesterday I go" → "yesterday I went"
   - Missing or wrong articles: "a apple" → "an apple"
   - Run-on sentences and sentence fragments
   - Wrong preposition usage: "different than" → "different from"
   - Double negatives: "I don't have nothing" → "I don't have anything"
   - Pronoun reference issues: ambiguous "it", "they", "this"
   - Faulty parallelism: "She likes hiking, to swim, and cycling" → "She likes hiking, swimming, and cycling"

3. PUNCTUATION ERRORS (like Word's blue underline):
   - Missing commas in lists and compound sentences
   - Wrong apostrophe usage: "it's" vs "its"
   - Missing periods, colons, semicolons
   - Quotation mark errors
   - Hyphenation errors

4. WORD CHOICE ISSUES:
   - Commonly confused words: "ensure/insure/assure", "fewer/less", "who/whom"
   - Wrong word form: "I am interesting" → "I am interested"
   - Wordiness and redundancy: "past history" → "history"
   - Unnecessary jargon

5. CAPITALIZATION ERRORS:
   - Improper capitalization of proper nouns
   - All caps usage in running text (except for proper names)
   - Capitalization inconsistencies

6. STYLE ISSUES:
   - Inconsistent terminology (using different words for the same thing)
   - Inconsistent formatting (mixing American/British English)
   - Passive voice overuse (when active would be clearer)

SPECIFIC COMMON ERRORS TO LOOK FOR:
- "alot" (not a word) → "a lot"
- "alright" (nonstandard) → "all right"
- "could care less" (illogical) → "couldn't care less"
- "for all intensive purposes" → "for all intents and purposes"
- "should of", "would of", "could of" (wrong) → "should have", "would have", "could have"
- "they" used for singular indefinite pronoun → "he or she", "they" (acceptable modern usage)
- "more then" (wrong) → "more than"
- contractions in formal technical writing (optional, check style guide)

VALID USAGE (DO NOT REPORT AS ERRORS):
- Company names: "MGI Tech Co., Ltd.", "BGI Genomics"
- Legal terms: "P.R.China", "etc." in lists
- Standard abbreviations: "e.g.", "i.e.", "vs.", "approx."
- Technical acronyms that are defined: "PCR", "ELISA", "DNA" after first definition

OUTPUT STRICT VALID JSON ONLY, NO extra text, NO markdown code blocks:
{{
  "issues": [
    {{
      "severity": "general|serious|suggestion",
      "category": "Spelling|Grammar|Punctuation|Word Choice|Capitalization|Style",
      "rule": "Brief rule name",
      "chapter": "Section/Chapter location",
      "original_text": "Exact problematic text",
      "context": "1-2 sentences of surrounding context",
      "suggestion": "Specific correction",
      "description": "Why this is an issue",
      "audit_basis": "English grammar/writing standard",
      "confidence": 85
    }}
  ]
}}

IMPORTANT:
- Be THOROUGH. A 20000 character document should have 10-30+ issues.
- Report specific corrections, not vague suggestions.
- If you find words like "accomodate", "occured", "seperate", "alot" - these ARE errors.
- Look carefully at contractions - ensure/insure/assure confusion - these are REAL errors to catch."""
        else:
            system_prompt = "你是一位拥有15年以上经验的资深技术文档审核专家，擅长审核中文技术文档、产品说明书和操作手册的质量。"
            user_prompt = f"""请审核以下中文技术文档（节选），识别所有影响文档质量的真实问题。

文档类型：医疗/技术设备用户手册
文档内容（前20000字）：
{content[:20000]}

请识别以下类别的问题：
1. 语法与句子结构 - 句子不完整、主谓不一致、时态混乱、表达生硬
2. 标点符号与格式 - 标点错误、中英文标点混用、格式不一致、空格问题
3. 用词与术语 - 错别字、用词错误、专业术语不规范、术语前后不一致
4. 技术准确性 - 技术信息缺失或错误、内容矛盾、表述不清
5. 风格一致性 - 大小写不一致、术语不统一、违反写作规范、语气不恰当
6. 结构与组织 - 章节缺失、逻辑不清晰、标题层级错误、引用问题
7. 专业性 - 口语化表达、网络用语、语气不适合技术文档

审核原则：
- 只报告确定的、具体的问题。不要猜测或不确定的内容。
- 每个问题必须包含：原文片段、上下文、具体修改建议。
- 相同/相似问题合并为一条。

请严格输出有效的JSON，不要额外文字，不要markdown代码块。

一份良好的技术文档在20000字中通常应该能识别5-20个真实问题。请至少报告你确实发现的问题。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        result = self.chat(messages, max_tokens=4096, temperature=0.2)
        if not result:
            return {"issues": []}

        try:
            text = result.strip()
            if text.startswith("```"):
                text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            return json.loads(text)
        except Exception as e:
            print(f"[AI] 解析审核结果失败: {e}")
            try:
                m = re.search(r"\{[\s\S]*\}", result)
                if m:
                    return json.loads(m.group(0))
            except Exception:
                pass
            return {"issues": []}

    def filter_rule_false_positives(self, candidate_issues, document_language):
        if not candidate_issues:
            return []

        is_english = document_language in ("en", "both")
        capped = candidate_issues[:50]

        if is_english:
            sample_text = "\n".join([
                f"[{idx+1}] Rule: {c.get('rule','')} | Text: {c.get('original_text','')} | Context: {(c.get('context','') or '')[:100]}"
                for idx, c in enumerate(capped)
            ])

            prompt = f"""You are reviewing potential issues found by regex rules in an English technical document. For each candidate issue below, determine if it is a TRUE problem (valid issue) or FALSE positive (not actually a problem in this context).

CANDIDATE ISSUES (numbered 1 to {len(capped)}):
{sample_text}

IMPORTANT RULES FOR VALIDATION:
- Company names like "MGI Tech Co., Ltd." are CORRECT - do NOT flag as issue
- Legal/geographic terms like "P.R.China" or "Wuhan" are CORRECT
- Normal English punctuation at the end of sentences is CORRECT
- Standard technical abbreviations (e.g., i.e., etc.) are CORRECT
- Only flag items where the text truly violates English technical writing conventions

OUTPUT: Strict JSON only:
{{
  "valid_indices": [list of indices that are TRUE issues, e.g., [1, 5, 12]]
}}

If NO items are valid issues, return: {{"valid_indices": []}}"""
        else:
            sample_text = "\n".join([
                f"[{idx+1}] 规则: {c.get('rule','')} | 原文: {c.get('original_text','')} | 上下文: {(c.get('context','') or '')[:100]}"
                for idx, c in enumerate(capped)
            ])
            prompt = f"""请判断以下在中文技术文档中由正则规则匹配出的候选问题，哪些是真正的问题（valid=true），哪些是误报（valid=false）。

候选问题列表（编号1-{len(capped)}）：
{sample_text}

重要判断原则：
- 英文公司名称如 "MGI Tech Co., Ltd." 中的标点是正确用法，不要误报
- 正常的中英文混排专有名词通常是正确的
- 只有真正违反中文技术文档写作规范的才标记为问题

请严格输出JSON格式：
{{
  "valid_indices": [真正是问题的编号，如 [1, 5, 12]]
}}

如果没有有效问题，返回: {{"valid_indices": []}}"""

        messages = [{"role": "user", "content": prompt}]
        result = self.chat(messages, max_tokens=2000, temperature=0.1)
        if not result:
            return candidate_issues

        try:
            text = result.strip()
            if text.startswith("```"):
                text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            data = json.loads(text)
            valid_indices = set(int(x) for x in data.get("valid_indices", []))
        except Exception as e:
            print(f"[AI] 过滤误报失败: {e}")
            return candidate_issues

        filtered = []
        for idx, issue in enumerate(capped):
            if (idx + 1) in valid_indices:
                filtered.append(issue)

        if len(candidate_issues) > len(capped):
            filtered.extend(candidate_issues[len(capped):])
        return filtered


ai_client = AIClient()
