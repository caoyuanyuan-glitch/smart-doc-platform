import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


class PolishLabIsolationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.polish_src = (BACKEND_ROOT / "app" / "api" / "polish.py").read_text(encoding="utf-8")
        cls.lab_src = (BACKEND_ROOT / "app" / "api" / "polish_lab.py").read_text(encoding="utf-8")

    def test_upload_directories_are_isolated(self):
        self.assertIn('os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "polished")', self.polish_src)
        self.assertIn('os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "polish-lab")', self.lab_src)
        self.assertNotIn('os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "polish-lab")', self.polish_src)

    def test_lab_module_keeps_original_untouched(self):
        self.assertIn("本模块从原始 `app.api.polish` 复制而来", self.lab_src)
        self.assertNotIn("本模块从原始 `app.api.polish` 复制而来", self.polish_src)

    def test_feedback_files_are_isolated(self):
        self.assertIn('PLATFORM_FEEDBACK_FILENAME = "平台反馈的句式清单.md"', self.polish_src)
        self.assertIn('PLATFORM_FEEDBACK_FILENAME = "平台反馈的句式清单-AI调试.md"', self.lab_src)
        self.assertNotIn("平台反馈的句式清单-AI调试.md", self.polish_src)
        self.assertIn('"polish-lab", "feedback"', self.lab_src)

    def test_database_tables_are_isolated(self):
        self.assertIn("from app.models.polished_document_lab import PolishedDocumentLab as PolishedDocument", self.lab_src)
        self.assertIn("from app.models.polish_feedback_lab import PolishFeedbackLab as PolishFeedback", self.lab_src)
        self.assertNotIn("polished_document_lab", self.polish_src)
        model_src = (BACKEND_ROOT / "app" / "models" / "polished_document_lab.py").read_text(encoding="utf-8")
        self.assertIn('__tablename__ = "polished_documents_lab"', model_src)

    def test_api_prefix_is_isolated(self):
        self.assertIn("/api/polish-lab", self.lab_src)
        self.assertNotIn("/api/polish-lab", self.polish_src)
