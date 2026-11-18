import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.utils import runtime_config  # noqa: E402


class RuntimeConfigBootstrapTestCase(unittest.TestCase):
    def test_runtime_env_does_not_override_existing_platform_secret(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backend_dir = Path(tmpdir)
            (backend_dir / "runtime.env").write_text(
                "KIMI_API_KEY=file-kimi\nQWEN_API_KEY=file-qwen\n",
                encoding="utf-8",
            )

            original_kimi = os.environ.get("KIMI_API_KEY")
            original_qwen = os.environ.get("QWEN_API_KEY")
            original_dashscope = os.environ.get("DASHSCOPE_API_KEY")
            try:
                os.environ["KIMI_API_KEY"] = "platform-kimi"
                os.environ["QWEN_API_KEY"] = "platform-qwen"
                os.environ.pop("DASHSCOPE_API_KEY", None)

                runtime_config._BOOTSTRAPPED = False
                with patch.object(runtime_config, "_BACKEND_DIR", backend_dir):
                    runtime_config.bootstrap_runtime_env()

                self.assertEqual(os.environ.get("KIMI_API_KEY"), "platform-kimi")
                self.assertEqual(os.environ.get("MOONSHOT_API_KEY"), "platform-kimi")
                self.assertEqual(os.environ.get("QWEN_API_KEY"), "platform-qwen")
                self.assertEqual(os.environ.get("DASHSCOPE_API_KEY"), "platform-qwen")
            finally:
                runtime_config._BOOTSTRAPPED = False
                if original_kimi is None:
                    os.environ.pop("KIMI_API_KEY", None)
                else:
                    os.environ["KIMI_API_KEY"] = original_kimi
                if original_qwen is None:
                    os.environ.pop("QWEN_API_KEY", None)
                else:
                    os.environ["QWEN_API_KEY"] = original_qwen
                if original_dashscope is None:
                    os.environ.pop("DASHSCOPE_API_KEY", None)
                else:
                    os.environ["DASHSCOPE_API_KEY"] = original_dashscope

    def test_later_runtime_file_overrides_repo_default_when_not_platform_injected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backend_dir = Path(tmpdir)
            home_dir = backend_dir / "fake-home"
            home_runtime_dir = home_dir / ".smart-doc-platform"
            home_runtime_dir.mkdir(parents=True)

            (backend_dir / "runtime.env").write_text(
                "KIMI_API_KEY=repo-kimi\n",
                encoding="utf-8",
            )
            (home_runtime_dir / "runtime.env").write_text(
                "KIMI_API_KEY=home-kimi\n",
                encoding="utf-8",
            )

            original_kimi = os.environ.get("KIMI_API_KEY")
            try:
                os.environ.pop("KIMI_API_KEY", None)
                runtime_config._BOOTSTRAPPED = False
                with patch.object(runtime_config, "_BACKEND_DIR", backend_dir), patch("pathlib.Path.home", return_value=home_dir):
                    runtime_config.bootstrap_runtime_env()

                self.assertEqual(os.environ.get("KIMI_API_KEY"), "home-kimi")
                self.assertEqual(os.environ.get("MOONSHOT_API_KEY"), "home-kimi")
            finally:
                runtime_config._BOOTSTRAPPED = False
                if original_kimi is None:
                    os.environ.pop("KIMI_API_KEY", None)
                else:
                    os.environ["KIMI_API_KEY"] = original_kimi
                os.environ.pop("MOONSHOT_API_KEY", None)

    def test_runtime_env_local_does_not_override_platform_secret(self):
        """runtime.env.local 只做本地覆盖，不得顶掉平台注入的密钥。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend_dir = Path(tmpdir)
            (backend_dir / "runtime.env").write_text(
                "KIMI_API_KEY=file-kimi\n",
                encoding="utf-8",
            )
            (backend_dir / "runtime.env.local").write_text(
                "KIMI_API_KEY=local-kimi\n",
                encoding="utf-8",
            )

            original_kimi = os.environ.get("KIMI_API_KEY")
            original_moonshot = os.environ.get("MOONSHOT_API_KEY")
            try:
                os.environ["KIMI_API_KEY"] = "platform-kimi"
                os.environ.pop("MOONSHOT_API_KEY", None)
                runtime_config._BOOTSTRAPPED = False
                with patch.object(runtime_config, "_BACKEND_DIR", backend_dir):
                    runtime_config.bootstrap_runtime_env()

                self.assertEqual(os.environ.get("KIMI_API_KEY"), "platform-kimi")
                self.assertEqual(os.environ.get("MOONSHOT_API_KEY"), "platform-kimi")
            finally:
                runtime_config._BOOTSTRAPPED = False
                if original_kimi is None:
                    os.environ.pop("KIMI_API_KEY", None)
                else:
                    os.environ["KIMI_API_KEY"] = original_kimi
                if original_moonshot is None:
                    os.environ.pop("MOONSHOT_API_KEY", None)
                else:
                    os.environ["MOONSHOT_API_KEY"] = original_moonshot

    def test_runtime_env_local_sets_workbuddy_switches(self):
        """runtime.env.local 里的 WORKBUDDY_* 开关应被加载。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend_dir = Path(tmpdir)
            (backend_dir / "runtime.env").write_text(
                "WORKBUDDY_RULE_PLATFORM_CH=off\nWORKBUDDY_TERM_PAIR=on\n",
                encoding="utf-8",
            )
            (backend_dir / "runtime.env.local").write_text(
                "WORKBUDDY_RULE_PLATFORM_CH=on\nWORKBUDDY_TERM_PAIR=off\n",
                encoding="utf-8",
            )

            original_ch = os.environ.get("WORKBUDDY_RULE_PLATFORM_CH")
            original_pair = os.environ.get("WORKBUDDY_TERM_PAIR")
            try:
                os.environ.pop("WORKBUDDY_RULE_PLATFORM_CH", None)
                os.environ.pop("WORKBUDDY_TERM_PAIR", None)
                runtime_config._BOOTSTRAPPED = False
                with patch.object(runtime_config, "_BACKEND_DIR", backend_dir):
                    runtime_config.bootstrap_runtime_env()

                self.assertEqual(os.environ.get("WORKBUDDY_RULE_PLATFORM_CH"), "on")
                self.assertEqual(os.environ.get("WORKBUDDY_TERM_PAIR"), "off")
            finally:
                runtime_config._BOOTSTRAPPED = False
                if original_ch is None:
                    os.environ.pop("WORKBUDDY_RULE_PLATFORM_CH", None)
                else:
                    os.environ["WORKBUDDY_RULE_PLATFORM_CH"] = original_ch
                if original_pair is None:
                    os.environ.pop("WORKBUDDY_TERM_PAIR", None)
                else:
                    os.environ["WORKBUDDY_TERM_PAIR"] = original_pair

    def test_tracked_runtime_env_contains_no_api_key_value(self):
        """被跟踪的 runtime.env 不得含真实 API Key。"""
        path = BACKEND_ROOT / "runtime.env"
        self.assertTrue(path.is_file())
        secret_key = re.compile(r"(API_KEY|SECRET|TOKEN|PASSWORD)", re.I)
        for raw in path.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            if not secret_key.search(key):
                continue
            text = value.strip().strip('"').strip("'")
            if not text:
                continue
            if "your-" in text.lower() or text.startswith("${") or text.startswith("<"):
                continue
            self.fail(f"tracked runtime.env contains secret-like assignment: {key}")
