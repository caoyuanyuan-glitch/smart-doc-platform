import tempfile
import unittest
from pathlib import Path

from app.api.qa import _extract_file_content, _rank_document_chunks


class QaCsvExtractTest(unittest.TestCase):
    def test_gbk_csv_keeps_chinese_and_ranks(self):
        raw = "zh-CN,en-US\n首次使用前可执行一次标准实验流程,Run a standard workflow\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.csv"
            path.write_bytes(raw.encode("gbk"))
            content = _extract_file_content(str(path), "csv")

        self.assertIn("首次使用前可执行一次标准实验流程", content)
        self.assertIn("Run a standard workflow", content)

        ranked = _rank_document_chunks(
            "首次使用前标准实验流程",
            [{"document_id": 1, "title": "memory.csv", "content": content, "folder_path": "资源库/记忆库"}],
            limit=3,
        )
        self.assertTrue(ranked)
        self.assertIn("标准实验流程", ranked[0]["chunk"])
