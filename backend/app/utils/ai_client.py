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

        # 自动识别火山引擎方舟 API Key
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
        # 优先级: Kimi > ArkClaw > DeepSeek > Qwen
        providers = []
        if self.kimi_client:
            providers.append(('Kimi', self.kimi_client, self.kimi_model))
        if self.arkclaw_client:
            providers.append(('ArkClaw', self.arkclaw_client, self.arkclaw_model))
        if self.deepseek_client:
            providers.append(('DeepSeek', self.deepseek_client, self.deepseek_model))
        if self.qwen_client:
            providers.append(('Qwen', self.qwen_client, self.qwen_model))

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

    # ------------------------------------------------------------------
    # 文档润色
    # ------------------------------------------------------------------
    @staticmethod
    def _strip_examples_from_guide(guide_text):
        """剔除句式清单表格中的"示例"列，仅保留"句式模板"列。
        
        句式清单格式：
        |序号|句式模板|示例|
        |1|操作步骤如下：|"操作步骤如下："|
        
        处理后：
        |序号|句式模板|
        |1|操作步骤如下：|
        """
        lines = guide_text.split('\n')
        result = []
        for line in lines:
            s = line.strip()
            if s.startswith('|') and s.endswith('|'):
                parts = s.split('|')
                # parts: ['', 'col1', 'col2', 'col3', ...]
                if len(parts) >= 4:
                    # 仅保留前两列（序号 + 句式模板）
                    result.append('|' + parts[1] + '|' + parts[2] + '|')
                    continue
            result.append(line)
        return '\n'.join(result)

    def polish_text(self, text, style_guide=None, terminology=None):
        system = """你是一位严格的中文技术文档校对员。将待审核文本逐句与句式清单比对并改写。

句式清单每行含三列：序号 | 句式模板 | 示例。
- 句式模板定义句式骨架（如"将...拨至【...】位置"）
- 示例展示该模板在真实文档中的用法，供你理解语境

处理步骤：
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
            # 构建术语替换指令
            term_lines = []
            for non_std, std in terminology.items():
                if non_std and std and non_std != std:
                    term_lines.append(f'  - \"{non_std}\" 必须替换为 \"{std}\"')
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

    # ------------------------------------------------------------------
    # 规则审核的二次验证 (ArkClaw 过滤误报)
    # 输入: [{original_text, context, rule, category, ...}] 候选问题
    # 输出: 过滤后的列表 (仅保留确定为错误的项)
    # ------------------------------------------------------------------
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
