import os
import json
import re
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
