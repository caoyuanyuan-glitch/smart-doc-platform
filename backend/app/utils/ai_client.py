import os
import json
import re
import base64
import mimetypes
import httpx
import time
from concurrent.futures import ThreadPoolExecutor, wait
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
IMAGE_DRAFT_BATCH_SIZE = 2
IMAGE_DRAFT_MAX_WORKERS = 6
IMAGE_DRAFT_TOTAL_TIMEOUT = 95


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

        self.proxy_api_key = os.getenv("OPENAI_API_KEY")
        self.proxy_base_url = os.getenv("OPENAI_BASE_URL")
        self.proxy_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        self.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
        self.fallback_base_url = self.proxy_base_url or os.getenv("ANTHROPIC_BASE_URL")
        self.fallback_model = self.proxy_model or os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")

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
        mcai_base_url = os.getenv("MCAI_LLM_BASE_URL")
        mcai_api_key = os.getenv("MCAI_LLM_API_KEY")
        mcai_model = os.getenv("MCAI_MODEL_PROVIDER_TYPE", "anthropic")

        self.mcai_proxy_client = None
        if mcai_base_url and _is_valid_key(mcai_api_key):
            self.mcai_proxy_client = OpenAI(
                api_key=mcai_api_key,
                base_url=mcai_base_url,
                timeout=timeout,
            )
            print(f"[AI] MCAI Proxy 已连接, base_url={mcai_base_url}, model={mcai_model}")

        proxy_api_key = self.dashscope_api_key or self.proxy_api_key
        proxy_base_url = self.fallback_base_url
        self.proxy_client = OpenAI(
            api_key=proxy_api_key,
            base_url=proxy_base_url,
            timeout=timeout,
        ) if _is_valid_key(proxy_api_key) and proxy_base_url else None
        if self.proxy_client:
            print(f"[AI] Proxy 回退已配置, base_url={proxy_base_url}, model={self.fallback_model}")

    @property
    def has_any_client(self):
        return self.kimi_client is not None or self.arkclaw_client is not None or self.deepseek_client is not None or self.mcai_proxy_client is not None or self.proxy_client is not None

    def available_providers(self):
        providers = []
        if self.kimi_client:
            providers.append("kimi")
        if self.deepseek_client:
            providers.append("deepseek")
        if self.arkclaw_client:
            providers.append("arkclaw")
        if self.mcai_proxy_client:
            providers.append("mcai")
        if self.proxy_client:
            providers.append("proxy")
        return providers

    def provider_status(self):
        return {
            "default_provider": (self.default_provider or "kimi").strip().lower() or "kimi",
            "priority": ["kimi", "deepseek", "arkclaw", "mcai", "proxy"],
            "providers": {
                "kimi": self.kimi_client is not None,
                "deepseek": self.deepseek_client is not None,
                "arkclaw": self.arkclaw_client is not None,
                "mcai": self.mcai_proxy_client is not None,
                "proxy": self.proxy_client is not None,
            },
            "available": self.available_providers(),
        }

    def resolve_translation_model(self, requested_model=None):
        preferred = []
        requested = (requested_model or "").strip().lower()
        if requested in {"kimi", "deepseek", "arkclaw"}:
            preferred.append(requested)

        default_provider = (self.default_provider or "").strip().lower()
        if default_provider in {"kimi", "deepseek", "arkclaw"} and default_provider not in preferred:
            preferred.append(default_provider)

        for name in ["kimi", "deepseek", "arkclaw"]:
            if name not in preferred:
                preferred.append(name)

        availability = {
            "kimi": self.kimi_client is not None,
            "deepseek": self.deepseek_client is not None,
            "arkclaw": self.arkclaw_client is not None,
        }
        for name in preferred:
            if availability.get(name):
                return name
        return None

    # ------------------------------------------------------------------
    # 基础 chat 接口
    # ------------------------------------------------------------------
    def call_deepseek(self, messages, max_tokens=2048, temperature=0.3):
        if not self.deepseek_client:
            return None
        import time
        max_retries = 3
        retry_delay = 2
        for attempt in range(1, max_retries + 1):
            try:
                response = self.deepseek_client.chat.completions.create(
                    model=self.deepseek_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                return response.choices[0].message.content
            except Exception as e:
                error_str = str(e)
                if "429" in error_str and attempt < max_retries:
                    print(f"DeepSeek 引擎繁忙 (429), 等待 {retry_delay}s 后重试... (第 {attempt}/{max_retries} 次)")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                print(f"DeepSeek调用失败: {str(e)}")
                return None
        return None

    def call_arkclaw(self, messages, max_tokens=2048, temperature=0.3):
        if not self.arkclaw_client:
            return None
        import time
        max_retries = 3
        retry_delay = 2
        for attempt in range(1, max_retries + 1):
            try:
                response = self.arkclaw_client.chat.completions.create(
                    model=self.arkclaw_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                return response.choices[0].message.content
            except Exception as e:
                error_str = str(e)
                if "429" in error_str and attempt < max_retries:
                    print(f"ArkClaw 引擎繁忙 (429), 等待 {retry_delay}s 后重试... (第 {attempt}/{max_retries} 次)")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                print(f"ArkClaw调用失败: {str(e)}")
                return None
        return None

    def call_kimi(self, messages, max_tokens=2048, temperature=0.3):
        if not self.kimi_client:
            return None
        import time
        max_retries = 3
        retry_delay = 2
        for attempt in range(1, max_retries + 1):
            try:
                response = self.kimi_client.chat.completions.create(
                    model=self.kimi_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                return response.choices[0].message.content
            except Exception as e:
                error_str = str(e)
                if "429" in error_str and attempt < max_retries:
                    print(f"Kimi 引擎繁忙 (429), 等待 {retry_delay}s 后重试... (第 {attempt}/{max_retries} 次)")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                print(f"Kimi调用失败: {str(e)}")
                return None
        return None

    def chat(self, messages, max_tokens=2048, fallback=True, temperature=0.3):
        # 优先级: Kimi > DeepSeek > ArkClaw > MCAI Proxy > Proxy
        providers = []
        if self.kimi_client:
            providers.append(('Kimi', self.kimi_client, self.kimi_model))
        if self.deepseek_client:
            providers.append(('DeepSeek', self.deepseek_client, self.deepseek_model))
        if self.arkclaw_client:
            providers.append(('ArkClaw', self.arkclaw_client, self.arkclaw_model))
        if self.mcai_proxy_client:
            mcai_model = os.getenv("MCAI_MODEL_PROVIDER_TYPE", "anthropic")
            providers.append(('MCAI', self.mcai_proxy_client, mcai_model))
        if self.proxy_client:
            providers.append(('Proxy', self.proxy_client, self.fallback_model))

        if not providers:
            return None

        print(f"[image-steps] providers={', '.join(name for name, _, _ in providers)}")

        max_retries = 3
        retry_delay = 2

        for name, client, model in providers:
            for attempt in range(1, max_retries + 1):
                try:
                    request_temperature = 1 if name == 'Kimi' else temperature
                    response = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=request_temperature,
                    )
                    choice = response.choices[0]
                    content = choice.message.content or ""
                    if content.strip():
                        return content
                    print(f"[AI] {name} 返回空内容: finish_reason={getattr(choice, 'finish_reason', '')}")
                    break
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

    @staticmethod
    def _format_image_step_text(value, limit=300):
        text = AIClient._clean_image_step_output(value)
        text = AIClient._clean_text(text, limit)
        if re.search(r"[A-Za-z]", text):
            text = re.sub(r'"([^"\n]{1,80})"', r'**\1**', text)
            text = re.sub(r'“([^”\n]{1,80})”', r'**\1**', text)
        return text

    @staticmethod
    def _extract_step_lines(text):
        lines = []
        in_steps = False
        for line in str(text or "").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("```"):
                continue
            if re.match(r'^\*{0,2}"?(?:summary|relation_summary|used_style_guide_name)"?\*{0,2}\s*:', raw, re.I):
                continue
            if re.match(r'^\*{0,2}"?steps"?\*{0,2}\s*:', raw, re.I):
                in_steps = True
                continue
            if in_steps and raw in {"[", "]", "],", "}", "},"}:
                continue
            item = re.sub(r"^\s*(?:[-*•]|\d+[.)、]|步骤\s*\d+\s*[：:])\s*", "", raw).strip()
            item = item.strip('"\',，,')
            item = re.sub(r"\*\*([^*]+)\*\*", r"\1", item)
            if item and len(item) >= 6:
                lines.append(item)
        return lines

    @staticmethod
    def _coerce_image_steps(data, raw_text=""):
        candidates = []
        if isinstance(data, dict):
            for key in ("steps", "step", "operation_steps", "rewritten_steps", "instructions", "procedures", "操作步骤"):
                value = data.get(key)
                if value:
                    candidates.append(value)
            for key in ("content", "text", "result", "answer"):
                value = data.get(key)
                if isinstance(value, str):
                    candidates.extend(AIClient._extract_step_lines(value))
        elif isinstance(data, list):
            candidates.append(data)
        if raw_text:
            candidates.extend(AIClient._extract_step_lines(raw_text))

        steps = []
        def add_step(value):
            text = str(value or "").strip()
            if not text:
                return
            if "\n" in text or re.search(r'^\s*```|(?:summary|relation_summary|used_style_guide_name|steps)', text, re.I):
                steps.extend(AIClient._extract_step_lines(text))
            else:
                steps.append(text)

        for item in candidates:
            if isinstance(item, list):
                for step in item:
                    add_step(step)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("step") or item.get("description")
                if text:
                    add_step(text)
            elif str(item).strip():
                add_step(item)
        return steps

    @staticmethod
    def _clean_image_step_output(step):
        text = str(step or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"```$", "", text).strip()
        text = text.strip('"\',，,')
        if re.match(r'^\*{0,2}"?(?:summary|relation_summary|used_style_guide_name)"?\*{0,2}\s*:', text, re.I):
            return ""
        text = re.sub(r'^\*{0,2}"?steps"?\*{0,2}\s*:\s*\[?', "", text, flags=re.I).strip()
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        return text.strip()

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

    @staticmethod
    def build_image_data_url(raw_bytes, file_name="", content_type=""):
        mime = content_type or mimetypes.guess_type(file_name or "")[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(raw_bytes).decode('ascii')}"

    def _analyze_image_batch_to_draft(self, batch_images, batch_start, total_images, user_prompt=""):
        image_range = f"第 {batch_start + 1}-{batch_start + len(batch_images)} 张，共 {total_images} 张"
        draft_instruction = f"""
你是一名技术文档编写助手，需要基于这一组连续界面截图还原局部操作流程。

当前图片范围：{image_range}

你的任务：
1. 提取每张图片中的关键信息，只保留对操作理解有帮助的界面元素、按钮、输入框、提示文字和状态变化。
2. 分析这一组图片之间的局部顺序和依赖关系。
3. 输出局部操作步骤，步骤必须可执行、连贯、避免空泛描述。
4. 此阶段只做读图理解和初稿整理，暂时不套用模板或风格指南。

输出严格 JSON：
{{
  "summary": "这一组图片内容的总体说明",
  "relation_summary": "这一组图片之间的逻辑关系与排序依据",
  "steps": ["步骤1", "步骤2"]
}}

要求：
- 只输出 JSON。
- steps 必须体现清晰顺序。
- steps 必须直接描述用户动作，适合直接放进操作说明书。
- steps、summary、relation_summary 必须使用图片主要语言输出。中文图片输出中文，英文图片输出英文。
- 每个 step 尽量包含界面位置、操作对象、输入动作和结果页面。
- 如果图片表现的是登录、跳转、按钮点击、软键盘输入等界面流程，按真实操作顺序还原。
""".strip()

        if user_prompt:
            draft_instruction += f"\n\n用户补充要求：{user_prompt.strip()}"

        user_content = [{"type": "text", "text": draft_instruction}]
        for image in batch_images:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": image.get("data_url")}
            })

        try:
            response = self.kimi_client.with_options(timeout=35, max_retries=0).chat.completions.create(
                model=self.kimi_model,
                messages=[{"role": "user", "content": user_content}],
                max_tokens=1024,
                temperature=1,
            )
            result = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            if not result:
                print(f"[Kimi] image batch draft WARNING: {image_range}, empty content, finish_reason={finish_reason}, usage={response.usage}")
                return None
        except Exception as e:
            print(f"Kimi 局部图片初稿失败: {image_range}, {str(e)}")
            return None

        data = self._extract_json(result, {})
        if not isinstance(data, dict):
            print(f"[Kimi] image batch draft WARNING: {image_range}, invalid batch draft json")
            return None

        steps = data.get("steps") or []
        if not isinstance(steps, list):
            steps = [str(steps)] if steps else []
        steps = [step for step in steps if str(step).strip()]
        if not steps:
            print(f"[Kimi] image batch draft WARNING: {image_range}, empty batch draft steps")
            return None

        return {
            "summary": self._clean_text(data.get("summary"), 500),
            "relation_summary": self._clean_text(data.get("relation_summary"), 800),
            "steps": [self._format_image_step_text(step, 300) for step in steps],
            "image_range": image_range,
            "start": batch_start,
        }

    def _analyze_small_image_set_to_draft(self, images, user_prompt=""):
        draft_instruction = f"""
你是一名技术文档编写助手，需要基于少量连续界面截图还原操作流程。

输出严格 JSON：
{{
  "summary": "总体说明，不超过 1 句",
  "relation_summary": "排序依据，不超过 1 句",
  "steps": ["步骤1", "步骤2"]
}}

要求：
- 只输出 JSON。
- 按图片顺序输出 steps，每张图片最多 2 个步骤。
- steps 必须描述用户动作和界面结果。
- steps、summary、relation_summary 必须使用图片主要语言输出。
- 英文步骤中的界面元素用 **粗体** 包裹。
""".strip()

        if user_prompt:
            draft_instruction += f"\n\n用户补充要求：{user_prompt.strip()}"

        user_content = [{"type": "text", "text": draft_instruction}]
        for image in images:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": image.get("data_url")}
            })

        try:
            response = self.kimi_client.with_options(timeout=120, max_retries=0).chat.completions.create(
                model=self.kimi_model,
                messages=[{"role": "user", "content": user_content}],
                max_tokens=4096,
                temperature=1,
            )
            result = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            if not result:
                print(f"[Kimi] small image draft WARNING: empty content, finish_reason={finish_reason}, usage={response.usage}")
                return None
        except Exception as e:
            print(f"Kimi 少量图片初稿失败: {str(e)}")
            return None

        data = self._extract_json(result, {})
        if not isinstance(data, dict):
            print("[Kimi] small image draft WARNING: invalid json")
            return None

        steps = data.get("steps") or []
        if not isinstance(steps, list):
            steps = [str(steps)] if steps else []
        steps = [step for step in steps if str(step).strip()]
        if not steps:
            print("[Kimi] small image draft WARNING: empty steps")
            return None

        return {
            "summary": self._clean_text(data.get("summary"), 500),
            "relation_summary": self._clean_text(data.get("relation_summary"), 800),
            "used_style_guide_name": "",
            "steps": [self._format_image_step_text(step, 300) for step in steps],
            "model": "kimi-draft",
        }

    def _refine_image_steps_text(self, draft_data, style_guide_bundle=None, template_reference=None, user_prompt="", timeout=90):
        refine_instruction = f"""
你是一名技术文档编辑，需要基于图片分析初稿改写操作步骤。

图片分析初稿 JSON：
{json.dumps(draft_data, ensure_ascii=False)}

输出严格 JSON：
{{
  "summary": "改写后的总体说明",
  "relation_summary": "流程顺序依据",
  "used_style_guide_name": "实际使用的风格指南名称",
  "steps": ["步骤1", "步骤2"]
}}

要求：
- 只输出 JSON。
- 保留初稿中的真实界面对象、按钮、输入内容和流程顺序。
- steps 必须是非空数组，元素数量与初稿 steps 基本一致；如果无需改写，也要返回按模板/指南调整措辞后的原 steps。
- steps 必须使用初稿主要语言输出。英文步骤中的界面元素用 **粗体** 包裹，禁止使用引号。
- 不新增图片中没有出现的对象或动作。
""".strip()

        if style_guide_bundle and style_guide_bundle.get("guides"):
            guides = style_guide_bundle["guides"]
            if style_guide_bundle.get("mode") == "selected":
                guide = guides[0]
                refine_instruction += (
                    f"\n\n写作风格指南\n"
                    f"请严格遵循以下指南输出操作说明。\n"
                    f"文件名：{guide.get('name')}\n"
                    f"语言：{guide.get('language')}\n"
                    f"内容：\n{guide.get('content')}"
                )
            else:
                guide_blocks = []
                for guide in guides:
                    guide_blocks.append(
                        f"文件名：{guide.get('name')}\n"
                        f"语言：{guide.get('language')}\n"
                        f"内容：\n{guide.get('content')}"
                    )
                refine_instruction += (
                    "\n\n候选写作风格指南\n"
                    "请先判断初稿主要语言，再选择最匹配的一份风格指南执行。"
                    "中文优先使用中文指南，英文优先使用英文指南。"
                    "输出 JSON 时，used_style_guide_name 必须填写你实际采用的指南文件名。\n\n"
                    + "\n\n".join(guide_blocks)
                )

        if template_reference and template_reference.get("content"):
            refine_instruction += (
                f"\n\n模板参考文件\n"
                f"文件名：{template_reference.get('name')}\n"
                "当模板中的表达与初稿流程存在相似描述时，优先参考模板中的写法、句式和动作描述。"
                "保留初稿里的真实对象、按钮、输入内容和页面名称。\n"
                f"模板内容：\n{template_reference.get('content')}"
            )

        if user_prompt:
            refine_instruction += f"\n\n用户补充要求：{user_prompt.strip()}"

        refine_providers = []
        if self.kimi_client:
            refine_providers.append(("Kimi", self.kimi_client, self.kimi_model, "kimi"))
        if self.deepseek_client:
            refine_providers.append(("DeepSeek", self.deepseek_client, self.deepseek_model, "deepseek"))
        if self.arkclaw_client:
            refine_providers.append(("ArkClaw", self.arkclaw_client, self.arkclaw_model, "arkclaw"))



        for provider_name, client, model, model_key in refine_providers:
            try:
                response = client.with_options(timeout=timeout, max_retries=0).chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": refine_instruction}],
                    max_tokens=2048,
                    temperature=1,
                )
                result = response.choices[0].message.content
            except Exception as e:
                print(f"{provider_name} 初稿改写失败: {str(e)}")
                continue

            data = self._extract_json(result, {})
            if not isinstance(data, dict):
                print(f"[{provider_name}] refine WARNING: invalid json")
                continue
            steps = self._coerce_image_steps(data, result)
            if not steps:
                print(f"[{provider_name}] refine WARNING: empty steps, raw={self._clean_text(result, 300)}")
                continue
            return {
                "summary": self._clean_text(data.get("summary") or draft_data.get("summary"), 500),
                "relation_summary": self._clean_text(data.get("relation_summary") or draft_data.get("relation_summary"), 800),
                "used_style_guide_name": self._clean_text(data.get("used_style_guide_name"), 160),
                "steps": [self._format_image_step_text(step, 300) for step in steps],
                "model": f"kimi+{model_key}",
            }

        return None

    def analyze_images_to_steps(self, images, user_prompt="", style_guide_bundle=None, template_reference=None):
        if not images:
            return None

        if not self.kimi_client:
            return None

        should_refine = bool(style_guide_bundle or template_reference or str(user_prompt or "").strip())

        if len(images) <= 4:
            small_draft = self._analyze_small_image_set_to_draft(images, user_prompt)
            if small_draft:
                if not should_refine:
                    return small_draft
                refined = self._refine_image_steps_text(
                    small_draft,
                    style_guide_bundle=style_guide_bundle,
                    template_reference=template_reference,
                    user_prompt=user_prompt,
                    timeout=90,
                )
                return refined or small_draft
            print("[image-steps] small image draft failed, trying batch draft fallback")

        batches = [
            (start, images[start:start + IMAGE_DRAFT_BATCH_SIZE])
            for start in range(0, len(images), IMAGE_DRAFT_BATCH_SIZE)
        ]
        print(f"[image-steps] Kimi draft batches={len(batches)}, batch_size={IMAGE_DRAFT_BATCH_SIZE}")

        batch_drafts = []
        max_workers = min(IMAGE_DRAFT_MAX_WORKERS, len(batches))
        executor = ThreadPoolExecutor(max_workers=max_workers)
        future_map = {
            executor.submit(
                self._analyze_image_batch_to_draft,
                batch_images,
                start,
                len(images),
                user_prompt,
            ): start
            for start, batch_images in batches
        }
        done, pending = wait(future_map.keys(), timeout=IMAGE_DRAFT_TOTAL_TIMEOUT)
        for future in pending:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

        if pending:
            pending_starts = [future_map[future] + 1 for future in pending]
            print(f"[image-steps] batch drafts timed out, skipped_starts={pending_starts}")

        for future in done:
            start = future_map[future]
            try:
                draft = future.result()
            except Exception as e:
                print(f"[Kimi] image batch draft exception: start={start}, {str(e)}")
                draft = None
            if draft:
                batch_drafts.append(draft)

        if len(batch_drafts) != len(batches):
            print(f"[image-steps] batch drafts incomplete, expected={len(batches)}, got={len(batch_drafts)}")

        if not batch_drafts:
            print("[Kimi] image draft failed: no successful batch drafts")
            return None

        batch_drafts.sort(key=lambda item: item.get("start", 0))
        draft_data = {
            "summary": "；".join([item.get("summary") or item.get("image_range") or "" for item in batch_drafts if item.get("summary") or item.get("image_range")]),
            "relation_summary": "；".join([item.get("relation_summary") or "" for item in batch_drafts if item.get("relation_summary")]),
            "steps": [step for item in batch_drafts for step in (item.get("steps") or [])],
            "batch_drafts": batch_drafts,
        }

        if len(batch_drafts) != len(batches):
            return {
                "summary": self._clean_text(draft_data.get("summary"), 500),
                "relation_summary": self._clean_text(draft_data.get("relation_summary"), 800),
                "used_style_guide_name": "",
                "steps": [self._format_image_step_text(step, 300) for step in draft_data.get("steps") or []],
                "model": "kimi-draft-partial",
            }

        if not should_refine:
            return {
                "summary": self._clean_text(draft_data.get("summary"), 500),
                "relation_summary": self._clean_text(draft_data.get("relation_summary"), 800),
                "used_style_guide_name": "",
                "steps": [self._format_image_step_text(step, 300) for step in draft_data.get("steps") or []],
                "model": "kimi-draft",
            }

        refine_instruction = f"""
你是一名技术文档编辑，需要基于图片分析初稿改写操作步骤。

图片分析初稿 JSON：
{json.dumps(draft_data, ensure_ascii=False)}

输出严格 JSON：
{{
  "summary": "改写后的总体说明",
  "relation_summary": "流程顺序依据",
  "used_style_guide_name": "实际使用的风格指南名称",
  "steps": ["步骤1", "步骤2"]
}}

要求：
- 只输出 JSON。
- 保留初稿中的真实界面对象、按钮、输入内容和流程顺序。
- steps 必须是非空数组，元素数量与初稿 steps 基本一致；如果无需改写，也要返回按模板/指南调整措辞后的原 steps。
- steps 必须使用初稿主要语言输出。英文步骤中的界面元素用 **粗体** 包裹，禁止使用引号。
- 不新增图片中没有出现的对象或动作。
""".strip()

        if style_guide_bundle and style_guide_bundle.get("guides"):
            guides = style_guide_bundle["guides"]
            if style_guide_bundle.get("mode") == "selected":
                guide = guides[0]
                refine_instruction += (
                    f"\n\n写作风格指南\n"
                    f"请严格遵循以下指南输出操作说明。\n"
                    f"文件名：{guide.get('name')}\n"
                    f"语言：{guide.get('language')}\n"
                    f"内容：\n{guide.get('content')}"
                )
            else:
                guide_blocks = []
                for guide in guides:
                    guide_blocks.append(
                        f"文件名：{guide.get('name')}\n"
                        f"语言：{guide.get('language')}\n"
                        f"内容：\n{guide.get('content')}"
                    )
                refine_instruction += (
                    "\n\n候选写作风格指南\n"
                    "请先判断初稿主要语言，再选择最匹配的一份风格指南执行。"
                    "中文优先使用中文指南，英文优先使用英文指南。"
                    "输出 JSON 时，used_style_guide_name 必须填写你实际采用的指南文件名。\n\n"
                    + "\n\n".join(guide_blocks)
                )

        if template_reference and template_reference.get("content"):
            refine_instruction += (
                f"\n\n模板参考文件\n"
                f"文件名：{template_reference.get('name')}\n"
                "当模板中的表达与初稿流程存在相似描述时，优先参考模板中的写法、句式和动作描述。"
                "保留初稿里的真实对象、按钮、输入内容和页面名称。\n"
                f"模板内容：\n{template_reference.get('content')}"
            )

        if user_prompt:
            refine_instruction += f"\n\n用户补充要求：{user_prompt.strip()}"

        refine_providers = []
        if self.kimi_client:
            refine_providers.append(("Kimi", self.kimi_client, self.kimi_model, "kimi"))
        if self.deepseek_client:
            refine_providers.append(("DeepSeek", self.deepseek_client, self.deepseek_model, "deepseek"))
        if self.arkclaw_client:
            refine_providers.append(("ArkClaw", self.arkclaw_client, self.arkclaw_model, "arkclaw"))


        print(f"[image-steps] refine providers={', '.join(name for name, _, _, _ in refine_providers)}")

        for provider_name, client, model, model_key in refine_providers:
            try:
                response = client.with_options(timeout=90, max_retries=0).chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": refine_instruction}],
                    max_tokens=2048,
                    temperature=1,
                )
                result = response.choices[0].message.content
            except Exception as e:
                print(f"{provider_name} 初稿改写失败: {str(e)}")
                continue

            data = self._extract_json(result, {})
            if not isinstance(data, dict):
                print(f"[{provider_name}] refine WARNING: invalid json")
                continue
            steps = self._coerce_image_steps(data, result)
            if not steps:
                print(f"[{provider_name}] refine WARNING: empty steps, raw={self._clean_text(result, 300)}")
                continue
            return {
                "summary": self._clean_text(data.get("summary") or draft_data.get("summary"), 500),
                "relation_summary": self._clean_text(data.get("relation_summary") or draft_data.get("relation_summary"), 800),
                "used_style_guide_name": self._clean_text(data.get("used_style_guide_name"), 160),
                "steps": [self._format_image_step_text(step, 300) for step in steps],
                "model": f"kimi+{model_key}",
            }

        print("[image-steps] refine failed, returning Kimi draft")
        return {
            "summary": self._clean_text(draft_data.get("summary"), 500),
            "relation_summary": self._clean_text(draft_data.get("relation_summary"), 800),
            "used_style_guide_name": "",
            "steps": [self._format_image_step_text(step, 300) for step in draft_data.get("steps") or []],
            "model": "kimi-draft",
        }

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
