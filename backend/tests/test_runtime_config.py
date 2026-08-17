import os
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
