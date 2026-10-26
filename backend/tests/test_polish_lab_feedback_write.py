import os
import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.polish_lab import (  # noqa: E402
    _append_terminology_pairs,
    _parse_corrections,
)


class PolishLabFeedbackWriteTest(unittest.TestCase):
    def test_parse_corrections_supports_ascii_arrow(self):
        self.assertEqual(_parse_corrections('设备 -> 仪器'), [('设备', '仪器')])

    def test_append_pairs_writes_markdown_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'terms.md')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('# 平台反馈的术语对照表\n\n| 非标准词 | 标准词 |\n| --- | --- |\n')
            written = _append_terminology_pairs(path, [('设备', '仪器')])
            self.assertEqual(written, [('设备', '仪器')])
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('| 设备 | 仪器 |', content)
            again = _append_terminology_pairs(path, [('设备', '仪器')])
            self.assertEqual(again, [])


if __name__ == '__main__':
    unittest.main()
